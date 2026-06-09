"""Shared enumerations used across models and schemas."""

from __future__ import annotations

from enum import Enum


class RepositoryStatus(str, Enum):
    """Lifecycle of an ingested repository."""

    PENDING = "pending"
    INGESTING = "ingesting"
    PARSING = "parsing"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class EntityKind(str, Enum):
    """The kind of code entity extracted by the parser."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"


class ChangeType(str, Enum):
    """How a code entity changed between two snapshots."""

    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    SIGNATURE_CHANGED = "signature_changed"
    RETURN_TYPE_CHANGED = "return_type_changed"
    PARAMETERS_CHANGED = "parameters_changed"
    BODY_MODIFIED = "body_modified"
    DOCSTRING_CHANGED = "docstring_changed"
    UNCHANGED = "unchanged"


class StalenessSeverity(str, Enum):
    """Severity of documentation drift caused by a code change."""

    BROKEN = "BROKEN"
    POTENTIALLY_OUTDATED = "POTENTIALLY_OUTDATED"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
