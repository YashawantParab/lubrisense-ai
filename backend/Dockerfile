# syntax=docker/dockerfile:1
#
# Build context is the REPO ROOT (see docker-compose.yml: `build: {context: .,
# dockerfile: backend/Dockerfile}`), not `backend/` — since Phase 11, the backend has a
# local, editable path dependency on `../ml-service` (ADR-090: `ml-service` stays a
# separate package, consumed the same way `edge` already consumes `../simulator` —
# see edge/Dockerfile's own comment for why both packages must be present, at the SAME
# relative paths, in both the builder and runtime stages).

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /uvx /bin/

WORKDIR /repo

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/repo/backend/.venv

COPY ml-service/pyproject.toml ml-service/README.md ./ml-service/
COPY ml-service/ml_service ./ml-service/ml_service
COPY backend/pyproject.toml backend/README.md ./backend/
RUN cd backend && uv sync --no-install-project --no-dev

COPY backend/app ./backend/app
COPY backend/alembic ./backend/alembic
COPY backend/alembic.ini ./backend/
RUN cd backend && uv sync --no-dev

# --- runtime: minimal image, non-root user ---
FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /repo

COPY --from=builder /repo/ml-service/ml_service ./ml-service/ml_service
COPY --from=builder /repo/backend/.venv ./backend/.venv
COPY --from=builder /repo/backend/app ./backend/app
COPY --from=builder /repo/backend/alembic ./backend/alembic
COPY --from=builder /repo/backend/alembic.ini ./backend/

# Real, already-trained model registry (Phase 11) — committed to git specifically so it
# survives a fresh checkout (see ml-service/artifacts/models' entry in .gitignore). Copied
# straight from the build context (not `--from=builder`, which never receives this path —
# only ml-service/ml_service package code does). docker-compose.yml's local dev mode
# bind-mounts this same host directory read-only at the identical container path instead
# of baking it in (so a fresh local training run is picked up without a rebuild); a hosted
# deploy has no host filesystem to mount from, so it needs its own copy of the same real
# data at the same path `ML_ARTIFACTS_DIR` expects.
COPY ml-service/artifacts/models /data/ml-artifacts

ENV PATH="/repo/backend/.venv/bin:$PATH" \
    PYTHONPATH="/repo/backend:/repo/ml-service" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# /data: the mqtt-bridge service's durable spool (app.pipeline.spool.BridgeSpool, ADR-056).
# Not used by the backend API or telemetry-consumer, but harmless to create in the shared
# image — mirrors edge/Dockerfile's pre-create-and-chown-before-USER pattern.
RUN mkdir -p /data && chown -R app:app /data

USER app
WORKDIR /repo/backend

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=15s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f\"http://localhost:{os.getenv('PORT', '8000')}/health\")" || exit 1

# Phase 33 perf finding: a single uvicorn worker pinned request handling to one CPU
# core, measured at ~103% CPU under 10 concurrent requests while the Docker host had 12
# cores idle — the backend was CPU-bound on a single process, not on DB connections
# (raising the pool size alone did not help). `UVICORN_WORKERS` defaults to 4, a
# proportionate value for this reference platform's target scale (see
# docs/PERFORMANCE.md), not the full host core count. Known consequence: in-process
# singletons (e.g. the Phase 27 LLM circuit breaker) become per-worker rather than
# globally shared — still functionally correct, just independently tracked per worker.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-4}"]