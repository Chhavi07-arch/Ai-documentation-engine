"""Repository routes: ingest, list, detail, files, entities."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.logging import get_logger
from app.routers.converters import entity_to_detail, entity_to_read
from app.schemas.entity import EntityDetail, EntityRead
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryDetail,
    RepositoryRead,
    SourceFileRead,
)
from app.services.ingestion_service import IngestionService
from app.services.repository_service import RepositoryService

logger = get_logger("docengine.api.repositories")
router = APIRouter(prefix="/repositories", tags=["repositories"])


def _ingest_in_background(repository_id: int) -> None:
    """Run ingestion with its own DB session (background tasks outlive the request)."""
    db = SessionLocal()
    try:
        IngestionService(db).ingest(repository_id)
    except Exception as exc:  # status is persisted as FAILED inside the service
        logger.warning("Background ingestion failed for repo %d: %s", repository_id, exc)
    finally:
        db.close()


@router.post(
    "/ingest",
    response_model=RepositoryRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a GitHub repository",
)
def ingest_repository(
    payload: RepositoryCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> RepositoryRead:
    """Register a repository and start cloning + parsing in the background.

    Returns immediately with status ``pending``; poll ``GET /repositories/{id}``
    to follow progress through to ``ready``.
    """
    repo = IngestionService(db).create_repository(payload.url)
    background_tasks.add_task(_ingest_in_background, repo.id)
    return RepositoryRead.model_validate(repo)


@router.get("", response_model=list[RepositoryRead], summary="List repositories")
def list_repositories(db: Session = Depends(get_db)) -> list[RepositoryRead]:
    repos = RepositoryService(db).list_repositories()
    return [RepositoryRead.model_validate(r) for r in repos]


@router.get("/{repository_id}", response_model=RepositoryDetail, summary="Repository detail")
def get_repository(repository_id: int, db: Session = Depends(get_db)) -> RepositoryDetail:
    service = RepositoryService(db)
    repo = service.get_repository(repository_id)
    detail = RepositoryDetail.model_validate(repo)
    detail.file_tree = service.build_file_tree(repository_id)
    return detail


@router.get(
    "/{repository_id}/files",
    response_model=list[SourceFileRead],
    summary="List source files",
)
def list_files(repository_id: int, db: Session = Depends(get_db)) -> list[SourceFileRead]:
    files = RepositoryService(db).list_files(repository_id)
    return [SourceFileRead.model_validate(f) for f in files]


@router.get(
    "/{repository_id}/entities",
    response_model=list[EntityRead],
    summary="List code entities",
)
def list_entities(
    repository_id: int,
    file_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EntityRead]:
    entities = RepositoryService(db).list_entities(repository_id, file_id=file_id)
    return [entity_to_read(e) for e in entities]


@router.get(
    "/entities/{entity_id}",
    response_model=EntityDetail,
    summary="Entity detail (full parsed structure)",
)
def get_entity(entity_id: int, db: Session = Depends(get_db)) -> EntityDetail:
    entity = RepositoryService(db).get_entity(entity_id)
    return entity_to_detail(entity)
