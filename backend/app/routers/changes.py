"""Change detection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.changes import DetectChangesRequest, DetectChangesResponse, EntityChange
from app.services.change_detection_service import ChangeDetectionService

router = APIRouter(tags=["changes"])


@router.post(
    "/detect-changes",
    response_model=DetectChangesResponse,
    summary="Detect code changes and flag stale documentation",
)
def detect_changes(
    payload: DetectChangesRequest, db: Session = Depends(get_db)
) -> DetectChangesResponse:
    """Re-parse the repository and compare it to the latest snapshot.

    The first run establishes a baseline; subsequent runs report structural
    changes and create staleness flags.
    """
    result = ChangeDetectionService(db).detect_changes(payload.repository_id)
    return DetectChangesResponse(
        repository_id=result["repository_id"],
        baseline_created=result["baseline_created"],
        snapshot_id=result["snapshot_id"],
        changes=[EntityChange(**c) for c in result["changes"]],
        flags_created=result["flags_created"],
    )
