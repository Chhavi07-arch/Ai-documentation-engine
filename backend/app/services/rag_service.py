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
from app.models.enums import EntityKind
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

# Relevance gate for the *remote* (dense semantic) embedder: its cosine scores
# are meaningful, so a low combined floor plus the LLM's grounding instruction
# is enough to reject off-topic queries.
_RELEVANCE_THRESHOLD = 0.05
# The *local* hashing embedder is noisier: genuinely off-topic queries still
# land cosine ~0.3-0.4 against unrelated chunks (hash collisions on common
# tokens), so a pure-vector floor would happily "answer" nonsense. We require
# concrete lexical evidence instead: either a match against the entity *name*
# (the strongest signal for code docs), several distinct query terms appearing
# in the doc text, or an exceptionally strong vector match. A junk query that
# merely shares one incidental common word with the docs has none of these and
# is correctly reported as "not found".
_LOCAL_MIN_NAME = 0.6     # ≥ one substring-or-better query↔name token match
_LOCAL_MIN_TEXT = 2.0     # ≥ two distinct query terms present in the doc text
_LOCAL_STRONG_VECTOR = 0.72   # well above the observed off-topic noise ceiling
_NOT_FOUND = "Information not found in documentation."


def _is_not_found(answer: str) -> bool:
    """True if the LLM answer is (just) the not-found sentinel.

    The model is instructed to reply with the exact sentinel when the context
    doesn't answer the question; tolerate trailing punctuation/quotes/whitespace
    so the response is recognized regardless of minor formatting.
    """
    normalized = (answer or "").strip().strip('"').rstrip(" .").lower()
    return normalized == _NOT_FOUND.rstrip(" .").lower()


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

        # High-level "explain the whole codebase" questions name no specific
        # entity, so the per-entity relevance gate below would (correctly, for
        # its purpose) reject them as "not found". Treat them instead as an
        # overview request grounded in the repository's top-level structure.
        if _is_overview_query(message):
            overview = await self._overview_answer(repo, message)
            if overview is not None:
                return overview

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
        if embedding_provider.mode == "openrouter":
            relevant = [
                h for h in ranked if h["combined_score"] >= _RELEVANCE_THRESHOLD
            ][:top_k]
        else:
            # Local hashing embedder — gate on a real lexical signal (name match
            # or several distinct doc-text terms) or a very strong vector match,
            # so off-topic questions are honestly rejected. A single incidental
            # shared word is NOT enough.
            relevant = [
                h
                for h in ranked
                if h["name_hits"] >= _LOCAL_MIN_NAME
                or h["text_hits"] >= _LOCAL_MIN_TEXT
                or h["vector_score"] >= _LOCAL_STRONG_VECTOR
            ][:top_k]

        # De-duplicate by entity so multiple chunks of the same entity surface
        # as one citation (keeping the highest-scoring chunk's excerpt).
        sources: list[dict] = []
        seen_sources: set[str] = set()
        for h in relevant:
            qn = h["metadata"].get("qualified_name", "unknown")
            if qn in seen_sources:
                continue
            seen_sources.add(qn)
            sources.append(
                {
                    "qualified_name": qn,
                    "relative_path": h["metadata"].get("relative_path", ""),
                    "kind": h["metadata"].get("kind", ""),
                    "score": round(h["combined_score"], 3),
                    "excerpt": truncate(h["text"], 320),
                }
            )

        if not relevant:
            return {"answer": _NOT_FOUND, "sources": [], "grounded": False}

        answer = await self._answer(message, relevant)
        # Even with relevant chunks retrieved, the LLM may judge that they don't
        # actually answer the question and return the not-found sentinel. In that
        # case the reply is NOT grounded — drop the sources so the UI never shows
        # citations next to an "Information not found" answer.
        if _is_not_found(answer):
            return {"answer": _NOT_FOUND, "sources": [], "grounded": False}
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
            lexical, name_hits, text_hits = _lexical_breakdown(
                query_tokens,
                meta.get("qualified_name", ""),
                h.get("text", ""),
            )
            # Keep the components around so the relevance gate can reason about
            # name vs. text vs. vector evidence separately (see RAGService.chat).
            h["vector_score"] = h.get("score", 0.0)
            h["name_hits"] = name_hits
            h["text_hits"] = text_hits
            # Vector score and lexical score are both ~[0, 1]; weight lexical
            # heavily because exact-name matches are the strongest signal here.
            h["combined_score"] = h["vector_score"] + 1.5 * lexical
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
        """Offline answer: surface the most relevant documentation verbatim.

        With no LLM configured the assistant cannot compose a prose answer, so
        it grounds the response in the single best-matching doc excerpt rather
        than inventing one — keeping the no-hallucination guarantee intact.
        """
        top = hits[0]
        name = top["metadata"].get("qualified_name", "the documentation")
        return (
            f"_Showing the most relevant documentation for_ `{name}`_:_"
            f"\n\n{truncate(top['text'], 800)}"
        )

    async def _overview_answer(self, repo: Repository, message: str) -> dict | None:
        """Answer a high-level question grounded in the repo's top-level shape.

        Rather than a single best-matching entity, this gathers the repository's
        modules and classes (preferring documented ones) and either composes a
        prose summary with the LLM or, offline, renders a deterministic
        structured overview. Returns ``None`` if there's nothing to summarize so
        the caller can fall through to normal retrieval.
        """
        modules = list(
            self.db.scalars(
                select(CodeEntity).where(
                    CodeEntity.repository_id == repo.id,
                    CodeEntity.kind == EntityKind.MODULE.value,
                )
            ).all()
        )
        classes = list(
            self.db.scalars(
                select(CodeEntity).where(
                    CodeEntity.repository_id == repo.id,
                    CodeEntity.kind == EntityKind.CLASS.value,
                )
            ).all()
        )
        if not modules and not classes:
            return None

        # Documented entities first (a docstring is the strongest summary
        # signal), then a stable path/name order. Cap counts so the answer — and
        # the LLM prompt — stays focused on the most informative pieces.
        top_modules = sorted(
            modules, key=lambda e: (e.docstring is None, e.relative_path or e.qualified_name)
        )[:20]
        top_classes = sorted(
            classes, key=lambda e: (e.docstring is None, e.qualified_name)
        )[:15]

        sources = [
            {
                "qualified_name": e.qualified_name,
                "relative_path": e.relative_path,
                "kind": e.kind,
                "score": 1.0,
                "excerpt": truncate(_first_line(e.docstring) or e.signature, 320),
            }
            for e in (top_modules + top_classes)
            if e.docstring or e.signature
        ][:8]

        if ai_service.enabled:
            context_blocks = [
                f"Source: {e.qualified_name} ({e.kind})\n"
                + truncate(e.docstring or e.signature or "", 500)
                for e in (top_modules + top_classes)
                if e.docstring or e.signature
            ][:18]
            prompt = build_chat_prompt(question=message, context_blocks=context_blocks)
            try:
                answer = await ai_service.complete(
                    system=CHAT_SYSTEM_PROMPT,
                    user=prompt,
                    temperature=0.1,
                    max_tokens=700,
                )
                return {"answer": answer, "sources": sources, "grounded": True}
            except AIServiceError:
                pass  # fall through to the deterministic overview

        return {
            "answer": self._structural_overview(repo, top_modules, top_classes),
            "sources": sources,
            "grounded": True,
        }

    def _structural_overview(
        self,
        repo: Repository,
        modules: list[CodeEntity],
        classes: list[CodeEntity],
    ) -> str:
        """Render a deterministic codebase overview from module/class docstrings."""
        lines = [
            f"# Overview: {repo.full_name}",
            "",
            f"This repository has **{repo.file_count} files** and "
            f"**{repo.entity_count} documented entities**.",
        ]
        if modules:
            lines += ["", "## Modules"]
            for m in modules:
                desc = _first_line(m.docstring)
                path = m.relative_path or m.qualified_name
                lines.append(f"- `{path}`" + (f" — {desc}" if desc else ""))
        if classes:
            lines += ["", "## Key classes"]
            for c in classes:
                desc = _first_line(c.docstring)
                lines.append(f"- `{c.qualified_name}`" + (f" — {desc}" if desc else ""))
        lines += [
            "",
            "> Structured overview generated from module and class docstrings. "
            "Re-run “Generate docs” with AI available, or ask about a specific "
            "function or class, for a richer answer.",
        ]
        return "\n".join(lines)


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


# An overview question pairs an intent verb ("explain", "overview", "summarize"
# …) with a whole-codebase noun ("codebase", "repo", "project" …), or is a
# self-contained phrase like "what does this project do". Such queries name no
# specific entity, so they bypass the per-entity relevance gate and are answered
# from the repository's top-level structure instead.
_OVERVIEW_VERB = re.compile(
    r"\b(explain|describe|overview|summar(y|ize|ise)|architecture|structure|"
    r"walk\s+me\s+through|high[-\s]?level|get(ting)?\s+started|tour|onboard)\b",
    re.IGNORECASE,
)
_OVERVIEW_NOUN = re.compile(
    r"\b(code\s?base|repo(sitory)?|project|the\s+code|this\s+code|app|application|"
    r"library|package|system|everything|whole\s+thing)\b",
    re.IGNORECASE,
)
_OVERVIEW_PHRASE = re.compile(
    r"what\s+(does|is)\s+(this|the|it)\b|what'?s\s+(this|it)\b|"
    r"how\s+(is|does)\s+(this|the)\s+(code\s?base|repo|repository|project|code)\b",
    re.IGNORECASE,
)


def _is_overview_query(message: str) -> bool:
    """True if the question is about the codebase as a whole (no single entity)."""
    if _OVERVIEW_PHRASE.search(message):
        return True
    return bool(_OVERVIEW_VERB.search(message) and _OVERVIEW_NOUN.search(message))


def _first_line(text: str | None) -> str:
    """First non-empty, stripped line of a docstring (its summary line)."""
    if not text:
        return ""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


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


def _lexical_breakdown(
    query_tokens: set[str], qualified_name: str, text: str
) -> tuple[float, float, float]:
    """Score how well a query lexically matches an entity's name and docs.

    Returns ``(normalized_score, name_hits, text_hits)``:

    - ``normalized_score`` is roughly [0, 1] and drives ranking. Name matches
      dominate because, for code docs, the entity name is the strongest signal.
    - ``name_hits`` is the *unnormalized* sum of query↔name token matches and
      ``text_hits`` the count of distinct query terms present in the doc text.
      Both are independent of query length, which makes them robust relevance
      gates: a genuinely off-topic query scores 0 on both regardless of phrasing,
      and a query that merely shares one incidental common word scores text_hits
      of just 1 — below the gate — so it is still rejected.
    """
    if not query_tokens:
        return 0.0, 0.0, 0.0

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
    normalized = min(1.0, 0.8 * name_score + 0.2 * text_score)
    return normalized, name_hits, text_hits
