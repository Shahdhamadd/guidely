"""Finding the chunks that best match a question."""

import numpy as np

from utils.categories import get_category, load_categories
from utils.config import MAX_HISTORY, MIN_SCORE, TOP_K
from utils.embeddings import embed_texts
from utils.errors import AppError
from utils.vector_store import load_index

# bge models are trained to put this before questions (but not before documents).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def earlier_questions(history):
    return " ".join(turn.question for turn in history[-MAX_HISTORY:])


def retrieve(question, top_k=TOP_K, category="", history=()):
    """Return the top_k chunks for a question, best first, with their similarity score.

    For a follow-up, the question is searched twice: alone, and together with the earlier
    questions (so "Can I carry them over?" still finds annual leave). Each chunk keeps its
    best score of the two searches.
    """
    index, chunks = load_index()

    search_texts = [QUERY_PREFIX + question]
    if history:
        search_texts.append(QUERY_PREFIX + earlier_questions(history) + " " + question)
    vectors, stats = embed_texts(search_texts, "questions_cache")
    categories = load_categories()

    # With a category filter, rank every chunk and keep the first top_k in that category.
    search_k = index.ntotal if category else top_k

    query = np.array(vectors, dtype="float32")
    scores, ids = index.search(query, search_k)

    best_scores = {}
    for row_scores, row_ids in zip(scores, ids):
        for score, chunk_id in zip(row_scores, row_ids):
            if chunk_id == -1:
                continue
            best_scores[chunk_id] = max(best_scores.get(chunk_id, -1.0), float(score))

    ranked = sorted(best_scores.items(), key=lambda item: item[1], reverse=True)

    results = []
    for chunk_id, score in ranked:
        chunk_category = get_category(chunks[chunk_id]["file"], categories)
        if category and chunk_category != category:
            continue
        results.append({
            **chunks[chunk_id],
            "category": chunk_category,
            "rank": len(results) + 1,
            "score": round(score, 3),
        })
        if len(results) == top_k:
            break
    return results, stats


def not_found(category):
    if category:
        return AppError(f"No relevant documents were found in the {category} category.", 404)
    return AppError("No relevant documents were found for this question.", 404)


def find_relevant(question, category="", history=()):
    """Retrieve chunks and keep only those similar enough to be worth sending to the model."""
    question = question.strip()
    if not question:
        raise AppError("Please type a question.", 400)

    results, stats = retrieve(question, category=category, history=history)
    relevant = [chunk for chunk in results if chunk["score"] >= MIN_SCORE]
    if not relevant:
        raise not_found(category)
    return question, relevant, stats
