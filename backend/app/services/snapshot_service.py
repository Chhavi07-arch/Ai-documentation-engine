"""Snapshot service — capture point-in-time structural fingerprints.

A snapshot stores, per entity, both a *structure hash* (the public contract:
name, params, return type, decorators) and a *body hash* (the full source).
Comparing two snapshots powers AST-aware change detection.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.diffing.entity_diff import EntityState
from app.models import CodeEntity, EntitySnapshot, Snapshot

logger = get_logger("docengine.snapshot")


class SnapshotService:
    """Create and retrieve structural snapshots of a repository."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_snapshot(
        self, repository_id: int, *, label: str = "snapshot", commit_sha: str | None = None
    ) -> Snapshot:
        """Capture the current entity structure of a repository as a snapshot."""
        entities = list(
            self.db.scalars(
                select(CodeEntity).where(CodeEntity.repository_id == repository_id)
            ).all()
        )

        snapshot = Snapshot(
            repository_id=repository_id,
            label=label,
            commit_sha=commit_sha,
            entity_count=len(entities),
        )
        self.db.add(snapshot)
        self.db.flush()

        for entity in entities:
            self.db.add(
                EntitySnapshot(
                    snapshot_id=snapshot.id,
                    qualified_name=entity.qualified_name,
                    kind=entity.kind,
                    signature=entity.signature,
                    return_type=entity.return_type,
                    parameters_json=entity.parameters_json,
                    docstring=entity.docstring,
                    source_code=entity.source_code,
                    structure_hash=entity.structure_hash,
                    body_hash=_sha256(entity.source_code or ""),
                )
            )

        self.db.commit()
        logger.info("Created snapshot %d (%s) with %d entities", snapshot.id, label, len(entities))
        return snapshot

    def create_snapshot_from_states(
        self,
        repository_id: int,
        states: list[EntityState],
        *,
        label: str = "snapshot",
        commit_sha: str | None = None,
    ) -> Snapshot:
        """Capture a snapshot from freshly parsed states (no DB entities yet).

        Used by change detection, which parses the latest source without
        mutating stored entities/documentation.
        """
        snapshot = Snapshot(
            repository_id=repository_id,
            label=label,
            commit_sha=commit_sha,
            entity_count=len(states),
        )
        self.db.add(snapshot)
        self.db.flush()

        for s in states:
            self.db.add(
                EntitySnapshot(
                    snapshot_id=snapshot.id,
                    qualified_name=s.qualified_name,
                    kind=s.kind,
                    signature=s.signature,
                    return_type=s.return_type,
                    parameters_json=s.parameters_json,
                    docstring=s.docstring,
                    source_code=s.source_code,
                    structure_hash=s.structure_hash,
                    body_hash=s.body_hash,
                )
            )
        self.db.commit()
        return snapshot

    def latest_snapshot(self, repository_id: int) -> Snapshot | None:
        """Return the most recent snapshot for a repository, if any."""
        return self.db.scalars(
            select(Snapshot)
            .where(Snapshot.repository_id == repository_id)
            .order_by(Snapshot.id.desc())
            .limit(1)
        ).first()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
