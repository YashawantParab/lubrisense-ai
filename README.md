# LubriSense AI

**A production-grade reference platform for condition-driven intelligent lubrication.**

LubriSense AI turns raw lubrication and machine-condition telemetry into maintenance
decisions technicians can trust, delivered early enough to act on, with the evidence and
workflow needed to act quickly — and it improves every time a technician closes the loop.

It is not a dashboard. It is a full industrial flow, implemented end to end:

```
Sensor → Signal → Condition → Decision → Action → Outcome → Learning
```

or, in more detail:

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
story, `docs/ARCHITECTURE.md` for the end-to-end architecture (including the full mermaid
diagram behind the flow above), `docs/DOMAIN_MODEL.md` for the personas/physical model/asset
hierarchy, `docs/ASSET_HIERARCHY.md` for how that domain model is implemented, and
`docs/FAILURE_MODE_CATALOG.md` for the synthetic failure library this reference platform
demonstrates.

**New here? Start with `docs/DEMO_GUIDE.md`** — a 60-90 second and a full 5-10 minute
walkthrough of the flagship demo story, with real screenshots.

This repository uses synthetic telemetry throughout. Every synthetic component is
explicitly labeled and built behind a replaceable interface so it can be swapped for a real
industrial integration later without redesigning the platform — see `docs/ARCHITECTURE.md`
§10 and `docs/INDUSTRIAL_ADOPTION.md` for exactly what that would take.

## Current status

Phases 1 through 36 are complete: the full chain above is implemented and demonstrated end
to end on a real flagship asset (telemetry → baselines → deterministic rules → ML → state
estimation (Kalman filtering) → condition/decision/prognostic intelligence → incident
management → maintenance workflow → RAG-grounded assistant with citations → technician
feedback → resolution), backed by real multi-tenant identity/auth/RBAC, auditability,
observability, resilience/degradation handling, CI/CD, and a comprehensive test suite. See
`IMPLEMENTATION_STATUS.md` for the phase-by-phase detail and `TECHNICAL_DECISIONS.md` for
every architecture decision (ADR) made along the way, including honestly-documented known
limitations.

## Services

| Service | Purpose | Local port |
|---|---|---|
| `frontend` | Next.js product UI — overview, fleet, machine detail, incidents, maintenance, knowledge, assistant, metrics, system/admin views | `3000` |
| `backend` | FastAPI platform API — all domain/intelligence logic, condition/decision engines, incident/maintenance workflow, RAG, agent tools | `8000` |
| `mqtt-bridge` | Ingests device/edge telemetry off MQTT and republishes onto Kafka | — |
| `telemetry-consumer` | Consumes Kafka telemetry, validates/dedupes/persists to TimescaleDB | — |
| `data-quality-worker` | Continuous sensor/stream data-quality evaluation (staleness, drift, stuck sensors, etc.) | — |
| `baseline-worker` | Builds/maintains rolling and contextual sensor baselines | — |
| `rules-worker` | Deterministic rule and cross-signal pattern evaluation | — |
| `feature-worker` | Phase 10 feature computation feeding ML and state estimation | — |
| `edge` | Reference edge-controller implementation (local rules, buffering, store-and-forward) | — |
| `postgres` | PostgreSQL + TimescaleDB + pgvector (`timescale/timescaledb-ha:pg16`) | `5432` |
| `redis` | Caching / rate limiting | `6379` |
| `mosquitto` | MQTT broker (device/edge transport) | `1883` (+ `9001` websockets) |
| `kafka` | Kafka, KRaft mode (internal platform event backbone) | `9092` |

`ml-service/` (model training/evaluation/registry) and `simulator/` (synthetic
telemetry/physical-asset simulation) are separate, independently-run Python projects — see
their own `README.md`/`docs/MLOPS.md`/`docs/SIMULATOR.md`.

## Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) (backend/ml-service/simulator/edge dependency management)
- Node.js 22+ and npm (frontend)

## Quick start

```bash
cp .env.example .env
make demo-reset
```

`make demo-reset` (equivalently `./scripts/demo-reset.sh`) brings the whole stack up,
applies migrations, seeds the base demo asset hierarchy, seeds the approved knowledge
corpus, and resets the flagship machine's full demo story — a known, deterministic,
demo-ready state in one command. It is safe to run repeatedly.

Then:

- Product UI: http://localhost:3000
- Flagship machine (the demo story): http://localhost:3000/machines/88551bef-3149-5a8d-9645-bcd9502f4795
- Backend health / readiness / metrics: http://localhost:8000/health, `/ready`, `/metrics`

See **`docs/DEMO_GUIDE.md`** for a guided walkthrough, and **`docs/DEVELOPER_SETUP.md`** for
running services outside Docker, running tests, and day-to-day development workflow.

## Verification commands

```bash
make verify        # lint + typecheck + all test suites + frontend build + pipeline/rules/baseline/data-quality checks
make demo-reset     # bring the stack to a known demo-ready state (idempotent)
make backend-test   # backend pytest suite (requires postgres + redis running)
make test           # backend + simulator + edge + ml-service test suites
```

See the `Makefile` for the full list of targets, and `.github/workflows/ci.yml` for what
runs in CI on every change (`docs/CI_CD.md`).

## Repository layout

```
frontend/        Next.js product UI
backend/         FastAPI platform backend (domain logic, APIs, persistence, workers)
ml-service/      Model training/evaluation/registry/promotion
simulator/       Synthetic telemetry / physical-asset simulation
edge/            Edge-controller reference implementation
infrastructure/  Docker Compose service configuration (Mosquitto, etc.)
docs/            Product, architecture, domain, event, and failure-mode documentation
scripts/         Developer/operational tooling, verification scripts, demo-reset
```

Full purpose of each directory: `docs/ARCHITECTURE.md` §11.

## Governance documents

- `CLAUDE.md` — project instructions and non-negotiable product/architecture rules
- `LOOP.md` — how implementation work is executed and verified phase by phase
- `IMPLEMENTATION_STATUS.md` — phase-by-phase progress across the whole build
- `TECHNICAL_DECISIONS.md` — architecture decision records (ADRs), including honestly-tracked
  known limitations
- `docs/DEMO_GUIDE.md` — guided product walkthrough
- `docs/INDUSTRIAL_ADOPTION.md` — what is real vs. synthetic, and what a real deployment
  would still require
