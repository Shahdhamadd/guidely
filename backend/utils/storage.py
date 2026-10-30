"""Reading and writing JSON files and the JSONL logs."""

import json
import os
import threading
from datetime import datetime, timedelta

from utils.config import LOG_RETENTION_DAYS, LOGS_DIR

# One lock for every file that several requests can change at the same time
# (caches, index, categories). RLock so a function holding it can call another that takes it.
lock = threading.RLock()


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path, data, indent=None):
    """Write to a temporary file first, then swap it in, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(data, indent=indent), encoding="utf-8")
    os.replace(temp_path, path)


def write_log(path, record):
    """Append one record with a timestamp as a line of JSON."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now().isoformat(timespec="seconds"), **record}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")


def read_log(path):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def prune_logs(days=LOG_RETENTION_DAYS):
    """Delete log lines older than `days`, so questions aren't kept forever. Returns how many were removed."""
    if days <= 0 or not LOGS_DIR.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for path in LOGS_DIR.glob("*.jsonl"):
        records = read_log(path)
        kept = [record for record in records if datetime.fromisoformat(record["time"]) >= cutoff]
        if len(kept) < len(records):
            temp_path = path.with_name(path.name + ".tmp")
            temp_path.write_text("".join(json.dumps(record) + "\n" for record in kept), encoding="utf-8")
            os.replace(temp_path, path)
            removed += len(records) - len(kept)
    return removed
