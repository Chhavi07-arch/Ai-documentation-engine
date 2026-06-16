"""FastAPI application entrypoint.

Wires together configuration, database initialization, CORS, exception
handlers, and all routers under a versioned ``/api`` prefix.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger
from app.routers import (
    chat,
    changes,
    documentation,
    repositories,
    staleness,
    system,
    webhooks,
)

logger = get_logger("docengine.main")

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize the database on startup."""
    init_db()
    logger.info(
        "AI Documentation Engine v%s started (AI %s).",
        __version__,
        "enabled" if settings.ai_enabled else "disabled — set OPENROUTER_API_KEY",
    )
    yield


app = FastAPI(
    title="AI Documentation Engine",
    description=(
        "Automatically ingest GitHub repositories, generate developer "
        "documentation with LLMs, detect stale docs, and chat over them."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Mount routers under /api.
for module in (system, repositories, documentation, changes, staleness, chat, webhooks):
    app.include_router(module.router, prefix=API_PREFIX)


@app.get("/", tags=["system"], summary="Service banner")
def root() -> dict:
    return {
        "name": "AI Documentation Engine",
        "version": __version__,
        "docs": "/docs",
        "api": API_PREFIX,
    }
