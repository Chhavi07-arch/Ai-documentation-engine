"""GitHub webhook routes.

Receives push events from GitHub and — without re-cloning — incrementally
fetches the new commits into the existing local clone, then runs change
detection so stale documentation is flagged automatically.

Security: every request is authenticated by verifying the ``X-Hub-Signature-256``
HMAC that GitHub computes over the raw body using a shared secret
(``GITHUB_WEBHOOK_SECRET``). The endpoint is disabled (503) when no secret is
configured, so changes can never be triggered by an unauthenticated caller.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import Repository
from app.services.change_detection_service import ChangeDetectionService
from app.services.ingestion_service import IngestionService

router = APIRouter(tags=["github"])
logger = get_logger("docengine.github")


def _verify_signature(raw: bytes, signature: str | None) -> None:
    """Reject the request unless the HMAC signature matches the shared secret."""
    secret = settings.github_webhook_secret.strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook is not configured. Set GITHUB_WEBHOOK_SECRET.",
        )
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing webhook signature.")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")


@router.post("/github/webhook", summary="GitHub push webhook")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Handle a GitHub ``push`` event: fetch latest, then detect changes.

    Returns a small summary. Pings and non-push events are acknowledged and
    ignored; pushes to a non-default branch or to an untracked repository are
    acknowledged without doing any work.
    """
    raw = await request.body()
    _verify_signature(raw, x_hub_signature_256)

    if x_github_event == "ping":
        return {"ok": True, "event": "ping"}
    if x_github_event != "push":
        return {"ok": True, "ignored": f"event '{x_github_event}' not handled"}

    payload = await request.json()
    full_name = (payload.get("repository") or {}).get("full_name")
    ref = payload.get("ref", "")  # e.g. "refs/heads/main"
    pushed_branch = ref.rsplit("/", 1)[-1] if ref else ""

    if not full_name:
        raise HTTPException(status_code=400, detail="Malformed push payload.")

    repo = db.scalars(
        select(Repository).where(Repository.full_name == full_name)
    ).first()
    if repo is None:
        logger.info("Webhook for untracked repo %s — ignoring.", full_name)
        return {"ok": True, "ignored": f"repository '{full_name}' is not tracked"}

    if pushed_branch and repo.default_branch and pushed_branch != repo.default_branch:
        return {
            "ok": True,
            "ignored": f"branch '{pushed_branch}' is not the default branch",
        }

    new_sha = IngestionService(db).sync_from_remote(repo.id)
    result = ChangeDetectionService(db).detect_changes(repo.id)
    logger.info(
        "Webhook synced %s to %s — %d changes, %d flags.",
        full_name, (new_sha or "?")[:8], len(result["changes"]), result["flags_created"],
    )
    return {
        "ok": True,
        "repository_id": repo.id,
        "commit": new_sha,
        "baseline_created": result["baseline_created"],
        "changes": len(result["changes"]),
        "flags_created": result["flags_created"],
    }
