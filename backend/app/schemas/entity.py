"""Schemas for parsed code entities."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EntityKind


class Parameter(BaseModel):
    """A single function/method parameter."""

    name: str
    annotation: str | None = None
    default: str | None = None
    kind: str = "positional"  # positional | keyword | vararg | kwarg


class EntityRead(BaseModel):
    """Compact entity representation for list/tree views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: EntityKind
    name: str
    qualified_name: str
    relative_path: str
    return_type: str | None = None
    is_async: bool = False
    line_start: int = 0
    line_end: int = 0
    has_docs: bool = False


class EntityDetail(BaseModel):
    """Full entity representation including parsed structure and source."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    source_file_id: int
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
    parameters: list[Parameter] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
