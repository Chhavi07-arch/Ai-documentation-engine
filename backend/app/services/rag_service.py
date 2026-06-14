"""RAG service — index documentation and answer questions over it.

Indexing: read a repository's generated docs → chunk → embed → store in Chroma.
Chat: embed the question → retrieve top-k chunks → ground the LLM answer in them
and return the cited sources. If nothing relevant is retrieved, the assistant
honestly reports that the answer is not in the documentation.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AIServiceError, NotFoundError
from app.core.logging import get_logger
from app.models import CodeEntity, Documentation, Repository
from app.prompts import CHAT_SYSTEM_PROMPT, build_chat_prompt
from app.rag import (
    DimensionMismatchError,
    chunk_documentation,
    embedding_provider,
    vector_store,
)
from app.services.ai_service import ai_service
from app.utils import truncate

logger = get_logger("docengine.rag")

# Below this similarity, retrieved chunks are treated as irrelevant. Tuned for
# the local hashing embedder (whose cosine scores run lower than dense semantic
# models); the LLM still filters weak matches via its grounding instruction,
# and genuinely off-topic queries score ~0 so they remain correctly rejected.
_RELEVANCE_THRESHOLD = 0.05
_NOT_FOUND = "Information not found in documentation."


class RAGService:
    """Index documentation and run the retrieval-augmented chat pipeline."""

    def __init__(self, db: Session) -> None:
        self.db = db

    async def index_repository(self, repository_id: int) -> int:
        """(Re)build the vector index for a repository's documentation.

        Returns the number of chunks indexed.
        """
        repo = self.db.get(Repository, repository_id)
        if repo is None:
            raise NotFoundError(f"Repository {repository_id} not found.")

        docs = list(
            self.db.scalars(
                select(Documentation).where(Documentation.repository_id == repository_id)
            ).all()
        )

        vector_store.reset_repository(repository_id)
        if not docs:
            return 0

        all_chunks = []
        for doc in docs:
            entity = self.db.get(CodeEntity, doc.entity_id)
            if entity is None:
                continue
            all_chunks.extend(
                chunk_documentation(
                    entity_id=entity.id,
                    qualified_name=entity.qualified_name,
                    relative_path=entity.relative_path,
                    kind=entity.kind,
                    markdown=doc.content_markdown,
                )
            )

        if not all_chunks:
            return 0

        embeddings = await embedding_provider.embed([c.text for c in all_chunks])
        vector_store.upsert_chunks(repository_id, all_chunks, embeddings)
        logger.info(
            "Indexed %d chunks for repo %d (%s embeddings)",
            len(all_chunks), repository_id, embedding_provider.mode,
        )
        return len(all_chunks)

    async def chat(self, *, repository_id: int, message: str, top_k: int = 5) -> dict:
        """Answer a question grounded in the repository's documentation."""
        repo = self.db.get(Repository, repository_id)
        if repo is None:
            raise NotFoundError(f"Repository {repository_id} not found.")

        # Lazily index on first chat if the collection is empty.
        if vector_store.count(repository_id) == 0:
            await self.index_repository(repository_id)

        # Retrieve a wide candidate set, then re-rank with a lexical signal so
        # name-based queries (e.g. "URLSafeSerializer", "dumps") reliably find
        # the right entity even with the local embedder.
        candidate_k = max(top_k * 6, 24)
        query_embedding = await embedding_provider.embed_one(message)
        try:
            hits = vector_store.query(repository_id, query_embedding, top_k=candidate_k)
        except DimensionMismatchError:
            # The collection was built with a different embedder (e.g. a prior
            # remote-embeddings run). Rebuild it with the current embedder and
            # retry once so chat self-heals instead of erroring.
            logger.warning(
                "Embedding dimension mismatch for repo %d — rebuilding index.",
                repository_id,
            )
            await self.index_repository(repository_id)
            query_embedding = await embedding_provider.embed_one(message)
            hits = vector_store.query(repository_id, query_embedding, top_k=candidate_k)

        ranked = self._rerank(message, hits)
        relevant = [h for h in ranked if h["combined_score"] >= _RELEVANCE_THRESHOLD][:top_k]

        sources = [
            {
                "qualified_name": h["metadata"].get("qualified_name", "unknown"),
                "relative_path": h["metadata"].get("relative_path", ""),
                "kind": h["metadata"].get("kind", ""),
                "score": round(h["combined_score"], 3),
                "excerpt": truncate(h["text"], 320),
            }
            for h in relevant
        ]

        if not relevant:
            return {"answer": _NOT_FOUND, "sources": [], "grounded": False}

        answer = await self._answer(message, relevant)
        return {"answer": answer, "sources": sources, "grounded": True}

    # --- internals ---------------------------------------------------------

    def _rerank(self, message: str, hits: list[dict]) -> list[dict]:
        """Blend vector similarity with a lexical score and sort descending.

        The lexical score rewards query terms that match the entity's qualified
        name (handling camelCase/snake_case) and appear in the doc text. This
        fixes the common failure where a purely vector-based local embedder
        surfaces unrelated entities for a clear name query.
        """
        query_tokens = _tokenize(message)
        for h in hits:
            meta = h.get("metadata", {})
            lexical = _lexical_score(
                query_tokens,
                meta.get("qualified_name", ""),
                h.get("text", ""),
            )
            # Vector score and lexical score are both ~[0, 1]; weight lexical
            # heavily because exact-name matches are the strongest signal here.
            h["combined_score"] = h.get("score", 0.0) + 1.5 * lexical
        hits.sort(key=lambda x: x["combined_score"], reverse=True)
        return hits

    async def _answer(self, message: str, hits: list[dict]) -> str:
        # Trim each context block so the prompt stays small enough for
        # low-credit accounts (and faster/cheaper in general).
        context_blocks = [
            f"Source: {h['metadata'].get('qualified_name', 'unknown')}\n"
            + truncate(h["text"], 700)
            for h in hits
        ]
        if not ai_service.enabled:
            return self._excerpt_answer(hits)

        prompt = build_chat_prompt(question=message, context_blocks=context_blocks)
        try:
            return await ai_service.complete(
                system=CHAT_SYSTEM_PROMPT,
                user=prompt,
                temperature=0.1,
                max_tokens=700,
            )
        except AIServiceError:
            return self._excerpt_answer(hits)

    def _excerpt_answer(self, hits: list[dict]) -> str:
        """Graceful, honest fallback that still shows the best matching docs."""
        top = hits[0]
        name = top["metadata"].get("qualified_name", "the documentation")
        return (
            f"_(Couldn't generate an AI answer just now — showing the most "
            f"relevant documentation for_ `{name}`_.)_\n\n{truncate(top['text'], 800)}"
        )


# --- lexical scoring helpers ----------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "how", "what", "which", "of",
    "to", "in", "on", "for", "and", "or", "with", "it", "this", "that", "work",
    "works", "use", "used", "using", "i", "you", "me", "can", "where", "when",
    "class", "method", "function", "module", "handle", "handles", "accept",
    "accepts", "there", "about", "tell", "explain", "show", "give",
}


def _token_match(qt: str, nt: str) -> float:
    """Similarity between a query token and a name token (0, 0.6, or 1.0)."""
    if qt == nt:
        return 1.0
    if qt in nt or nt in qt:
        return 0.6  # substring, e.g. "serializer" in "urlsafeserializer"
    # Shared stem, e.g. "signing" ~ "signer" (common prefix "sign").
    prefix = 0
    for a, b in zip(qt, nt):
        if a != b:
            break
        prefix += 1
    if prefix >= 4:
        return 0.6
    return 0.0


def _tokenize(text: str) -> set[str]:
    """Lowercase word + camelCase/snake_case sub-token set, minus stopwords."""
    tokens: set[str] = set()
    for word in _WORD_RE.findall(text):
        lower = word.lower()
        if len(lower) >= 2 and lower not in _STOPWORDS:
            tokens.add(lower)
        # Split identifiers like URLSafeSerializer / get_signature into parts.
        for part in _CAMEL_RE.findall(word):
            p = part.lower()
            if len(p) >= 2 and p not in _STOPWORDS:
                tokens.add(p)
    return tokens


def _lexical_score(query_tokens: set[str], qualified_name: str, text: str) -> float:
    """Score how well a query lexically matches an entity's name and docs.

    Returns roughly [0, 1]. Name matches dominate because, for code docs, the
    entity name is the strongest relevance signal.
    """
    if not query_tokens:
        return 0.0

    name_tokens = _tokenize(qualified_name)
    text_tokens = _tokenize(text)

    name_hits = 0.0
    for qt in query_tokens:
        best = max((_token_match(qt, nt) for nt in name_tokens), default=0.0)
        name_hits += best

    text_hits = sum(1.0 for qt in query_tokens if qt in text_tokens)

    name_score = name_hits / len(query_tokens)
    text_score = text_hits / len(query_tokens)
    # Heavily favor name matches; text matches are a lighter supporting signal.
    return min(1.0, 0.8 * name_score + 0.2 * text_score)
