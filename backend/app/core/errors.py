"""Consistent API error model.

Every error response — whether raised deliberately by domain code or caught as an
unexpected exception — takes the same shape:

    {
      "code": "DATABASE_UNAVAILABLE",
      "message": "Database is temporarily unavailable.",
      "details": {},
      "correlation_id": "..."
    }

Stack traces and internal exception details are never included in the response body;
they belong in structured logs only.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_correlation_id

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    """Base class for deliberate, domain-meaningful API errors.

    Raise a subclass (or this class directly) anywhere in application code to produce a
    well-formed error response without hand-building JSON in route handlers.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ServiceUnavailableError(ApplicationError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code, message, status_code=status.HTTP_503_SERVICE_UNAVAILABLE, details=details
        )


def _error_body(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = jsonable_encoder(
        {
            "code": code,
            "message": message,
            "details": details,
            "correlation_id": get_correlation_id(),
        }
    )
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def handle_application_error(
        _request: Request, exc: ApplicationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("HTTP_ERROR", str(exc.detail), {}),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "VALIDATION_ERROR",
                "Request validation failed.",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception while processing request", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                "INTERNAL_SERVER_ERROR",
                "An unexpected error occurred.",
                {},
            ),
        )
