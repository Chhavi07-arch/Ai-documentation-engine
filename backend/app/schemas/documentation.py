"""Schemas for documentation reads and generation requests."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.entity import EntityRead


class DocumentationRead(BaseModel):
    """Generated documentation for an entity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    entity_id: int
    content_markdown: str
    summary: str | None = None
    version: int
    generator: str
    created_at: datetime
    updated_at: datetime
    entity: EntityRead | None = None


class GenerateDocsRequest(BaseModel):
    """Request to (re)generate documentation for a repository.

    If ``entity_ids`` is provided, only those entities are regenerated;
    otherwise documentation is generated for every entity missing docs
    (or all entities when ``force`` is true).
    """

    repository_id: int
    entity_ids: list[int] | None = None
    force: bool = False


class GenerateDocsResponse(BaseModel):
    """Result of a documentation generation run."""

    repository_id: int
    generated: int
    skipped: int
    failed: int
    generator: str
