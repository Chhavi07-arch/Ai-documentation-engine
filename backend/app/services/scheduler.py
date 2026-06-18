"""Background scheduler for automatic change detection.

When ``AUTO_DETECT_ENABLED`` is set, this runs a recurring task that re-detects
stale documentation for every READY repository on a fixed interval — so flags
appear on their own, without anyone clicking "Detect changes". It is the polling
counterpart to the event-driven GitHub webhook.

Design notes:
* The loop lives on the FastAPI event loop but does its blocking work (DB +
  parsing + optional git fetch) inside ``asyncio.to_thread`` so it never stalls
  request handling.
* Cycles never overlap: each cycle fully completes before the next interval is
  counted, so a slow sweep simply delays the next one rather than stacking up.
* Every repository is processed independently — one failing repo is logged and
  skipped, never aborting the rest of the cycle.
"""

from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models import Repository
from app.models.enums import RepositoryStatus
from app.services.change_detection_service import ChangeDetectionService
from app.services.ingestion_service import IngestionService

logger = get_logger("docengine.scheduler")

# Never poll faster than this, regardless of configuration.
_MIN_INTERVAL_SECONDS = 10


class AutoDetectScheduler:
    """Owns the recurring auto-detection task and its lifecycle."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the background loop if auto-detection is enabled."""
        if not settings.auto_detect_enabled:
            logger.info(
                "Auto-detect disabled (set AUTO_DETECT_ENABLED=true to enable)."
            )
            return
        if self.running:
            return
        interval = max(_MIN_INTERVAL_SECONDS, settings.auto_detect_interval_seconds)
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop(interval))
        logger.info(
            "Auto-detect ENABLED — every %ss (sync_remote=%s).",
            interval, settings.auto_detect_sync_remote,
        )

    async def stop(self) -> None:
        """Signal the loop to stop and wait for it to finish."""
        if not self._task:
            return
        if self._stop is not None:
            self._stop.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            logger.info("Auto-detect stopped.")

    async def _loop(self, interval: int) -> None:
        assert self._stop is not None
        while not self._stop.is_set():
            # Sleep for `interval`, but wake immediately if asked to stop.
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break  # stop was set during the wait
            except asyncio.TimeoutError:
                pass  # interval elapsed → run a cycle
            try:
                await asyncio.to_thread(self._run_cycle)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Auto-detect cycle error: %s", exc)

    def _run_cycle(self) -> None:
        """One sweep over all READY repositories (runs in a worker thread)."""
        db = SessionLocal()
        try:
            repos = (
                db.query(Repository)
                .filter(Repository.status == RepositoryStatus.READY.value)
                .all()
            )
            if not repos:
                return
            total_flags = 0
            for repo in repos:
                try:
                    if settings.auto_detect_sync_remote:
                        IngestionService(db).sync_from_remote(repo.id)
                    result = ChangeDetectionService(db).detect_changes(repo.id)
                    total_flags += int(result.get("flags_created") or 0)
                except Exception as exc:
                    logger.warning(
                        "Auto-detect failed for repo %s (%s): %s",
                        repo.id, repo.full_name, exc,
                    )
                    db.rollback()
            if total_flags:
                logger.info(
                    "Auto-detect cycle: %d new flag(s) across %d repo(s).",
                    total_flags, len(repos),
                )
        finally:
            db.close()


# Single app-wide instance, started/stopped by the FastAPI lifespan.
auto_detect_scheduler = AutoDetectScheduler()
