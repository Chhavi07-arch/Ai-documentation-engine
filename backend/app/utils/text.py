"""Text helpers: slugs, safe filenames, truncation, fenced-code language."""

from __future__ import annotations

import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Map a source file extension to the Markdown code-fence language so syntax
# highlighting is correct across every language we parse (not just Python).
_FENCE_BY_EXT = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c++": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp",
    ".cs": "csharp",
    ".php": "php",
}


def fence_language(relative_path: str | None) -> str:
    """Markdown code-fence language for a file path.

    e.g. ``"src/app.ts" -> "typescript"``. Returns ``""`` (an unlabelled fence)
    when the extension is unknown, so we never mislabel non-Python code.
    """
    if not relative_path:
        return ""
    return _FENCE_BY_EXT.get(Path(relative_path).suffix.lower(), "")


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
