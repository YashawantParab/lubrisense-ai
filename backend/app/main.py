"""FastAPI application factory.

Wires together configuration, structured logging, correlation ID propagation, the
consistent error model, infrastructure connections (database, Redis), and versioned API
routing. Domain/business logic does not live here — this module only assembles the app.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api import health
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient
from app.observability.http_metrics import HTTPMetricsMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database = Database(settings)
        app.state.redis_client = RedisClient(settings)
        logger.info("Application startup complete", extra={"environment": settings.app_env})
        try:
            yield
        finally:
            await app.state.database.dispose()
            await app.state.redis_client.close()
            logger.info("Application shutdown complete")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts_list,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[settings.correlation_id_header],
    )
    app.add_middleware(
        CorrelationIdMiddleware,
        header_name=settings.correlation_id_header,
    )
    app.add_middleware(HTTPMetricsMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_v1_router)

    return app


app = create_app()
