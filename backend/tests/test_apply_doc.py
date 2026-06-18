"""Tests for applying a reviewed draft as the entity's documentation on resolve.

Keeps a human in the loop (they review the draft first) but ensures clicking
resolve with an approved draft actually replaces the stored documentation.
"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import CodeEntity, Documentation, Repository, StalenessFlag
from app.models.enums import (
    ChangeType,
    EntityKind,
    RepositoryStatus,
    StalenessSeverity,
)
from app.services.staleness_service import StalenessService


def _seed(db):
    repo = Repository(
        name="t", full_name="t/t", url="https://github.com/t/t",
        local_path="", status=RepositoryStatus.READY.value,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    entity = CodeEntity(
        repository_id=repo.id, source_file_id=0, kind=EntityKind.FUNCTION.value,
        name="login", qualified_name="auth.login", relative_path="auth.py",
        signature="def login(email, password)", structure_hash="h",
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    flag = StalenessFlag(
        repository_id=repo.id, entity_id=entity.id, qualified_name="auth.login",
        change_type=ChangeType.PARAMETERS_CHANGED.value,
        severity=StalenessSeverity.BROKEN.value, reason="params changed",
        resolved=False,
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return repo, entity, flag


def test_apply_documentation_saves_the_reviewed_doc():
    db = SessionLocal()
    repo, entity, flag = _seed(db)

    new_doc = "## `login`\n\nUpdated documentation for the new signature."
    repo_id = StalenessService(db).apply_documentation(flag.id, new_doc)

    assert repo_id == repo.id
    saved = db.scalar(
        select(Documentation).where(Documentation.entity_id == entity.id)
    )
    assert saved is not None
    assert saved.content_markdown == new_doc
    assert saved.generator == "ai"
    db.close()


def test_apply_documentation_noop_for_deleted_entity():
    """A deleted entity (no entity_id) has nothing to attach docs to."""
    db = SessionLocal()
    repo, _, _ = _seed(db)
    orphan = StalenessFlag(
        repository_id=repo.id, entity_id=None, qualified_name="auth.gone",
        change_type=ChangeType.DELETED.value,
        severity=StalenessSeverity.BROKEN.value, reason="removed", resolved=False,
    )
    db.add(orphan)
    db.commit()
    db.refresh(orphan)

    result = StalenessService(db).apply_documentation(orphan.id, "anything")
    assert result is None  # nothing applied
    db.close()


def test_resolve_still_marks_resolved():
    db = SessionLocal()
    _, _, flag = _seed(db)
    StalenessService(db).resolve_flag(flag.id)
    db.refresh(flag)
    assert flag.resolved is True
    db.close()
