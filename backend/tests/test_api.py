import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from fastapi.testclient import TestClient

from main import app
from routes import documents, search
from routes.documents import (
    CACHE_FILE,
    CATEGORIES_FILE,
    CHUNKS_FILE,
    DOCS_DIR,
    MAX_UPLOAD_MB,
    QUERY_CACHE_FILE,
    chunk_to_embedding_text,
    load_json,
    remove_oldest,
    text_hash,
)
from routes.search import QUERY_PREFIX, is_refusal, pick_sources

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def build_index():
    documents.reindex()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_documents():
    response = client.get("/documents")
    assert response.status_code == 200
    assert len(response.json()["documents"]) >= 5


def test_documents_have_categories():
    data = client.get("/documents").json()
    policy = next(d for d in data["documents"] if d["name"] == "policy.txt")
    assert policy["category"] == "HR"
    assert "HR" in data["categories"]


def test_change_category():
    try:
        response = client.put("/documents/guide.txt/category", json={"category": "Testing"})
        assert response.status_code == 200
        guide = next(d for d in client.get("/documents").json()["documents"] if d["name"] == "guide.txt")
        assert guide["category"] == "Testing"
    finally:
        client.put("/documents/guide.txt/category", json={"category": "Customer Support"})


def test_category_filter():
    question = "How many vacation days do I get?"

    response = client.post("/search/retrieve", json={"question": question, "category": "IT"})
    results = response.json()["results"]
    assert len(results) > 0
    assert all(chunk["category"] == "IT" for chunk in results)

    response = client.post("/search/retrieve", json={"question": question, "category": "HR"})
    assert response.json()["results"][0]["file"] == "policy.txt"


def test_empty_question():
    response = client.post("/search/ask", json={"question": "   "})
    assert response.status_code == 400
    assert response.json() == {"error": "Please type a question."}


def test_missing_question_field():
    response = client.post("/search/ask", json={})
    assert response.status_code == 400
    assert "error" in response.json()


def test_no_results():
    response = client.post("/search/ask", json={"question": "What is the capital of France?"})
    assert response.status_code == 404
    assert response.json() == {"error": "No relevant documents were found for this question."}


def test_missing_model(monkeypatch):
    monkeypatch.setattr(search, "LLM_MODEL", "")
    response = client.post("/search/ask", json={"question": "How many vacation days do I get?"})
    assert response.status_code == 500
    assert response.json() == {"error": "No AI model is configured. Set LLM_MODEL in the .env file."}


def test_model_timeout(monkeypatch):
    def slow_model(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(search, "LLM_MODEL", "test-model")
    monkeypatch.setattr(search.requests, "post", slow_model)
    response = client.post("/search/ask", json={"question": "How many vacation days do I get?"})
    assert response.status_code == 504
    assert "took longer than" in response.json()["error"]


def test_no_index(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "INDEX_FILE", tmp_path / "missing.faiss")
    monkeypatch.setitem(documents.memory, "index", None)
    response = client.post("/search/ask", json={"question": "How many vacation days do I get?"})
    assert response.status_code == 404
    assert "No documents are indexed yet" in response.json()["error"]


def test_unknown_document():
    response = client.get("/documents/does-not-exist.txt")
    assert response.status_code == 404
    assert "error" in response.json()


def test_unsupported_file_type():
    response = client.post("/documents/upload", files={"file": ("virus.exe", b"hello")})
    assert response.status_code == 400
    assert "unsupported file type" in response.json()["error"]


def test_corrupted_file():
    response = client.post("/documents/upload", files={"file": ("broken.pdf", b"%PDF-1.4 garbage")})
    assert response.status_code == 422
    assert "corrupted" in response.json()["error"]
    assert not (DOCS_DIR / "broken.pdf").exists()


def test_file_too_big():
    big_text = b"a" * (MAX_UPLOAD_MB * 1024 * 1024 + 1)
    response = client.post("/documents/upload", files={"file": ("huge.txt", big_text)})
    assert response.status_code == 413
    assert "too big" in response.json()["error"]
    assert not (DOCS_DIR / "huge.txt").exists()


def test_broken_upload_keeps_original():
    faq = DOCS_DIR / "faq.txt"
    original = faq.read_bytes()

    try:
        response = client.post("/documents/upload", files={"file": ("faq.txt", b"   ")})
        assert response.status_code == 422
        assert "no readable text" in response.json()["error"]
        assert faq.read_bytes() == original
    finally:
        if not faq.exists() or faq.read_bytes() != original:
            faq.write_bytes(original)


def test_delete_document():
    text = b"# Parking\n\nStaff can park for free in the basement."
    client.post("/documents/upload", files={"file": ("delete-me.txt", text)}, data={"category": "Facilities"})
    assert (DOCS_DIR / "delete-me.txt").exists()
    assert load_json(CATEGORIES_FILE, {})["delete-me.txt"] == "Facilities"

    response = client.delete("/documents/delete-me.txt")
    assert response.status_code == 200
    assert not (DOCS_DIR / "delete-me.txt").exists()
    assert "delete-me.txt" not in load_json(CATEGORIES_FILE, {})

    chunk_files = {chunk["file"] for chunk in load_json(CHUNKS_FILE, [])}
    assert "delete-me.txt" not in chunk_files

    deleted_chunk = chunk_to_embedding_text({"section": "Parking", "text": "Staff can park for free in the basement."})
    assert text_hash(deleted_chunk) not in load_json(CACHE_FILE, {})


def test_remove_oldest():
    cache = {"first": 1, "second": 2, "third": 3, "fourth": 4}
    remove_oldest(cache, 2)
    assert cache == {"third": 3, "fourth": 4}


def test_delete_unknown_document():
    response = client.delete("/documents/does-not-exist.txt")
    assert response.status_code == 404
    assert "error" in response.json()


def test_repeated_question_uses_cache():
    question = {"question": "How long must my password be?"}
    client.post("/search/retrieve", json=question)

    response = client.post("/search/retrieve", json=question)
    assert response.json()["cache"] == {"cache_hits": 1, "new_embeddings": 0}


def test_many_questions_at_once():
    run_id = uuid.uuid4().hex[:8]
    questions = [f"Question {run_id}-{i} about annual leave" for i in range(20)]

    def ask(question):
        return client.post("/search/retrieve", json={"question": question}).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(ask, questions))

    assert codes == [200] * 20
    cache = json.loads(QUERY_CACHE_FILE.read_text(encoding="utf-8"))
    for question in questions:
        assert text_hash(QUERY_PREFIX + question) in cache


def test_is_refusal():
    assert is_refusal("I couldn't find this in the documents.")
    assert is_refusal("I couldn't find the Enterprise plan in the provided sources.")
    assert is_refusal("The sources do not contain information about parking.")
    assert not is_refusal("If you can't find a file, check the Trash for 30 days [1].")
    assert not is_refusal("Full-time employees get 21 days of paid leave [1].")


def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["documents"] >= 5
    assert "latency_ms" in data


def test_made_up_citation_still_has_sources():
    chunks = [
        {"file": "a.txt", "section": "One", "category": "General", "score": 0.9, "text": "First fact."},
        {"file": "b.txt", "section": "Two", "category": "General", "score": 0.8, "text": "Second fact."},
    ]
    assert len(pick_sources("Some answer [7].", chunks)) == 2
    assert [s["file"] for s in pick_sources("Some answer [2] [7].", chunks)] == ["b.txt"]


def test_follow_up_uses_history():
    question = "Can I carry them over to next year?"
    history = [{"question": "How many vacation days do full-time staff get?", "answer": "21 days [1]."}]

    response = client.post("/search/retrieve", json={"question": question, "history": history})
    assert response.status_code == 200
    assert response.json()["results"][0]["section"] == "Annual Leave"


def test_export_queries_csv():
    response = client.get("/logs/queries.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0].startswith("time,question,category,follow_up,status,latency_ms")


def stream_events(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_stream_sends_pieces_then_sources(monkeypatch):
    pieces = ["Full-time staff get ", "21 days ", "of paid leave [1]."]
    monkeypatch.setattr(search, "stream_llm", lambda question, chunks, history=(): iter(pieces))

    response = client.post("/search/ask/stream", json={"question": "How many vacation days do full-time staff get?"})
    assert response.status_code == 200
    events = stream_events(response)

    assert [e["text"] for e in events if e["type"] == "token"] == pieces
    done = events[-1]
    assert done["type"] == "done"
    assert done["answer"] == "".join(pieces)
    assert done["sources"][0]["section"] == "Annual Leave"
    assert "latency_ms" in done


def test_stream_refusal_ends_with_error(monkeypatch):
    monkeypatch.setattr(search, "stream_llm", lambda question, chunks, history=(): iter(["I couldn't find this in the documents."]))

    response = client.post("/search/ask/stream", json={"question": "How many vacation days do full-time staff get?"})
    done = stream_events(response)[-1]
    assert done["type"] == "error"
    assert done["status_code"] == 404


def test_stream_errors_before_answer_are_normal(monkeypatch):
    monkeypatch.setattr(search, "LLM_MODEL", "")
    response = client.post("/search/ask/stream", json={"question": "How many vacation days do I get?"})
    assert response.status_code == 500
    assert "No AI model is configured" in response.json()["error"]

    response = client.post("/search/ask/stream", json={"question": "   "})
    assert response.status_code == 400
