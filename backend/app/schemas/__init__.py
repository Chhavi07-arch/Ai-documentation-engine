"""Pydantic schemas for request validation and response serialization."""

from app.schemas.common import Message, PaginatedMeta
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryDetail,
    RepositoryRead,
    SourceFileRead,
    FileTreeNode,
)
from app.schemas.entity import (
    EntityRead,
    EntityDetail,
    Parameter,
)
from app.schemas.documentation import (
    DocumentationRead,
    GenerateDocsRequest,
    GenerateDocsResponse,
)
from app.schemas.changes import (
    DetectChangesRequest,
    DetectChangesResponse,
    EntityChange,
)
from app.schemas.staleness import StalenessFlagRead, DraftUpdateRequest, DraftUpdateResponse
from app.schemas.chat import ChatRequest, ChatResponse, RetrievedSource

__all__ = [
    "Message",
    "PaginatedMeta",
    "RepositoryCreate",
    "RepositoryRead",
    "RepositoryDetail",
    "SourceFileRead",
    "FileTreeNode",
    "EntityRead",
    "EntityDetail",
    "Parameter",
    "DocumentationRead",
    "GenerateDocsRequest",
    "GenerateDocsResponse",
    "DetectChangesRequest",
    "DetectChangesResponse",
    "EntityChange",
    "StalenessFlagRead",
    "DraftUpdateRequest",
    "DraftUpdateResponse",
    "ChatRequest",
    "ChatResponse",
    "RetrievedSource",
]
