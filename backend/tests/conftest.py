import os
import shutil
import tempfile
from pathlib import Path

# Runs before the app is imported: the tests work on a temporary copy of backend/data, so uploads,
# deletes, category changes, the index and the logs never touch the real files, even if a test crashes.
# The index (with its embedding cache) is copied too, so the tests don't re-embed every document.
REAL_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="guidely-test-data-"))

shutil.copytree(REAL_DATA_DIR, TEST_DATA_DIR, dirs_exist_ok=True, ignore=shutil.ignore_patterns("logs"))
os.environ["GUIDELY_DATA_DIR"] = str(TEST_DATA_DIR)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
