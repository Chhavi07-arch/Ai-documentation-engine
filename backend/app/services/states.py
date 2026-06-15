"""Shared builders for structural :class:`EntityState` fingerprints.

Both ingestion (when capturing a baseline snapshot) and change detection turn
parsed Python source — and tracked documentation files such as ``README.md`` —
into the same ``EntityState`` shape, so everything flows through one diff
pipeline. This module is deliberately dependency-light (it imports no services)
so either layer can use it without an import cycle.

Documentation files have no code entity, so each tracked doc file is represented
as a single ``doc``-kind state keyed by its relative path, with its full content
hashed into the body hash. The normal snapshot/diff machinery then reports an
added, modified, or deleted doc with no special casing downstream.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.diffing.entity_diff import EntityState
from app.parsers.base import ParsedEntity, ParsedFile
from app.utils import dump_json

# Directories that never contain first-party source or docs worth tracking.
SKIP_DIRS = {
    ".git", ".github", "__pycache__", ".venv", "venv", "env", "node_modules",
    "build", "dist", ".mypy_cache", ".pytest_cache", ".tox", "site-packages",
    "migrations", ".idea", ".vscode",
}
MAX_FILE_BYTES = 1_000_000  # 1 MB — skip generated/huge files

# Non-code documentation files we track for content drift. Editing any of these
# (e.g. a README) is surfaced as a staleness flag even though there is no code
# entity behind it.
DOC_EXTENSIONS = {".md", ".rst"}
DOC_KIND = "doc"


def state_from_parsed_entity(entity: ParsedEntity) -> EntityState:
    """Build the structural fingerprint of a single parsed code entity."""
    return EntityState(
        qualified_name=entity.qualified_name,
        kind=entity.kind.value,
        signature=entity.signature,
        return_type=entity.return_type,
        parameters_json=dump_json([p.to_dict() for p in entity.parameters]),
        docstring=entity.docstring,
        structure_hash=entity.structure_hash(),
        body_hash=entity.body_hash(),
        source_code=entity.source_code,
    )


def states_from_parsed(parsed_files: list[ParsedFile]) -> list[EntityState]:
    """Flatten parsed files into a list of code entity states."""
    states: list[EntityState] = []
    for pf in parsed_files:
        states.extend(state_from_parsed_entity(e) for e in pf.entities)
    return states


def doc_states_from_tree(root: Path) -> list[EntityState]:
    """Fingerprint tracked documentation files (``*.md``, ``*.rst``) under ``root``.

    Each file becomes one ``doc``-kind :class:`EntityState` keyed by its relative
    path, with its content hashed into both the structure and body hash. A pure
    content edit therefore changes the body hash and is reported as a
    modification; new and removed files become additions and deletions.
    """
    states: list[EntityState] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() not in DOC_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        digest = _sha256(content)
        states.append(
            EntityState(
                qualified_name=rel.as_posix(),
                kind=DOC_KIND,
                signature="",
                return_type=None,
                parameters_json="[]",
                docstring=None,
                structure_hash=digest,
                body_hash=digest,
                source_code=content,
            )
        )
    return states


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
