"""Pytest configuration: use an isolated temp database and create tables.

Set the database URL before importing any app module so the engine binds to the
throwaway test database rather than the development one.
"""

import os
import shutil
import tempfile

_TMP = tempfile.gettempdir()
_TEST_DB = os.path.join(_TMP, "docengine_test.db")
_TEST_VEC = os.path.join(_TMP, "docengine_test_vec")
_TEST_DOCS = os.path.join(_TMP, "docengine_test_docs")
_TEST_REPOS = os.path.join(_TMP, "docengine_test_repos")

# Isolate all on-disk state so tests never touch development storage.
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["VECTOR_STORAGE_DIR"] = _TEST_VEC
os.environ["DOCS_STORAGE_DIR"] = _TEST_DOCS
os.environ["REPOSITORIES_DIR"] = _TEST_REPOS

# Start from a clean slate for vector storage to avoid stale ChromaDB state.
shutil.rmtree(_TEST_VEC, ignore_errors=True)

# Import only after the env var is set.
from app.core.database import init_db  # noqa: E402

# Start each test session from a clean schema.
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
init_db()
