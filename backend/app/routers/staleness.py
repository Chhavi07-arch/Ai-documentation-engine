"""Staleness routes: list flags, draft updates, resolve flags."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.common import Message
from app.schemas.staleness import (
    DraftUpdateRequest,
    DraftUpdateResponse,
    ResolveFlagRequest,
    StalenessFlagRead,
)
from app.services.rag_service import RAGService
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
    summary="Resolve a flag, optionally applying the reviewed draft",
)
async def resolve_flag(
    flag_id: int,
    payload: ResolveFlagRequest = ResolveFlagRequest(),
    db: Session = Depends(get_db),
) -> Message:
    """Resolve a staleness flag.

    If ``apply_markdown`` is supplied (a human-reviewed draft), it is saved as
    the entity's documentation and the chat index is refreshed before the flag
    is resolved — so accepting a fix actually updates the docs, with a human
    still in the loop.
    """
    service = StalenessService(db)
    applied = False
    if payload.apply_markdown:
        repo_id = service.apply_documentation(flag_id, payload.apply_markdown)
        if repo_id is not None:
            await RAGService(db).index_repository(repo_id)
            applied = True
    service.resolve_flag(flag_id)
    return Message(
        message="Documentation updated and flag resolved." if applied else "Flag resolved."
    )
