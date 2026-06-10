"""Schemas for change detection."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import ChangeType, StalenessSeverity


class EntityChange(BaseModel):
    """A single detected change between two snapshots."""

    qualified_name: str
    kind: str
    change_type: ChangeType
    severity: StalenessSeverity | None = None
    reason: str = ""
    renamed_from: str | None = None


class DetectChangesRequest(BaseModel):
    """Request to detect changes for a repository.

    Re-clones / re-parses the repository and compares it against the most
    recent snapshot. The first run simply establishes a baseline snapshot.
    """

    repository_id: int


class DetectChangesResponse(BaseModel):
    """Result of a change-detection run."""

    repository_id: int
    baseline_created: bool
    snapshot_id: int
    changes: list[EntityChange]
    flags_created: int
