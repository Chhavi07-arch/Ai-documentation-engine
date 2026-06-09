"""Application-level exceptions and FastAPI exception handlers.

Services raise the domain exceptions defined here; the registered handlers
translate them into clean JSON responses with appropriate HTTP status codes.
This keeps routers thin and error handling consistent across the API.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("docengine.errors")


class AppError(Exception):
    """Base class for expected, user-facing application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_failed"


class IngestionError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "ingestion_failed"


class AIServiceError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "ai_service_error"


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach JSON exception handlers to the FastAPI app."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        # Expected errors are logged at INFO — they are part of normal flow.
        logger.info("AppError [%s]: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # jsonable_encoder strips non-serializable error context (e.g. the
        # underlying ValueError objects Pydantic attaches).
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("validation_failed", "Request validation failed.")
            | {"details": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Unexpected errors are logged at ERROR with a traceback for debugging.
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", "An unexpected error occurred."),
        )
