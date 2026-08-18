# syntax=docker/dockerfile:1
#
# Build context is the REPO ROOT (see docker-compose.yml `edge` service:
# `build: {context: ., dockerfile: edge/Dockerfile}`), not `edge/` — the edge package has a
# local, editable path dependency on `../simulator` (Phase 5 brief §2: drive
# `SimulationEngine` in-process, don't duplicate simulator logic), so both packages must be
# present, at the SAME relative paths, in both the builder and runtime stages — an editable
# install's `.pth` reference points at `/repo/simulator`, which must still resolve at
# runtime.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /uvx /bin/

WORKDIR /repo

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/repo/edge/.venv

COPY simulator/pyproject.toml simulator/README.md ./simulator/
COPY simulator/simulator ./simulator/simulator
COPY edge/pyproject.toml edge/README.md ./edge/
RUN cd edge && uv sync --no-dev

COPY edge/edge ./edge/edge
COPY edge/scripts ./edge/scripts

# --- runtime: minimal image, non-root user ---
FROM python:3.12-slim AS runtime

RUN groupadd --system edge && useradd --system --gid edge --no-create-home edge

WORKDIR /repo

COPY --from=builder /repo/simulator/simulator ./simulator/simulator
COPY --from=builder /repo/edge/.venv ./edge/.venv
COPY --from=builder /repo/edge/edge ./edge/edge
COPY --from=builder /repo/edge/scripts ./edge/scripts

ENV PATH="/repo/edge/.venv/bin:$PATH" \
    PYTHONPATH="/repo/edge:/repo/simulator" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN mkdir -p /repo/edge/data/edge && chown -R edge:edge /repo/edge/data

USER edge
WORKDIR /repo/edge

VOLUME ["/repo/edge/data"]

CMD ["python", "-m", "edge", "run"]
