"""OpenRouter AI client — a thin, reusable abstraction over chat + embeddings.

The rest of the app talks to this module rather than to OpenRouter directly, so
the provider/model is configurable in one place and AI features degrade
gracefully when no API key is present.
"""

from __future__ import annotations

import re

import httpx

from app.core.config import settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger

logger = get_logger("docengine.ai")

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class AIService:
    """Wraps OpenRouter's OpenAI-compatible chat and embedding endpoints."""

    def __init__(self) -> None:
        self._model = settings.openrouter_model
        self._embedding_model = settings.openrouter_embedding_model
        self._base_url = settings.openrouter_base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        """True when an API key is configured."""
        return settings.ai_enabled

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": settings.openrouter_app_url,
            "X-Title": settings.openrouter_app_name,
            "Content-Type": "application/json",
        }

    # --- chat completion ---------------------------------------------------

    async def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> str:
        """Run a single chat completion and return the assistant text.

        Raises :class:`AIServiceError` when the key is missing or the upstream
        call fails — callers decide whether to fall back.
        """
        if not self.enabled:
            raise AIServiceError("OpenRouter API key is not configured.")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                data = await self._post_chat(client, system, user, temperature, max_tokens)
        except httpx.HTTPError as exc:
            logger.error("OpenRouter chat transport error: %s", exc)
            raise AIServiceError("Could not reach the AI provider.") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:  # pragma: no cover - defensive
            raise AIServiceError("Malformed response from AI provider.") from exc

    async def _post_chat(
        self,
        client: httpx.AsyncClient,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """POST a chat completion, retrying once with a smaller budget on 402.

        Low-credit OpenRouter accounts return 402 with an "can only afford N
        tokens" hint. We honor that hint and retry once so the request can still
        succeed instead of failing outright.
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        response = await client.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
        )

        if response.status_code == 402:
            affordable = _affordable_tokens(response.text)
            if affordable and affordable < max_tokens:
                logger.info(
                    "Low credits — retrying chat with max_tokens=%d.", affordable
                )
                payload["max_tokens"] = affordable
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "OpenRouter chat error %s: %s",
                exc.response.status_code, exc.response.text[:200],
            )
            raise AIServiceError(
                f"AI request failed: {exc.response.status_code}"
            ) from exc

        return response.json()

    # --- embeddings --------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for ``texts`` via OpenRouter.

        Raises :class:`AIServiceError` on failure; the RAG layer falls back to
        a local hashing embedder when this is unavailable.
        """
        if not self.enabled:
            raise AIServiceError("OpenRouter API key is not configured.")
        if not texts:
            return []

        payload = {"model": self._embedding_model, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("OpenRouter embeddings unavailable: %s", exc)
            raise AIServiceError("Embedding request failed.") from exc

        try:
            return [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError) as exc:  # pragma: no cover - defensive
            raise AIServiceError("Malformed embedding response.") from exc


def _affordable_tokens(error_body: str) -> int | None:
    """Extract the "can only afford N" token hint from a 402 error body."""
    match = re.search(r"can only afford (\d+)", error_body)
    if not match:
        return None
    # Leave a small margin so the retry comfortably fits the budget.
    return max(64, int(match.group(1)) - 16)


# A shared singleton is sufficient — the client is stateless.
ai_service = AIService()
