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
    provider: str  # "anthropic" or "openrouter"
    model: str
    embedding_mode: str  # "openrouter" when a key is set, else "local"
    database: str  # "postgresql" (persistent) or "sqlite" (ephemeral)
    auto_detect_enabled: bool  # background polling for stale docs is active
    auto_detect_interval_seconds: int  # how often the sweep runs
    auto_detect_sync_remote: bool  # sweep also git-fetches the latest from GitHub


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

    use_remote_embeddings = (
        settings.use_openrouter_embeddings
        and ai_service.enabled
        and settings.resolved_provider == "openrouter"
    )
    return ConfigResponse(
        ai_enabled=ai_service.enabled,
        provider=settings.resolved_provider,
        model=ai_service.model,
        embedding_mode="openrouter" if use_remote_embeddings else "local",
        database=engine.dialect.name,
        auto_detect_enabled=settings.auto_detect_enabled,
        auto_detect_interval_seconds=settings.auto_detect_interval_seconds,
        auto_detect_sync_remote=settings.auto_detect_sync_remote,
    )


@router.get("/diagnostics/ai", summary="Live AI connectivity check")
async def diagnostics_ai() -> dict:
    """Make a tiny real AI call and report success or the exact upstream error.

    Useful when docs/chat unexpectedly fall back: tells you whether the key,
    credits, or model is the problem.
    """
    return await ai_service.diagnose()


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
