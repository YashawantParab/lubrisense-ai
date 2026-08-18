# Developer Setup

This walks a new engineer through running the platform locally: what to install, how to
start the stack, and how to verify the platform foundation (Phase 1) and the asset
hierarchy (Phase 2) yourself rather than taking it on faith.

## 1. Prerequisites

- **Docker** and **Docker Compose** (`docker compose version`)
- **[uv](https://docs.astral.sh/uv/)** — backend dependency/environment manager
  (`uv --version`). `uv` also manages the Python interpreter itself; you do not need a
  specific system Python version installed.
- **Node.js 22+** and **npm** (`node --version`, `npm --version`) — frontend
- **make** (optional but recommended — every command below has a `make` target)

## 2. Clone and configure

```bash
git clone <this-repo>
cd lubrisense-ai
cp .env.example .env
```

`.env` is git-ignored. The defaults in `.env.example` work as-is for local development —
no values are required to change to get started.

## 3. Start the platform stack

```bash
docker compose up -d
docker compose ps
```

Wait for every service to report `healthy`. First run will take longer while images are
pulled and the backend/frontend images are built. Typical steady-state boot time after
images are cached: well under a minute.

If a service fails to become healthy, check its logs:

```bash
docker compose logs <service-name>   # e.g. postgres, backend, kafka
```

## 4. Verify the backend API

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:8000/ready | python3 -m json.tool
curl -s http://localhost:8000/api/v1/system/info | python3 -m json.tool
```

`/health` should return `{"status": "ok"}`. `/ready` should return `{"status": "ready", ...}`
with `database` and `redis` both `healthy: true`. Every response includes an
`X-Correlation-ID` response header — pass your own via a request header to see it echoed
back:

```bash
curl -s -i -H "X-Correlation-ID: my-test-id" http://localhost:8000/health | grep -i x-correlation-id
```

A request to a non-existent path shows the consistent error shape:

```bash
curl -s http://localhost:8000/nope | python3 -m json.tool
```

## 5. Verify the frontend

Open http://localhost:3000. You should see the LubriSense AI platform-status page showing:

- **Frontend**: Running, with the resolved environment and API base URL
- **Backend connectivity**: live result of `GET /ready`, including per-dependency status
- **Backend system info**: live result of `GET /api/v1/system/info`

Once you've run migrations and seeded demo data (steps 7–8 below), also check:
http://localhost:3000/hierarchy (asset hierarchy tree) and http://localhost:3000/sensors
(sensor inventory).

If backend connectivity shows "Unreachable," confirm the backend container is healthy
(`docker compose ps`) and that `NEXT_PUBLIC_API_BASE_URL` in `.env` matches how you're
accessing the stack.

## 6. Verify MQTT and Kafka

```bash
make mqtt-verify
make kafka-verify
```

Both scripts drive the client tooling bundled inside the Mosquitto/Kafka containers
themselves (via `docker exec`) and print `PASSED`/`FAILED`. See `scripts/README.md`.

## 7. Run database migrations

Migrations run automatically against whatever `DATABASE_URL` points to. Against the
Dockerized Postgres:

```bash
cd backend
uv sync --extra dev
DATABASE_URL="postgresql+psycopg://lubrisense:lubrisense@localhost:5432/lubrisense" \
  uv run alembic upgrade head
```

(`make migrate` runs the same command assuming the default local `.env` values.) Confirm:

```bash
docker exec lubrisense-postgres psql -U lubrisense -d lubrisense -c "\dt"
```

You should see all 18 tables, including `tenant`, `customer_account`, `machine`, `sensor`,
etc. — see `docs/ASSET_HIERARCHY.md` for the full schema.

## 8. Seed the demo asset hierarchy

Deterministic and idempotent — safe to run more than once:

```bash
cd backend
DATABASE_URL="postgresql+psycopg://lubrisense:lubrisense@localhost:5432/lubrisense" \
  uv run python scripts/seed_demo_data.py
```

(`make seed` runs the same command assuming the default local `.env` values.) This creates
one demo tenant with 3 customers, 5 sites, 6 plants, 12 production lines, 24 machines, and
their bearings/lubrication systems/sensors — see `docs/ASSET_HIERARCHY.md` §10 for the
exact topology. Confirm:

```bash
docker exec lubrisense-postgres psql -U lubrisense -d lubrisense -c \
  "SELECT count(*) FROM machine;"   # should be 24
```

Then query the seeded hierarchy through the API (the tenant id below is deterministic —
see `.env.example`):

```bash
curl -s -H "X-Tenant-ID: bbdd114e-b5a7-5890-a5bd-9e8c787a5fe0" \
  http://localhost:8000/api/v1/hierarchy | python3 -m json.tool | head -30
```

## 9. Run the backend outside Docker (optional, for active development)

```bash
cd backend
uv sync --extra dev
DATABASE_URL="postgresql+psycopg://lubrisense:lubrisense@localhost:5432/lubrisense" \
REDIS_URL="redis://localhost:6379/0" \
  uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

This requires `postgres` and `redis` to already be running (`docker compose up -d postgres
redis` is enough — you don't need the whole stack).

## 10. Run the frontend outside Docker (optional)

```bash
cd frontend
npm install
npm run dev
```

## 11. Run backend tests, lint, and type checks

```bash
cd backend
uv run pytest              # requires postgres + redis reachable (see step 9)
uv run ruff check .
uv run mypy app
```

Or from the repo root: `make backend-test`, `make backend-lint`, `make backend-typecheck`.

## 12. Run frontend lint, type check, format check, and build

```bash
cd frontend
npm run lint
npm run typecheck
npm run format:check
npm run build
```

Or from the repo root: `make frontend-lint`, `make frontend-typecheck`, `make
frontend-build`.

## 13. Run everything at once

```bash
make verify
```

Runs backend lint, backend type check, backend tests, frontend lint, frontend type check,
frontend build, and the MQTT/Kafka verification scripts, in sequence. This is the same set
of checks CI runs (`.github/workflows/ci.yml`), minus the Docker build/compose steps
(CI does not build/run the full Docker Compose stack — see that workflow file for exactly
what it checks).

## 14. Tear down

```bash
docker compose down          # stop and remove containers, keep volumes (data persists)
docker compose down -v       # also remove volumes (full reset — you will lose local data)
```

## Troubleshooting

- **`docker compose up` hangs on a service**: check `docker compose logs <service>`. Kafka
  and Postgres take longest to become healthy on first boot (image pull + initialization).
- **Backend can't reach the database**: confirm `postgres` is `healthy` in `docker compose
  ps` before the backend container starts; `depends_on: condition: service_healthy` should
  already enforce this, but a manual `docker compose up -d postgres` first can help
  isolate the issue.
- **Port already in use**: every port is configurable in `.env` (e.g. `POSTGRES_PORT`,
  `BACKEND_PORT`) if something else on your machine is already using a default port.
