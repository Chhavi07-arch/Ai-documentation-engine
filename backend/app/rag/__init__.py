"""Retrieval-Augmented Generation (RAG) pipeline.

Flow:
  documentation → chunking → embeddings → ChromaDB → retrieval → LLM answer

The pipeline is split into small, swappable pieces:
  * :mod:`app.rag.chunking`   — split markdown docs into retrievable chunks
  * :mod:`app.rag.embeddings` — OpenRouter embeddings with a local fallback
  * :mod:`app.rag.vector_store` — thin ChromaDB wrapper
"""

from app.rag.chunking import DocChunk, chunk_documentation
from app.rag.embeddings import EmbeddingProvider, embedding_provider
from app.rag.vector_store import DimensionMismatchError, VectorStore, vector_store

__all__ = [
    "DocChunk",
    "chunk_documentation",
    "EmbeddingProvider",
    "embedding_provider",
    "VectorStore",
    "vector_store",
    "DimensionMismatchError",
]
