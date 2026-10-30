"""Embedding text with sentence-transformers, with a cache on disk so the same text is never embedded twice."""

import hashlib

from sentence_transformers import SentenceTransformer

from utils.config import CACHE_FILE, EMBEDDING_MODEL, MAX_CACHED_QUESTIONS, QUERY_CACHE_FILE
from utils.storage import load_json, lock, save_json

# Two caches: one for document chunks and one for questions. Each maps text_hash -> vector.
CACHE_FILES = {"chunks_cache": CACHE_FILE, "questions_cache": QUERY_CACHE_FILE}
caches = {"chunks_cache": None, "questions_cache": None}

model = None


def get_model():
    """Load the embedding model the first time it is needed."""
    global model
    if model is None:
        model = SentenceTransformer(EMBEDDING_MODEL)
    return model


def text_hash(text):
    """The cache key. The model name is part of it, so changing the model never reuses old vectors."""
    return hashlib.sha256(f"{EMBEDDING_MODEL}|{text}".encode("utf-8")).hexdigest()


def load_cache(name):
    """Read a cache from disk once, then keep it in memory."""
    if caches[name] is None:
        caches[name] = load_json(CACHE_FILES[name], {})
    return caches[name]


def remove_least_recent(cache, max_size):
    """Dicts keep insertion order and every use moves a key to the end, so the first keys are the least recently used."""
    while len(cache) > max_size:
        oldest = next(iter(cache))
        del cache[oldest]


def remove_unused(cache, texts):
    """Drop vectors of chunks that no longer exist (deleted or edited documents). Returns how many were removed."""
    keep = {text_hash(text) for text in texts}
    unused = [key for key in cache if key not in keep]
    for key in unused:
        del cache[key]
    return len(unused)


def embed_with_cache(texts, cache):
    """Embed only the texts missing from the cache. Returns the vectors in order and the hit/miss counts."""
    missing = [text for text in texts if text_hash(text) not in cache]

    # Move every hit to the end, so a question that keeps being asked is never the one removed.
    for text in texts:
        key = text_hash(text)
        if key in cache:
            cache[key] = cache.pop(key)

    if missing:
        vectors = get_model().encode(missing, normalize_embeddings=True)
        for text, vector in zip(missing, vectors):
            cache[text_hash(text)] = vector.tolist()

    vectors = [cache[text_hash(text)] for text in texts]
    stats = {"cache_hits": len(texts) - len(missing), "new_embeddings": len(missing)}
    return vectors, stats


def embed_texts(texts, cache_name):
    """Embed texts using one of the two caches and save the cache only if something new was added."""
    with lock:
        cache = load_cache(cache_name)
        vectors, stats = embed_with_cache(texts, cache)
        if stats["new_embeddings"]:
            if cache_name == "questions_cache":
                remove_least_recent(cache, MAX_CACHED_QUESTIONS)
            save_json(CACHE_FILES[cache_name], cache)
    return vectors, stats


def cache_sizes():
    """How many vectors each cache holds, for the startup log."""
    with lock:
        return {name: len(load_cache(name)) for name in CACHE_FILES}
