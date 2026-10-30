"""Scores retrieval and answers on tests/eval_questions.json and writes tests/eval_results.md.

Needs Ollama running and the documents indexed. Run from backend/: python -m tests.evaluate
"""

import json
from pathlib import Path

from routes.search import answer_question
from utils.errors import AppError
from utils.retrieval import retrieve

TESTS_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = TESTS_DIR / "eval_questions.json"
RESULTS_FILE = TESTS_DIR / "eval_results.md"

GROUPS = ["direct", "reworded", "multi"]


def expected_sources(case):
    if "sources" in case:
        return case["sources"]
    return [{"file": case["file"], "section": case["section"]}]


def is_expected(chunk, case):
    return any(chunk["file"] == s["file"] and chunk["section"] == s["section"] for s in expected_sources(case))


def found_all(chunks, case):
    return all(
        any(chunk["file"] == s["file"] and chunk["section"] == s["section"] for chunk in chunks)
        for s in expected_sources(case)
    )


def matches(text, keyword):
    # A keyword can be a list of other ways to say the same thing, e.g. ["USB", "thumb drive"].
    options = keyword if isinstance(keyword, list) else [keyword]
    return any(option.lower() in text.lower() for option in options)


def contains_keyword(text, keywords):
    return any(matches(text, keyword) for keyword in keywords)


def contains_all_keywords(text, keywords):
    return all(matches(text, keyword) for keyword in keywords)


def evaluate_unanswerable(case):
    try:
        reply = answer_question(case["question"])
    except AppError as error:
        return {"refused": error.status_code == 404, "answer": f"ERROR: {error.message}"}
    return {"refused": False, "answer": reply["answer"]}


def evaluate_case(case):
    results, _ = retrieve(case["question"])
    retrieved = found_all(results, case)

    try:
        reply = answer_question(case["question"])
    except AppError as error:
        return {"retrieved": retrieved, "answer": f"ERROR: {error.message}",
                "correct_answer": False, "correct_reference": False, "snippet": "", "snippet_supports": False}

    good_sources = [s for s in reply["sources"] if is_expected(s, case)]
    snippet = good_sources[0]["snippet"] if good_sources else reply["sources"][0]["snippet"]

    if case.get("type") == "multi":
        correct_answer = contains_all_keywords(reply["answer"], case["keywords"])
    else:
        correct_answer = contains_keyword(reply["answer"], case["keywords"])

    return {
        "retrieved": retrieved,
        "answer": reply["answer"],
        "correct_answer": correct_answer,
        "correct_reference": len(good_sources) > 0,
        "snippet": snippet,
        "snippet_supports": contains_keyword(snippet, case["keywords"]),
    }


def percent(rows, key):
    count = sum(row[key] for row in rows)
    if not rows:
        return "-"
    return f"{count}/{len(rows)} = {round(count / len(rows) * 100)}%"


def main():
    cases = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    rows = {group: [] for group in GROUPS}
    refusals = []
    misses = []

    mark = lambda ok: "yes" if ok else "NO"

    for number, case in enumerate(cases, start=1):
        group = case.get("type", "direct")
        print(f"\n{number}. [{group}] {case['question']}")

        if group == "unanswerable":
            result = evaluate_unanswerable(case)
            refusals.append(result)
            print(f"   answer:   {result['answer']}")
            print(f"   refused correctly: {mark(result['refused'])}")
            if not result["refused"]:
                misses.append(f"[{group}] {case['question']} -> answered instead of refusing: {result['answer']}")
            continue

        result = evaluate_case(case)
        rows[group].append(result)

        expected = ", ".join(f"{s['file']} > {s['section']}" for s in expected_sources(case))
        print(f"   expected:  {expected}")
        print(f"   answer:    {result['answer']}")
        print(f"   snippet:   {result['snippet']}")
        print(f"   in top 3: {mark(result['retrieved'])} | correct answer: {mark(result['correct_answer'])}"
              f" | correct reference: {mark(result['correct_reference'])} | snippet supports: {mark(result['snippet_supports'])}")

        failed = [name for name in ["retrieved", "correct_answer", "correct_reference", "snippet_supports"] if not result[name]]
        if failed:
            misses.append(f"[{group}] {case['question']} -> failed: {', '.join(failed)}. Answer: {result['answer']}")

    answerable = rows["direct"] + rows["reworded"] + rows["multi"]
    columns = [rows["direct"], rows["reworded"], rows["multi"], answerable]
    metrics = [
        ("Retrieval@3", "retrieved", ">= 80%"),
        ("Answer correct", "correct_answer", "-"),
        ("Reference coverage", "correct_reference", ">= 90%"),
        ("Source precision", "snippet_supports", ">= 80%"),
    ]

    lines = [
        f"| Metric | Direct ({len(rows['direct'])}) | Reworded ({len(rows['reworded'])}) "
        f"| Multi-section ({len(rows['multi'])}) | All answerable ({len(answerable)}) | Target |",
        "|---|---|---|---|---|---|",
    ]
    for name, key, target in metrics:
        cells = " | ".join(percent(column, key) for column in columns)
        lines.append(f"| {name} | {cells} | {target} |")

    lines.append("")
    lines.append(f"Unanswerable questions refused correctly: {percent(refusals, 'refused')}")
    lines.append("")
    lines.append("## Misses")
    lines.append("")
    lines += [f"- {miss}" for miss in misses] or ["- none"]

    report = "\n".join(lines)
    RESULTS_FILE.write_text(report + "\n", encoding="utf-8")
    print("\n" + report)
    print(f"\nSaved to {RESULTS_FILE.name}")


if __name__ == "__main__":
    main()
