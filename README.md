# LubriSense AI

**A production-grade reference platform for condition-driven intelligent lubrication.**

LubriSense AI turns raw lubrication and machine-condition telemetry into maintenance
decisions technicians can trust, delivered early enough to act on, with the evidence and
workflow needed to act quickly — and it improves every time a technician closes the loop.

It is not a dashboard. It is a full industrial flow, built end to end:

```
Physical System → Sensors → Edge → Telemetry → Data Quality → Rules / ML
→ Condition Intelligence → Decision Intelligence → Workflow Intelligence
→ Technician Action → Feedback → Product Learning
```

organized around three intelligence layers:

1. **Machine & Sensor Intelligence** — what is happening?
2. **Decision Intelligence** — what does it mean, and what should we do?
3. **Workflow Intelligence** — how do we act?

AI is not the product. The product is a better maintenance decision, made earlier, with
more confidence, with less manual effort. See `docs/PRODUCT_VISION.md` for the full product
story, `docs/ARCHITECTURE.md` for the end-to-end architecture, `docs/DOMAIN_MODEL.md` for
the personas/physical model/asset hierarchy, `docs/ASSET_HIERARCHY.md` for how that domain
model is actually implemented (schema, tenancy, sensor attachment, seed data), `docs/EVENT_CATALOG.md` for the telemetry and
event contracts, and `docs/FAILURE_MODE_CATALOG.md` for the initial synthetic failure
library.

This repository uses synthetic telemetry throughout. Every synthetic component is
explicitly labeled and built behind a replaceable interface so it can be swapped for a real
industrial integration later without redesigning the platform — see
`docs/ARCHITECTURE.md` §10.

## Current phase

**Phase 2 — Domain Model + Asset Hierarchy.** Phase 1 established the runnable platform
skeleton (FastAPI backend, Next.js frontend, PostgreSQL/TimescaleDB/pgvector, Redis, MQTT,
Kafka, Docker Compose, CI). Phase 2 builds the real, tenant-scoped industrial domain model
on top of it: Tenant → CustomerAccount → Site → Plant → ProductionLine → Machine →
Bearing, plus the full lubrication-system chain (Reservoir/Pump/Controller/Distributor/
Circuit/LubricationPoint) and tenant-safe Sensor/Gateway attachment — with a repository/
service/API layer and a minimal hierarchy-navigation UI. It does **not** yet implement
synthetic telemetry, physical simulation, rules, ML, or the final product dashboard — see
`IMPLEMENTATION_STATUS.md` for the full phase plan and `docs/ASSET_HIERARCHY.md` for the
domain-model implementation detail.

## Services

| Service | Purpose | Local port |
|---|---|---|
| `frontend` | Next.js platform-status page + asset-hierarchy/machine-detail/sensor-inventory UI (Phase 2); the final product UI comes in Phase 28 | `3000` |
| `backend` | FastAPI platform API — health/readiness, system info (Phase 1); domain/intelligence logic in later phases | `8000` |
| `postgres` | PostgreSQL + TimescaleDB + pgvector (`timescale/timescaledb-ha:pg16`) | `5432` |
| `redis` | Redis (connectivity only in Phase 1) | `6379` |
| `mosquitto` | MQTT broker (device/edge transport) | `1883` (+ `9001` websockets) |
| `kafka` | Kafka, KRaft mode (internal platform event backbone) | `9092` |

`ml-service/`, `simulator/`, and `edge/` exist as scaffolds with no Phase 1 runtime
responsibility — see their individual `README.md` files for what they will own and when.

## Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) (backend dependency/environment management)
- Node.js 22+ and npm (frontend)

## Quick start

```bash
cp .env.example .env
docker compose up -d
docker compose ps          # everything should report "healthy"
```

Then, seed the demo asset hierarchy (deterministic, idempotent — safe to re-run):

```bash
cd backend && uv sync --extra dev
DATABASE_URL="postgresql+psycopg://lubrisense:lubrisense@localhost:5432/lubrisense" \
  uv run alembic upgrade head
DATABASE_URL="postgresql+psycopg://lubrisense:lubrisense@localhost:5432/lubrisense" \
  uv run python scripts/seed_demo_data.py
```

Then:

- Frontend platform status: http://localhost:3000
- Asset hierarchy: http://localhost:3000/hierarchy
- Sensor inventory: http://localhost:3000/sensors
- Backend health: http://localhost:8000/health
- Backend readiness: http://localhost:8000/ready
- Backend system info: http://localhost:8000/api/v1/system/info
- Full asset hierarchy API (requires the seeded demo tenant's `X-Tenant-ID` header — see
  `.env.example` / `docs/ASSET_HIERARCHY.md` §3.2): http://localhost:8000/api/v1/hierarchy

For running services outside Docker, running tests, and a full walkthrough, see
**`docs/DEVELOPER_SETUP.md`**.

## Verification commands

```bash
make verify        # lint + typecheck + backend tests + frontend build + MQTT/Kafka checks
make backend-test   # backend pytest suite (requires postgres + redis running)
make mqtt-verify    # MQTT publish/subscribe round trip
make kafka-verify   # Kafka produce/consume round trip
```

See the `Makefile` for the full list of targets (`up`, `down`, `logs`, `migrate`, `lint`,
`typecheck`, `test`, `build`).

## Repository layout

```
frontend/        Next.js product UI
backend/         FastAPI platform backend (domain logic, APIs, persistence)
ml-service/      Model training/evaluation/inference (later phase)
simulator/       Synthetic telemetry / physical-asset simulation (later phase)
edge/            Edge-controller reference implementation (later phase)
infrastructure/  Docker Compose service configuration (Mosquitto, etc.)
docs/            Product, architecture, domain, event, and failure-mode documentation
tests/           Cross-service integration tests (later phase)
scripts/         Developer/operational tooling and verification scripts
```

Full purpose of each directory: `docs/ARCHITECTURE.md` §11.

## Governance documents

- `CLAUDE.md` — project instructions and non-negotiable product/architecture rules
- `LOOP.md` — how implementation work is executed and verified phase by phase
- `IMPLEMENTATION_STATUS.md` — current phase and progress across all planned phases
- `TECHNICAL_DECISIONS.md` — architecture decision records (ADRs)
