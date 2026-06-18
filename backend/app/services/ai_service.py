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
        self._embedding_model = settings.openrouter_embedding_model
        self._base_url = settings.openrouter_base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        """True when an API key is configured for the resolved provider."""
        return settings.ai_enabled

    @property
    def provider(self) -> str:
        """The active backend: "anthropic" or "openrouter"."""
        return settings.resolved_provider

    @property
    def model(self) -> str:
        return settings.active_model

    @property
    def _model(self) -> str:  # backwards-compatible alias used internally
        return settings.active_model

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

        Routes to Anthropic's native API or OpenRouter based on the resolved
        provider. Raises :class:`AIServiceError` when the key is missing or the
        upstream call fails — callers decide whether to fall back.
        """
        if not self.enabled:
            raise AIServiceError("No AI API key is configured.")

        if self.provider == "anthropic":
            return await self._complete_anthropic(system, user, temperature, max_tokens)

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

    async def _complete_anthropic(
        self, system: str, user: str, temperature: float, max_tokens: int
    ) -> str:
        """Chat completion via Anthropic's native Messages API (official SDK)."""
        from anthropic import AsyncAnthropic
        from anthropic import APIStatusError, APIError

        client = AsyncAnthropic(api_key=settings.active_ai_key, timeout=120.0)
        try:
            message = await client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except APIStatusError as exc:
            logger.error("Anthropic chat error %s: %s", exc.status_code, str(exc)[:200])
            raise AIServiceError(f"AI request failed: {exc.status_code}") from exc
        except APIError as exc:
            logger.error("Anthropic chat error: %s", exc)
            raise AIServiceError("Could not reach the AI provider.") from exc

        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ).strip()
        if not text:
            raise AIServiceError("Empty response from AI provider.")
        return text

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

    async def diagnose(self) -> dict:
        """Make a tiny live call to verify the AI actually works.

        Returns a structured result including the real upstream status and error
        body, so misconfiguration (bad key, no credits, unknown model) can be
        diagnosed without digging through server logs.
        """
        if not self.enabled:
            return {"ok": False, "reason": "no_api_key", "provider": self.provider, "model": self._model}

        if self.provider == "anthropic":
            try:
                await self._complete_anthropic("", "ping", 0.0, 5)
                return {"ok": True, "provider": "anthropic", "model": self._model}
            except AIServiceError as exc:
                return {
                    "ok": False, "reason": "anthropic_error",
                    "detail": str(exc)[:300], "provider": "anthropic", "model": self._model,
                }

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            return {
                "ok": False, "reason": "transport_error",
                "detail": str(exc)[:300], "provider": "openrouter", "model": self._model,
            }
        if r.status_code == 200:
            return {"ok": True, "provider": "openrouter", "model": self._model}
        return {
            "ok": False, "reason": f"http_{r.status_code}",
            "detail": r.text[:400], "provider": "openrouter", "model": self._model,
        }

    # --- embeddings --------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for ``texts`` via OpenRouter.

        Raises :class:`AIServiceError` on failure; the RAG layer falls back to
        a local hashing embedder when this is unavailable.
        """
        if not self.enabled:
            raise AIServiceError("OpenRouter API key is not configured.")
        if self.provider != "openrouter":
            # Anthropic has no embeddings endpoint — fall back to the local embedder.
            raise AIServiceError("Remote embeddings are only available via OpenRouter.")
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
