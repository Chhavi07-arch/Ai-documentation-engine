"""Documentation routes: generate, list, fetch per entity."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.database import get_db
from app.models import Documentation
from app.routers.converters import entity_to_read
from app.schemas.documentation import (
    DocumentationRead,
    GenerateDocsRequest,
    GenerateDocsResponse,
)
from app.services.doc_generation_service import DocGenerationService
from app.services.rag_service import RAGService

router = APIRouter(tags=["documentation"])


def _to_read(db: Session, doc: Documentation) -> DocumentationRead:
    read = DocumentationRead.model_validate(doc)
    if doc.entity is not None:
        read.entity = entity_to_read(doc.entity)
    return read


@router.post(
    "/generate-docs",
    response_model=GenerateDocsResponse,
    summary="Generate documentation for a repository",
)
async def generate_docs(
    payload: GenerateDocsRequest, db: Session = Depends(get_db)
) -> GenerateDocsResponse:
    """Generate (or regenerate) documentation, then refresh the chat index."""
    result = await DocGenerationService(db).generate_for_repository(
        payload.repository_id,
        entity_ids=payload.entity_ids,
        force=payload.force,
    )
    # Keep the RAG index in sync so the chatbot reflects the new docs.
    await RAGService(db).index_repository(payload.repository_id)
    return GenerateDocsResponse(**result)


@router.get(
    "/repositories/{repository_id}/docs",
    response_model=list[DocumentationRead],
    summary="List documentation for a repository",
)
def list_docs(repository_id: int, db: Session = Depends(get_db)) -> list[DocumentationRead]:
    docs = list(
        db.scalars(
            select(Documentation).where(Documentation.repository_id == repository_id)
        ).all()
    )
    return [_to_read(db, d) for d in docs]


@router.get(
    "/docs/{entity_id}",
    response_model=DocumentationRead,
    summary="Get documentation for a single entity",
)
def get_doc(entity_id: int, db: Session = Depends(get_db)) -> DocumentationRead:
    doc = db.scalars(
        select(Documentation).where(Documentation.entity_id == entity_id)
    ).first()
    if doc is None:
        raise NotFoundError(f"No documentation found for entity {entity_id}.")
    return _to_read(db, doc)
