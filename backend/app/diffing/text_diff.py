"""Plain-text/markdown diffing helpers."""

from __future__ import annotations

import difflib


def unified_markdown_diff(
    old: str, new: str, *, from_label: str = "current", to_label: str = "drafted"
) -> str:
    """Return a unified diff between two markdown documents."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    return "\n".join(diff)
