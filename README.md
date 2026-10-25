# Guidely

Guidely is a question-answering app for a company's internal documents. You ask a question, it finds the relevant parts of the documents and writes a short answer that cites the files it used.

Everything runs locally: a React (Vite) frontend, a FastAPI backend, `sentence-transformers` for embeddings, FAISS for search, and Ollama for the language model.

## Dataset

The sample documents are in `backend/data/sample-docs/`. They describe a made-up company called Brightpath.

| File | Category | Topics |
|---|---|---|
| `policy.txt` | HR | Working hours, annual leave, sick leave, remote work, parental leave |
| `faq.txt` | Customer Support | Plans and pricing, refunds, cancelling, passwords, support |
| `guide.txt` | Customer Support | Installing the desktop app, syncing, sync problems |
| `security.txt` | IT | Passwords, 2FA, laptops, phishing, incidents |
| `expenses.txt` | Finance | Submitting expenses, meals, travel, home office, training |
| `onboarding.txt` | HR | First day, onboarding buddy, first week, probation |

Each section starts with a `# Heading` line. The heading is used when citing a source, for example `policy.txt › Annual leave`.

Each document has one category, stored in `backend/data/categories.json`. Categories are set when uploading or changed from the Documents page; a document without one is in "General". On the Ask page you can limit a question to one category, and every source shows its category.

## Setup

You need Python 3.12, Node.js 22 and [Ollama](https://ollama.com).

```bash
ollama pull llama3.2:3b
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
cd frontend && npm install
```

Start the backend from `backend/`:

```bash
../.venv/Scripts/python -m uvicorn main:app --reload
```

Start the frontend from `frontend/`:

```bash
npm run dev
```

Open http://localhost:5173, go to the Documents page and click Re-index all. The API docs are at http://localhost:8000/docs.

## How it works

Indexing:

1. Each `.txt`, `.md` or `.pdf` file is read as plain text. Files that can't be read are skipped and listed in the response.
2. The text is split by `# Heading`, then into chunks of up to 250 words. Paragraphs are not cut in half.
3. Each chunk is embedded with `BAAI/bge-small-en-v1.5`. Embeddings are cached by a SHA-256 hash of the chunk text, so a chunk that hasn't changed is never embedded twice. Each re-index also removes the embeddings of chunks that were edited or deleted. Question embeddings live in a separate cache (`query_cache.json`) that keeps the newest 500 questions (`MAX_CACHED_QUESTIONS`).
4. The vectors go into a FAISS index (cosine similarity) and the chunk labels go into `chunks.json`.

Answering:

1. The question is embedded and the 3 closest chunks are retrieved. If a category is chosen, only chunks from documents in that category are kept. The category is looked up at search time, so changing it doesn't need a re-index.
2. Chunks with a similarity below 0.45 are dropped. If nothing is left, the API returns 404 "No relevant documents".
3. The chunks are numbered and sent to the model, which is told to answer only from them in 1 to 3 sentences and cite them as `[1]`, `[2]`.
4. The response contains the answer, the cited sources, and for each source the sentence that matches the answer best.

The Search page uses `/search/ask/stream`, which sends one JSON object per line: `{"type": "token", "text": ...}` for each piece of the answer as the model writes it, then either `{"type": "done", ...}` with the same fields as `/search/ask`, or `{"type": "error", "error": ..., "status_code": ...}` if the model refuses or stops. Errors that happen before the model starts (empty question, no relevant documents, Ollama not running) are returned as normal JSON errors.

Follow-up questions:

The Search page remembers the conversation. With each new question it sends the last 3 questions and answers as `history`. The backend searches twice, once with the new question alone and once with the earlier questions added in front, and keeps the best score for each chunk. This way "Can I carry them over?" after a question about vacation days still finds the Annual Leave section. The earlier turns are also given to the model so it knows what "them" means. "New conversation" clears the history.

Errors are returned as `{"error": "..."}` with a 4xx or 5xx status. Questions, errors and re-indexing are logged, and `/metrics` shows the totals.

## API endpoints

| Brief requirement | Endpoint | What it does |
|---|---|---|
| Upload documents and create embeddings | `POST /documents/upload` | Saves the file, checks it can be read, then re-indexes |
| Persist embeddings to the vector database | `POST /documents/index` | Embeds changed chunks, writes the FAISS index and `chunks.json` to disk |
| Retrieve stored embeddings for similarity search | `GET /documents/embeddings` | Returns every stored vector with its file and section |
| Process a question and return an answer with references | `POST /search/ask` | Embeds the question, searches FAISS, asks the model, returns answer + sources |

Other endpoints:

| Endpoint | What it does |
|---|---|
| `GET /documents`, `GET/PUT/DELETE /documents/{name}` | List, read, edit and delete documents |
| `PUT /documents/{name}/category` | Change a document's category |
| `POST /search/ask/stream` | Same as `/search/ask`, but sends the answer while the model writes it (used by the Search page) |
| `POST /search/retrieve` | Search only, without the model (used to test retrieval) |
| `GET /health` | Returns `{"status": "ok"}` |
| `GET /metrics` | Counts of documents, chunks, queries, errors, latency and cache hits |
| `GET /logs/queries.csv` | Downloads the query log as CSV (also a button on the Documents page) |

The CSV has one row per question: `time, question, category, follow_up, status, latency_ms, cache_hits, new_embeddings, sources, error`.

## About the "missing model key" test

The brief assumes an OpenAI API key. Guidely uses a free local model through Ollama instead, so there is no API key. The equivalent setting is `LLM_MODEL` in `.env`. If it is empty, `/search/ask` returns 500 with `{"error": "No AI model is configured. Set LLM_MODEL in the .env file."}`. If Ollama is not running it returns 503, and if the model is not installed it returns 500 with the `ollama pull` command to fix it.

## Bonus features

- Follow-up questions with conversation history
- Document categories with a filter on the Search page
- Query log export as CSV
- `/health` and `/metrics` endpoints

## Testing & Metrics

Measured on my laptop (Intel i9-13900H, 16 GB RAM, CPU only) with warm caches.

| # | Metric | Target | Result |
|---|---|---|---|
| 1 | Retrieval@3 (32 answerable questions) | ≥ 80% | 100% (32/32) |
| 2 | Answer reference coverage | ≥ 90% | 97% (31/32) |
| 3 | Latency | median < 3s, p95 < 5s | median 2.57s, p95 2.84s (20 questions) |
| 4 | Embedding cache on repeated questions | 100% hits | 100% (20/20 hits, 0 new embeddings) |
| 5 | Failure handling (empty query, missing model, corrupted file, no results) | 4xx/5xx with clear error | Pass (400, 500, 422, 404). Also tested: model timeout 504, nothing indexed 404 |
| 6 | Source precision | ≥ 80% | 88% (28/32) |
| 7 | Indexing 6 files | No errors, unchanged files skipped | 0.1s, 6/6 skipped |
| 8 | Unanswerable questions refused | - | 100% (6/6) |
| 9 | Follow-up questions (the 4 example pairs on the Search page) | - | 4/4 answered with the right source |

Metrics 1, 2, 6 and 8 come from `tests/evaluate.py` and were checked by hand. The 38 questions in `tests/eval_questions.json` are in four groups:

| Group | Count | What it tests | Retrieval@3 | Answer correct |
|---|---|---|---|---|
| Direct | 20 | Questions that use the same words as the docs | 100% | 95% |
| Reworded | 8 | Different words, e.g. "thumb drive" for USB, "accommodation" for hotel | 100% | 88% |
| Multi-section | 4 | Answer needs two sections, sometimes from two files; both must be in the top 3 | 100% | 100% |
| Unanswerable | 6 | Questions the docs don't cover; the right result is "not found" | - | 6/6 refused |

What the misses show (full list in `tests/eval_results.md`):
- **Wrong answers:** "Can I log in from home during my second week?" got a vague answer citing the onboarding guide, even though the Remote Work section (which says remote work starts after probation) was retrieved. "When do I have to submit my expense receipts?" answered "a photo of the receipt" instead of "within 30 days".
- **Grader too strict (fixed):** "No, the desktop app does not work on Linux" and "No, you are not allowed to keep client information on a thumb drive" were correct but didn't contain the keywords ("not supported", "USB"). A keyword in `eval_questions.json` can now be a list of other ways to say the same thing, e.g. `["not supported", "does not work"]`.
- **Refusals in the model's own words:** the model doesn't always use the exact "I couldn't find this in the documents." sentence (e.g. "I couldn't find the Enterprise plan in the provided sources."). The backend also treats an answer as "not found" when it has a phrase like "couldn't find" or "do not contain" **and** no `[n]` citation, so a real answer like "If you can't find a file, check the Trash [1]" is kept.

Metrics 3, 4, 5 and 7 are logged by the backend and shown at http://localhost:8000/metrics.

To run the tests, from `backend/`:

```bash
../.venv/Scripts/python -m tests.evaluate
../.venv/Scripts/python -m pytest tests/test_api.py -v
```
