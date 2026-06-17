"""System routes: health check, AI configuration status, dashboard stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import CodeEntity, Repository, StalenessFlag
from app.models.enums import RepositoryStatus
from app.services.ai_service import ai_service

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    version: str


class ConfigResponse(BaseModel):
    ai_enabled: bool
    model: str
    embedding_mode: str  # "openrouter" when a key is set, else "local"
    database: str  # "postgresql" (persistent) or "sqlite" (ephemeral)


class DashboardStats(BaseModel):
    repositories: int
    ready_repositories: int
    entities: int
    documented_entities: int
    open_flags: int
    documentation_coverage: float  # 0..1


@router.get("/health", response_model=HealthResponse, summary="Health check")
def health() -> HealthResponse:
    from app import __version__

    return HealthResponse(status="ok", version=__version__)


@router.get("/config", response_model=ConfigResponse, summary="AI configuration status")
def config() -> ConfigResponse:
    from app.core.database import engine

    use_remote_embeddings = settings.use_openrouter_embeddings and ai_service.enabled
    return ConfigResponse(
        ai_enabled=ai_service.enabled,
        model=settings.openrouter_model,
        embedding_mode="openrouter" if use_remote_embeddings else "local",
        database=engine.dialect.name,
    )


@router.get("/stats", response_model=DashboardStats, summary="Dashboard statistics")
def stats(db: Session = Depends(get_db)) -> DashboardStats:
    repositories = db.scalar(select(func.count()).select_from(Repository)) or 0
    ready = (
        db.scalar(
            select(func.count())
            .select_from(Repository)
            .where(Repository.status == RepositoryStatus.READY.value)
        )
        or 0
    )
    entities = db.scalar(select(func.count()).select_from(CodeEntity)) or 0
    documented = db.scalar(select(func.sum(Repository.documented_count))) or 0
    open_flags = (
        db.scalar(
            select(func.count())
            .select_from(StalenessFlag)
            .where(StalenessFlag.resolved.is_(False))
        )
        or 0
    )

    coverage = round(documented / entities, 3) if entities else 0.0
    return DashboardStats(
        repositories=repositories,
        ready_repositories=ready,
        entities=entities,
        documented_entities=documented,
        open_flags=open_flags,
        documentation_coverage=coverage,
    )
