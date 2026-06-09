"""Repository and source-file ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import RepositoryStatus


class Repository(Base):
    """A GitHub repository that has been ingested into the engine."""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(512))  # e.g. "owner/repo"
    url: Mapped[str] = mapped_column(String(1024))
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    local_path: Mapped[str] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(
        String(32), default=RepositoryStatus.PENDING.value, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    # Aggregated counters kept up to date by the ingestion pipeline.
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    documented_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    files: Mapped[list["SourceFile"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    entities: Mapped[list["CodeEntity"]] = relationship(  # type: ignore[name-defined]
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class SourceFile(Base):
    """A single Python source file discovered inside a repository."""

    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    # Path relative to the repository root, e.g. "app/services/auth.py".
    relative_path: Mapped[str] = mapped_column(String(1024), index=True)
    module_path: Mapped[str] = mapped_column(String(1024))  # dotted module name
    content_hash: Mapped[str] = mapped_column(String(64))  # sha256 of file body
    line_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    repository: Mapped["Repository"] = relationship(back_populates="files")
    entities: Mapped[list["CodeEntity"]] = relationship(  # type: ignore[name-defined]
        back_populates="source_file",
        cascade="all, delete-orphan",
    )
