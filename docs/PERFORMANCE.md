# Performance / Scale (Phase 33)

## Purpose

Find and fix obvious scaling bottlenecks at this platform's actual target scale — not a
speculative massive-scale exercise. All numbers below are measured against the real
Docker Compose stack (12 containers, single developer machine, 12 host CPUs visible to
Docker), never estimated.

## Target scale

Reference/demo scale, per CLAUDE.md and the Phase 33 brief: hundreds to low-thousands of
assets, multiple sensors per asset, continuous telemetry, multiple tenants. This platform
has **not** been tested at real industrial fleet scale (tens of thousands of assets) —
see "Known limitations" below and `docs/INDUSTRIAL_ADOPTION.md`.

## Baseline measurements

**Unloaded (single request), real demo tenant:**

| Endpoint | Latency |
|---|---|
| `/api/v1/fleet/overview` | 115ms |
| `/api/v1/hierarchy` | 26ms |
| `/api/v1/incidents` | 70ms |
| `/api/v1/maintenance/cases` | 99ms |
| `/api/v1/product-metrics` | 97ms |
| `/api/v1/product-metrics/north-star` | 11ms |
| `/api/v1/audit/events?limit=50` | 3ms |
| `/api/v1/machines/{id}` | 8ms |
| `/api/v1/intelligence/machines/{id}` | 164ms (fresh full condition/decision/prognostic chain per call — ADR-125, deliberately not cached) |
| `/api/v1/telemetry?machine_id=...&limit=200` | 5ms |
| `/api/v1/baselines?machine_id=...` | 4ms |
| `/api/v1/rules/findings?machine_id=...` | 18ms |
| `/api/v1/device-management/machines/{id}/devices` | 8ms |

All well within an interactive-UI budget; no single-request bottleneck found.

**Loaded (10 concurrent requests, 50 total), before the Phase 33 fix:** `/fleet/overview`
p50 1251ms / p95 1958ms — an over 10x degradation from the unloaded number, with `docker
stats` showing the backend container pinned at ~103% CPU (saturating one core) while 11
other host cores sat idle and Postgres itself was at 66% CPU (not the bottleneck).
Raising the SQLAlchemy connection pool size alone (5/10 → 20/20) did not meaningfully
change this — confirming the constraint was CPU on a single Python process, not database
connection availability.

**Loaded, after the fix (see below):** `/fleet/overview` p50 272ms / p95 808ms — a 4.3x
improvement; throughput 7.0 → 20.8 req/s. See `backend/scripts/load_test.py`.

## The fix

`backend/Dockerfile` now runs uvicorn with `--workers ${UVICORN_WORKERS:-4}` instead of a
single worker process, so concurrent requests are actually distributed across multiple
CPU cores. `database_pool_size`/`database_max_overflow` were re-tuned to 10/10
**per worker** (not per container) — at 4 workers that's 40 total connections, safely
under Postgres's 100-connection ceiling alongside the other pipeline-worker containers
(measured ~23 connections in use at idle).

**Known consequence, documented not hidden**: in-process singletons — most notably the
Phase 27 `CircuitBreaker` for the LLM provider seam — are now per-worker-process rather
than globally shared across the container. Each worker tracks its own open/half-open/
closed state independently. This is still functionally correct (each worker still
protects itself against a failing provider) but not globally coordinated; a shared
Redis-backed breaker would be the production fix, out of scope for this reference
implementation (see `docs/RESILIENCE.md`).

## Known/reviewed bottlenecks

- **`FleetOverview.customers_by_status`'s O(customers) query loop** (flagged since Phase
  21/23, `docs/CUSTOMER_SERVICES.md`, `docs/BACKEND_HARDENING.md`): re-measured this
  phase. The *shared development database* has accumulated ~1,900 `CustomerAccount` rows
  across many isolated test-tenant runs, which looked alarming until re-checked per
  tenant — the real demo tenant has 3 customers, and `/fleet/overview` for that tenant
  measures 115ms unloaded / 272ms p50 loaded. **Confirmed not a current problem**; the
  pattern remains documented as something to revisit only if a single tenant's customer
  count grows into the hundreds.
- **Telemetry/condition/incident query indexes**: `telemetry`, `condition_assessment`,
  and `incident` all already carry the composite `(tenant_id, machine_id, time DESC)`
  index their hot-path queries need (added in earlier phases) — verified via `\d` against
  the live schema this phase; no missing index found.
- **Frontend request patterns**: grepped every `.tsx` page for a fetch/query call inside
  a `.map()` — none found. The Fleet and Overview pages already join hierarchy data with
  a single incidents query rather than one per machine (Phase 28 design decision).
- **Phase 10 feature computation cost**: unchanged this phase; already documented as an
  on-demand, not continuously-scheduled, per-tick computation in
  `docs/FEATURE_ENGINEERING.md` — no new measurement performed, no regression suspected
  since nothing in this phase touched that code path.

## Load test tool

`backend/scripts/load_test.py` — concurrent real HTTP requests against a running
backend, reporting p50/p95/max latency and achieved req/s per endpoint. No external
load-testing infrastructure (k6, Locust, etc.) — a small, reproducible, dependency-free
script matching this platform's own httpx dependency.

```
uv run python scripts/load_test.py --tenant-id <uuid> --concurrency 10 --requests 50
```

## Telemetry ingest throughput

Not re-benchmarked as a dedicated stress test this phase — the existing Phase 5/6
`scripts/verify_pipeline.sh` (simulator → edge → MQTT → Kafka → TimescaleDB) already
exercises the real ingest path end-to-end and remains the reference tool for it; building
a second, parallel ingest-throughput harness was judged unnecessary complexity for this
phase's scope (`docs/TELEMETRY_PIPELINE.md` has the architecture). The live database
holds ~93,700 real telemetry rows accumulated from prior phases' verification runs — the
pipeline has demonstrably ingested at demo scale without issue; a dedicated
rows-per-second ceiling was not measured.

## Memory / CPU

Measured at idle: backend ~156MB RSS (single worker, pre-fix) / all 12 containers
comfortably within a 16GB host. No GPU is used anywhere (scikit-learn CPU-only models).
Practical on an i7/16GB development machine, matching the brief's own target.

## Known limitations

- No test at real industrial fleet scale (tens of thousands of assets) has been run or
  claimed.
- `UVICORN_WORKERS=4` was chosen as a proportionate default for this reference
  platform's target scale, not derived from a formal capacity-planning exercise; a real
  deployment should re-measure against its own expected concurrent request volume.
- The LLM circuit breaker's per-worker (not shared) state, noted above.
- No caching layer (Redis is provisioned but not used for response caching) — every
  request recomputes from Postgres; acceptable at measured demo-scale latency, would be
  the next lever if a real deployment needed to go faster before considering
  horizontal scaling.
