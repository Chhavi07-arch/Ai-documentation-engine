"""Common, shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class Message(BaseModel):
    """A simple status message response."""

    message: str


class PaginatedMeta(BaseModel):
    """Pagination metadata returned alongside list endpoints."""

    total: int
    count: int
