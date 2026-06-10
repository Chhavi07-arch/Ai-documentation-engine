"""Schemas for repositories, source files, and the file tree."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import RepositoryStatus

# Accepts https/http GitHub URLs, optionally ending in `.git`.
_GITHUB_URL = re.compile(
    r"^https?://(www\.)?github\.com/[\w.\-]+/[\w.\-]+/?(\.git)?$",
    re.IGNORECASE,
)


class RepositoryCreate(BaseModel):
    """Request body for ingesting a new repository."""

    url: str

    @field_validator("url")
    @classmethod
    def validate_github_url(cls, value: str) -> str:
        value = value.strip()
        if not _GITHUB_URL.match(value):
            raise ValueError(
                "Must be a valid public GitHub repository URL, e.g. "
                "https://github.com/owner/repo"
            )
        return value


class SourceFileRead(BaseModel):
    """A source file within a repository."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    relative_path: str
    module_path: str
    line_count: int


class FileTreeNode(BaseModel):
    """A node in the repository file tree (directory or file)."""

    name: str
    path: str
    type: str  # "dir" | "file"
    file_id: int | None = None
    entity_count: int = 0
    children: list["FileTreeNode"] = []


class RepositoryRead(BaseModel):
    """Compact repository representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    full_name: str
    url: str
    default_branch: str
    description: str | None = None
    status: RepositoryStatus
    error_message: str | None = None
    file_count: int
    entity_count: int
    documented_count: int
    created_at: datetime
    updated_at: datetime


class RepositoryDetail(RepositoryRead):
    """Repository detail including its file tree."""

    file_tree: list[FileTreeNode] = []


FileTreeNode.model_rebuild()
