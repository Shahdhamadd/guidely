"""The FAISS index: building it from the documents, saving it to disk and loading it back."""

import time

import faiss
import numpy as np

from utils.chunking import chunk_document, chunk_to_embedding_text, parse_file
from utils.config import CACHE_FILE, CHUNKS_FILE, DOCS_DIR, FILE_HASHES_FILE, INDEX_FILE, INDEX_LOG
from utils.embeddings import embed_texts, load_cache, remove_unused, text_hash
from utils.errors import AppError
from utils.storage import load_json, lock, save_json, write_log

# The index and its chunks are loaded from disk once and kept in memory.
# chunks[i] is the chunk whose vector is at position i in the index.
memory = {"index": None, "chunks": None}


def build_faiss_index(vectors):
    """Vectors are normalized, so inner product (IndexFlatIP) is the same as cosine similarity."""
    matrix = np.array(vectors, dtype="float32")
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_FILE))
    return index


def load_index():
    """Return (index, chunks), reading them from disk the first time."""
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
    """Read every document, chunk it, embed the chunks (cached ones are reused) and rebuild the index.

    Returns a report of what happened, which is also written to the index log.
    """
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
            # One broken file shouldn't stop the others from being indexed.
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
    print(f"[index] {report['files_indexed']} files, {report['chunks']} chunks | "
          f"cache: {report['cache_hits']} hits, {report['new_embeddings']} new embeddings | {report['seconds']}s")
    return report
