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

Each section starts with a `# Heading` line, which is used when citing a source (e.g. `policy.txt › Annual leave`). Categories are stored in `backend/data/categories.json` and can be used to filter questions on the Ask page.

## Setup

You need Python 3.12, Node.js 22 and [Ollama](https://ollama.com). The commands are for Windows; on macOS or Linux use `.venv/bin/python` instead of `.venv/Scripts/python`.

```bash
ollama pull llama3.2:3b
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
cd frontend && npm install
```

Settings are in `.env` (not committed; copy it from `.env.example`). There are no API keys. Make sure Ollama is running (`ollama serve` if it isn't).

Start the backend from `backend/` (the first start downloads the ~130 MB embedding model):

```bash
../.venv/Scripts/python -m uvicorn main:app --reload
```

Start the frontend from `frontend/`:

```bash
npm run dev
```

Open http://localhost:5173 (not `127.0.0.1`, which the backend's CORS setting doesn't allow), go to the Documents page and click **Re-index all** once. API docs are at http://localhost:8000/docs.

## Project structure

```
guidely/
├── backend/
│   ├── main.py              # App setup, error handlers, /health, /metrics, CSV export
│   ├── routes/
│   │   ├── documents.py     # Parsing, chunking, embedding cache, FAISS index, document endpoints
│   │   └── search.py        # Retrieval, prompt, Ollama calls, answer + sources
│   ├── models/record.py     # Request bodies
│   ├── data/sample-docs/    # The 6 sample documents
│   └── tests/               # API tests and retrieval/answer evaluation
├── frontend/src/
│   ├── pages/               # SearchPage (Ask) and AdminPage (Documents)
│   ├── components/
│   └── api.js               # Calls to the backend
├── requirements.txt
└── .env.example
```

## How it works

Indexing:

1. Each `.txt`, `.md` or `.pdf` file is read as plain text. Files that can't be read are skipped and listed in the response.
2. The text is split by `# Heading`, then into chunks of up to 250 words (about 330 tokens) without cutting paragraphs. This is smaller than the brief's 500–1,000 tokens on purpose: the sections are short, and one topic per chunk gave better retrieval. Change it with `CHUNK_WORDS`.
3. Each chunk is embedded with `BAAI/bge-small-en-v1.5`. Embeddings are cached by a SHA-256 hash of the chunk text, so unchanged chunks are never embedded again. Question embeddings are cached too.
4. The vectors go into a FAISS index (cosine similarity) saved to `backend/data/index/`.

Answering:

1. The question is embedded and the 3 closest chunks are retrieved (optionally only from one category).
2. Chunks with a similarity below 0.45 are dropped. If nothing is left, the API returns 404 "No relevant documents".
3. The chunks are numbered and sent to the model, which answers only from them in 1 to 3 sentences and cites them as `[1]`, `[2]`.
4. The response contains the answer, the cited sources, and for each source the sentence that best supports the answer.

The Search page streams the answer as it is written and remembers the last 3 questions, so follow-ups like "Can I carry them over?" work. Errors are returned as `{"error": "..."}` with a 4xx or 5xx status.

## API endpoints

| Brief requirement | Endpoint |
|---|---|
| Upload documents and create embeddings | `POST /documents/upload` |
| Persist embeddings to the vector database | `POST /documents/index` |
| Retrieve stored embeddings for similarity search | `GET /documents/embeddings` |
| Process a question and return an answer with references | `POST /search/ask` |

Other endpoints: `GET/PUT/DELETE /documents/{name}` (read, edit, delete), `PUT /documents/{name}/category`, `POST /search/ask/stream` (streamed answer), `POST /search/retrieve` (search without the model), `GET /health`, `GET /metrics` and `GET /logs/queries.csv`.

The brief's "missing model key" test: Guidely uses a local model, so there is no API key. The equivalent is an empty `LLM_MODEL` in `.env`, which returns 500 with a clear error. If Ollama isn't running the API returns 503.

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

Metrics 1, 2, 6 and 8 come from `tests/evaluate.py`, which runs the 38 questions in `tests/eval_questions.json` (20 direct, 8 reworded, 4 needing two sections, 6 unanswerable). It scores answers automatically by expected sources and keywords, and I reviewed every miss by hand. Full results and misses are in `tests/eval_results.md`.

Metrics 3, 4, 5 and 7 are logged by the backend and shown at http://localhost:8000/metrics. That endpoint covers the whole query log, including cold starts, so its latency can be higher than the warm-cache run above.

To run the tests, from `backend/`:

```bash
../.venv/Scripts/python -m pytest tests/test_api.py -v
```

```bash
../.venv/Scripts/python -m tests.evaluate
```

`test_api.py` builds the index itself and doesn't need Ollama. `evaluate.py` uses the real model, so Ollama must be running and the documents indexed first.
