"""Language-agnostic parser interfaces and data structures.

These dataclasses are the contract between parsers and the rest of the system.
Keeping them independent of any specific language (or of SQLAlchemy/Pydantic)
makes the parsing layer easy to test and extend to new languages later.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.enums import EntityKind


@dataclass
class ParsedParameter:
    """A single parameter of a function or method."""

    name: str
    annotation: str | None = None
    default: str | None = None
    kind: str = "positional"  # positional | keyword | vararg | kwarg

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "annotation": self.annotation,
            "default": self.default,
            "kind": self.kind,
        }


@dataclass
class ParsedEntity:
    """A single parsed code construct (module, class, function, or method)."""

    kind: EntityKind
    name: str
    qualified_name: str
    parent_name: str | None = None
    signature: str = ""
    return_type: str | None = None
    docstring: str | None = None
    source_code: str = ""
    relative_path: str = ""
    is_async: bool = False
    line_start: int = 0
    line_end: int = 0
    parameters: list[ParsedParameter] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def structure_hash(self) -> str:
        """Hash of the *interface* of this entity.

        Captures everything a documentation consumer cares about — name,
        parameters, return type, decorators — but deliberately excludes the
        function body. Two entities with the same structure hash have the same
        public contract, so existing docs about that contract stay valid.
        """
        params = "|".join(
            f"{p.name}:{p.annotation}={p.default}:{p.kind}" for p in self.parameters
        )
        material = "::".join(
            [
                self.kind.value,
                self.qualified_name,
                params,
                self.return_type or "",
                ",".join(sorted(self.decorators)),
                "async" if self.is_async else "sync",
            ]
        )
        return _sha256(material)

    def body_hash(self) -> str:
        """Hash of the full source, used to detect body-only modifications."""
        return _sha256(self.source_code)


@dataclass
class ParsedFile:
    """Result of parsing a single source file."""

    relative_path: str
    module_path: str
    content_hash: str
    line_count: int
    entities: list[ParsedEntity] = field(default_factory=list)


class BaseParser(ABC):
    """Interface every language parser implements."""

    #: File extensions this parser is responsible for (e.g. ``{".py"}``).
    extensions: set[str] = set()

    @abstractmethod
    def parse_file(self, *, source: str, relative_path: str, module_path: str) -> ParsedFile:
        """Parse a single source file into a :class:`ParsedFile`."""

    def supports(self, relative_path: str) -> bool:
        """Return True if this parser handles the given file."""
        return any(relative_path.endswith(ext) for ext in self.extensions)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
