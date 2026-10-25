import json
import os
import re
import time

import numpy as np
import requests
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from models.record import Question
from routes.documents import (
    QUERY_LOG,
    AppError,
    embed_texts,
    get_category,
    get_model,
    load_categories,
    load_index,
    write_log,
)

TOP_K = int(os.getenv("TOP_K", "3"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.45"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "3"))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

NO_ANSWER = "I couldn't find this in the documents."

REFUSAL_PHRASES = [
    "couldn't find", "could not find", "can't find", "cannot find", "unable to find",
    "do not contain", "don't contain", "does not contain", "doesn't contain",
    "no information", "not mentioned",
]

FILLER_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "so", "to", "of", "in", "on", "at", "by",
    "for", "with", "from", "is", "are", "was", "be", "it", "this", "that", "can", "will",
    "you", "your", "i", "my", "we", "our", "they", "their",
}

SYSTEM_PROMPT = f"""You are Guidely, a helpful assistant for Brightpath employees and support agents.
Answer the question using ONLY the numbered sources you are given.
Rules:
- Keep the answer short: 1 to 3 sentences.
- Treat words with the same meaning as the same thing (for example, a doctor's note is a medical certificate).
- For yes/no questions, first state the rule from the source, then apply it to the question, then say yes or no.
  Example: "Sick for more than 2 days needs a medical certificate [1]. 3 days is more than 2, so yes, you need one."
- After each fact, write the number of its source in square brackets, like [1].
- If the sources do not contain the answer, reply exactly: {NO_ANSWER}"""


def earlier_questions(history):
    return " ".join(turn.question for turn in history[-MAX_HISTORY:])


def retrieve(question, top_k=TOP_K, category="", history=()):
    index, chunks = load_index()

    search_texts = [QUERY_PREFIX + question]
    if history:
        search_texts.append(QUERY_PREFIX + earlier_questions(history) + " " + question)
    vectors, stats = embed_texts(search_texts, "questions_cache")
    categories = load_categories()

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


def build_prompt(question, chunks):
    parts = []
    for number, chunk in enumerate(chunks, start=1):
        parts.append(f"[{number}] ({chunk['file']} > {chunk['section']})\n{chunk['text']}")
    sources_text = "\n\n".join(parts)
    return f"Sources:\n\n{sources_text}\n\nQuestion: {question}"


def build_messages(question, chunks, history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-MAX_HISTORY:]:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": remove_citations(turn.answer).strip()})
    messages.append({"role": "user", "content": build_prompt(question, chunks)})
    return messages


def timeout_error():
    return AppError(f"The AI model took longer than {LLM_TIMEOUT} seconds to answer. Please try again.", 504)


def call_llm(question, chunks, history, stream):
    if not LLM_MODEL:
        raise AppError("No AI model is configured. Set LLM_MODEL in the .env file.", 500)

    payload = {
        "model": LLM_MODEL,
        "messages": build_messages(question, chunks, history),
        "stream": stream,
        "options": {"temperature": 0},
        "keep_alive": -1,
    }

    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=LLM_TIMEOUT, stream=stream)
    except requests.exceptions.Timeout:
        raise timeout_error()
    except requests.exceptions.ConnectionError:
        raise AppError("The AI model server (Ollama) is not running. Start it with: ollama serve", 503)

    if response.status_code == 404:
        raise AppError(f"The AI model '{LLM_MODEL}' is not installed. Run: ollama pull {LLM_MODEL}", 500)
    if response.status_code != 200:
        raise AppError("The AI model returned an error. Please try again.", 502)

    return response


def ask_llm(question, chunks, history=()):
    response = call_llm(question, chunks, history, stream=False)
    return response.json()["message"]["content"].strip()


def stream_llm(question, chunks, history=()):
    response = call_llm(question, chunks, history, stream=True)

    def pieces():
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                message = json.loads(line)
                if message.get("error"):
                    raise AppError("The AI model returned an error. Please try again.", 502)
                yield message.get("message", {}).get("content", "")
                if message.get("done"):
                    break
        except requests.exceptions.RequestException:
            raise timeout_error()
        finally:
            response.close()

    return pieces()


def words_in(text):
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    return words - FILLER_WORDS


def remove_citations(answer):
    return re.sub(r"\s*\[\d+\]", "", answer)


def best_sentence(text, answer):
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
    text = answer.lower()
    if NO_ANSWER.lower() in text:
        return True

    has_citation = re.search(r"\[\d+\]", answer)
    return not has_citation and any(phrase in text for phrase in REFUSAL_PHRASES)


def pick_sources(answer, chunks):
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


def not_found(category):
    if category:
        return AppError(f"No relevant documents were found in the {category} category.", 404)
    return AppError("No relevant documents were found for this question.", 404)


def find_relevant(question, category="", history=()):
    question = question.strip()
    if not question:
        raise AppError("Please type a question.", 400)

    results, stats = retrieve(question, category=category, history=history)
    relevant = [chunk for chunk in results if chunk["score"] >= MIN_SCORE]
    if not relevant:
        raise not_found(category)
    return question, relevant, stats


def build_result(answer, relevant, stats, category=""):
    answer = answer.strip()
    if is_refusal(answer):
        raise not_found(category)

    return {
        "answer": answer,
        "sources": pick_sources(answer, relevant),
        "cache": stats,
    }


def answer_question(question, category="", history=()):
    question, relevant, stats = find_relevant(question, category, history)
    answer = ask_llm(question, relevant, history)
    return build_result(answer, relevant, stats, category)


router = APIRouter(prefix="/search")


def warm_up():
    get_model()
    try:
        requests.post(f"{OLLAMA_URL}/api/generate", json={"model": LLM_MODEL, "keep_alive": -1}, timeout=LLM_TIMEOUT)
        print(f"[startup] embedding model and {LLM_MODEL} are loaded")
    except requests.exceptions.RequestException:
        print("[startup] Ollama is not reachable; questions will fail until it is running")


def log_query(question, latency_ms, category="", follow_up=False, result=None, error=None):
    record = {"question": question, "category": category or "All", "follow_up": follow_up, "latency_ms": latency_ms}

    if result:
        record["status"] = "ok"
        record["cache_hits"] = result["cache"]["cache_hits"]
        record["new_embeddings"] = result["cache"]["new_embeddings"]
        record["sources"] = [f"{s['file']} > {s['section']}" for s in result["sources"]]
    else:
        record["status"] = "error"
        record["error"] = error

    write_log(QUERY_LOG, record)
    print(f"[query] {latency_ms} ms | {record['status']} | {question}")


@router.post("/retrieve")
def retrieve_chunks(body: Question):
    question = body.question.strip()
    if not question:
        raise AppError("Please type a question.", 400)

    results, stats = retrieve(question, category=body.category, history=body.history)
    return {"question": question, "results": results, "cache": stats}


@router.post("/ask")
def ask(body: Question):
    start = time.perf_counter()
    follow_up = bool(body.history)

    try:
        result = answer_question(body.question, body.category, body.history)
    except AppError as error:
        latency_ms = round((time.perf_counter() - start) * 1000)
        log_query(body.question, latency_ms, body.category, follow_up, error=error.message)
        raise

    latency_ms = round((time.perf_counter() - start) * 1000)
    log_query(body.question, latency_ms, body.category, follow_up, result=result)

    result["latency_ms"] = latency_ms
    return result


def event(data):
    return json.dumps(data) + "\n"


@router.post("/ask/stream")
def ask_stream(body: Question):
    start = time.perf_counter()
    follow_up = bool(body.history)

    def elapsed_ms():
        return round((time.perf_counter() - start) * 1000)

    # Errors before the model starts writing (empty question, nothing found,
    # Ollama down) are returned as normal JSON errors with a status code.
    try:
        question, relevant, stats = find_relevant(body.question, body.category, body.history)
        pieces = stream_llm(question, relevant, body.history)
    except AppError as error:
        log_query(body.question, elapsed_ms(), body.category, follow_up, error=error.message)
        raise

    def events():
        answer = ""
        try:
            for piece in pieces:
                answer += piece
                yield event({"type": "token", "text": piece})
            result = build_result(answer, relevant, stats, body.category)
        except AppError as error:
            log_query(body.question, elapsed_ms(), body.category, follow_up, error=error.message)
            yield event({"type": "error", "error": error.message, "status_code": error.status_code})
            return

        latency_ms = elapsed_ms()
        log_query(body.question, latency_ms, body.category, follow_up, result=result)
        yield event({"type": "done", **result, "latency_ms": latency_ms})

    return StreamingResponse(events(), media_type="application/x-ndjson")
