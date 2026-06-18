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


def test_chat_rejects_off_topic_question(tmp_path: Path):
    """Off-topic questions must be honestly rejected — not answered from
    unrelated docs. The local hashing embedder gives junk queries non-trivial
    cosine noise, so the relevance gate must require a real lexical signal.
    """
    db = SessionLocal()
    repo = _seed_repo_with_docs(db, tmp_path)

    res = asyncio.run(
        RAGService(db).chat(
            repository_id=repo.id,
            message="What is the airspeed velocity of an unladen swallow?",
        )
    )
    assert res["grounded"] is False
    assert res["answer"] == "Information not found in documentation."
    assert res["sources"] == []
    db.close()


def test_chat_rejects_offtopic_sharing_one_common_word(tmp_path: Path):
    """A junk question that incidentally shares ONE common word with the docs
    (here "user") must still be rejected — one weak text hit is not enough."""
    db = SessionLocal()
    repo = _seed_repo_with_docs(db, tmp_path)  # doc mentions "user", "email", ...

    res = asyncio.run(
        RAGService(db).chat(
            repository_id=repo.id,
            message="Where can I buy a user manual for my lawnmower engine?",
        )
    )
    assert res["grounded"] is False
    assert res["answer"] == "Information not found in documentation."
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


def test_chat_answers_codebase_overview(tmp_path: Path):
    """High-level 'explain the codebase' questions are grounded in the repo's
    top-level structure rather than rejected for naming no specific entity."""
    db = SessionLocal()
    repo = _seed_repo_with_docs(db, tmp_path)
    # Add a module entity with a docstring — the overview's primary signal.
    module = CodeEntity(
        repository_id=repo.id,
        source_file_id=0,
        kind="module",
        name="auth",
        qualified_name="auth",
        docstring="Authentication helpers for logging users in and out.",
        relative_path="auth.py",
    )
    db.add(module)
    db.commit()

    res = asyncio.run(
        RAGService(db).chat(repository_id=repo.id, message="can you explain the codebase?")
    )
    assert res["grounded"] is True
    assert res["answer"] != "Information not found in documentation."
    assert any(s["qualified_name"] == "auth" for s in res["sources"])
    db.close()
