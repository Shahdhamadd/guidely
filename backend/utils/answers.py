"""Checking the model's answer and turning its [1], [2] citations into sources with snippets."""

import re

from utils.retrieval import not_found

NO_ANSWER = "I couldn't find this in the documents."

REFUSAL_PHRASES = [
    "couldn't find", "could not find", "can't find", "cannot find", "unable to find",
    "do not contain", "don't contain", "does not contain", "doesn't contain",
    "no information", "not mentioned",
]

# Ignored when comparing an answer with a sentence, so only meaningful words count.
FILLER_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "so", "to", "of", "in", "on", "at", "by",
    "for", "with", "from", "is", "are", "was", "be", "it", "this", "that", "can", "will",
    "you", "your", "i", "my", "we", "our", "they", "their",
}


def words_in(text):
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    return words - FILLER_WORDS


def remove_citations(answer):
    return re.sub(r"\s*\[\d+\]", "", answer)


def best_sentence(text, answer):
    """The sentence of a chunk that shares the most words with the answer. Shown as the source snippet."""
    answer_words = words_in(remove_citations(answer))
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))

    best = sentences[0]
    best_score = -1
    for sentence in sentences:
        score = len(words_in(sentence) & answer_words)
        if score > best_score:
            best = sentence
            best_score = score
    return best


def is_refusal(answer):
    """True if the model said it couldn't answer. An answer with a citation is never a refusal."""
    text = answer.lower()
    if NO_ANSWER.lower() in text:
        return True

    has_citation = re.search(r"\[\d+\]", answer)
    return not has_citation and any(phrase in text for phrase in REFUSAL_PHRASES)


def pick_sources(answer, chunks):
    """Return the chunks the answer cites. If it cites none (or only made-up numbers), return all of them."""
    cited_numbers = {int(number) for number in re.findall(r"\[(\d+)\]", answer)}
    valid_numbers = cited_numbers & set(range(1, len(chunks) + 1))

    sources = []
    for number, chunk in enumerate(chunks, start=1):
        if valid_numbers and number not in valid_numbers:
            continue
        sources.append({
            "id": number,
            "file": chunk["file"],
            "section": chunk["section"],
            "category": chunk["category"],
            "score": chunk["score"],
            "snippet": best_sentence(chunk["text"], answer),
            "text": chunk["text"],
        })
    return sources


def build_result(answer, relevant, stats, category=""):
    """The JSON returned for a question. A refusal becomes a 404, like a search with no results."""
    answer = answer.strip()
    if is_refusal(answer):
        raise not_found(category)

    return {
        "answer": answer,
        "sources": pick_sources(answer, relevant),
        "cache": stats,
    }
