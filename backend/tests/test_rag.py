"""Tests for the RAG pipeline: consistent embeddings and chat self-heal."""

import asyncio
from pathlib import Path

from app.core.database import SessionLocal
from app.models import CodeEntity, Documentation, Repository
from app.models.enums import RepositoryStatus
from app.rag import embedding_provider, vector_store
from app.services.rag_service import RAGService


def _seed_repo_with_docs(db, tmp_path: Path) -> Repository:
    repo = Repository(
        name="rag",
        full_name="rag/rag",
        url="https://github.com/rag/rag",
        local_path=str(tmp_path),
        status=RepositoryStatus.READY.value,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    entity = CodeEntity(
        repository_id=repo.id,
        source_file_id=0,
        kind="function",
        name="login",
        qualified_name="auth.login",
        signature="def login(email, password)",
        source_code="def login(email, password): ...",
        relative_path="auth.py",
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)

    db.add(
        Documentation(
            repository_id=repo.id,
            entity_id=entity.id,
            content_markdown="## login\n\nAuthenticates a user with email and password.",
            generator="fallback",
        )
    )
    db.commit()
    return repo


def test_local_embeddings_are_consistent_dimension():
    a = asyncio.run(embedding_provider.embed_one("hello world authenticate user"))
    b = asyncio.run(embedding_provider.embed_one("a different sentence entirely"))
    assert len(a) == len(b) and len(a) > 0


def test_chat_indexes_and_grounds_answer(tmp_path: Path):
    db = SessionLocal()
    repo = _seed_repo_with_docs(db, tmp_path)

    res = asyncio.run(
        RAGService(db).chat(repository_id=repo.id, message="How do I log in a user?")
    )
    assert res["grounded"] is True
    assert any(s["qualified_name"] == "auth.login" for s in res["sources"])
    db.close()


def test_chat_self_heals_on_dimension_mismatch(tmp_path: Path):
    """A collection built with a different dimension must not 500 the chat."""
    db = SessionLocal()
    repo = _seed_repo_with_docs(db, tmp_path)

    # Poison the collection with a wrong-dimension vector to simulate a stale
    # index created by a different embedder.
    vector_store.reset_repository(repo.id)
    collection = vector_store._collection(repo.id)
    collection.add(ids=["bad"], embeddings=[[0.1, 0.2, 0.3]], documents=["x"])

    # Chat must detect the mismatch, rebuild the index, and answer cleanly.
    res = asyncio.run(
        RAGService(db).chat(repository_id=repo.id, message="How do I log in a user?")
    )
    assert res["grounded"] in (True, False)  # no exception is the key assertion
    assert isinstance(res["answer"], str) and res["answer"]
    db.close()
