# syntax=docker/dockerfile:1

# --- builder: resolve and install dependencies into a virtualenv ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml README.md ./
RUN uv sync --no-install-project --no-dev

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --no-dev

# --- runtime: minimal image, non-root user ---
FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app ./app
COPY --from=builder /app/alembic ./alembic
COPY --from=builder /app/alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# /data: the mqtt-bridge service's durable spool (app.pipeline.spool.BridgeSpool, ADR-056).
# Not used by the backend API or telemetry-consumer, but harmless to create in the shared
# image — mirrors edge/Dockerfile's pre-create-and-chown-before-USER pattern.
RUN mkdir -p /data && chown -R app:app /data

USER app

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
