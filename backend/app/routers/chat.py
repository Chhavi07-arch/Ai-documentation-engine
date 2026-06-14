"""Documentation-aware chat (RAG) route."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import RAGService

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, summary="Ask the documentation chatbot")
async def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    """Answer a question using only the repository's documentation.

    Returns the answer together with the documentation sources it was grounded
    in. If no relevant docs are found, it says so honestly.
    """
    result = await RAGService(db).chat(
        repository_id=payload.repository_id,
        message=payload.message,
        top_k=payload.top_k,
    )
    return ChatResponse(**result)
