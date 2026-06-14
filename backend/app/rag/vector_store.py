"""ChromaDB-backed vector store.

We manage embeddings ourselves (see :mod:`app.rag.embeddings`) and pass them to
Chroma explicitly, so the store works identically whether vectors come from
OpenRouter or the local fallback. Each repository gets its own collection so
retrieval is naturally scoped.
"""

from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import InvalidDimensionException

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.chunking import DocChunk

logger = get_logger("docengine.vectorstore")


class DimensionMismatchError(Exception):
    """Raised when a query embedding's dimension differs from the collection's.

    This happens if a collection was built with a different embedder (e.g. an
    older remote-embeddings run). Callers self-heal by re-indexing.
    """


class VectorStore:
    """Thin wrapper over a persistent ChromaDB client.

    The underlying client is created lazily on first use so that merely
    importing the app has no filesystem side effects — this keeps imports fast
    and makes the store easy to point at a temp directory in tests.
    """

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(settings.vector_storage_path),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
            )
        return self._client

    def _collection_name(self, repository_id: int) -> str:
        return f"repo_{repository_id}_docs"

    def _collection(self, repository_id: int):
        # cosine space matches our L2-normalized fallback vectors.
        return self.client.get_or_create_collection(
            name=self._collection_name(repository_id),
            metadata={"hnsw:space": "cosine"},
        )

    def reset_repository(self, repository_id: int) -> None:
        """Drop a repository's collection so it can be re-indexed cleanly."""
        try:
            self.client.delete_collection(self._collection_name(repository_id))
        except Exception:
            # Collection may not exist yet — that's fine.
            pass

    def upsert_chunks(
        self,
        repository_id: int,
        chunks: list[DocChunk],
        embeddings: list[list[float]],
    ) -> None:
        """Insert or update document chunks with their embeddings."""
        if not chunks:
            return
        collection = self._collection(repository_id)
        collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata for c in chunks],
        )

    def query(
        self, repository_id: int, query_embedding: list[float], *, top_k: int = 5
    ) -> list[dict]:
        """Return the top-k most similar chunks for a query embedding."""
        collection = self._collection(repository_id)
        count = collection.count()
        if count == 0:
            return []

        try:
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )
        except InvalidDimensionException as exc:
            # The collection was built with a different embedder. Signal the
            # caller to rebuild it with the current one.
            raise DimensionMismatchError(str(exc)) from exc

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        hits: list[dict] = []
        for doc, meta, distance in zip(documents, metadatas, distances):
            hits.append(
                {
                    "text": doc,
                    "metadata": meta or {},
                    # cosine distance → similarity score in [0, 1].
                    "score": max(0.0, 1.0 - float(distance)),
                }
            )
        return hits

    def count(self, repository_id: int) -> int:
        return self._collection(repository_id).count()


vector_store = VectorStore()
