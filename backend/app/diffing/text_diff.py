"""Plain-text/markdown diffing helpers."""

from __future__ import annotations

import difflib


def unified_markdown_diff(
    old: str, new: str, *, from_label: str = "current", to_label: str = "drafted"
) -> str:
    """Return a unified diff between two markdown documents.

    Lines are split *without* keeping their terminators so that, combined with
    ``lineterm=""`` and ``"\n".join(...)``, each hunk line carries exactly one
    newline — otherwise every line would be doubled with a blank line.
    """
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    return "\n".join(diff)
