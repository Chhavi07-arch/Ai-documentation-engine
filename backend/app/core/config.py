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

    # --- Database ---
    database_url: str = Field(
        default="sqlite:///./docengine.db", alias="DATABASE_URL"
    )

    # --- GitHub webhook ---
    # Shared secret used to verify the HMAC signature GitHub sends with each
    # push event. Leave empty to disable the webhook endpoint (it then returns
    # 503 so changes can't be triggered without a configured secret).
    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")

    # --- CORS ---
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

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
    def ai_enabled(self) -> bool:
        """True when an OpenRouter key is configured."""
        return bool(self.openrouter_api_key.strip())

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
