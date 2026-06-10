"""Schemas for staleness flags and documentation update drafting."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ChangeType, StalenessSeverity


class StalenessFlagRead(BaseModel):
    """A documentation staleness flag."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    entity_id: int | None = None
    qualified_name: str
    change_type: ChangeType
    severity: StalenessSeverity
    reason: str
    resolved: bool
    created_at: datetime


class DraftUpdateRequest(BaseModel):
    """Request to draft an updated documentation version for a stale entity."""

    flag_id: int


class DraftUpdateResponse(BaseModel):
    """A drafted documentation update with a unified diff against the original."""

    flag_id: int
    entity_id: int | None
    qualified_name: str
    original_markdown: str
    drafted_markdown: str
    unified_diff: str
    generator: str
