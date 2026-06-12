"""Staleness routes: list flags, draft updates, resolve flags."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.common import Message
from app.schemas.staleness import (
    DraftUpdateRequest,
    DraftUpdateResponse,
    StalenessFlagRead,
)
from app.services.staleness_service import StalenessService

router = APIRouter(tags=["staleness"])


@router.get(
    "/stale-docs",
    response_model=list[StalenessFlagRead],
    summary="List documentation staleness flags",
)
def list_stale_docs(
    repository_id: int | None = Query(default=None),
    include_resolved: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[StalenessFlagRead]:
    flags = StalenessService(db).list_flags(
        repository_id=repository_id, include_resolved=include_resolved
    )
    return [StalenessFlagRead.model_validate(f) for f in flags]


@router.post(
    "/draft-update",
    response_model=DraftUpdateResponse,
    summary="Draft an updated documentation version for a stale entity",
)
async def draft_update(
    payload: DraftUpdateRequest, db: Session = Depends(get_db)
) -> DraftUpdateResponse:
    result = await StalenessService(db).draft_update(payload.flag_id)
    return DraftUpdateResponse(**result)


@router.post(
    "/stale-docs/{flag_id}/resolve",
    response_model=Message,
    summary="Mark a staleness flag as resolved",
)
def resolve_flag(flag_id: int, db: Session = Depends(get_db)) -> Message:
    StalenessService(db).resolve_flag(flag_id)
    return Message(message="Flag resolved.")
