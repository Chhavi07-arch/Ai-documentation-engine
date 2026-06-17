"""Database engine, session factory, and FastAPI dependency.

Uses SQLAlchemy 2.0 with SQLite by default. The ``get_db`` dependency yields a
session per request and guarantees it is closed afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# Managed Postgres providers (e.g. Render) hand out ``postgres://`` URLs, but
# SQLAlchemy 2.0 requires the ``postgresql://`` scheme. Normalize so the same
# code runs on SQLite locally and Postgres in production.
_DB_URL = settings.database_url
if _DB_URL.startswith("postgres://"):
    _DB_URL = "postgresql://" + _DB_URL[len("postgres://"):]

_IS_SQLITE = _DB_URL.startswith("sqlite")

# `check_same_thread` is required for SQLite when used with FastAPI's
# threadpool. For other databases it is simply ignored.
_connect_args = {"check_same_thread": False} if _IS_SQLITE else {}

engine = create_engine(
    _DB_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


if _IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        """Tune SQLite for concurrent API access.

        WAL lets readers (the polling frontend) proceed while a writer (e.g. a
        long doc-generation run) holds the database, and ``busy_timeout`` makes
        writers wait briefly for the lock instead of failing immediately with
        "database is locked".
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")  # wait up to 10s for locks
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def init_db() -> None:
    """Create all tables. Imported models register themselves on ``Base``."""
    # Import models so their tables are registered on the metadata before
    # ``create_all`` runs. Local import avoids a circular dependency.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
