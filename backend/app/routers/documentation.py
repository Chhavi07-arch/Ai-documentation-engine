"""Documentation routes: generate, list, fetch per entity."""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.database import get_db
from app.models import CodeEntity, Documentation
from app.routers.converters import entity_to_read
from app.schemas.documentation import (
    DocumentationRead,
    GenerateDocsRequest,
    GenerateDocsResponse,
)
from app.services.doc_generation_service import DocGenerationService
from app.services.rag_service import RAGService
from app.utils import safe_filename

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


@router.get(
    "/docs/{entity_id}/export",
    summary="Download an entity's documentation as a Markdown file",
)
def export_doc(entity_id: int, db: Session = Depends(get_db)) -> Response:
    doc = db.scalars(
        select(Documentation).where(Documentation.entity_id == entity_id)
    ).first()
    if doc is None:
        raise NotFoundError(f"No documentation found for entity {entity_id}.")
    entity = db.get(CodeEntity, entity_id)
    name = safe_filename(entity.qualified_name) if entity else f"entity_{entity_id}"
    return Response(
        content=doc.content_markdown or "",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.md"'},
    )


@router.get(
    "/repositories/{repository_id}/docs/export",
    summary="Download all of a repository's documentation as a zip archive",
)
def export_repository_docs(repository_id: int, db: Session = Depends(get_db)) -> Response:
    docs = list(
        db.scalars(
            select(Documentation).where(Documentation.repository_id == repository_id)
        ).all()
    )
    if not docs:
        raise NotFoundError(f"No documentation to export for repository {repository_id}.")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for doc in docs:
            entity = db.get(CodeEntity, doc.entity_id)
            name = safe_filename(entity.qualified_name) if entity else f"entity_{doc.entity_id}"
            archive.writestr(f"{name}.md", doc.content_markdown or "")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="repo_{repository_id}_docs.zip"'
        },
    )
