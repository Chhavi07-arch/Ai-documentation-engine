"""GitHub webhook endpoint — commit-hook-driven change detection.

A ``push`` event for a repository that has already been ingested automatically
re-runs structural change detection, so documentation staleness is surfaced as
the code evolves without anyone clicking "Detect changes". This realizes the
assignment's "monitor the repository for code changes via commit hooks" path.

Signature verification (``X-Hub-Signature-256`` HMAC) is enforced whenever
``GITHUB_WEBHOOK_SECRET`` is configured; with no secret set the endpoint accepts
unsigned payloads so it is trivial to demo locally.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, BackgroundTasks, Header, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models import Repository
from app.services.change_detection_service import ChangeDetectionService
from app.services.ingestion_service import IngestionService
from app.utils.git_utils import update_local_clone

logger = get_logger("docengine.api.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _error(code: str, message: str, http_status: int) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"error": {"code": code, "message": message}})


def _verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    """Constant-time HMAC-SHA256 check; accept when no secret is configured."""
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _detect_in_background(repository_id: int, auto_pull: bool) -> None:
    """Run detection (optionally pulling latest first) on its own DB session."""
    db = SessionLocal()
    try:
        if auto_pull:
            repo = db.get(Repository, repository_id)
            if repo is not None:
                local_path = IngestionService(db).local_working_path(repo)
                try:
                    update_local_clone(local_path)
                except Exception as exc:  # pragma: no cover - network dependent
                    logger.warning("Auto-pull failed for repo %d: %s", repository_id, exc)
        ChangeDetectionService(db).detect_changes(repository_id)
    except Exception as exc:
        logger.warning("Webhook detection failed for repo %d: %s", repository_id, exc)
    finally:
        db.close()


@router.post(
    "/github",
    status_code=status.HTTP_202_ACCEPTED,
    summary="GitHub push webhook → auto-detect stale documentation",
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    """Trigger change detection for the repository named in a GitHub push event."""
    body = await request.body()

    if not _verify_signature(settings.github_webhook_secret, body, x_hub_signature_256):
        return _error("unauthorized", "Invalid or missing webhook signature.", 401)

    if x_github_event == "ping":
        return JSONResponse(status_code=200, content={"status": "pong"})

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return _error("bad_payload", "Webhook body is not valid JSON.", 400)

    full_name = (payload.get("repository") or {}).get("full_name")
    if not full_name:
        return _error("bad_payload", "Payload is missing repository.full_name.", 400)

    db = SessionLocal()
    try:
        repo_ids = [
            r.id
            for r in db.scalars(
                select(Repository).where(func.lower(Repository.full_name) == full_name.lower())
            ).all()
        ]
    finally:
        db.close()

    if not repo_ids:
        return _error("not_found", f"No ingested repository named '{full_name}'.", 404)

    for rid in repo_ids:
        background_tasks.add_task(_detect_in_background, rid, settings.webhook_auto_pull)

    logger.info("Webhook (%s) queued detection for %s → repos %s", x_github_event, full_name, repo_ids)
    return {
        "event": x_github_event or "push",
        "repository": full_name,
        "repositories_queued": repo_ids,
        "auto_pull": settings.webhook_auto_pull,
    }
