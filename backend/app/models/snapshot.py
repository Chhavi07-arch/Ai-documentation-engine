"""Snapshot ORM models — point-in-time captures of repository structure.

A :class:`Snapshot` records the structural fingerprint of every entity at a
moment in time. Comparing two snapshots powers AST-based change detection
without re-parsing historical code.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Snapshot(Base):
    """A structural snapshot of a repository at a point in time."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64), default=None)
    label: Mapped[str] = mapped_column(String(255), default="snapshot")
    entity_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entities: Mapped[list["EntitySnapshot"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class EntitySnapshot(Base):
    """The captured structural state of one entity within a snapshot."""

    __tablename__ = "entity_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("snapshots.id", ondelete="CASCADE"), index=True
    )

    qualified_name: Mapped[str] = mapped_column(String(1024), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    signature: Mapped[str] = mapped_column(Text, default="")
    return_type: Mapped[str | None] = mapped_column(String(512), default=None)
    parameters_json: Mapped[str] = mapped_column(Text, default="[]")
    docstring: Mapped[str | None] = mapped_column(Text, default=None)
    source_code: Mapped[str] = mapped_column(Text, default="")

    structure_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    body_hash: Mapped[str] = mapped_column(String(64), default="")

    snapshot: Mapped["Snapshot"] = relationship(back_populates="entities")
