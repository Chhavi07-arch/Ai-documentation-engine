"""Embedding provider with an automatic local fallback.

Primary path: OpenAI-compatible embeddings via OpenRouter. If that is
unavailable (no key, network error, model not enabled), we fall back to a
deterministic local hashing embedder. The fallback is not semantically as
strong, but it keeps the chatbot fully functional offline and for demos.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.core.config import settings
from app.core.logging import get_logger
from app.core.exceptions import AIServiceError
from app.services.ai_service import ai_service

logger = get_logger("docengine.embeddings")

# Dimensionality of the local fallback embedding.
_LOCAL_DIM = 384
_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]+")


class EmbeddingProvider:
    """Produce embeddings, transparently falling back to a local embedder."""

    def __init__(self) -> None:
        self._mode: str = "unknown"

    @property
    def mode(self) -> str:
        """Either ``"openrouter"`` or ``"local"`` after first use."""
        return self._mode

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Uses OpenRouter only when explicitly enabled AND a key is present;
        otherwise (the default) uses the deterministic local embedder. This
        guarantees every vector in a repository's collection has a consistent
        dimension, which a fixed-dimension vector store requires.
        """
        if not texts:
            return []
        if settings.use_openrouter_embeddings and ai_service.enabled:
            try:
                vectors = await ai_service.embed(texts)
                self._mode = "openrouter"
                return vectors
            except AIServiceError:
                logger.info("Remote embeddings failed; using local embeddings.")
        self._mode = "local"
        return [self._local_embed(t) for t in texts]

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0] if vectors else []

    # --- local fallback ----------------------------------------------------

    def _local_embed(self, text: str) -> list[float]:
        """A deterministic bag-of-words hashing embedding (L2-normalized).

        Each token is hashed into a fixed-size vector with a signed bucket. This
        captures lexical overlap well enough for documentation retrieval when no
        embedding API is available.
        """
        vector = [0.0] * _LOCAL_DIM
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % _LOCAL_DIM
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


embedding_provider = EmbeddingProvider()
