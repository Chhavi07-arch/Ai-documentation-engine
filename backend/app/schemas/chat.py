"""Schemas for the documentation-aware RAG chatbot."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedSource(BaseModel):
    """A documentation chunk retrieved as context for a chat answer."""

    qualified_name: str
    relative_path: str
    kind: str
    score: float
    excerpt: str


class ChatRequest(BaseModel):
    """A user question scoped to one repository's documentation."""

    repository_id: int
    message: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=12)


class ChatResponse(BaseModel):
    """An answer grounded in retrieved documentation, with sources."""

    answer: str
    sources: list[RetrievedSource]
    grounded: bool  # False when no relevant docs were found
