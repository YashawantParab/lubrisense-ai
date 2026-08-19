# Hosted Deployment (Public Demo)

This document describes how to deploy the LubriSense AI release candidate as a **public,
reviewer-facing hosted demo** — Vercel (frontend) + a hosted FastAPI container service
(Render or equivalent) + a hosted PostgreSQL + pgvector database.

This is **not** a claim of industrial production readiness. It is a hosted instance of
the exact same reference platform, running on persisted, pre-seeded demo data instead of
the continuous industrial ingestion path. See `docs/INDUSTRIAL_ADOPTION.md` for the full
boundary and `docs/HOSTED_RELEASE_GATE.md` for the pre-launch checklist. No external
deployment has been performed as part of preparing this document — everything below was
verified locally against equivalent conditions (see "Local hosted-mode verification").

This work is tracked as **POST-ROADMAP HOSTED DEPLOYMENT PREPARATION** — it sits after
Phase 39 (`IMPLEMENTATION_STATUS.md`) and is deliberately not a new numbered roadmap
phase: it is a deployment-configuration exercise against the already-complete Phase 0–39
platform, not new product functionality.

## Architecture

```
Reviewer's browser
      |
      v
  Vercel (Next.js frontend)  --https-->  Hosted backend (FastAPI, Render/equivalent)
                                                |
                                                v
                                    Hosted PostgreSQL + pgvector
```

**Not deployed publicly** — genuinely not required for the reviewer-facing demo, and
intentionally excluded:

- the edge simulator (`simulator/`, `edge/`)
- the MQTT broker (Mosquitto) and Kafka
- `mqtt-bridge`, `telemetry-consumer`, `data-quality-worker`, `baseline-worker`,
  `rules-worker`, `feature-worker`

The flagship demo story is entirely produced by pre-seeding through real service calls
directly against the database (`backend/scripts/seed_hosted_demo.py`), the same
convention `seed_flagship_story.py` already established locally — the real MQTT/Kafka
ingestion pipeline is proven separately by `scripts/verify_pipeline.sh` against the full
local stack; re-routing the hosted demo through it would add infrastructure cost without
adding evidence of correctness. Running the background workers continuously against a
static, pre-seeded demo dataset would provide no benefit and one real risk: staleness-
based data-quality evaluation would eventually flag the demo's own telemetry as stale
since nothing feeds it live, degrading the demo's visual quality the longer it sits
between reseeds. Not running them avoids that entirely.

The full industrial architecture (simulator, MQTT, Kafka, all workers) remains completely
intact in the repository and in `docker-compose.yml` for local development — nothing was
removed, only left un-deployed for the hosted demo specifically.

## 1. Database

**Requirement**: a standard hosted PostgreSQL instance with the **pgvector** extension
available. TimescaleDB is *not* required — see ADR-175 in `TECHNICAL_DECISIONS.md`: the
two TimescaleDB-specific migration statements (`CREATE EXTENSION timescaledb`,
`create_hypertable()`) now check server/database extension availability first and are
skipped cleanly when unavailable, leaving `telemetry` as a standard Postgres table. Every
query in `backend/app/` is already plain SQL, identical either way.

Verified locally: the full migration chain (all 15 migrations, `alembic upgrade head`)
run cleanly against a real `pgvector/pgvector:pg16` container (pgvector present,
TimescaleDB genuinely absent — confirmed via `pg_available_extensions`). A real pgvector
cosine-similarity query against a `vector(256)` column (the exact shape
`knowledge_chunk.embedding` uses) was also verified working.

Providers known to support pgvector on managed Postgres: Supabase, Neon, Render Postgres,
and most others as of recent offerings — confirm pgvector availability with your chosen
provider before provisioning.

**Migration command** (run once per deploy from a shell with `DATABASE_URL` pointed at
the hosted database):

```bash
cd backend
DATABASE_URL="postgresql+psycopg://<user>:<password>@<host>:<port>/<db>" \
  uv run alembic upgrade head
```

## 2. Hosted demo data

**Seed command** (idempotent — safe to run once at first deploy, and safe to re-run any
time to reset the demo to its known-good state):

```bash
cd backend
DATABASE_URL="..." uv run python scripts/seed_hosted_demo.py
```

This orchestrates, in order:

1. `seed_demo_data.py` — base tenant/customer/site/plant/line/machine hierarchy.
2. `seed_knowledge_corpus.py` — the approved knowledge corpus for RAG/assistant.
3. `seed_flagship_story.py` — the flagship machine's full story: telemetry → baselines →
   rule findings → state estimates → condition/decision → incident → maintenance case →
   technician finding/action → recovery telemetry → resolved incident with
   `TRUE_POSITIVE` feedback.
4. `seed_healthy_machine.py` — a second real machine (Motor 001) seeded with only calm,
   in-range telemetry, landing on a genuine `NORMAL_OPERATION` read with no incident — a
   fleet-realistic comparison point ("most machines look like this").
5. A CMMS draft (via the real, draft-only `CMMSService`) and a device/configuration
   snapshot (via the real `DeviceConfigurationService`) on the flagship's completed
   maintenance case, so those panels are populated without requiring the reviewer to
   click "Create CMMS draft" themselves first.

**No public reset endpoint.** This is a script run from a deploy shell/one-off job, never
an HTTP route — nothing exposed to the internet can trigger a reset. Re-running the seed
command is the only reset mechanism, and it only ever touches its own deterministic demo
tenant/machines (see ADR-173 in `TECHNICAL_DECISIONS.md`) — never any other data.

## 3. Auth strategy

The existing Phase 24 demo-auth mechanism is exactly the right shape for a public demo
and needs no code change — only correct configuration:

- **`AUTH_ENFORCEMENT_MODE=strict`** (backend). The local/dev default (`permissive`)
  silently grants a full-access principal to any request with no bearer token — safe
  behind `localhost`, not safe on the public internet. `strict` requires a real signed
  token on every request; `Settings.model_post_init` already refuses to start in
  `permissive` mode when `APP_ENV` is `production` or `hosted_demo` (see §11 below).
- **`DEMO_AUTH_SECRET`** must be overridden to a real generated secret, never the
  insecure local default — also enforced by `model_post_init`.
- The frontend's existing `AuthProvider` (`frontend/src/lib/auth/context.tsx`) already
  calls `POST /api/v1/auth/demo-login` for a fixed default role (`ADMIN`) on page load
  and stores the issued bearer token — this is the "controlled demo-login" the reviewer
  never has to think about. No frontend change needed.
- Every request is still scoped to the one fixed demo tenant
  (`NEXT_PUBLIC_DEMO_TENANT_ID`) — no cross-tenant exposure is possible even with a
  freely-issued demo token, since a token's `tenant_id` claim is checked against the
  resolved tenant on every request (403 on mismatch).
- `demo-login` itself issues a token for *any* of the six fixed roles on request with no
  password — this is an intentional, clearly-labeled demo mechanism (`docs/SECURITY.md`),
  not a real login flow. Nothing behind it is more sensitive than "see/use the demo
  product features that role's RBAC permissions allow" — no user management, billing, or
  infrastructure control exists behind any role.

## 4. Environment variables

### Frontend (Vercel project settings → Environment Variables)

| Variable | Value | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://<your-backend>.onrender.com` | The browser-facing backend URL. Baked into the client bundle at build time. |
| `NEXT_PUBLIC_APP_ENV` | `hosted_demo` | Cosmetic only (no frontend branching reads this today beyond display). |
| `NEXT_PUBLIC_DEMO_TENANT_ID` | `bbdd114e-b5a7-5890-a5bd-9e8c787a5fe0` | The deterministic demo tenant id `seed_demo_data.py` creates. Unchanged from local. |
| `BACKEND_INTERNAL_URL` | *(omit)* | Server components fall back to `NEXT_PUBLIC_API_BASE_URL` when unset (`frontend/src/lib/env/server.ts`) — Vercel has no private network to the backend the way the Docker Compose network does, so there is no separate "internal" URL to set. |

### Backend (Render/equivalent service environment)

| Variable | Value | Notes |
|---|---|---|
| `APP_ENV` | `hosted_demo` | Triggers the same fail-fast safety validation as `production` (ADR added as part of this work — see `Settings.model_post_init`), without claiming real industrial deployment. |
| `DATABASE_URL` | `postgresql+psycopg://...` | The hosted Postgres connection string. |
| `AUTH_ENFORCEMENT_MODE` | `strict` | Required in `hosted_demo` — see §3. |
| `DEMO_AUTH_SECRET` | *(generated secret)* | Required, must not be the insecure default. |
| `CORS_ALLOWED_ORIGINS` | `https://<your-frontend>.vercel.app` | Must not be `*` — enforced. Comma-separate if you also serve a preview domain. |
| `TRUSTED_HOSTS` | `<your-backend>.onrender.com` | Must not be `*` — enforced. |
| `REDIS_URL` | *(hosted Redis URL, if provisioned)* | See §7 — soft dependency; only `/ready` and nothing reviewer-facing actually needs it. |
| `ML_ARTIFACTS_DIR` | `/tmp/ml-artifacts` | See §5 — an ephemeral, writable path; the registry creates it empty and correctly reports zero models, matching the already-honest local "no promoted model" state. |
| `LOG_FORMAT` | `json` | Matches local/CI default. |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `8000` (or platform-assigned `$PORT`) | See §10. |
| `UVICORN_WORKERS` | `2` (suggested) | Lower than the local default of 4 — a public demo on a modest hosted instance size does not need the same worker count Phase 33's load-test baseline targeted; tune to the instance's actual CPU allocation. |

Do not set `KAFKA_BOOTSTRAP_SERVERS`, `MQTT_HOST`, or any worker-specific variable — the
backend API process never reads them at startup (`app/main.py`'s `lifespan` only
constructs a `Database` and a `RedisClient`); they are only consumed by the worker
processes this deployment does not run.

**No secrets are committed anywhere in this repository.** `.env` is git-ignored;
`.env.example` documents the full *local* variable set with safe non-secret defaults.

## 5. Model artifacts

Neither trained model (`LUBRICATION_ANOMALY_V1`, `FAILURE_CLASSIFICATION_V1`) has cleared
its own promotion gate (`docs/MODEL_CARD.md`) — the platform already, honestly, reports
`0 ML result(s)` for every machine, including the flagship. No model artifact is required
for the hosted demo to be complete and correct. `ML_ARTIFACTS_DIR` should point at an
empty, writable, ephemeral path (e.g. `/tmp/ml-artifacts`); `ModelRegistry.__init__`
already does `base_dir.mkdir(parents=True, exist_ok=True)`, so it creates the directory
and reports an empty registry gracefully — no code change, no artifact to ship, nothing
to commit.

## 6. RAG / pgvector

Verified locally against a standard pgvector-only Postgres container (§1). The embedding
provider (`HashingEmbeddingProvider`,
`backend/app/knowledge/embeddings/provider.py`) is a fully local, deterministic,
dependency-free hashing-trick vectorizer — no external embedding API, no API key,
zero marginal cost per query. The assistant's answer composer (`DemoLLMProvider`,
`backend/app/agent/providers/llm_provider.py`) is likewise a deterministic template
composer over real retrieved evidence — no external LLM API, no API key. Both were
built this way from Phase 18/19 specifically so the platform "must pass locally without
a paid external LLM" — the hosted demo inherits that property for free, no
`APP_MODE`-specific branching needed.

## 7. Filesystem assumptions

No SQLite usage and no writable-project-directory assumption exists in the backend API
process itself. The one SQLite-backed component (`app.pipeline.spool.BridgeSpool`, the
MQTT→Kafka bridge's durable local spool) belongs to the `mqtt-bridge` process, which the
hosted demo does not run. `ML_ARTIFACTS_DIR` (§5) is the only filesystem write the
backend API process performs, and it tolerates a fully ephemeral filesystem (ephemeral is
in fact the intended shape here — ephemeral, gracefully-empty). No other absolute or
developer-machine-only path exists in the backend.

`/ready` checks Redis in addition to Postgres (§below). Redis is otherwise unused by any
reviewer-facing code path today — provisioning a small hosted Redis instance is the
simplest way to make `/ready` fully accurate; omitting it leaves `/ready` reporting
`not_ready` while the product itself remains fully functional (documented, not hidden —
this is a health-check-accuracy question, not a reviewer-facing functionality gap).

## 8. CORS / API

`app/main.py` already builds `CORSMiddleware`/`TrustedHostMiddleware` from
`Settings.cors_allowed_origins_list`/`trusted_hosts_list` — set them to the real Vercel
frontend origin and the real backend hostname respectively (§4). `hosted_demo` (like
`production`) refuses to start with either left wildcarded. HTTPS termination is handled
by the hosting platform (Vercel and Render/equivalent both terminate TLS in front of the
application) — no in-app HTTPS-specific configuration is needed.

## 9. Frontend deployment (Vercel)

- `npm run build` (`next build`, `output: "standalone"`) already verified clean locally
  (Phase 39). Vercel's own Next.js build pipeline does not require the `standalone`
  output setting — it is used for the self-hosted Docker image (`frontend/Dockerfile`)
  and is simply unused by Vercel's own packaging, not a conflict.
- No hardcoded `localhost` URLs exist outside the documented env-var defaults
  (`frontend/src/lib/env/public.ts`, `.../server.ts`) — both fall back to `localhost` only
  when the corresponding env var is unset, so setting `NEXT_PUBLIC_API_BASE_URL` on
  Vercel is the only change needed.
- Direct-route refresh: every dynamic route (`/machines/[machineId]`,
  `/incidents/[incidentId]`, `/maintenance/[caseId]`) is a standard Next.js App Router
  page — Vercel serves these correctly on a hard refresh/direct link with no extra
  rewrite configuration.
- Public assets (`frontend/public/`, favicon/icon) and fonts are bundled/served by
  Next.js's own static asset pipeline — no external asset host dependency.

## 10. Backend deployment (Render or equivalent container/Python hosting)

- **Image**: `backend/Dockerfile` as-is (already binds `0.0.0.0:8000`, already runs as a
  non-root user, already has a `HEALTHCHECK`). If the platform injects its own `$PORT`
  (Render does), override the container command's `--port` accordingly, or set
  `APP_PORT`/adjust the Dockerfile `CMD` to read `${PORT:-8000}` — see the suggested
  `render.yaml` below for the exact form.
- **Start command** (already the image's `CMD`, shown here for a non-Docker Python
  buildpack alternative):
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers ${UVICORN_WORKERS:-2}
  ```
- **Health/readiness**: `/health` (liveness — always 200 if the process is up) and
  `/ready` (Postgres + Redis dependency check, 503 if either is unreachable) already
  exist and need no change. Point the platform's health check at `/health` for
  liveness/restart decisions; `/ready` is available for a more thorough check if the
  platform supports a separate readiness probe.
- **Startup does not require Kafka/MQTT/Redis**: `app/main.py`'s `lifespan` only
  constructs `Database` and `RedisClient` — both are lazy (they do not connect until
  first use). The process starts and serves every reviewer-facing route with only
  Postgres reachable; Redis's absence only affects `/ready`'s own accuracy (§7).
- A minimal `render.yaml` blueprint is included at the repository root as a starting
  point — adapt plan sizes/region/domain to your actual account before use; it has not
  been applied against a live Render account as part of this work (no external
  deployment was performed).

## 11. Hosted demo mode (`APP_ENV=hosted_demo`)

A configuration/deployment distinction, not a parallel product implementation — the exact
same `app.main.create_app()`, the exact same route handlers, the exact same domain/service
logic run regardless of `APP_ENV`. Setting it to `hosted_demo`:

- Triggers the same fail-fast safety validation `production` already had
  (`Settings.model_post_init`, extended in this work to cover both) — refuses to start with
  permissive auth, a default secret, or wildcard CORS/trusted-hosts.
- Is otherwise purely informational (logged on startup, shown nowhere destructive).

It does **not**, and must never: bypass RBAC/tenant boundaries, fabricate API responses,
hardcode a frontend-visible value that should come from the backend, or skip evidence/
provenance on any response. Nothing in `app/` branches business logic on `hosted_demo` —
only `Settings.model_post_init`'s safety checks and this document's deployment
configuration differ from local development.

## 12. Startup / seed

One documented, idempotent, deployment-safe command (§2):
`uv run python scripts/seed_hosted_demo.py`. Run it once after the first successful
migration on a fresh hosted database; re-run it any time to reset the demo to its known
state. It is not invoked automatically on every process start (no seeding-on-boot) —
every one of the sub-scripts it orchestrates was individually verified idempotent by
running it multiple times in immediate succession without producing duplicate rows.

## 13. Limitations (hosted demo specifically)

- The industrial ingestion path (simulator/MQTT/Kafka/workers) is not publicly hosted —
  by design (see "Architecture" above), not an oversight. It remains fully runnable
  locally (`docker compose up -d`) for anyone who clones the repository.
- Redis is a soft dependency (§7) — without a provisioned hosted Redis, `/ready` reports
  `not_ready` while the product itself remains fully functional; provisioning a small
  hosted Redis instance resolves this cleanly if desired.
- The flagship story's recovery-phase post-action condition has a known, documented
  ~1-in-8 timing-sensitive flake (Phase 39 addendum to ADR-172 in
  `TECHNICAL_DECISIONS.md`) — the incident and maintenance case still resolve/complete
  correctly either way; re-running `seed_hosted_demo.py` resolves the cosmetic case.
- No rate limiting exists on the public API surface today. Basic platform-level abuse
  protection (Vercel/Render's own infrastructure-level protections) is the only mitigation
  currently in place; a dedicated application-level rate limiter is a reasonable follow-up
  but was out of scope for this work (adding it would be a new product feature, not a
  deployment-configuration change) — flagged in `docs/HOSTED_RELEASE_GATE.md`.
- `TRUSTED_HOSTS`/`CORS_ALLOWED_ORIGINS` must be set to the real deployed hostnames before
  first boot in `hosted_demo` mode — the app will refuse to start otherwise (by design).

## 14. Rollback / redeploy guidance

- **Frontend**: Vercel keeps every previous deployment; use its dashboard/CLI to
  instantly roll back to a prior deployment if a new one regresses.
- **Backend**: redeploy the previous known-good image/commit through the platform's
  standard rollback mechanism (Render keeps prior deploys available to roll back to).
- **Database**: migrations in this repository are additive/forward-only in the demo's
  actual usage pattern (no destructive migration has been part of this work); if a
  migration ever needs reverting, `alembic downgrade -1` is available but has not been
  exercised against a hosted target as part of this work — treat it as a manual,
  supervised operation, not an automated rollback step.
- **Demo data**: `seed_hosted_demo.py` is itself the "rollback" for demo data — re-run it
  to return the flagship/healthy machines to their known-good deterministic state.

## Local hosted-mode verification performed (POST-ROADMAP HOSTED DEPLOYMENT PREPARATION)

See `docs/HOSTED_RELEASE_GATE.md` for the full checklist and current results. Summary:
migrations verified against a real non-TimescaleDB Postgres+pgvector container end to
end; `hosted_demo`/`production` safety validation covered by a new automated test suite
(`backend/tests/test_config.py`); the full `seed_hosted_demo.py` orchestration run
successfully against the local stack with the worker containers stopped, producing a
working flagship story, healthy comparison machine, CMMS draft, and device/configuration
snapshot.
