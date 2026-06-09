"""Staleness flag ORM model — documentation impacted by a code change."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StalenessFlag(Base):
    """A record that a code change may have made documentation stale."""

    __tablename__ = "staleness_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("code_entities.id", ondelete="SET NULL"), default=None, index=True
    )

    qualified_name: Mapped[str] = mapped_column(String(1024), index=True)
    change_type: Mapped[str] = mapped_column(String(32))  # ChangeType
    severity: Mapped[str] = mapped_column(String(32), index=True)  # StalenessSeverity
    reason: Mapped[str] = mapped_column(Text, default="")

    # Captured code for drafting an updated doc later.
    old_source: Mapped[str | None] = mapped_column(Text, default=None)
    new_source: Mapped[str | None] = mapped_column(Text, default=None)
    # The documentation that existed when the change was detected (for diffing).
    original_doc_markdown: Mapped[str | None] = mapped_column(Text, default=None)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
