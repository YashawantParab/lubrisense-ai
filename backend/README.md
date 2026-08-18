# LubriSense AI — Backend

FastAPI platform backend. Owns telemetry processing, data quality, rules, condition
intelligence, decision intelligence, incidents, maintenance workflow orchestration, and
business metrics (see `docs/ARCHITECTURE.md` §11). Business logic lives in `app/services/`,
never in route handlers.

Phase 1 established the platform foundation (health/readiness, system info, configuration,
structured logging, correlation IDs, consistent error model, database/Redis connectivity,
migrations). Phase 2 adds the real, tenant-scoped industrial domain model — asset
hierarchy, lubrication-system chain, sensors — through the repository/service/API layers.
No simulator, rules, or ML yet — see `IMPLEMENTATION_STATUS.md` for phase boundaries and
`docs/ASSET_HIERARCHY.md` for the domain-model implementation.

## Structure

```
app/
  api/            route handlers (thin; delegate to services) + Pydantic schemas
  core/           config, logging, correlation ID middleware, error model
  domain/         ORM domain models (Tenant, CustomerAccount, ..., Sensor) + enums
  services/       business logic (tenant context, validation, hierarchy rules)
  repositories/   tenant-scoped persistence-layer repositories
  infrastructure/ database/Redis adapters, ORM metadata
  auth/           authentication/authorization (later phase)
  audit/          audit logging (later phase)
  observability/  metrics/tracing (later phase)
alembic/          database migrations
scripts/          seed_demo_data.py — deterministic, idempotent demo dataset
tests/            pytest suite
```

## Local development

This project uses [uv](https://docs.astral.sh/uv/) for dependency and virtual environment
management.

```bash
cd backend
uv sync --extra dev
```

Requires Postgres and Redis reachable via `DATABASE_URL` / `REDIS_URL` (see root
`.env.example`). Easiest path: start them via the root `docker-compose.yml`
(`docker compose up -d postgres redis`), or run the full stack.

Run the API:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run migrations:

```bash
uv run alembic upgrade head
```

Seed the deterministic demo asset hierarchy (safe to re-run):

```bash
uv run python scripts/seed_demo_data.py
```

Run tests / lint / type check:

```bash
uv run pytest
uv run ruff check .
uv run mypy app
```

See `docs/DEVELOPER_SETUP.md` for the full local environment walkthrough.
