"""Tests for the automatic change-detection scheduler.

The async loop is thin; the real work is one synchronous sweep, ``_run_cycle``,
which we can call directly. It must detect changes for READY repositories and
create staleness flags with no manual ``/detect-changes`` call.
"""

from pathlib import Path

from app.core.database import SessionLocal
from app.models import Repository, StalenessFlag
from app.models.enums import RepositoryStatus, StalenessSeverity
from app.services.ingestion_service import IngestionService
from app.services.scheduler import AutoDetectScheduler


def _make_ready_repo(db, path: Path) -> Repository:
    repo = Repository(
        name="auto", full_name="auto/auto", url="https://github.com/auto/auto",
        local_path=str(path), status=RepositoryStatus.PENDING.value,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def test_run_cycle_auto_detects_signature_change(tmp_path: Path):
    db = SessionLocal()
    repo = _make_ready_repo(db, tmp_path)
    (tmp_path / "auth.py").write_text(
        "def login(email, password):\n    return True\n", encoding="utf-8"
    )
    IngestionService(db).ingest_local(repo)  # baseline + status READY

    flags_before = (
        db.query(StalenessFlag).filter(StalenessFlag.repository_id == repo.id).count()
    )
    assert flags_before == 0

    # Change the signature on disk — but do NOT call detect-changes ourselves.
    (tmp_path / "auth.py").write_text(
        "def login(email, password, otp):\n    return True\n", encoding="utf-8"
    )

    # The scheduler's sweep is what should notice the change.
    AutoDetectScheduler()._run_cycle()

    flags = (
        db.query(StalenessFlag).filter(StalenessFlag.repository_id == repo.id).all()
    )
    login = [f for f in flags if f.qualified_name.endswith("auth.login")]
    assert login, "auto-detect cycle should have flagged auth.login"
    assert login[0].severity == StalenessSeverity.BROKEN.value
    db.close()


def test_run_cycle_skips_non_ready_repos(tmp_path: Path):
    """A repo that never reached READY must not be swept."""
    db = SessionLocal()
    repo = _make_ready_repo(db, tmp_path)
    repo.status = RepositoryStatus.FAILED.value  # not READY
    db.commit()

    # Should be a no-op (no working copy parsed, no flags), and never raise.
    AutoDetectScheduler()._run_cycle()

    flags = (
        db.query(StalenessFlag).filter(StalenessFlag.repository_id == repo.id).count()
    )
    assert flags == 0
    db.close()
