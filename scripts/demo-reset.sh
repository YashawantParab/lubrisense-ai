#!/usr/bin/env bash
# One deterministic command to bring the whole platform to a known, demo-ready state:
# stack up, migrations applied, base asset hierarchy seeded, approved knowledge corpus
# seeded, and the flagship machine's full story (telemetry -> baseline -> rule finding
# -> state estimate -> condition -> decision -> incident -> maintenance -> recovery)
# reset and rebuilt from scratch.
#
# Safe to run repeatedly: every step here is independently idempotent (`seed_demo_data.py`
# upserts by deterministic UUID, `seed_knowledge_corpus.py` upserts by document_key,
# `seed_flagship_story.py` deletes and rebuilds only its own dedicated flagship machine's
# telemetry/state estimates before reseeding — see ADR-173 in TECHNICAL_DECISIONS.md).
# Nothing here touches any other tenant, machine, or developer's local data.
#
# Usage:
#   ./scripts/demo-reset.sh
#   make demo-reset
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPOSE="${COMPOSE:-docker compose}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-lubrisense-postgres}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-lubrisense-backend}"

step() { echo; echo "==> $1"; }

step "Starting the platform stack (no-op if already up)"
$COMPOSE up -d

step "Waiting for postgres and backend to report healthy"
for c in "$POSTGRES_CONTAINER" "$BACKEND_CONTAINER"; do
  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "starting")"
    [ "$status" = "healthy" ] && break
    sleep 2
  done
  if [ "$status" != "healthy" ]; then
    echo "demo-reset FAILED: container '$c' did not become healthy in time." >&2
    exit 1
  fi
done

step "Applying database migrations"
(cd backend && uv run alembic upgrade head)

step "Seeding the base demo asset hierarchy (idempotent)"
(cd backend && uv run python scripts/seed_demo_data.py)

step "Seeding the approved knowledge corpus (idempotent)"
(cd backend && uv run python scripts/seed_knowledge_corpus.py)

step "Resetting and seeding the flagship machine's full story"
(cd backend && uv run python scripts/seed_flagship_story.py)

echo
echo "demo-reset: DONE — the platform is in a known demo-ready state."
echo "Frontend:   http://localhost:3000"
echo "Flagship:   http://localhost:3000/machines/88551bef-3149-5a8d-9645-bcd9502f4795"
