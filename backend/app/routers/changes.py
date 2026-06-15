"""Change detection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.changes import DetectChangesRequest, DetectChangesResponse, EntityChange
from app.services.change_detection_service import ChangeDetectionService
from app.services.ingestion_service import IngestionService

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


@router.post(
    "/sync-and-detect",
    response_model=DetectChangesResponse,
    summary="Pull latest commits from GitHub, then detect changes",
)
def sync_and_detect(
    payload: DetectChangesRequest, db: Session = Depends(get_db)
) -> DetectChangesResponse:
    """Incrementally fetch the repository's latest commits, then detect changes.

    This is the manual counterpart to the GitHub webhook: it updates the local
    clone in place (no re-clone) and re-runs detection, so you can pick up
    pushed changes — including README/doc edits — without configuring a webhook.
    """
    IngestionService(db).sync_from_remote(payload.repository_id)
    result = ChangeDetectionService(db).detect_changes(payload.repository_id)
    return DetectChangesResponse(
        repository_id=result["repository_id"],
        baseline_created=result["baseline_created"],
        snapshot_id=result["snapshot_id"],
        changes=[EntityChange(**c) for c in result["changes"]],
        flags_created=result["flags_created"],
    )
