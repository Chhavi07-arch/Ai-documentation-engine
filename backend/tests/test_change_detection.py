"""Change-detection tests against a local working tree.

These verify the core fix: detection parses the CURRENT local files in place
(picking up edits and new files) and never re-clones or reverts the working
tree. Each test uses a throwaway directory as the repository's working copy.
"""

from pathlib import Path

from app.core.database import SessionLocal
from app.models import CodeEntity, Repository, StalenessFlag
from app.models.enums import ChangeType, RepositoryStatus, StalenessSeverity
from app.services.change_detection_service import ChangeDetectionService
from app.services.ingestion_service import IngestionService
from sqlalchemy import select


def _make_repo(db, path: Path) -> Repository:
    repo = Repository(
        name="t",
        full_name="t/t",
        url="https://github.com/t/t",
        local_path=str(path),
        status=RepositoryStatus.PENDING.value,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def _baseline(db, repo: Repository) -> None:
    """Index the current local files and create the baseline snapshot."""
    IngestionService(db).ingest_local(repo)


def _changes_for(result: dict, suffix: str) -> list[dict]:
    return [c for c in result["changes"] if c["qualified_name"].endswith(suffix)]


def test_signature_change_is_detected_as_broken(tmp_path: Path):
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    (tmp_path / "auth.py").write_text(
        "def login(email, password):\n    return True\n", encoding="utf-8"
    )
    _baseline(db, repo)

    # The exact case from the bug report: add an `otp` parameter.
    (tmp_path / "auth.py").write_text(
        "def login(email, password, otp):\n    return True\n", encoding="utf-8"
    )
    result = ChangeDetectionService(db).detect_changes(repo.id)

    assert result["baseline_created"] is False
    login = _changes_for(result, "auth.login")
    assert login, "expected a change for auth.login"
    assert login[0]["change_type"] in (
        ChangeType.PARAMETERS_CHANGED.value,
        ChangeType.SIGNATURE_CHANGED.value,
    )
    assert login[0]["severity"] == StalenessSeverity.BROKEN.value

    # A staleness flag was persisted with BROKEN severity.
    flags = list(
        db.scalars(select(StalenessFlag).where(StalenessFlag.repository_id == repo.id)).all()
    )
    assert any(f.severity == StalenessSeverity.BROKEN.value for f in flags)
    db.close()


def test_body_modification_is_potentially_outdated(tmp_path: Path):
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    (tmp_path / "calc.py").write_text(
        "def total():\n    return 1\n", encoding="utf-8"
    )
    _baseline(db, repo)

    (tmp_path / "calc.py").write_text(
        "def total():\n    return 2\n", encoding="utf-8"
    )
    result = ChangeDetectionService(db).detect_changes(repo.id)

    total = _changes_for(result, "calc.total")
    assert total, "expected a change for calc.total"
    assert total[0]["change_type"] == ChangeType.BODY_MODIFIED.value
    assert total[0]["severity"] == StalenessSeverity.POTENTIALLY_OUTDATED.value
    db.close()


def test_new_file_and_entities_are_detected(tmp_path: Path):
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    (tmp_path / "core.py").write_text("def existing():\n    pass\n", encoding="utf-8")
    _baseline(db, repo)

    # Add a brand new file with a new function (recursive scan must find it).
    (tmp_path / "feature.py").write_text(
        "def brand_new(x):\n    return x\n", encoding="utf-8"
    )
    result = ChangeDetectionService(db).detect_changes(repo.id)

    qnames = {c["qualified_name"] for c in result["changes"]}
    assert "feature" in qnames, "new module should be detected"
    assert "feature.brand_new" in qnames, "new function should be detected"
    for c in result["changes"]:
        if c["qualified_name"] in {"feature", "feature.brand_new"}:
            assert c["change_type"] == ChangeType.ADDED.value
    db.close()


def test_new_entity_in_existing_file_is_detected(tmp_path: Path):
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    (tmp_path / "svc.py").write_text("def a():\n    pass\n", encoding="utf-8")
    _baseline(db, repo)

    # Append a new function to the existing file.
    (tmp_path / "svc.py").write_text(
        "def a():\n    pass\n\n\ndef b():\n    pass\n", encoding="utf-8"
    )
    result = ChangeDetectionService(db).detect_changes(repo.id)

    added = _changes_for(result, "svc.b")
    assert added, "expected the new function svc.b to be detected"
    assert added[0]["change_type"] == ChangeType.ADDED.value
    db.close()


def test_detection_is_cumulative_and_stable(tmp_path: Path):
    """Two edits must both be reported, and re-detecting must be idempotent."""
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    return 1\n", encoding="utf-8")
    _baseline(db, repo)

    svc = ChangeDetectionService(db)

    # Edit the first file, detect.
    (tmp_path / "a.py").write_text("def a():\n    return 2\n", encoding="utf-8")
    first = svc.detect_changes(repo.id)
    assert len(_changes_for(first, "a.a")) == 1

    # Edit the second file and detect again — BOTH function changes must show
    # (the baseline did not advance and "consume" the first edit).
    (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    second = svc.detect_changes(repo.id)
    assert len(_changes_for(second, "a.a")) == 1
    assert len(_changes_for(second, "b.b")) == 1
    assert second["flags_created"] == len(second["changes"])

    # Detecting again with no further edits yields the same set (stable, no dupes).
    third = svc.detect_changes(repo.id)
    assert len(third["changes"]) == len(second["changes"])
    assert third["flags_created"] == second["flags_created"]
    db.close()


def test_resolved_flag_survives_redetection(tmp_path: Path):
    """Re-running detection must not silently reopen a flag the user resolved."""
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    (tmp_path / "c.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _baseline(db, repo)

    (tmp_path / "c.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    svc = ChangeDetectionService(db)
    svc.detect_changes(repo.id)

    flag = db.scalars(
        select(StalenessFlag).where(StalenessFlag.qualified_name == "c.f")
    ).first()
    assert flag is not None
    flag.resolved = True
    db.commit()

    # Re-detect with the same edit still present — the flag must stay resolved.
    svc.detect_changes(repo.id)
    flags = list(
        db.scalars(select(StalenessFlag).where(StalenessFlag.qualified_name == "c.f")).all()
    )
    assert flags and all(f.resolved for f in flags)
    db.close()


def test_property_getter_is_preferred_over_setter(tmp_path: Path):
    """A @property getter must survive ingestion dedup, not be overwritten by its
    setter — so docs describe the public read contract, not a write-only setter."""
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    (tmp_path / "p.py").write_text(
        "class C:\n"
        "    @property\n"
        "    def value(self):\n"
        '        """Read the value."""\n'
        "        return self._v\n"
        "    @value.setter\n"
        "    def value(self, v):\n"
        "        self._v = v\n",
        encoding="utf-8",
    )
    IngestionService(db).ingest_local(repo)

    entity = db.scalars(
        select(CodeEntity).where(
            CodeEntity.repository_id == repo.id,
            CodeEntity.qualified_name == "p.C.value",
        )
    ).first()
    assert entity is not None
    assert "property" in (entity.decorators_json or "")
    # The getter takes only `self` — the setter's `v` parameter must not appear.
    assert '"v"' not in (entity.parameters_json or "")
    assert entity.docstring == "Read the value."
    db.close()


def test_local_edits_are_preserved(tmp_path: Path):
    """Detection must NOT revert or re-clone the working tree."""
    db = SessionLocal()
    repo = _make_repo(db, tmp_path)
    target = tmp_path / "keep.py"
    target.write_text("def f():\n    return 0\n", encoding="utf-8")
    _baseline(db, repo)

    edited = "def f(extra):\n    return 999  # local edit\n"
    target.write_text(edited, encoding="utf-8")
    extra_file = tmp_path / "added_locally.py"
    extra_file.write_text("VALUE = 42\n", encoding="utf-8")

    ChangeDetectionService(db).detect_changes(repo.id)

    # The working tree is exactly as the user left it — nothing reverted/removed.
    assert target.read_text(encoding="utf-8") == edited
    assert extra_file.exists()
    assert extra_file.read_text(encoding="utf-8") == "VALUE = 42\n"
    db.close()
