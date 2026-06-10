"""Source code parsing engine.

The parser is intentionally modular: :mod:`app.parsers.python_parser` handles
Python via the standard-library ``ast`` module, while
:mod:`app.parsers.base` defines the language-agnostic data structures and the
``BaseParser`` interface that future language parsers can implement.
"""

from app.parsers.base import (
    BaseParser,
    ParsedEntity,
    ParsedFile,
    ParsedParameter,
)
from app.parsers.python_parser import PythonParser

__all__ = [
    "BaseParser",
    "ParsedEntity",
    "ParsedFile",
    "ParsedParameter",
    "PythonParser",
]
