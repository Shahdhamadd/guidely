"""Document endpoints: list, upload, read, edit, delete, change category and re-index."""

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, UploadFile

from models.record import Category, DocumentText
from utils.categories import get_category, load_categories, remove_category, set_category
from utils.chunking import parse_file
from utils.config import DOCS_DIR, MAX_UPLOAD_MB, SUPPORTED_TYPES
from utils.errors import AppError
from utils.vector_store import load_index, reindex

router = APIRouter(prefix="/documents")


def find_document(name):
    # Path(name).name drops any folder part, so "../main.py" can't reach files outside sample-docs.
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
    """Save a document, then re-index. A file with the same name replaces the old one."""
    path = DOCS_DIR / Path(file.filename).name
    if path.suffix.lower() not in SUPPORTED_TYPES:
        raise AppError(f"{path.name}: unsupported file type. Use .txt, .md or .pdf", 400)

    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AppError(f"{path.name} is too big. The limit is {MAX_UPLOAD_MB} MB.", 413)

    # Check the file in a temporary folder first, so a broken upload never replaces a good document.
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
    """Return the stored vectors from the FAISS index, with the chunk each one belongs to."""
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
    if len(body.text.encode("utf-8")) > MAX_UPLOAD_MB * 1024 * 1024:
        raise AppError(f"{path.name} is too big. The limit is {MAX_UPLOAD_MB} MB.", 413)

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
