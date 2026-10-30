"""Measures answer latency and the question cache on this machine, so the README numbers can be checked live.

Needs Ollama running and the documents indexed. Run from backend/: python -m tests.benchmark
It asks 20 questions once to warm up (loads the model, fills the cache), then times them a second time.
Nothing is written to the query log, so /metrics isn't changed.
"""

import json
import platform
import statistics
import time

from main import percentile, warm_up
from routes.search import answer_question
from tests.evaluate import QUESTIONS_FILE
from utils.config import LLM_MODEL
from utils.errors import AppError

QUESTION_COUNT = 20


def timed_answer(question):
    start = time.perf_counter()
    try:
        result = answer_question(question)
        stats = result["cache"]
    except AppError as error:
        print(f"   error: {error.message}")
        stats = None
    return round((time.perf_counter() - start) * 1000), stats


def main():
    cases = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    questions = [case["question"] for case in cases if case.get("type") != "unanswerable"][:QUESTION_COUNT]

    print(f"Machine: {platform.processor() or platform.machine()} | {platform.system()} {platform.release()}")
    print(f"Model: {LLM_MODEL} | {len(questions)} questions\n")
    warm_up()

    print("\nWarm-up pass (not measured)...")
    for question in questions:
        timed_answer(question)

    print("Measured pass:")
    latencies = []
    hits = 0
    new = 0
    for question in questions:
        latency_ms, stats = timed_answer(question)
        latencies.append(latency_ms)
        if stats:
            hits += stats["cache_hits"]
            new += stats["new_embeddings"]
        print(f"   {latency_ms:>6} ms | {question}")

    print(f"\nMedian latency: {statistics.median(latencies) / 1000:.2f}s (target < 3s)")
    print(f"p95 latency:    {percentile(latencies, 95) / 1000:.2f}s (target < 5s)")
    print(f"Question cache: {hits} hits, {new} new embeddings (target: all hits)")


if __name__ == "__main__":
    main()
