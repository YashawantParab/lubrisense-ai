"""Correlation ID middleware.

Accepts an incoming correlation ID (from `X-Correlation-ID` by default, configurable via
`CORRELATION_ID_HEADER`) if it looks like a valid identifier, otherwise generates one. The
ID is stored in request-scoped context (so log lines emitted while handling the request can
include it — see `app.core.logging`), attached to `request.state`, and echoed back in the
response headers.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import set_correlation_id

_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _generate_correlation_id() -> str:
    return str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Callable, *, header_name: str) -> None:  # type: ignore[type-arg]
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(self.header_name)
        is_valid_incoming = bool(incoming and _VALID_CORRELATION_ID.match(incoming))
        correlation_id = incoming if is_valid_incoming and incoming else _generate_correlation_id()

        set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers[self.header_name] = correlation_id
        return response
