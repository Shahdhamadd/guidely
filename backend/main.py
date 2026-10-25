import csv
import io
import math
import statistics
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from routes import documents, search
from routes.documents import (
    CHUNKS_FILE,
    DOCS_DIR,
    ERROR_LOG,
    INDEX_LOG,
    QUERY_LOG,
    AppError,
    load_json,
    read_log,
    write_log,
)

@asynccontextmanager
async def lifespan(app):
    search.warm_up()
    yield


app = FastAPI(title="Guidely", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(search.router)


def error_response(request, status_code, message):
    write_log(ERROR_LOG, {"path": request.url.path, "status_code": status_code, "error": message})
    print(f"[error] {status_code} | {request.url.path} | {message}")
    return JSONResponse(status_code=status_code, content={"error": message})


@app.exception_handler(AppError)
def handle_app_error(request, error):
    return error_response(request, error.status_code, error.message)


@app.exception_handler(RequestValidationError)
def handle_bad_request(request, error):
    return error_response(request, 400, "The request is missing a field or has the wrong format.")


@app.exception_handler(Exception)
def handle_unexpected_error(request, error):
    return error_response(request, 500, "Something went wrong on the server.")


@app.get("/health")
def health():
    return {"status": "ok"}


def percentile(values, percent):
    ordered = sorted(values)
    position = math.ceil(len(ordered) * percent / 100) - 1
    return ordered[position]


@app.get("/metrics")
def metrics():
    queries = read_log(QUERY_LOG)
    answered = [q for q in queries if q["status"] == "ok"]
    latencies = [q["latency_ms"] for q in answered]

    cache_hits = sum(q["cache_hits"] for q in answered)
    new_embeddings = sum(q["new_embeddings"] for q in answered)

    seen = set()
    repeated = []
    for q in answered:
        if q["question"] in seen:
            repeated.append(q)
        seen.add(q["question"])
    repeated_hits = sum(q["cache_hits"] for q in repeated)

    errors = read_log(ERROR_LOG)
    index_runs = read_log(INDEX_LOG)

    return {
        "documents": len([path for path in DOCS_DIR.iterdir() if path.is_file()]),
        "chunks": len(load_json(CHUNKS_FILE, [])),
        "queries_total": len(queries),
        "queries_answered": len(answered),
        "latency_ms": {
            "median": statistics.median(latencies) if latencies else None,
            "p95": percentile(latencies, 95) if latencies else None,
        },
        "query_cache": {
            "cache_hits": cache_hits,
            "new_embeddings": new_embeddings,
            "repeated_questions": len(repeated),
            "repeated_hit_rate_percent": round(repeated_hits / len(repeated) * 100, 1) if repeated else None,
        },
        "errors_total": len(errors),
        "errors_by_type": dict(Counter(e["error"] for e in errors)),
        "last_index_run": index_runs[-1] if index_runs else None,
    }


CSV_COLUMNS = ["time", "question", "category", "follow_up", "status", "latency_ms",
               "cache_hits", "new_embeddings", "sources", "error"]


@app.get("/logs/queries.csv")
def export_queries():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)

    for query in read_log(QUERY_LOG):
        query["sources"] = " | ".join(query.get("sources", []))
        writer.writerow([query.get(column, "") for column in CSV_COLUMNS])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=guidely-queries.csv"},
    )

