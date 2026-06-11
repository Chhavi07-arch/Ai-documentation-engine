"""FastAPI routers, grouped by resource."""

from app.routers import (
    chat,
    changes,
    documentation,
    repositories,
    staleness,
    system,
)

__all__ = [
    "repositories",
    "documentation",
    "changes",
    "staleness",
    "chat",
    "system",
]
