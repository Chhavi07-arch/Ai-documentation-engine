"""Source code parsing engine.

The parser is intentionally modular and multi-language:

* :mod:`app.parsers.python_parser` handles Python via the standard-library
  ``ast`` module (the richest result for our own language).
* :mod:`app.parsers.treesitter_parser` handles every other supported language
  via tree-sitter, driven by a declarative spec per language.
* :mod:`app.parsers.base` defines the language-agnostic data structures and the
  ``BaseParser`` interface both implementations share.

:class:`ParserRegistry` maps a file path to the correct parser by extension, so
ingestion can stay language-agnostic — it just asks the registry.
"""

from __future__ import annotations

from app.parsers.base import (
    BaseParser,
    ParsedEntity,
    ParsedFile,
    ParsedParameter,
)
from app.parsers.python_parser import PythonParser
from app.parsers.treesitter_parser import (
    LANGUAGE_SPECS,
    SPEC_BY_EXTENSION,
    TreeSitterParser,
)


class ParserRegistry:
    """Resolve the right :class:`BaseParser` for a file by its extension.

    Python is served by :class:`PythonParser`; all other supported languages by
    a per-language :class:`TreeSitterParser` (instances are cached so each
    grammar is loaded at most once).
    """

    def __init__(self) -> None:
        self._python = PythonParser()
        self._treesitter: dict[str, TreeSitterParser] = {}

    @property
    def supported_extensions(self) -> set[str]:
        """All file extensions any parser can handle (e.g. ``{".py", ".js", ...}``)."""
        return set(self._python.extensions) | set(SPEC_BY_EXTENSION)

    def parser_for(self, relative_path: str) -> BaseParser | None:
        """Return the parser for ``relative_path``, or ``None`` if unsupported."""
        lowered = relative_path.lower()
        for ext in self._python.extensions:
            if lowered.endswith(ext):
                return self._python
        for ext, spec in SPEC_BY_EXTENSION.items():
            if lowered.endswith(ext):
                cached = self._treesitter.get(spec.ts_name)
                if cached is None:
                    cached = TreeSitterParser(spec)
                    self._treesitter[spec.ts_name] = cached
                return cached
        return None


__all__ = [
    "BaseParser",
    "ParsedEntity",
    "ParsedFile",
    "ParsedParameter",
    "PythonParser",
    "TreeSitterParser",
    "ParserRegistry",
    "LANGUAGE_SPECS",
    "SPEC_BY_EXTENSION",
]
