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
| `benefits.txt` | HR | Health insurance, dental, claims, pension, wellness allowance |

`benefits.txt` is the long one: its Health Insurance section is about 350 words, so it is split into two chunks (see How it works).

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
│   ├── main.py              # App setup, startup, error handlers, /health, /metrics, CSV export
│   ├── routes/              # Endpoints only
│   │   ├── documents.py     # Upload, read, edit, delete, categories, re-index, embeddings
│   │   └── search.py        # /search/ask, /search/ask/stream, /search/retrieve
│   ├── utils/               # Reusable logic used by the routes
│   │   ├── config.py        # Paths and .env settings
│   │   ├── chunking.py      # Reading .txt/.md/.pdf and splitting into chunks
│   │   ├── embeddings.py    # Embedding model and the embedding cache
│   │   ├── vector_store.py  # Building, saving and loading the FAISS index
│   │   ├── retrieval.py     # Similarity search, category filter, follow-ups
│   │   ├── llm.py           # Prompt and Ollama calls
│   │   ├── answers.py       # Refusal check, citations to sources, snippets
│   │   ├── categories.py    # Document categories
│   │   ├── storage.py       # JSON files, logs and log retention
│   │   └── errors.py        # AppError -> {"error": ...} with a status code
│   ├── models/record.py     # Request bodies
│   ├── data/sample-docs/    # The 7 sample documents
│   └── tests/               # API tests, retrieval/answer evaluation and the latency benchmark
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
2. The text is split by `# Heading`, then into chunks of up to 250 words (about 330 tokens) without cutting paragraphs. A longer section becomes several chunks with the same heading (`benefits.txt › Health Insurance` is 244 + 105 words). This is smaller than the brief's 500–1,000 tokens on purpose: the sections are short, and one topic per chunk gave better retrieval. Change it with `CHUNK_WORDS`.
3. Each chunk is embedded with `BAAI/bge-small-en-v1.5`. Embeddings are cached by a SHA-256 hash of the chunk text, so unchanged chunks are never embedded again. Question embeddings are cached too.
4. The vectors go into a FAISS index (cosine similarity) saved to `backend/data/index/`.

Answering:

1. The question is embedded and the 3 closest chunks are retrieved (optionally only from one category).
2. Chunks with a similarity below 0.45 are dropped. If nothing is left, the API returns 404 "No relevant documents".
3. The chunks are numbered and sent to the model, which answers only from them in 1 to 3 sentences and cites them as `[1]`, `[2]`.
4. The response contains the answer, the cited sources, and for each source the sentence that best supports the answer.

The Search page streams the answer as it is written and remembers the last 3 questions, so follow-ups like "Can I carry them over?" work. Errors are returned as `{"error": "..."}` with a 4xx or 5xx status.

**Why a refusal is a 404.** There are two ways a question can go unanswered: no chunk scores above 0.45 (step 2), or the chunks are close but the model says they don't contain the answer. For the user both mean the same thing, "the documents don't cover this", so both return the same 404 "No relevant documents" error. That keeps one rule for clients (a 200 always has an answer with at least one source, never a non-answer dressed up as success), lets the Search page show the same hint in both cases, and keeps refusals out of the latency and source statistics in `/metrics`, which only count answered questions. 404 rather than 500 because nothing went wrong on the server: the requested information just isn't there. In the streamed version the 200 status is already sent before the refusal is known, so it arrives as a final `{"type": "error", "status_code": 404}` event.

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

## Security and privacy

- **No login.** Guidely is meant to run on one machine, so there are no user accounts. Uvicorn listens on `127.0.0.1` by default, so only this computer can reach the API.
- **Size limits.** Uploads and edits are both limited to `MAX_UPLOAD_MB` (413 if bigger). File names are reduced to their base name, so `../` can't reach files outside `sample-docs`.
- **Prompt injection.** Document text goes to the model, so a document could contain instructions like "ignore your rules". The system prompt tells the model the sources are reference text and that it must never follow instructions inside them. A small local model can't be guaranteed to obey, so treat uploaded documents as trusted content.
- **Log retention.** The query log stores each question as typed. Lines older than `LOG_RETENTION_DAYS` (default 30) are deleted every time the backend starts.
- **Question cache.** Up to `MAX_CACHED_QUESTIONS` (500) question vectors are kept. When it's full, the least recently used one is removed, and a cache hit counts as a use, so frequent questions stay cached. Order changes from hits are saved the next time a new question is added.

## Testing & Metrics

Measured on my laptop (Intel i9-13900H, 16 GB RAM) with warm caches, 7 documents and `llama3.2:3b`. Latency depends on the machine, so `tests/benchmark.py` reproduces metrics 3 and 4 on any computer (see below).

| # | Metric | Target | Result |
|---|---|---|---|
| 1 | Retrieval@3 (36 answerable questions) | ≥ 80% | 97% (35/36) |
| 2 | Answer reference coverage | ≥ 90% | 97% (35/36) |
| 3 | Latency | median < 3s, p95 < 5s | median 0.40s, p95 0.65s (20 questions, `/search/ask`) |
| 4 | Embedding cache on repeated questions | 100% hits | 100% (20/20 hits, 0 new embeddings) |
| 5 | Failure handling (empty query, missing model, corrupted file, no results) | 4xx/5xx with clear error | Pass (400, 500, 422, 404). Also tested: model timeout 504, nothing indexed 404 |
| 6 | Source precision | ≥ 80% | 89% (32/36) |
| 7 | Re-indexing 7 unchanged files | No errors, nothing re-embedded | 0.05s, 45/45 cache hits, 0 new embeddings |
| 8 | Unanswerable questions refused | - | 100% (6/6) |
| 9 | Follow-up questions (the 4 example pairs on the Search page) | - | 4/4 answered with the right source |

Metrics 1, 2, 6 and 8 come from `tests/evaluate.py`, which runs the 42 questions in `tests/eval_questions.json` (24 direct, 8 reworded, 4 needing two sections, 6 unanswerable). It scores answers automatically by expected sources and keywords, and I reviewed every miss by hand. Full results and misses are in `tests/eval_results.md`.

### Cache in the logs

On startup the backend logs what it loaded from disk instead of re-embedding:

```
[startup] embedding model BAAI/bge-small-en-v1.5 is loaded
[startup] embedding cache loaded from disk: 45 chunk vectors, 388 question vectors
[startup] FAISS index loaded from disk: 45 vectors (nothing re-embedded)
[startup] llama3.2:3b is loaded in Ollama
```

Each question and each re-index logs its cache hits:

```
[query] 398 ms | ok | cache: 1 hits, 0 new | How many vacation days do full-time staff get?
[index] 7 files, 45 chunks | cache: 45 hits, 0 new embeddings | 0.05s
```

The same numbers are saved in `backend/data/logs/` (`queries.jsonl`, `index.jsonl`, `errors.jsonl`).

Metrics 3, 4, 5 and 7 are logged by the backend and shown at http://localhost:8000/metrics. That endpoint covers the whole query log, including cold starts, so its latency can be higher than the warm-cache run above.

To run the tests, from `backend/`:

```bash
../.venv/Scripts/python -m pytest tests/test_api.py -v
```

```bash
../.venv/Scripts/python -m tests.evaluate
```

```bash
../.venv/Scripts/python -m tests.benchmark
```

`test_api.py` doesn't need Ollama. `tests/conftest.py` copies `backend/data` to a temporary folder before the app is imported, and the tests only use that copy: uploads, deletes, category changes, the index and the logs never touch the real files, even if a test crashes, and test runs never show up in `/metrics` or the CSV export. The copy is deleted when the tests finish.

`evaluate.py` and `benchmark.py` use the real model, so Ollama must be running and the documents indexed first. `benchmark.py` asks 20 questions once to warm up, then times them again and prints the median and p95 latency and the cache hits. It doesn't write to the query log. A run on my laptop gave median 0.40s, p95 0.67s, 20/20 cache hits.
