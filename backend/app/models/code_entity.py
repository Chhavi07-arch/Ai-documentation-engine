"""Code entity ORM model — a parsed function, class, method, or module."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import EntityKind


class CodeEntity(Base):
    """A structured representation of a single parsed code construct.

    Rich structural fields (parameters, decorators, imports) are stored as JSON
    strings to keep the schema simple while remaining queryable in Python.
    """

    __tablename__ = "code_entities"
    __table_args__ = (
        UniqueConstraint("repository_id", "qualified_name", name="uq_entity_qname"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[int] = mapped_column(
        ForeignKey("source_files.id", ondelete="CASCADE"), index=True
    )

    kind: Mapped[str] = mapped_column(String(16), index=True)  # EntityKind
    name: Mapped[str] = mapped_column(String(255), index=True)
    # Fully qualified, e.g. "app.services.auth.AuthService.login".
    qualified_name: Mapped[str] = mapped_column(String(1024), index=True)
    parent_name: Mapped[str | None] = mapped_column(String(1024), default=None)

    signature: Mapped[str] = mapped_column(Text, default="")
    return_type: Mapped[str | None] = mapped_column(String(512), default=None)
    docstring: Mapped[str | None] = mapped_column(Text, default=None)
    source_code: Mapped[str] = mapped_column(Text, default="")
    relative_path: Mapped[str] = mapped_column(String(1024), default="")

    is_async: Mapped[bool] = mapped_column(default=False)
    line_start: Mapped[int] = mapped_column(Integer, default=0)
    line_end: Mapped[int] = mapped_column(Integer, default=0)

    # JSON-encoded structural details (see schemas for shape).
    parameters_json: Mapped[str] = mapped_column(Text, default="[]")
    decorators_json: Mapped[str] = mapped_column(Text, default="[]")
    imports_json: Mapped[str] = mapped_column(Text, default="[]")

    # Hash of the structural signature, used for fast change detection.
    structure_hash: Mapped[str] = mapped_column(String(64), default="", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    repository: Mapped["Repository"] = relationship(  # type: ignore[name-defined]
        back_populates="entities"
    )
    source_file: Mapped["SourceFile"] = relationship(  # type: ignore[name-defined]
        back_populates="entities"
    )
    documentation: Mapped["Documentation | None"] = relationship(  # type: ignore[name-defined]
        back_populates="entity",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def is_documentable(self) -> bool:
        """Modules, classes, functions and methods all get documentation."""
        return self.kind in {k.value for k in EntityKind}
