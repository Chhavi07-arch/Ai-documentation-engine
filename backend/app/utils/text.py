"""Text helpers: slugs, safe filenames, truncation."""

from __future__ import annotations

import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, hyphenated slug suitable for ids and anchors."""
    return _SLUG_RE.sub("-", value.lower()).strip("-")


def safe_filename(value: str) -> str:
    """Turn a qualified name into a filesystem-safe filename (no extension)."""
    return value.replace(".", "__").replace("/", "_").replace("\\", "_")


def truncate(value: str, limit: int = 280) -> str:
    """Truncate text to ``limit`` characters with an ellipsis."""
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"
