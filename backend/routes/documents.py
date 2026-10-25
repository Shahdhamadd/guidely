import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv
from fastapi import APIRouter, Form, UploadFile
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from models.record import Category, DocumentText

PROJECT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_DIR / ".env")

BACKEND_DIR = PROJECT_DIR / "backend"
DOCS_DIR = BACKEND_DIR / "data" / "sample-docs"
INDEX_DIR = BACKEND_DIR / "data" / "index"
CACHE_FILE = INDEX_DIR / "embedding_cache.json"
QUERY_CACHE_FILE = INDEX_DIR / "query_cache.json"
INDEX_FILE = INDEX_DIR / "index.faiss"
CHUNKS_FILE = INDEX_DIR / "chunks.json"
FILE_HASHES_FILE = INDEX_DIR / "file_hashes.json"
CATEGORIES_FILE = BACKEND_DIR / "data" / "categories.json"

LOGS_DIR = BACKEND_DIR / "data" / "logs"
QUERY_LOG = LOGS_DIR / "queries.jsonl"
ERROR_LOG = LOGS_DIR / "errors.jsonl"
INDEX_LOG = LOGS_DIR / "index.jsonl"

SUPPORTED_TYPES = {".txt", ".md", ".pdf"}
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "250"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
MAX_CACHED_QUESTIONS = int(os.getenv("MAX_CACHED_QUESTIONS", "500"))


class AppError(Exception):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def parse_file(path):
    suffix = path.suffix.lower()

    if suffix not in SUPPORTED_TYPES:
        raise AppError(f"{path.name}: unsupported file type '{suffix}'. Use .txt, .md or .pdf", 400)

    try:
        if suffix == ".pdf":
            reader = PdfReader(path)
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            text = path.read_text(encoding="utf-8")
    except Exception:
        raise AppError(f"{path.name}: the file is corrupted or could not be read")

    if not text.strip():
        raise AppError(f"{path.name}: the file contains no readable text")

    return text


def split_into_sections(text):
    sections = []
    heading = "Introduction"
    lines = []

    for line in text.splitlines():
        if line.startswith("#"):
            if "\n".join(lines).strip():
                sections.append((heading, "\n".join(lines)))
            heading = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)

    if "\n".join(lines).strip():
        sections.append((heading, "\n".join(lines)))

    return sections


def split_long_paragraph(paragraph, max_words):
    words = paragraph.split()
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


def chunk_section(body, max_words):
    paragraphs = []
    for paragraph in body.split("\n\n"):
        paragraph = paragraph.strip()
        if paragraph:
            paragraphs.extend(split_long_paragraph(paragraph, max_words))

    chunks = []
    current = []
    current_words = 0
    for paragraph in paragraphs:
        size = len(paragraph.split())
        if current and current_words + size > max_words:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0
        current.append(paragraph)
        current_words += size

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def chunk_document(file_name, text, max_words=CHUNK_WORDS):
    chunks = []
    for heading, body in split_into_sections(text):
        for piece in chunk_section(body, max_words):
            chunks.append({
                "file": file_name,
                "section": heading,
                "text": piece,
            })
    return chunks


model = None


def get_model():
    global model
    if model is None:
        model = SentenceTransformer(EMBEDDING_MODEL)
    return model


def text_hash(text):
    return hashlib.sha256(f"{EMBEDDING_MODEL}|{text}".encode("utf-8")).hexdigest()


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path, data, indent=None):
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(data, indent=indent), encoding="utf-8")
    os.replace(temp_path, path)


def write_log(path, record):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now().isoformat(timespec="seconds"), **record}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")


def read_log(path):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


memory = {"chunks_cache": None, "questions_cache": None, "index": None, "chunks": None}

CACHE_FILES = {"chunks_cache": CACHE_FILE, "questions_cache": QUERY_CACHE_FILE}

lock = threading.RLock()


def load_cache(name):
    if memory[name] is None:
        memory[name] = load_json(CACHE_FILES[name], {})
    return memory[name]


def remove_oldest(cache, max_size):
    while len(cache) > max_size:
        oldest = next(iter(cache))
        del cache[oldest]


def remove_unused(cache, texts):
    keep = {text_hash(text) for text in texts}
    unused = [key for key in cache if key not in keep]
    for key in unused:
        del cache[key]
    return len(unused)


def embed_texts(texts, cache_name):
    with lock:
        cache = load_cache(cache_name)
        vectors, stats = embed_with_cache(texts, cache)
        if stats["new_embeddings"]:
            if cache_name == "questions_cache":
                remove_oldest(cache, MAX_CACHED_QUESTIONS)
            save_json(CACHE_FILES[cache_name], cache)
    return vectors, stats


def embed_with_cache(texts, cache):
    missing = [text for text in texts if text_hash(text) not in cache]

    if missing:
        vectors = get_model().encode(missing, normalize_embeddings=True)
        for text, vector in zip(missing, vectors):
            cache[text_hash(text)] = vector.tolist()

    vectors = [cache[text_hash(text)] for text in texts]
    stats = {"cache_hits": len(texts) - len(missing), "new_embeddings": len(missing)}
    return vectors, stats


def chunk_to_embedding_text(chunk):
    return f"{chunk['section']}\n{chunk['text']}"


def build_faiss_index(vectors):
    matrix = np.array(vectors, dtype="float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_FILE))
    return index


def load_index():
    with lock:
        if memory["index"] is None:
            if not INDEX_FILE.exists() or not CHUNKS_FILE.exists():
                raise AppError("No documents are indexed yet. Upload documents and run re-index first.", 404)
            memory["index"] = faiss.read_index(str(INDEX_FILE))
            memory["chunks"] = load_json(CHUNKS_FILE, [])
        return memory["index"], memory["chunks"]


def reindex():
    with lock:
        return build_new_index()


def build_new_index():
    start = time.perf_counter()

    old_hashes = load_json(FILE_HASHES_FILE, {})
    new_hashes = {}
    all_chunks = []
    errors = []

    for path in sorted(DOCS_DIR.iterdir()):
        if not path.is_file():
            continue
        try:
            text = parse_file(path)
        except AppError as error:
            errors.append(str(error))
            continue
        new_hashes[path.name] = text_hash(text)
        all_chunks.extend(chunk_document(path.name, text))

    if not all_chunks:
        raise AppError("There are no readable documents to index.", 404)

    texts = [chunk_to_embedding_text(chunk) for chunk in all_chunks]
    vectors, stats = embed_texts(texts, "chunks_cache")

    chunks_cache = load_cache("chunks_cache")
    removed = remove_unused(chunks_cache, texts)
    if removed:
        save_json(CACHE_FILE, chunks_cache)

    index = build_faiss_index(vectors)
    save_json(CHUNKS_FILE, all_chunks)
    save_json(FILE_HASHES_FILE, new_hashes)
    memory["index"] = index
    memory["chunks"] = all_chunks

    unchanged = [name for name, h in new_hashes.items() if old_hashes.get(name) == h]

    report = {
        "files_indexed": len(new_hashes),
        "files_unchanged": len(unchanged),
        "files_failed": errors,
        "chunks": len(all_chunks),
        "cache_hits": stats["cache_hits"],
        "new_embeddings": stats["new_embeddings"],
        "embeddings_removed": removed,
        "seconds": round(time.perf_counter() - start, 2),
    }
    write_log(INDEX_LOG, report)
    print(f"[index] {report['files_indexed']} files, {report['new_embeddings']} new embeddings, {report['seconds']}s")
    return report


router = APIRouter(prefix="/documents")


DEFAULT_CATEGORY = "General"


def load_categories():
    return load_json(CATEGORIES_FILE, {})


def get_category(name, categories):
    return categories.get(name, DEFAULT_CATEGORY)


def set_category(name, category):
    category = category.strip()[:30] or DEFAULT_CATEGORY
    with lock:
        categories = load_categories()
        categories[name] = category
        save_json(CATEGORIES_FILE, categories, indent=2)
    return category


def remove_category(name):
    with lock:
        categories = load_categories()
        if categories.pop(name, None):
            save_json(CATEGORIES_FILE, categories, indent=2)


def find_document(name):
    path = DOCS_DIR / Path(name).name
    if not path.is_file():
        raise AppError(f"Document '{name}' was not found.", 404)
    return path


@router.get("")
def list_documents():
    categories = load_categories()
    documents = [
        {"name": path.name, "category": get_category(path.name, categories)}
        for path in sorted(DOCS_DIR.iterdir())
        if path.is_file()
    ]
    all_categories = sorted({document["category"] for document in documents})
    return {"documents": documents, "categories": all_categories}


@router.post("/upload")
def upload_document(file: UploadFile, category: str = Form("")):
    path = DOCS_DIR / Path(file.filename).name
    if path.suffix.lower() not in SUPPORTED_TYPES:
        raise AppError(f"{path.name}: unsupported file type. Use .txt, .md or .pdf", 400)

    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AppError(f"{path.name} is too big. The limit is {MAX_UPLOAD_MB} MB.", 413)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / path.name
        temp_path.write_bytes(content)
        parse_file(temp_path)
        shutil.move(temp_path, path)

    if category.strip() or path.name not in load_categories():
        set_category(path.name, category)

    return {"message": f"{path.name} was uploaded and indexed.", "index": reindex()}


@router.post("/index")
def index_documents():
    return reindex()


@router.get("/embeddings")
def get_embeddings():
    index, chunks = load_index()
    vectors = index.reconstruct_n(0, index.ntotal)

    embeddings = []
    for chunk, vector in zip(chunks, vectors):
        embeddings.append({
            "file": chunk["file"],
            "section": chunk["section"],
            "vector": vector.tolist(),
        })
    return {"count": len(embeddings), "dimensions": index.d, "embeddings": embeddings}


@router.get("/{name}")
def read_document(name: str):
    path = find_document(name)
    return {"name": path.name, "text": parse_file(path)}


@router.put("/{name}")
def edit_document(name: str, body: DocumentText):
    path = find_document(name)
    if path.suffix.lower() == ".pdf":
        raise AppError("PDF files cannot be edited here. Upload a new version instead.", 400)
    if not body.text.strip():
        raise AppError("The document text cannot be empty.", 400)

    path.write_text(body.text, encoding="utf-8")
    return {"message": f"{path.name} was saved and re-indexed.", "index": reindex()}


@router.put("/{name}/category")
def change_category(name: str, body: Category):
    path = find_document(name)
    category = set_category(path.name, body.category)
    return {"message": f"{path.name} is now in {category}.", "category": category}


@router.delete("/{name}")
def delete_document(name: str):
    path = find_document(name)
    documents = [p for p in DOCS_DIR.iterdir() if p.is_file()]
    if len(documents) == 1:
        raise AppError("You cannot delete the last document. Upload another one first.", 400)

    path.unlink()
    remove_category(path.name)
    return {"message": f"{path.name} was deleted and the index was rebuilt.", "index": reindex()}
