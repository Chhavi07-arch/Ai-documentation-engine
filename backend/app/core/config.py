"""Application configuration.

Settings are loaded from environment variables (and an optional ``.env`` file)
using ``pydantic-settings``. Importing :data:`settings` anywhere in the app
gives a single, validated, strongly-typed configuration object.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = the `backend/` directory (two levels up from this file).
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Every field maps to an environment variable of the same (upper-cased) name.
    Defaults are chosen so the project runs locally with zero configuration,
    except for ``OPENROUTER_API_KEY`` which is required for AI features.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- AI / OpenRouter ---
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="anthropic/claude-sonnet-4-6", alias="OPENROUTER_MODEL"
    )
    openrouter_embedding_model: str = Field(
        default="openai/text-embedding-3-small", alias="OPENROUTER_EMBEDDING_MODEL"
    )
    # Embeddings power RAG retrieval. They default to the deterministic local
    # embedder because (a) it is free and reliable, and (b) a fixed-dimension
    # vector store cannot mix embedders of different dimensions. Chat *answers*
    # always use the OpenRouter LLM regardless of this setting. Opt in to remote
    # embeddings only if your provider/model reliably supports the /embeddings
    # endpoint.
    use_openrouter_embeddings: bool = Field(
        default=False, alias="USE_OPENROUTER_EMBEDDINGS"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_app_url: str = Field(
        default="http://localhost:3000", alias="OPENROUTER_APP_URL"
    )
    openrouter_app_name: str = Field(
        default="AI Documentation Engine", alias="OPENROUTER_APP_NAME"
    )

    # --- AI provider selection ---
    # Which backend serves chat + doc generation:
    #   "auto"       — use Anthropic if an Anthropic key is present (or the key in
    #                  OPENROUTER_API_KEY starts with "sk-ant-"), else OpenRouter
    #   "anthropic"  — call Anthropic's API directly (uses ANTHROPIC_API_KEY)
    #   "openrouter" — call OpenRouter (uses OPENROUTER_API_KEY)
    ai_provider: str = Field(default="auto", alias="AI_PROVIDER")
    # Native Anthropic API key (https://console.anthropic.com/settings/keys),
    # looks like "sk-ant-...". Empty → fall back to OpenRouter / local.
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    # Anthropic model id (no "anthropic/" prefix — that prefix is OpenRouter-only).
    anthropic_model: str = Field(default="claude-sonnet-4-6", alias="ANTHROPIC_MODEL")

    # --- Database ---
    database_url: str = Field(
        default="sqlite:///./docengine.db", alias="DATABASE_URL"
    )

    # --- GitHub webhook ---
    # Shared secret used to verify the HMAC signature GitHub sends with each
    # push event. Leave empty to disable the webhook endpoint (it then returns
    # 503 so changes can't be triggered without a configured secret).
    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")

    # --- Automatic change detection (background polling) ---
    # When enabled, a background task periodically re-runs change detection for
    # every READY repository, so stale-doc flags appear on their own without
    # anyone clicking "Detect changes". This is the polling complement to the
    # event-driven GitHub webhook. Disabled by default so it's an explicit
    # opt-in (a busy server may not want a recurring sweep).
    auto_detect_enabled: bool = Field(default=False, alias="AUTO_DETECT_ENABLED")
    # How often (seconds) to run a detection cycle. Clamped to a 10s floor so a
    # mistyped tiny value can't hammer the server.
    auto_detect_interval_seconds: int = Field(
        default=300, alias="AUTO_DETECT_INTERVAL_SECONDS"
    )
    # When True, each cycle first git-fetches the latest commits (catches pushes
    # to GitHub). When False, it only re-parses the local working tree (catches
    # local edits; lighter and never touches the network). Fetching resets the
    # working copy to remote HEAD, so leave this False if you rely on local edits.
    auto_detect_sync_remote: bool = Field(
        default=False, alias="AUTO_DETECT_SYNC_REMOTE"
    )

    # --- CORS ---
    # Cover both common Next.js dev ports (3000, and 3001 when 3000 is taken)
    # on localhost and 127.0.0.1, so a clean checkout works regardless of where
    # `next dev` lands. Override via CORS_ORIGINS in production.
    cors_origins: str = Field(
        default=(
            "http://localhost:3000,http://localhost:3001,"
            "http://127.0.0.1:3000,http://127.0.0.1:3001"
        ),
        alias="CORS_ORIGINS",
    )

    # --- Storage directories ---
    repositories_dir: str = Field(default="../repositories", alias="REPOSITORIES_DIR")
    docs_storage_dir: str = Field(default="../docs_storage", alias="DOCS_STORAGE_DIR")
    vector_storage_dir: str = Field(
        default="../vector_storage", alias="VECTOR_STORAGE_DIR"
    )

    # --- Derived helpers ---------------------------------------------------

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def repositories_path(self) -> Path:
        return self._resolve(self.repositories_dir)

    @property
    def docs_storage_path(self) -> Path:
        return self._resolve(self.docs_storage_dir)

    @property
    def vector_storage_path(self) -> Path:
        return self._resolve(self.vector_storage_dir)

    @property
    def resolved_provider(self) -> str:
        """Which AI backend is active: "anthropic" or "openrouter"."""
        if self.ai_provider in ("anthropic", "openrouter"):
            return self.ai_provider
        # "auto": prefer Anthropic when an Anthropic key is configured — including
        # the common case of an "sk-ant-..." key pasted into OPENROUTER_API_KEY.
        if self.anthropic_api_key.strip():
            return "anthropic"
        if self.openrouter_api_key.strip().startswith("sk-ant-"):
            return "anthropic"
        return "openrouter"

    @property
    def active_ai_key(self) -> str:
        """The API key for the resolved provider."""
        if self.resolved_provider == "anthropic":
            return self.anthropic_api_key.strip() or self.openrouter_api_key.strip()
        return self.openrouter_api_key.strip()

    @property
    def active_model(self) -> str:
        """The chat/generation model id for the resolved provider."""
        if self.resolved_provider == "anthropic":
            return self.anthropic_model
        return self.openrouter_model

    @property
    def ai_enabled(self) -> bool:
        """True when a usable key is configured for the resolved provider."""
        return bool(self.active_ai_key)

    def _resolve(self, value: str) -> Path:
        """Resolve a (possibly relative) storage path against the backend root."""
        path = Path(value)
        if not path.is_absolute():
            path = (BACKEND_ROOT / path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance (singleton)."""
    return Settings()


settings = get_settings()
