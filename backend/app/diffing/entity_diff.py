"""AST-aware entity diffing.

Compares two sets of entity states (typically two snapshots) and classifies how
each entity changed. The classification is structural — based on parsed
parameters, return types, and signatures — not naive text diffing. A rename
heuristic matches a deleted entity to an added one when their bodies are
identical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models.enums import ChangeType, StalenessSeverity


@dataclass(frozen=True)
class EntityState:
    """A minimal structural fingerprint of an entity for comparison."""

    qualified_name: str
    kind: str
    signature: str
    return_type: str | None
    parameters_json: str
    docstring: str | None
    structure_hash: str
    body_hash: str
    source_code: str = ""

    @property
    def parameters(self) -> list[dict]:
        try:
            return json.loads(self.parameters_json or "[]")
        except json.JSONDecodeError:
            return []


@dataclass
class ChangeResult:
    """The result of classifying a single entity's change."""

    qualified_name: str
    kind: str
    change_type: ChangeType
    severity: StalenessSeverity | None
    reason: str
    renamed_from: str | None = None
    old_source: str | None = None
    new_source: str | None = None


# Severity policy — central, so the rules are easy to read and tune.
_SEVERITY: dict[ChangeType, StalenessSeverity] = {
    ChangeType.DELETED: StalenessSeverity.BROKEN,
    ChangeType.SIGNATURE_CHANGED: StalenessSeverity.BROKEN,
    ChangeType.PARAMETERS_CHANGED: StalenessSeverity.BROKEN,
    ChangeType.RETURN_TYPE_CHANGED: StalenessSeverity.BROKEN,
    ChangeType.RENAMED: StalenessSeverity.BROKEN,
    ChangeType.BODY_MODIFIED: StalenessSeverity.POTENTIALLY_OUTDATED,
    ChangeType.DOCSTRING_CHANGED: StalenessSeverity.REVIEW_RECOMMENDED,
    ChangeType.ADDED: StalenessSeverity.REVIEW_RECOMMENDED,
}


def classify_change(old: EntityState | None, new: EntityState | None) -> ChangeResult:
    """Classify the change between an old and new state of one entity."""
    assert old or new, "classify_change requires at least one state"

    if old is None and new is not None:
        return ChangeResult(
            qualified_name=new.qualified_name,
            kind=new.kind,
            change_type=ChangeType.ADDED,
            severity=_SEVERITY[ChangeType.ADDED],
            reason="New entity added; documentation should be created.",
            new_source=new.source_code,
        )

    if new is None and old is not None:
        return ChangeResult(
            qualified_name=old.qualified_name,
            kind=old.kind,
            change_type=ChangeType.DELETED,
            severity=_SEVERITY[ChangeType.DELETED],
            reason="Entity was removed; its documentation is now broken.",
            old_source=old.source_code,
        )

    # Both present — find the most significant difference.
    assert old is not None and new is not None
    change_type, reason = _classify_modification(old, new)
    return ChangeResult(
        qualified_name=new.qualified_name,
        kind=new.kind,
        change_type=change_type,
        severity=_SEVERITY.get(change_type),
        reason=reason,
        old_source=old.source_code,
        new_source=new.source_code,
    )


def _classify_modification(old: EntityState, new: EntityState) -> tuple[ChangeType, str]:
    """Return the highest-severity modification between two present states."""
    if old.return_type != new.return_type:
        return (
            ChangeType.RETURN_TYPE_CHANGED,
            f"Return type changed from `{old.return_type or 'None'}` to "
            f"`{new.return_type or 'None'}`.",
        )

    if _param_names(old) != _param_names(new):
        return (
            ChangeType.PARAMETERS_CHANGED,
            "Parameters changed; documented arguments may be incorrect.",
        )

    if old.signature != new.signature:
        return (
            ChangeType.SIGNATURE_CHANGED,
            "Signature changed (types/defaults); documentation may be inaccurate.",
        )

    if old.body_hash != new.body_hash:
        return (
            ChangeType.BODY_MODIFIED,
            "Implementation changed; behavior/examples may need review.",
        )

    if (old.docstring or "") != (new.docstring or ""):
        return (
            ChangeType.DOCSTRING_CHANGED,
            "Docstring changed; a documentation refresh is recommended.",
        )

    return ChangeType.UNCHANGED, "No structural change detected."


def _param_names(state: EntityState) -> list[str]:
    return [p.get("name", "") for p in state.parameters]


def diff_snapshots(
    old_states: list[EntityState], new_states: list[EntityState]
) -> list[ChangeResult]:
    """Diff two snapshots and return all non-trivial changes.

    A deleted entity whose body exactly matches an added entity is reported as a
    rename rather than a delete+add pair.
    """
    old_by_name = {s.qualified_name: s for s in old_states}
    new_by_name = {s.qualified_name: s for s in new_states}

    results: list[ChangeResult] = []
    handled_new: set[str] = set()

    # Deletions and renames.
    for name, old_state in old_by_name.items():
        if name in new_by_name:
            continue
        rename_target = _find_rename(old_state, new_by_name, old_by_name)
        if rename_target is not None:
            results.append(
                ChangeResult(
                    qualified_name=rename_target.qualified_name,
                    kind=rename_target.kind,
                    change_type=ChangeType.RENAMED,
                    severity=_SEVERITY[ChangeType.RENAMED],
                    reason=f"Renamed from `{name}`; documentation references are broken.",
                    renamed_from=name,
                    old_source=old_state.source_code,
                    new_source=rename_target.source_code,
                )
            )
            handled_new.add(rename_target.qualified_name)
        else:
            results.append(classify_change(old_state, None))

    # Additions and modifications.
    for name, new_state in new_by_name.items():
        if name in handled_new:
            continue
        old_state = old_by_name.get(name)
        result = classify_change(old_state, new_state)
        if result.change_type is not ChangeType.UNCHANGED:
            results.append(result)

    return results


def _find_rename(
    old_state: EntityState,
    new_by_name: dict[str, EntityState],
    old_by_name: dict[str, EntityState],
) -> EntityState | None:
    """Find an added entity whose body matches a deleted entity (a rename)."""
    for name, candidate in new_by_name.items():
        if name in old_by_name:
            continue  # already existed — not an addition
        if candidate.kind != old_state.kind:
            continue
        if candidate.body_hash == old_state.body_hash and old_state.body_hash:
            return candidate
    return None
