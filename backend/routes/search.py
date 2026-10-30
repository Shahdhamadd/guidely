"""Question endpoints: question -> embedding -> FAISS search -> LLM answer -> sources."""

import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from models.record import Question
from utils.answers import build_result
from utils.config import QUERY_LOG
from utils.errors import AppError
from utils.llm import ask_llm, stream_llm
from utils.retrieval import find_relevant, retrieve
from utils.storage import write_log

router = APIRouter(prefix="/search")


def answer_question(question, category="", history=()):
    question, relevant, stats = find_relevant(question, category, history)
    answer = ask_llm(question, relevant, history)
    return build_result(answer, relevant, stats, category)


def log_query(question, latency_ms, category="", follow_up=False, result=None, error=None):
    """Write one line to the query log. /metrics and the CSV export are built from this log."""
    record = {"question": question, "category": category or "All", "follow_up": follow_up, "latency_ms": latency_ms}

    if result:
        record["status"] = "ok"
        record["cache_hits"] = result["cache"]["cache_hits"]
        record["new_embeddings"] = result["cache"]["new_embeddings"]
        record["sources"] = [f"{s['file']} > {s['section']}" for s in result["sources"]]
        cache = f"cache: {record['cache_hits']} hits, {record['new_embeddings']} new"
    else:
        record["status"] = "error"
        record["error"] = error
        cache = error

    write_log(QUERY_LOG, record)
    print(f"[query] {latency_ms} ms | {record['status']} | {cache} | {question}")


@router.post("/retrieve")
def retrieve_chunks(body: Question):
    """Search only, without the model. Useful for checking retrieval."""
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
    """Like /ask, but sends the answer as it is written, one JSON line per event:
    {"type": "token"} pieces, then {"type": "done"} with the sources, or {"type": "error"}.
    """
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
