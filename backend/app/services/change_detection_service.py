"""Change detection service.

Re-parses a repository's current source and compares it, structurally, against
the most recent snapshot. Detected changes become staleness flags. Detection is
non-destructive: stored entities and their documentation are left untouched so
they remain available for diffing and update drafting.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.diffing.entity_diff import ChangeResult, EntityState, diff_snapshots
from app.models import (
    CodeEntity,
    Documentation,
    EntitySnapshot,
    Repository,
    Snapshot,
    StalenessFlag,
)
from app.models.enums import ChangeType
from app.services.ingestion_service import IngestionService
from app.services.snapshot_service import SnapshotService
from app.services.states import DOC_KIND, doc_states_from_tree, states_from_parsed

logger = get_logger("docengine.changes")


class ChangeDetectionService:
    """Detect structural changes and raise documentation staleness flags."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.snapshots = SnapshotService(db)

    def detect_changes(self, repository_id: int) -> dict:
        """Compare the CURRENT LOCAL working tree against the FIXED baseline.

        The baseline is the snapshot captured at ingestion. Detection always
        diffs the current on-disk working copy against that same baseline, so
        results are cumulative and stable: editing two files then detecting
        reports both changes, and detecting again (without further edits)
        reports the same set rather than "consuming" them.

        It parses the working copy in place — it never re-clones, fetches, or
        pulls — so manual local edits are preserved. Returns a dict matching
        :class:`DetectChangesResponse`.
        """
        repo = self.db.get(Repository, repository_id)
        if repo is None:
            raise NotFoundError(f"Repository {repository_id} not found.")

        baseline = self.snapshots.latest_snapshot(repository_id)

        # Parse the current local working tree (no git operations whatsoever),
        # then add fingerprints for tracked documentation files (README/*.md,
        # *.rst) so content edits to them are detected alongside code changes.
        ingestion = IngestionService(self.db)
        parsed_files, metadata = ingestion.parse_local_tree(repo)
        new_states = states_from_parsed(parsed_files) + doc_states_from_tree(
            ingestion.local_working_path(repo)
        )

        if baseline is None:
            # No baseline yet (e.g. repo ingested before snapshots existed):
            # establish one now and report nothing to compare against.
            snapshot = self.snapshots.create_snapshot_from_states(
                repository_id,
                new_states,
                label="ingest-baseline",
                commit_sha=metadata.get("commit_sha"),
            )
            self.db.commit()
            logger.info(
                "Change detection: created baseline snapshot %d for repo %d.",
                snapshot.id, repository_id,
            )
            return {
                "repository_id": repository_id,
                "baseline_created": True,
                "snapshot_id": snapshot.id,
                "changes": [],
                "flags_created": 0,
            }

        old_states = _states_from_snapshot(baseline)
        changes = [
            c for c in diff_snapshots(old_states, new_states)
            if c.change_type is not ChangeType.UNCHANGED
        ]
        # Doc files reuse the code diff machinery, so give them doc-appropriate
        # wording instead of the code-centric default reasons.
        for c in changes:
            if c.kind == DOC_KIND:
                c.reason = _doc_reason(c)

        # Recompute the flag set from scratch each run so counts are stable and
        # never duplicated across repeated detections.
        flags_created = self._replace_flags(repo, changes)
        self.db.commit()

        by_type: dict[str, int] = {}
        for c in changes:
            by_type[c.change_type.value] = by_type.get(c.change_type.value, 0) + 1
        logger.info(
            "Change detection for repo %d vs baseline snapshot %d "
            "(%d entities) → current tree %d files / %d entities: "
            "%d changes %s, %d flags.",
            repository_id, baseline.id, baseline.entity_count,
            len(parsed_files), len(new_states),
            len(changes), by_type or "{}", flags_created,
        )

        return {
            "repository_id": repository_id,
            "baseline_created": False,
            "snapshot_id": baseline.id,
            "changes": [self._to_change_dict(c) for c in changes],
            "flags_created": flags_created,
        }

    # --- flag creation -----------------------------------------------------

    def _replace_flags(self, repo: Repository, changes: list[ChangeResult]) -> int:
        """Recompute the repository's staleness flags from the current diff.

        Existing flags for the repo are cleared first so repeated detections are
        idempotent — the flag set always reflects the current diff vs baseline,
        with no duplicates or stale leftovers.
        """
        self.db.execute(
            delete(StalenessFlag).where(StalenessFlag.repository_id == repo.id)
        )
        self.db.flush()

        created = 0
        for change in changes:
            entity = self._find_entity(repo.id, change)
            original_doc = self._existing_doc_markdown(entity)
            self.db.add(
                StalenessFlag(
                    repository_id=repo.id,
                    entity_id=entity.id if entity else None,
                    qualified_name=change.qualified_name,
                    change_type=change.change_type.value,
                    severity=change.severity.value if change.severity else "REVIEW_RECOMMENDED",
                    reason=change.reason,
                    old_source=change.old_source,
                    new_source=change.new_source,
                    original_doc_markdown=original_doc,
                )
            )
            created += 1
        return created

    def _find_entity(self, repository_id: int, change: ChangeResult) -> CodeEntity | None:
        # Prefer the new name; fall back to the pre-rename name.
        for name in (change.qualified_name, change.renamed_from):
            if not name:
                continue
            entity = self.db.scalars(
                select(CodeEntity).where(
                    CodeEntity.repository_id == repository_id,
                    CodeEntity.qualified_name == name,
                )
            ).first()
            if entity:
                return entity
        return None

    def _existing_doc_markdown(self, entity: CodeEntity | None) -> str | None:
        if entity is None:
            return None
        doc = self.db.scalars(
            select(Documentation).where(Documentation.entity_id == entity.id)
        ).first()
        return doc.content_markdown if doc else None

    def _to_change_dict(self, change: ChangeResult) -> dict:
        return {
            "qualified_name": change.qualified_name,
            "kind": change.kind,
            "change_type": change.change_type.value,
            "severity": change.severity.value if change.severity else None,
            "reason": change.reason,
            "renamed_from": change.renamed_from,
        }


# --- EntityState builders --------------------------------------------------
#
# Parsed-source and doc-file builders live in ``app.services.states`` so both
# ingestion and change detection share them. Only the snapshot-reading builder
# (DB-specific) stays here.


def _doc_reason(change: ChangeResult) -> str:
    """Human-friendly reason text for a documentation-file change."""
    if change.change_type is ChangeType.ADDED:
        return "New documentation file added."
    if change.change_type is ChangeType.DELETED:
        return "Documentation file was removed."
    if change.change_type is ChangeType.RENAMED:
        return f"Documentation file renamed from `{change.renamed_from}`."
    return "Documentation content changed; review it for accuracy."


def _states_from_snapshot(snapshot: Snapshot) -> list[EntityState]:
    states: list[EntityState] = []
    for es in snapshot.entities:
        states.append(
            EntityState(
                qualified_name=es.qualified_name,
                kind=es.kind,
                signature=es.signature,
                return_type=es.return_type,
                parameters_json=es.parameters_json,
                docstring=es.docstring,
                structure_hash=es.structure_hash,
                body_hash=es.body_hash,
                source_code=es.source_code,
            )
        )
    return states
