"""Service-layer error types.

All are `ApplicationError` subclasses (app.core.errors) so they flow through the same
consistent error-response middleware as everything else — a service never needs to know
or care how FastAPI turns an exception into a response body.
"""

from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.errors import ApplicationError


class NotFoundError(ApplicationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=status.HTTP_404_NOT_FOUND)


class ConflictError(ApplicationError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, status_code=status.HTTP_409_CONFLICT, details=details)


class InvalidHierarchyError(ApplicationError):
    """A requested relationship would violate a domain invariant — e.g. a parent in a
    different tenant, or a parent that is retired/decommissioned."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            code, message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, details=details
        )
