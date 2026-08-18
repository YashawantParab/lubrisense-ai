# LubriSense AI — Technical Decisions

This document records important architectural and product-engineering decisions.

Do not use this as a general notes file.

Record only decisions that materially influence the architecture, implementation, product behavior, security, scalability, or maintainability.

---

# Decision Format

For every decision use:

## ADR-XXX — Title

### Status

PROPOSED / ACCEPTED / SUPERSEDED / REJECTED

### Context

Why this decision is needed.

### Decision

What was chosen.

### Alternatives Considered

Other reasonable options.

### Why This Option

Why the selected option is preferred.

### Consequences

Positive and negative consequences.

### Revisit When

Conditions that may require reconsideration.

---

# ADR-001 — Production-Grade Reference Implementation

### Status

ACCEPTED

### Context

LubriSense AI is being built using synthetic industrial data because real proprietary industrial telemetry, controller interfaces, asset data, CMMS configuration, enterprise identity, and validated lubrication-domain parameters are unavailable.

The architecture should nevertheless represent how a commercial industrial condition-monitoring system would be structured.

### Decision

Build LubriSense AI as a production-grade reference implementation.

Internal platform capabilities must be functional.

External/proprietary dependencies must be isolated behind adapters or configuration boundaries.

Synthetic values must be explicitly identified as demo engineering assumptions.

### Alternatives Considered

1. Build only a portfolio demo.
2. Create only frontend visualizations.
3. Pretend synthetic integrations are real production integrations.

### Why This Option

It provides a credible industrial product architecture without falsely claiming proprietary production integration.

### Consequences

Positive:

- architecture can demonstrate enterprise product thinking
- real integrations can later replace adapters
- backend can be evaluated independently from synthetic data

Negative:

- some production connectors remain stubs/interfaces
- real field validation cannot be claimed

### Revisit When

Real industrial hardware, telemetry, enterprise systems, or validated domain parameters become available.

---

# ADR-002 — Three-Layer Intelligence Architecture

### Status

ACCEPTED

### Context

The product must clearly separate physical-data intelligence, maintenance decision logic, and GenAI-assisted workflow.

Combining all intelligence into one AI service would reduce explainability and create unsafe boundaries.

### Decision

Use three intelligence layers:

1. Machine & Sensor Intelligence
2. Decision Intelligence
3. Workflow Intelligence

Machine & Sensor Intelligence determines what is happening.

Decision Intelligence determines what it means and what action is appropriate.

Workflow Intelligence helps humans execute the action using RAG and guarded tools.

### Alternatives Considered

1. One generic AI service.
2. LLM-based diagnosis.
3. ML model directly producing maintenance work orders.

### Why This Option

The separation improves:

- safety
- explainability
- maintainability
- model governance
- graceful degradation

### Consequences

Requires more explicit interfaces between services, but produces a stronger industrial architecture.

### Revisit When

Only if strong evidence shows one layer should be merged without compromising safety or explainability.

---

# ADR-003 — Rules Before ML Where Physics Is Clear

### Status

ACCEPTED

### Context

Many industrial states can be identified using known deterministic conditions.

ML should not replace obvious physical rules merely to increase AI usage.

### Decision

Use deterministic rules where physical thresholds or known states are clear.

Use ML where:

- patterns are multivariable
- baselines vary
- fixed thresholds create excessive false alerts
- forecasting or anomaly detection provides additional value

### Alternatives Considered

1. ML for every condition.
2. Rules only.
3. LLM-based anomaly reasoning.

### Why This Option

Hybrid logic gives better explainability and resilience.

### Consequences

Requires maintaining both rule and model versions.

### Revisit When

Real domain validation indicates a different boundary.

---

# ADR-004 — LLMs Are Not Physical Control Systems

### Status

ACCEPTED

### Context

GenAI is useful for knowledge retrieval and maintenance workflow, but is non-deterministic and inappropriate as a direct machine controller.

### Decision

LLMs and agents may:

- retrieve documentation
- explain diagnoses
- summarize evidence
- find similar incidents
- generate inspection checklists
- draft work orders

LLMs and agents may not:

- start/stop machinery
- activate pumps
- change lubrication intervals
- change lubricant quantity
- override PLC logic
- modify safety parameters
- automatically close critical incidents

### Why This Option

Maintains a clear industrial safety boundary.

### Consequences

Human approval remains part of operational workflows.

---

# ADR-005 — Edge for Resilience, Central Platform for Fleet Intelligence

### Status

PROPOSED

### Context

Industrial systems must maintain essential monitoring during connectivity loss.

### Decision

Proposed responsibilities:

EDGE:

- sensor collection
- deterministic alarms
- buffering
- store-and-forward
- offline operation
- basic data-quality checks

CENTRAL PLATFORM:

- fleet analytics
- ML
- forecasting
- state estimation
- decision intelligence
- RAG
- model management
- business metrics

### Alternatives Considered

1. Cloud-only processing.
2. Full ML inference at edge.
3. Edge-only architecture.

### Why This Option

Provides resilience while keeping complex fleet intelligence centrally manageable.

### Consequences

Requires explicit synchronization and event-handling strategy.

### Revisit When

Actual target hardware and latency requirements are known.

---

# ADR-006 — MQTT and Kafka Have Different Responsibilities

### Status

ACCEPTED — validated in Phase 1 (both brokers start healthy in `docker-compose.yml`;
see ADR-015 for the specific Kafka implementation chosen).

### Context

MQTT is commonly useful for device/gateway communication, while Kafka is better suited to scalable internal event streaming.

### Decision

Proposed:

Sensors / Edge
→ MQTT

Platform Ingestion
→ Kafka

Internal consumers use Kafka for:

- data-quality evaluation
- feature updates
- rule evaluation
- ML processing
- incident generation
- downstream analytics

### Alternatives Considered

1. MQTT only.
2. Kafka directly at device layer.
3. REST-only telemetry.

### Why This Option

Separates device communication from enterprise event processing.

### Consequences

Adds infrastructure complexity in local development.

### Revisit When

If real edge hardware constraints (Phase 5) make running an MQTT client impractical, or if
fleet scale (Phase 33) shows Kafka single-broker/single-partition defaults are
insufficient.

---

# ADR-007 — PostgreSQL + TimescaleDB + pgvector

### Status

ACCEPTED — validated in Phase 1 (see ADR-014 for the specific local image chosen).

### Context

LubriSense requires:

- relational domain data
- time-series telemetry
- vector retrieval

### Decision

Use:

PostgreSQL for domain/business data

TimescaleDB for telemetry

pgvector for RAG embeddings

### Alternatives Considered

- InfluxDB + PostgreSQL + external vector DB
- MongoDB
- Elasticsearch
- separate vector service

### Why This Option

Reduces infrastructure sprawl while providing required data capabilities.

### Consequences

Requires careful schema/index/retention design.

### Revisit When

Scale testing identifies a bottleneck.

---

# ADR-008 — Frontend Does Not Generate Product Truth

### Status

ACCEPTED

### Context

A polished UI can hide fake or disconnected backend functionality.

### Decision

All production-like values visible in the frontend must originate from backend APIs.

Examples:

- health scores
- conditions
- predictions
- confidence
- evidence
- work orders
- incidents
- business metrics

Frontend may only contain static content for:

- labels
- help text
- formatting
- navigation

### Consequences

Backend APIs must exist before final UI integration.

---

# ADR-009 — Technician Feedback Is Stored but Does Not Automatically Retrain Models

### Status

ACCEPTED

### Context

Technician findings are valuable labels but can be noisy, incomplete or incorrect.

### Decision

Store technician outcomes such as:

TRUE_POSITIVE
FALSE_POSITIVE
MISSED_FAILURE
INCONCLUSIVE

Use them as candidate future training data.

Do not automatically retrain or promote a production model based directly on operational feedback.

### Consequences

Requires model-governance workflow.

---

# ADR-010 — Asset Context Is Mandatory

### Status

ACCEPTED

### Context

Industrial sensor values are difficult to interpret without knowing the physical asset and operating context.

### Decision

Every relevant measurement and diagnosis must resolve through the asset hierarchy.

Required context may include:

- customer
- plant
- production line
- machine
- bearing
- lubrication system
- circuit
- lubrication point
- sensor
- firmware
- operating state
- maintenance history

### Consequences

Domain model is more complex but much more realistic.

---

# ADR-011 — Repository Architecture Mirrors the Intelligence Chain

### Status

ACCEPTED

### Context

The repository already contains empty top-level directories (`frontend/`, `backend/`,
`ml-service/`, `simulator/`, `edge/`, `infrastructure/`, `docs/`, `tests/`, `scripts/`). Phase 0
needed to assign each directory an explicit purpose so later phases build into a coherent
structure rather than improvising boundaries as code is written.

### Decision

Each top-level directory owns a distinct segment of the end-to-end chain defined in
`docs/ARCHITECTURE.md` §1:

- `simulator/` and `edge/` stand in for the physical asset / sensors / edge controller stages,
  and are the explicit seam where real industrial integration replaces synthetic behavior.
- `backend/` owns telemetry processing, data quality, rules, condition intelligence, decision
  intelligence, incidents, workflow orchestration, and business metrics.
- `ml-service/` owns model training/evaluation/inference, kept separate from `backend/` so model
  logic never lives inside API route handlers.
- `frontend/` renders product surfaces only; it must not compute production-like values.
- `infrastructure/` owns local-dev and reference-deployment infra (Compose/IaC).
- `docs/`, `tests/`, `scripts/` are cross-cutting.

Full mapping in `docs/ARCHITECTURE.md` §11.

### Alternatives Considered

1. A single monolithic `app/` directory.
2. Splitting by technical layer only (api/, db/, workers/) without an explicit
   simulator/edge separation from backend.

### Why This Option

Keeps the synthetic-vs-real boundary (ADR-001) physically visible in the repository layout, and
keeps ML logic out of API handlers per `CLAUDE.md` backend rules.

### Consequences

Later phases must respect these boundaries; moving logic across them (e.g., embedding a model
directly in `backend/`) should be treated as an architecture regression, not a convenience.

### Revisit When

If Phase 1 tooling reveals a directory boundary that creates more friction than clarity.

---

# ADR-012 — Structured Event Contracts Between Intelligence Layers

### Status

ACCEPTED

### Context

ADR-002 establishes three intelligence layers but did not specify how they communicate. Without
an explicit contract, it would be easy for a future implementation to let, e.g., an ML model's
raw output leak into the frontend as if it were a governed decision.

### Decision

Machine & Sensor Intelligence communicates to Decision Intelligence exclusively via a persisted,
versioned `ConditionAssessment` object. Decision Intelligence communicates to Workflow
Intelligence and the frontend exclusively via a persisted, versioned `Decision` object. Both are
defined in `docs/EVENT_CATALOG.md` §3. Raw telemetry, rule outputs, and model inference outputs
are also captured as their own event types (`TelemetryReading`, `RuleEvaluated`,
`ModelInferenceCompleted`) so the full chain is auditable, not just the final outputs.

### Alternatives Considered

1. Let each layer expose an ad hoc internal API shape, decided per-implementation.
2. Skip persisting intermediate events and only persist final decisions.

### Why This Option

A structured, persisted contract makes the layer boundary enforceable in code review and
testable in isolation, and gives Decision Intelligence and Workflow Intelligence a stable
interface even as models/rules evolve underneath. Persisting intermediate events (not just final
outputs) is required for explainability, audit, and future model evaluation.

### Consequences

Requires schema versioning discipline (`schema_version`, `rule_version`, `model_version` fields)
from the first implementation, adding some upfront design cost.

### Revisit When

Phase 2 domain-model implementation may refine exact field types/constraints; the contract's
existence and layer boundary should not change without revisiting ADR-002.

---

# ADR-013 — Failure-Mode Catalog Distinguishes Lubrication-Caused from Independent Bearing Issues

### Status

ACCEPTED

### Context

Vibration and bearing-temperature abnormalities can be caused by a lubrication-system fault
(e.g., Gradual Restriction) or by an unrelated mechanical issue (misalignment, imbalance,
fatigue). Conflating the two risks sending technicians to service the wrong system and
overstating what the evidence actually supports.

### Decision

The failure-mode catalog (`docs/FAILURE_MODE_CATALOG.md`) includes an explicit "Bearing Issue
Independent of Lubrication" mode, differentiated from lubrication-caused modes by checking
whether lubrication-system signals (reservoir, pressure, flow, cycle completion) are normal while
machine-condition signals (vibration, bearing temperature) are not. All evidence language across
rules, ML, and GenAI must use calibrated causal language ("consistent with," "possible
contribution," never asserted direct causality) per §13 of that document.

### Alternatives Considered

1. Treat all bearing abnormalities as lubrication-related by default.
2. Leave causal attribution entirely to free-text GenAI explanation without a structured
   evidence rule.

### Why This Option

Prevents false attribution, keeps Decision Intelligence's recommended action routed to the
correct maintenance discipline, and enforces the "never claim direct causality from simple
correlation" rule structurally rather than only as a style guideline.

### Consequences

Rule/ML logic must evaluate lubrication-system and machine-condition signals as distinguishable
evidence groups, not a single flattened feature vector, to preserve this distinction.

### Revisit When

Real failure-label data becomes available and may reveal correlation patterns not captured by
this simple normal/abnormal split.

---

# ADR-014 — Single TimescaleDB-HA Image Provides Both TimescaleDB and pgvector

### Status

ACCEPTED

### Context

ADR-007 proposed PostgreSQL + TimescaleDB + pgvector but left the local image strategy open,
flagging a risk that the two extensions might not coexist cleanly in one off-the-shelf image
(`docs/ARCHITECTURE.md` §14). This had to be resolved concretely in Phase 1, not assumed.

### Decision

Use `timescale/timescaledb-ha:pg16` as the single Postgres image for local development and
as the reference image for deployment. Verified directly: `CREATE EXTENSION timescaledb` and
`CREATE EXTENSION vector` both succeed in the same database
(`pg_extension` shows `timescaledb 2.29.1` and `vector 0.8.6` installed together, alongside
`timescaledb_toolkit`). The Phase 1 bootstrap migration
(`backend/alembic/versions/0001_initial_schema.py`) creates both extensions with
`IF NOT EXISTS` guards.

### Alternatives Considered

1. Plain `postgres` image + manually compiling/installing both extensions — more control,
   significantly more Dockerfile/image-maintenance burden for no real Phase 1 benefit.
2. Separate Postgres instances for TimescaleDB-backed telemetry and pgvector-backed RAG
   embeddings — avoids any coexistence risk entirely, but reintroduces the infrastructure
   sprawl ADR-007 was written to avoid, and complicates cross-referencing telemetry with
   RAG context later.
3. `timescale/timescaledb-ha` "all extensions" variant tags — heavier image than needed;
   the plain `pg16` tag already includes `vector`, so the larger tag adds no Phase 1 value.

### Why This Option

One image, one running database, both extensions confirmed to install and coexist without
conflict. This is the simplest option that satisfies ADR-007 without deferring the
coexistence question further.

### Consequences

Positive: no separate database/image-maintenance burden; telemetry (Timescale hypertables,
Phase 6+) and RAG embeddings (pgvector, Phase 18+) can share one database if that continues
to make sense.

Negative: coupled to this specific vendor image's extension bundling; if a future TimescaleDB
version drops pgvector from the bundle, this decision must be revisited.

### Revisit When

Scale testing (Phase 33) or a TimescaleDB upstream image change indicates the two workloads
should be split, or a hosted/managed Postgres offering used for the reference deployment
does not bundle both extensions.

---

# ADR-015 — Kafka in KRaft Mode, No ZooKeeper

### Status

ACCEPTED

### Context

ADR-006 established that Kafka is used for internal platform event streaming but did not
pick an implementation. Running ZooKeeper alongside Kafka adds a second stateful service to
local development and the reference deployment for no benefit modern Kafka doesn't already
provide without it.

### Decision

Use the official `apache/kafka:3.7.0` image in KRaft mode
(`process.roles=broker,controller`), single node, no ZooKeeper. Configuration is entirely
environment-variable-driven in `docker-compose.yml` (`KAFKA_NODE_ID`, `KAFKA_PROCESS_ROLES`,
`KAFKA_LISTENERS`, `KAFKA_CONTROLLER_QUORUM_VOTERS`, etc.). Verified end to end with
`scripts/verify_kafka.sh`: topic creation, produce, and consume all succeed against this
configuration.

### Alternatives Considered

1. ZooKeeper-based Kafka — the traditional/most-documented setup, but ZooKeeper is in
   deprecation across the Kafka ecosystem and adds a second stateful coordination service
   with no Phase 1 benefit.
2. `bitnami/kafka` KRaft image — also viable, but the official Apache-published image was
   preferred to reduce third-party image dependency for core platform infrastructure.
3. A managed/hosted Kafka-compatible service (e.g. Redpanda Cloud) — out of scope for a
   local-first reference implementation; nothing prevents swapping the broker later since
   the application only depends on `KAFKA_BOOTSTRAP_SERVERS`.

### Why This Option

Simplest reliable modern local setup that matches how a real deployment would run Kafka
today, with no extra coordination service to operate.

### Consequences

Single-node, single-broker: fine for local development and this reference implementation,
but not representative of a production multi-broker cluster's replication/partitioning
behavior. `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR`, `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR`,
and `KAFKA_TRANSACTION_STATE_LOG_MIN_ISR` are all pinned to `1` accordingly — these must be
revisited before any real multi-broker deployment.

### Revisit When

Phase 6 (Telemetry Pipeline) needs to validate actual throughput, or Phase 33 (Performance +
Scale Testing) requires a multi-broker topology.

---

# ADR-016 — Python Dependency Management via uv

### Status

ACCEPTED

### Context

The backend needs a Python dependency/environment manager. The host environment's system
Python (3.9) is older than the project's target (3.12+), so the tool also needs to manage
the Python version itself, not just packages.

### Decision

Use [uv](https://docs.astral.sh/uv/) with `pyproject.toml` as the single source of
dependency truth (`backend/pyproject.toml`), `uv.lock` for reproducible installs, and `uv
run` for all dev commands (`ruff`, `mypy`, `pytest`, `alembic`, `uvicorn`). The backend
Dockerfile also uses `uv sync` in its builder stage.

### Alternatives Considered

1. Poetry — comparable feature set, but not installed in the target environment and
   meaningfully slower for install/resolve.
2. Plain `pip` + `requirements.txt` — no built-in Python-version management, weaker lock
   file guarantees.
3. `pipenv` — largely superseded in the current Python tooling ecosystem.

### Why This Option

`uv` resolves and installs the full dependency set (including dev tools) faster than the
alternatives, manages the Python interpreter version itself (no dependency on the host's
system Python), and produces a single lock file for reproducible installs in CI and Docker.

### Consequences

Contributors need `uv` installed locally (or use the Dockerized backend, which needs
nothing extra). CI installs it via `astral-sh/setup-uv`.

### Revisit When

Only if `uv` proves unreliable in CI/Docker at larger scale — no such evidence in Phase 1.

---

# ADR-017 — npm as the Frontend Package Manager

### Status

ACCEPTED

### Context

`create-next-app` defaults to npm when no other lockfile/package manager is detected, and a
package manager choice needed to be made explicit rather than left to whatever ran first.

### Decision

Use npm (`package-lock.json` committed) for the frontend.

### Alternatives Considered

1. pnpm — faster installs and stricter dependency isolation, but adds a tool contributors
   must separately install; no Phase 1 pain point npm actually has that pnpm solves.
2. yarn — comparable to npm; no concrete advantage for this project's needs.

### Why This Option

Zero additional tooling for contributors (npm ships with Node.js, already required), and
`create-next-app`'s default kept the generated project's scripts/config consistent with
upstream Next.js documentation.

### Consequences

Slightly slower installs than pnpm at larger dependency-tree sizes; not a concern at
Phase 1's dependency count.

### Revisit When

If frontend dependency-install time becomes a measurable friction point (Phase 28+).

---

# ADR-018 — Structured Logging via stdlib `logging` + a JSON Formatter

### Status

ACCEPTED

### Context

LOOP.md and CLAUDE.md require structured, machine-readable backend logs with
timestamp/level/service/message/correlation_id, but explicitly warn against overbuilding
observability in Phase 1 (full OpenTelemetry tracing is a later phase).

### Decision

Use Python's standard-library `logging` module with a custom `JSONLogFormatter`
(`backend/app/core/logging.py`) that emits one JSON object per line, pulling
`correlation_id` from a `contextvars`-based request context
(`backend/app/core/context.py`). `LOG_FORMAT=console` switches to a human-readable
formatter for local development. No external logging framework (e.g. `structlog`) was
added.

### Alternatives Considered

1. `structlog` — richer structured-logging ergonomics (bound loggers, processors), but adds
   a dependency and a learning curve for a Phase 1 need that stdlib `logging` plus one
   formatter class fully satisfies.
2. Plain unstructured text logs — fails the explicit CLAUDE.md/LOOP.md requirement for
   machine-readable logs.

### Why This Option

Meets the stated requirement with the smallest reasonable footprint, and the
`contextvars`-based correlation ID is the same seam distributed tracing (`trace_id`/
`span_id`) will extend later without changing any call site.

### Consequences

If richer structured-logging features (log sampling, processor pipelines) are needed later,
migrating to `structlog` would touch `app/core/logging.py` only — call sites use the
standard `logging.getLogger(__name__)` pattern throughout, so the migration surface is
small.

### Revisit When

A later observability phase (Phase 26) needs processor-pipeline features stdlib `logging`
doesn't provide.

---

# ADR-019 — Typed, Environment-Driven Configuration on Both Sides

### Status

ACCEPTED

### Context

CLAUDE.md requires typed backend settings and an explicit frontend split between
server-only and public/browser-safe environment variables, with no secrets exposed through
`NEXT_PUBLIC_*` variables.

### Decision

Backend: a single `pydantic-settings` `Settings` class (`backend/app/core/config.py`) with
one alias per environment variable and safe local defaults, cached via `lru_cache` so it is
parsed once per process.

Frontend: two explicitly separate modules —
`frontend/src/lib/env/public.ts` (only reads `NEXT_PUBLIC_*` variables, safe to import
anywhere) and `frontend/src/lib/env/server.ts` (guarded by the `server-only` package, which
fails the build if imported from client code). `BACKEND_INTERNAL_URL` (server-only, Docker
network address) versus `NEXT_PUBLIC_API_BASE_URL` (public, host-facing address) is the
concrete case this split exists for.

### Alternatives Considered

1. A single flat frontend env module — simpler, but relies entirely on naming discipline to
   avoid leaking a server-only value into the client bundle; the `server-only` package makes
   the mistake a build failure instead of a naming convention.
2. Manually parsing `os.environ` in the backend — no validation, no typing, no single
   source of truth for defaults.

### Why This Option

Both sides get one authoritative, typed place configuration is read from, and the
frontend's server/public split is enforced by tooling, not just convention.

### Consequences

Every new environment variable must be added to `Settings` (backend) or the appropriate
`public.ts`/`server.ts` module (frontend) rather than read ad hoc from `process.env`/
`os.environ` at the point of use.

### Revisit When

Not expected to change; extend by adding fields, not by changing the pattern.

---

# ADR-020 — Single Bridge Network, Service-Name DNS, Host Ports for Dev Tooling

### Status

ACCEPTED

### Context

Services need to reach each other inside `docker-compose.yml` and, for local development
convenience, be reachable from the host (`psql`, `redis-cli`, browser, curl, IDE tooling).

### Decision

All services join one bridge network (`lubrisense-net`) and address each other by Compose
service name (`postgres`, `redis`, `mosquitto`, `kafka`, `backend`). Every service also
publishes its port to the host (configurable via `.env`, e.g. `POSTGRES_PORT`,
`KAFKA_PORT`) so host-side tooling and the verification scripts
(`scripts/verify_mqtt.sh`, `scripts/verify_kafka.sh`) work without extra network
configuration.

### Alternatives Considered

1. Multiple networks segmenting frontend-facing vs. internal-only services — more realistic
   production posture, but no Phase 1 requirement calls for it yet and it would complicate
   local debugging for no current benefit.
2. No host port publishing (container-network-only) — closer to a hardened deployment, but
   makes local development and the verification scripts significantly more awkward.

### Why This Option

Simplest topology that satisfies both inter-service communication and local-development
ergonomics; Kafka's advertised listener (`kafka:9092`) intentionally matches the internal
service-name address other containers use, since verification runs via `docker exec`
rather than host-side Kafka clients (see `scripts/verify_kafka.sh`).

### Consequences

Host port publishing is a local-development convenience, not a security posture — see
`docs/ARCHITECTURE.md` §10 (cybersecurity validation is explicitly a later, real-deployment
concern, not claimed here).

### Revisit When

A later phase introduces a hardened/production-like Compose or Kubernetes profile
(Phase 30+).

---

# ADR-021 — Liveness and Readiness Are Different Checks

### Status

ACCEPTED

### Context

`/health` and `/ready` are both required, and CLAUDE.md/LOOP.md distinguish "process
health" from "dependency readiness" — collapsing them into one check would make the backend
report itself unhealthy (and get restarted by an orchestrator) for a transient database
blip it could otherwise recover from.

### Decision

`GET /health` (`backend/app/api/health.py`) only calls `check_liveness()`, which always
returns healthy if the process can run the handler at all — no dependency calls. `GET
/ready` calls `check_readiness()`, which checks database and Redis connectivity and returns
HTTP 503 with a per-dependency breakdown if any check fails. Docker Compose health checks
(`docker-compose.yml`) use `/health` for the backend container's own `HEALTHCHECK`, while
`depends_on: condition: service_healthy` on `postgres`/`redis` gates backend startup on
*their* health checks rather than polling `/ready`.

### Alternatives Considered

1. One combined `/health` endpoint that checks dependencies — simpler, but conflates
   process liveness with dependency availability, which is exactly the distinction
   Kubernetes-style liveness/readiness probes exist to avoid.
2. `/ready` returning 200 with a `"not_ready"` body instead of a 503 — technically valid,
   but most orchestrators key routing/restart decisions off the HTTP status code, not the
   body, so a 503 makes the readiness signal actionable without extra parsing.

### Why This Option

Matches standard liveness/readiness semantics so this backend behaves correctly if/when it
sits behind a real orchestrator (Kubernetes or otherwise) in a later phase, without
over-engineering Phase 1 itself.

### Consequences

Two code paths to maintain (`check_liveness`, `check_readiness` in
`backend/app/services/health_service.py`), but each is a few lines and the distinction is
tested directly (`backend/tests/test_health.py`).

### Revisit When

Not expected to change.

---

# ADR-022 — Composite Tenant-Scoped Foreign Keys for Cross-Tenant Referential Integrity

### Status

ACCEPTED

### Context

Phase 2 requires that "the API layer [be] unable to accidentally query across tenants" and
that cross-tenant relationships be prevented, not just checked. Relying only on
application-level `tenant_id` filtering in every query is a real production risk: one
missed `WHERE tenant_id = ...` clause anywhere in a large codebase silently leaks
cross-tenant data.

### Decision

Every tenant-owned table carries `UNIQUE(tenant_id, id)` in addition to its primary key
(`app/domain/mixins.py::tenant_unique()`). Every parent/child foreign key is a *composite*
foreign key — `(tenant_id, parent_id) -> parent(tenant_id, id)`
(`app/domain/mixins.py::composite_tenant_fk()`) — instead of a plain `parent_id ->
parent(id)` foreign key. `LubricationPoint` is the clearest payoff: it carries two
independent composite FKs (to `circuit` and to `bearing`), so the database itself rejects
any attempt to link a circuit and a bearing from different tenants, satisfying the
"LubricationPoint cannot connect a Circuit and Bearing from different tenants" invariant
without a trigger or application-level check.

### Alternatives Considered

1. Plain foreign keys + tenant filtering only in application code (repositories/services).
   Simpler schema, but the isolation guarantee lives entirely in code discipline — a single
   missed filter is a real cross-tenant leak.
2. A Postgres `ROW LEVEL SECURITY` policy keyed on a session variable. Stronger in some
   ways, but requires setting a session-scoped GUC on every connection (awkward with a
   pooled async engine) and doesn't, by itself, solve the *insert*-time problem of a child
   row pointing at a wrong-tenant parent — RLS controls row *visibility*, not
   cross-table FK consistency.
3. A `CHECK` constraint comparing `tenant_id` across tables via a trigger. Works, but a
   composite FK is native Postgres functionality doing the same job more simply.

### Why This Option

Every table still also gets normal application-layer tenant filtering (defense in depth —
every `TenantScopedRepository` query includes `WHERE tenant_id = ...`, see
`app/repositories/base.py`), but the composite FK means a cross-tenant reference is
rejected by the database even if a repository/service check is ever missed or bypassed.
`backend/tests/test_domain_validation.py` proves this at the `IntegrityError` level, not
just at the service-error level.

### Consequences

Every table needs both its own `tenant_id` FK to `tenant` and, for each parent
relationship, a composite FK instead of a plain one — more verbose model definitions
(mitigated by the `composite_tenant_fk()` helper). One genuine complication: `reservoir_id`
/ `pump_id` / `controller_id` on `LubricationSystem` create a real FK cycle with `reservoir`
/ `pump` / `controller` (each has a required composite FK back to `lubrication_system`).
Intended resolution: SQLAlchemy's `use_alter=True` on those three specific constraints,
meant to emit them as a post-creation `ALTER TABLE` rather than inline in `CREATE TABLE`,
breaking the cycle — see the comment on `LubricationSystem.__table_args__`.

**Correction (found during Phase 7):** that intended resolution didn't actually work.
`use_alter=True` declared inline inside `op.create_table(...)` only suppresses the FK from
the inline `CREATE TABLE` DDL — it does not, by itself, cause Alembic to emit the follow-up
`ALTER TABLE ... ADD CONSTRAINT`. That step requires an explicit `op.create_foreign_key(...)`
call, which migration 08276baaeac2 never added. The three constraints were therefore never
created; the gap sat unnoticed because every write path already went through
`composite_tenant_fk()`-validated application code. It was masked further in migration
1f9fe8b7b163 (Phase 6), which misread alembic autogenerate's correct "these FKs are
missing" diff as a known false positive (by analogy with the real DESC-index false
positives elsewhere in the same diff) and suppressed it again. Fixed in migration
5257a5e8e595 (Phase 7) with the explicit `op.create_foreign_key(...)` calls Alembic never
emitted, applied against the live database and verified via `pg_constraint` plus a full
downgrade/upgrade cycle.

### Revisit When

Only if composite FKs prove to meaningfully complicate a future migration or ORM upgrade —
no such evidence yet.

---

# ADR-023 — Sensor/Gateway Attachment via Multiple Nullable Composite FKs + Exactly-One CHECK

### Status

ACCEPTED

### Context

A sensor attaches to exactly one of several different physical entity types (Machine,
Bearing, LubricationSystem, Reservoir, Pump, Circuit); a gateway to exactly one of Site or
Plant. The phase brief explicitly warns against "an unsafe arbitrary polymorphic
foreign-key design unless justified."

### Decision

`Sensor` and `Gateway` each carry one nullable composite foreign key per attachable entity
type, plus a `CHECK` constraint (`ck_sensor_exactly_one_attachment` /
`ck_gateway_exactly_one_attachment`) requiring exactly one to be non-null
(`app/domain/models.py`).

### Alternatives Considered

1. Generic polymorphic association: a single `(entity_type: str, entity_id: uuid)` pair.
   Rejected — the database cannot verify `entity_id` actually belongs to the table named
   by `entity_type`, and it cannot apply the tenant-composite-FK pattern (ADR-022) to an
   association whose target table isn't fixed at the schema level. This is exactly the
   "unsafe arbitrary polymorphic foreign-key design" the phase brief flags.
2. A separate join table per attachable type (`sensor_machine`, `sensor_bearing`, ...).
   Would work, but adds six join tables for no real benefit over six nullable columns on
   `Sensor` itself, and complicates the "exactly one" invariant (would need a check across
   tables rather than one row).

### Why This Option

Every attachment is a real, independently tenant-safe foreign key. The exclusivity rule is
enforced by Postgres, not application code — see
`backend/tests/test_domain_validation.py::test_sensor_requires_exactly_one_attachment_*`.

### Consequences

Adding a seventh attachable entity type means adding a new nullable column, a new composite
FK, and updating the CHECK constraint's column list — a small, explicit, three-line change,
not a schema redesign.

### Revisit When

If the number of attachable entity types grows large enough (a dozen+) that the wide-table
approach becomes unwieldy — no evidence of that at six.

---

# ADR-024 — Enums as VARCHAR + CHECK, Not Native Postgres ENUM Types

### Status

ACCEPTED

### Context

The domain model has many enumerations (`ServiceTier`, `CommercialStatus`, `Criticality`,
`OperationalStatus`, `MachineStatus`, `MachineType`, `LubricationSystemType`,
`CommissioningState`, `SensorType`, `SensorStatus`, `SensorQualityState`, `TenantStatus`) —
all explicitly demo/reference taxonomies (`docs/DOMAIN_MODEL.md` §2.3), not finalized
industry standards, and likely to gain values as later phases add nuance.

### Decision

Every enum is declared as a Python `StrEnum` and mapped via
`sqlalchemy.Enum(..., native_enum=False)` — persisted as `VARCHAR` with a `CHECK`
constraint, not a native Postgres `ENUM` type (`app/domain/models.py::_enum_column`).

### Alternatives Considered

1. Native Postgres `ENUM` types. More storage-efficient and self-documenting in `\d`
   output, but adding a value requires `ALTER TYPE ... ADD VALUE`, which historically
   cannot run inside the same transaction as other DDL in older Postgres versions and is a
   heavier migration operation than a `CHECK` constraint change.
2. No constraint at all (plain `VARCHAR`, validated only in Python/Pydantic). Rejected —
   loses database-level protection against bad data inserted outside the ORM (e.g. a manual
   `UPDATE`, a future direct-SQL migration, or a bug in a different service that shares the
   database).

### Why This Option

`native_enum=False` gets both: real Python type safety (the `StrEnum` classes are used
directly as field types in both ORM models and Pydantic schemas) and real database-level
validation (the `CHECK` constraint), while keeping "add a new value" a simple, low-risk
migration appropriate for taxonomies this project explicitly expects to evolve.

### Consequences

Slightly more verbose column definitions than a bare `sa.Enum(...)` — mitigated by the
`_enum_column()` helper. `CHECK`-constraint-based enums don't show their allowed values in
`\d` the way native enums do; allowed values are visible in the constraint definition or in
`app/domain/enums.py`.

### Revisit When

If a specific enum's value set genuinely stabilizes and storage/query performance at very
large row counts becomes a measured concern — no evidence yet.

---

# ADR-025 — Development-Only Tenant Context via a Required, Validated Header

### Status

ACCEPTED — explicitly temporary, see Revisit When.

### Context

Phase 2 requires every tenant-owned entity to resolve through an explicit tenant context in
the API layer, but full authentication/RBAC is explicitly out of scope until a later phase
(LOOP.md). The API cannot simply have no tenant concept in the meantime, or every later
phase would need to retrofit tenant-scoping into already-built endpoints.

### Decision

Every asset-hierarchy endpoint requires an `X-Tenant-ID` header, resolved and validated by
`app/api/deps.py::get_current_tenant`: parsed as a UUID
(`get_tenant_id_header` — 400 if missing/malformed), then looked up and required to be an
`ACTIVE` tenant (404 if unknown, 403 if inactive). Every service method takes an explicit
`tenant_id: uuid.UUID` parameter — never inferred from a global/thread-local/request
context — so the boundary between "trusted tenant id" and "everything downstream" is a
single function call, not scattered through the codebase.

### Alternatives Considered

1. No tenant header; accept a `tenant_id` query parameter or request-body field per
   endpoint. Rejected — inconsistent across endpoints, and easy to forget on a new one.
2. Skip validation, trust any `X-Tenant-ID` value blindly. Rejected — even as a dev-only
   mechanism, an unvalidated header would let a client silently operate against a
   non-existent or wrong tenant with no error, masking bugs during this phase's own
   development.
3. Build minimal real authentication now instead of a header stand-in. Rejected — LOOP.md
   explicitly defers auth/RBAC to a dedicated later phase; building a partial version now
   would likely need to be redone properly then.

### Why This Option

Gives every layer below the API a real, validated `tenant_id` to work with — repositories
and services are written exactly as they will be post-authentication, with tenant_id as an
explicit parameter. The *only* code that changes when real authentication arrives is
`get_tenant_id_header` (swap "read a header" for "extract a claim from a verified
token/session") — `get_current_tenant`'s existence/status check, and everything downstream,
stays the same.

### Consequences

**This is not a security boundary.** A client can put any UUID in the header. This is
explicitly documented at the point of use (`get_current_tenant`'s docstring) and in
`docs/ASSET_HIERARCHY.md` §3.2 to avoid anyone mistaking it for real tenant isolation at
the API layer (isolation between *data* is still fully enforced by ADR-022's composite FKs
and repository-level filtering — what's missing is proof that the *caller* is allowed to
act as the tenant they claim).

### Revisit When

The authentication/RBAC phase begins. `get_tenant_id_header` is the single function to
replace.

---

# ADR-026 — Hierarchy Queries Use Explicit `selectinload` Chains, Not Lazy Loading

### Status

ACCEPTED

### Context

Two endpoints assemble multi-level trees in one response
(`GET /api/v1/hierarchy`: Customer→Site→Plant→ProductionLine→Machine;
`GET /api/v1/machines/{id}/hierarchy`: Machine→Bearings and
Machine→LubricationSystem→{Reservoirs,Pumps,Controllers,Distributors,Circuits→
LubricationPoints}). The async SQLAlchemy engine does not support implicit lazy-loading
outside an active await context — an unguarded relationship access after the session has
moved on raises `MissingGreenlet`. This was caught concretely during Phase 2 development
when a naive `LubricationSystemResponse.model_validate(item)` in the *list* endpoint (whose
query does not eager-load) would have crashed exactly this way.

### Decision

Every multi-level query explicitly eager-loads with `selectinload` chains
(`CustomerAccountRepository.list_with_full_hierarchy`,
`MachineRepository.get_with_equipment`,
`LubricationSystemRepository.get_with_equipment`). Endpoints that don't need the nested
detail (the *list* view of lubrication systems) use a separate, smaller response schema
(`LubricationSystemSummaryResponse`) that only exposes fields present on the un-eager-loaded
query result, rather than eager-loading data nobody asked for.

### Alternatives Considered

1. Lazy-load relationships on demand. Not viable under the async engine without `AsyncAttrs`/
   explicit `await` boilerplate at every access site — `selectinload` is simpler and
   produces a bounded, predictable number of queries.
2. `joinedload` (single query via SQL `JOIN`s) instead of `selectinload` (one additional
   query per level). Rejected for the deepest chains (4–5 levels) — a single mega-join
   multiplies row counts (Cartesian-product-like fan-out across each collection) and is
   harder to reason about than a small, fixed number of `IN (...)` queries.

### Why This Option

`selectinload` gives a fixed, small number of queries regardless of row count at each
level (no N+1), is straightforward to read as an explicit list of "what this endpoint
needs," and avoids the `MissingGreenlet` failure mode entirely by never relying on implicit
lazy access.

### Consequences

Every new nested field a response schema needs must have a corresponding `selectinload` (or
its own dedicated summary schema) — an omission fails loudly (`MissingGreenlet`) rather than
silently returning wrong data, which is the safer failure mode.

### Revisit When

`docs/ASSET_HIERARCHY.md` §8 documents the current scaling ceiling (fine to thousands of
machines per tenant for `/machines/{id}/hierarchy`; `/hierarchy` returning a whole tenant's
fleet in one response would need pagination at large fleet sizes). Revisit if real usage
approaches that ceiling.

---

# ADR-027 — Offset/Limit Pagination Everywhere

### Status

ACCEPTED

### Context

Every list endpoint needs a consistent pagination approach (LOOP.md §24).

### Decision

`limit`/`offset` query parameters (default `limit=50`, max `200`, default `offset=0`),
implemented once in `TenantScopedRepository.list` (`app/repositories/base.py`) and reused
by every repository; response shape is `{"items": [...], "meta": {"total", "limit",
"offset", "has_more"}}` (`app/api/schemas/common.py::PaginatedResponse`).

### Alternatives Considered

1. Cursor-based (keyset) pagination. More stable under concurrent inserts and avoids the
   `COUNT(*)`/deep-`OFFSET` cost at large table sizes, but adds real complexity (a stable
   sort key per entity, opaque cursor encoding/decoding) that Phase 2's entity counts
   (dozens to low hundreds per tenant) don't yet justify.
2. No pagination (return everything). Rejected outright — fails at any real fleet size and
   was explicitly ruled out by the phase brief.

### Why This Option

Simplest approach that is genuinely consistent across all list endpoints, with a single
shared implementation so every repository gets identical semantics for free.

### Consequences

`COUNT(*)` runs on every list call (one query, in addition to the page query) — acceptable
at current scale; would need reconsideration (e.g. approximate counts, or dropping `total`
from the default response) if list endpoints are ever called against tables large enough
for `COUNT(*)` itself to be slow.

### Revisit When

Query latency or write-concurrency issues actually appear at realistic fleet-scale list
sizes (thousands+ of rows per tenant) — not before.

---

# ADR-028 — Deterministic Seed IDs via `uuid.uuid5`

### Status

ACCEPTED

### Context

The demo dataset (`backend/scripts/seed_demo_data.py`) must be idempotent — re-running it
must not create duplicate rows (LOOP.md §27, §41).

### Decision

Every seeded entity's primary key is `uuid.uuid5(SEED_NAMESPACE, stable_string_key)` — a
deterministic UUID derived from a fixed namespace constant and a stable string built from
the entity's natural identity (e.g. `"customer:NSI"`, `"machine:7"`, `"bearing:7:DRIVE_END"`).
`get_or_create()` looks up that id first and only inserts if absent — the entire idempotency
mechanism is "the same input always produces the same id."

### Alternatives Considered

1. Random UUIDs (`uuid.uuid4`) + a separate "already seeded" tracking table/flag. Works, but
   requires either an all-or-nothing seed marker (can't safely re-run after a partial
   failure) or a second lookup mechanism (e.g. by natural key/unique code) duplicating what
   `uuid5` gives for free.
2. Natural/sequential integer keys for seed data specifically, UUIDs for everything else.
   Rejected — would mean two different ID schemes in the same tables depending on
   provenance (seeded vs. API-created), which is confusing and has no real benefit over
   just using `uuid5` for the seeded rows too.

### Why This Option

`uuid5` is a standard-library one-liner that makes "run this script twice" trivially safe
and, as a side benefit, makes the demo tenant's data reproducible byte-for-byte across
environments (useful for the machine-hierarchy examples in this document and in
`docs/DEVELOPER_SETUP.md`, which reference a real, stable tenant id).

### Consequences

Seeded IDs are not random-looking UUIDs — anyone inspecting the database can recompute them
from the namespace + key, which is fine (they're demo data, not secrets) and is in fact the
whole point.

### Revisit When

Not expected to change; this pattern extends cleanly if the seed dataset grows.

---

# ADR-029 — ORM Models Double as the Domain Layer; No Parallel Dataclass Domain Model

### Status

ACCEPTED

### Context

The suggested backend structure (`docs/ARCHITECTURE.md` §11, `LOOP.md`) lists `domain/` as
a directory separate from `infrastructure/`, which could be read as "domain/ should contain
framework-independent dataclasses, with a separate ORM-mapping layer elsewhere." Phase 2
needed to decide how literally to take that separation.

### Decision

The SQLAlchemy ORM classes in `app/domain/models.py` **are** the domain layer — there is no
parallel, framework-independent dataclass representation that repositories translate to/
from. Services and repositories operate on these ORM objects directly. The real separation
Phase 2 enforces is domain (`app/domain/`) vs. API contract (`app/api/schemas/`): a
Pydantic response schema never exposes an ORM object's internals directly, and request
schemas are separate dataclasses in the service layer's `*Create` types
(`CustomerAccountCreate`, `SiteCreate`, etc.) — but domain and persistence are one layer,
not two.

### Alternatives Considered

1. Pure dataclasses for domain entities, with a separate mapper layer translating to/from
   SQLAlchemy models. More "clean architecture"-orthodox, but for a schema this size (16
   entities) it would roughly double the amount of field-listing boilerplate for no
   behavioral difference yet — no domain logic exists today that isn't either a database
   constraint or a service-layer validation already expressed in terms of the ORM objects.
2. Anemic ORM models with all logic in services (current approach) vs. rich domain models
   with behavior methods on the entities themselves. Mostly moot at Phase 2's stage — the
   one behavior method that exists (`Sensor.attached_entity_type`/`attached_entity_id`) is
   read-only and trivial; revisit if genuine domain behavior (state transitions, computed
   invariants) accumulates.

### Why This Option

Avoids maintaining two parallel representations of the same 16 entities with no present
benefit; keeps the actually-important boundary (domain/persistence vs. API contract, per
`TECHNICAL_DECISIONS.md` ADR-008: frontend/API never sees raw ORM objects) sharp and
enforced by the schema layer instead.

### Consequences

If domain logic grows complex enough that mixing it with SQLAlchemy's mapped-class
machinery becomes awkward (e.g. needing to unit-test business rules without a database),
introducing a thin dataclass layer for just the entities that need it remains possible
without a full rewrite — the API/schema boundary, which is the one that matters for
external contracts, is already in place.

### Revisit When

A specific domain entity accumulates enough non-trivial business logic that testing it
without a database becomes a real friction point — no evidence of that yet.

---

# ADR-030 — Simulator Reads Topology via Plain SQL, Not the Backend ORM

### Status

ACCEPTED

### Context

Phase 3 requires the simulator to operate on the real Phase 2 asset hierarchy (machine,
bearings, lubrication system chain, sensors) rather than a disconnected synthetic universe.
`simulator/` is a separate top-level service directory with its own `pyproject.toml`
(`TECHNICAL_DECISIONS.md` ADR-011 — repository architecture mirrors the intelligence
chain), so how it reads that data without coupling to `backend/` needed a decision.

### Decision

`simulator.engine.repository.TopologyRepository` connects to the same PostgreSQL database
with plain `psycopg` and hand-written, read-only SQL (`SELECT` only, never writes), mapping
rows onto simulator-local dataclasses in `simulator.domain.topology`. It does not import
`backend.app.domain.models` or any other backend package.

### Alternatives Considered

1. Import `backend/app` as a dependency of `simulator/`. Rejected — couples two services
   that are supposed to be independently deployable/runnable (a real edge/simulator
   deployment should not need the full FastAPI backend installed), and backend's SQLAlchemy
   models are async-session-oriented, an awkward fit for a simple, synchronous,
   read-at-startup topology load.
2. A dedicated internal HTTP API on the backend for topology lookup. More architecturally
   "correct" for a true microservice boundary, but the Phase 3 brief explicitly says "Do not
   build a full simulator API yet" (§30) and a topology-read HTTP API on the backend is out
   of scope for the same reason — Phase 3 is physical simulation quality, not API surface.
3. Duplicate the schema via a second Alembic-managed migration set owned by `simulator/`.
   Rejected — one schema, one migration history (Phase 2's), read by multiple services, is
   simpler than trying to keep two migration histories in sync for the same tables.

### Why This Option

Plain SQL against the live schema is the smallest change that satisfies "use the actual
seeded domain entities, do not create a separate disconnected asset universe" without
adding a service dependency or a second schema-ownership question. `TopologyRepository`
is small and isolated (`simulator/simulator/engine/repository.py`) — if Phase 6+ later
decides a real topology API is warranted, only this one module needs to change.

### Consequences

The simulator has an implicit schema dependency on `backend/`'s Alembic migrations (table
and column names) without a compile-time contract — a backend schema change that renames a
column silently breaks the simulator's SQL rather than failing a type check.
`tests/test_topology_repository.py` runs against the live database specifically to catch
this class of drift early.

### Revisit When

Phase 6 (Telemetry Pipeline) or a real microservice deployment boundary makes a proper
topology API worth the added surface — no evidence of that yet at Phase 3.

---

# ADR-031 — Reduced-Order Physics with Exact Exponential Lag, Not Linear Euler Steps

### Status

ACCEPTED

### Context

Nearly every physical quantity the simulator models (pump pressure, bearing temperature,
bearing vibration, circuit restriction's natural variation, ambient-adjacent lubricant
temperature) needs to move toward a changing target smoothly rather than jump
instantaneously (Phase 3 brief §5, §10: "avoid physically impossible instantaneous jumps",
"do NOT make vibration instantly rise whenever pressure rises"). The simulator also must
support a wide range of step sizes — 1s live-demo steps up to 60s+ steps for multi-day
historical generation (§15, §21) — without the lag behavior becoming step-size-dependent.

### Decision

Every lagged quantity uses `simulator.physics.util.exp_relax`: the exact closed-form
solution of a first-order lag, `new = current + (target - current) * (1 - exp(-dt/tau))`,
rather than a linear Euler step (`current + (target - current) * dt/tau`).

### Alternatives Considered

1. Linear Euler step (`dt/tau` directly as the blend factor). Simpler to read, but
   numerically unstable once `dt` approaches or exceeds `tau` — a 60s step against a
   pump-pressure time constant of 6s would overshoot the target by roughly `dt/tau = 10x`
   and oscillate divergently, a real risk given Phase 3's requirement to support both small
   live-demo steps and large historical-generation steps with the *same* physics code.
2. A fixed small internal sub-step (e.g. always integrate at 1s regardless of the caller's
   requested step) with Euler integration. Avoids the instability but silently multiplies
   the number of physics evaluations for large-step historical runs, working against §21's
   "do not generate unnecessary [computation]" spirit and adding a second, hidden time
   granularity the rest of the engine doesn't otherwise have.

### Why This Option

The exponential form is unconditionally stable for any `dt >= 0` and `tau > 0` — the result
is always strictly between `current` and `target`, by construction, regardless of step
size. It is one line of well-understood control-theory math (`simulator/simulator/physics/
util.py`), reused everywhere a lag is needed, so every physics module gets the stability
guarantee for free rather than re-deriving it.

### Consequences

All lag-based physics functions take `dt_s` explicitly rather than assuming a fixed
timestep, which is also what makes the CLI's `--step` and mode-based default step sizes
(SMOKE=5s vs FULL=60s) safe to vary without touching physics code.

### Revisit When

Not expected to change; if a future phase needs second-order dynamics (e.g. genuine
overshoot/ringing behavior for a specific failure mode), that would be an additive model
for that specific signal, not a replacement for this general-purpose lag primitive.

---

# ADR-032 — Ground Truth and Observed Telemetry Are Distinct Output Types

### Status

ACCEPTED

### Context

Phase 3 brief §18 requires that hidden physical state (`restriction_factor`,
`pump_efficiency`, true bearing condition, ...) never leak into what a later ML phase would
treat as a feature — a model evaluated against ground truth it would never have access to
in a real deployment would report unrealistically good performance that cannot be
reproduced against real sensors.

### Decision

`simulator.engine.output` defines two structurally distinct dataclasses,
`SimulationReading` (observable — `true_value`/`observed_value` for one sensor) and
`GroundTruthRecord` (hidden state — `restriction_factor`, `pump_efficiency`,
`lubrication_effectiveness`, `health`, ...), written to two separate files
(`<output>.readings.jsonl` / `<output>.ground_truth.jsonl`) by two separate `JsonlWriter`
instances. `tests/test_ground_truth_separation.py` asserts structurally (via
`dataclasses.fields`) that `SimulationReading`'s field set is disjoint from a fixed list of
hidden-state field names, so a future edit that accidentally adds e.g. `restriction_factor`
to `SimulationReading` fails a test immediately rather than being caught only by review.

### Alternatives Considered

1. One combined record type with an "internal" vs. "observable" field-visibility flag or
   documentation convention. Rejected — relies entirely on every future consumer reading and
   respecting a convention; a copy-paste of the wrong fields into a training pipeline would
   compile and run without error.
2. Keep hidden state only in `SimulationEngine`'s in-memory state, with no persisted ground
   truth output at all. Rejected — Phase 3 brief §29 explicitly requires a ground-truth
   stream for future model evaluation; without it, later phases have no way to check "did
   the model actually detect the condition that was really present."

### Why This Option

Two separate types in two separate files is enforceable by the type system and the
filesystem, not just a naming convention — a Phase 11+ feature pipeline that only ever
opens `<run>.readings.jsonl` structurally cannot see `GroundTruthRecord` fields.

### Consequences

Any new hidden-state variable a future phase introduces must be added to
`GroundTruthRecord` (and the disjointness test's field list), not bolted onto
`SimulationReading` for convenience.

### Revisit When

Not expected to change — this is the foundational contract the rest of the ML pipeline
(Phases 10-13) is built to respect.

---

# ADR-033 — Single Seeded RNG Instance Threaded Through the Whole Engine

### Status

ACCEPTED

### Context

Phase 3 brief §16 requires that "given the same seed, configuration, asset, scenario, start
state, the simulator must produce reproducible output" — determinism is required for tests,
model evaluation, and demo replay, and must hold across every stochastic element (sensor
noise, sensor bias, operating-profile load-target draws, ambient-temperature noise,
circuit natural-variation noise, pump-efficiency noise).

### Decision

`SimulationEngine.__init__` creates exactly one `random.Random(seed)` instance and passes
it explicitly into every physics/sensor function that needs randomness
(`OperatingProfile.step(..., rng)`, `step_ambient_temperature(..., rng)`,
`LubricationCycleController.step(..., rng)`, `sensor_models.observe(..., rng)`, etc.).
Nothing in `simulator/` calls the global `random` module functions or creates a second
`random.Random()` instance mid-run.

### Alternatives Considered

1. Multiple independent RNGs (one per subsystem: sensors, operating profile, physics
   noise). Gives slightly more isolation (changing one subsystem's call count doesn't
   perturb another's draws), but multiplies the seed-management surface and the brief's
   determinism requirement is "same seed -> same output" for the *whole* simulation, not
   independently per subsystem — one RNG is the simplest thing that satisfies it.
2. NumPy's `Generator` (`numpy.random.default_rng(seed)`) instead of stdlib `random.Random`.
   Comparable determinism guarantees and better performance for large vectorized draws, but
   Phase 3's draws are all scalar (one Gaussian/uniform per tick per quantity), so stdlib
   `random` avoids adding NumPy as a hard runtime dependency for something `random.Random`
   already does correctly and simply. (NumPy is still a `dev`-only dependency, used solely
   by the optional `matplotlib` visual-validation script's dependency chain.)

### Why This Option

One RNG instance, explicitly passed rather than module-global, makes the determinism
mechanism auditable by inspection — every stochastic call site visibly takes `rng` as a
parameter, so there is no hidden global-state source of nondeterminism to miss.
`tests/test_engine_determinism.py` proves same-seed => identical output and
different-seed => different noise but identical measurement-type shape.

### Consequences

Every new stochastic physics/sensor function added in a later phase must accept `rng`
explicitly as a parameter — using `random.random()` or a fresh `random.Random()` anywhere
in `simulator/` would silently break determinism and should be treated as a bug.

### Revisit When

Not expected to change.

---

# ADR-034 — JSON Lines as the Internal Output Contract, CSV/Parquet as Optional Conveniences

### Status

ACCEPTED

### Context

Phase 3 brief §17 and §19 require a structured internal output contract that a future
telemetry adapter can map onto `docs/EVENT_CATALOG.md`'s `TelemetryReading`, while also
warning "do not make flat CSV the architecture boundary" (§19).

### Decision

`SimulationReading`/`GroundTruthRecord`/`RunMetadata` are Python dataclasses
(`simulator.engine.output`) with a `to_dict()` method; the CLI's default output is JSON
Lines (`JsonlWriter`, one JSON object per line, append-only, matching the append-only
telemetry principle in `docs/EVENT_CATALOG.md` §1). `--csv` additionally writes a
`CsvReadingWriter` copy of `SimulationReading` rows only, for quick spreadsheet/manual
inspection.

### Alternatives Considered

1. CSV as the primary/only output. Rejected outright by the phase brief; CSV also cannot
   naturally represent `GroundTruthRecord`'s nested per-bearing/per-circuit lists without a
   lossy flattening scheme.
2. Parquet as the primary output. Better for large-scale analytical (TRAINING/FULL mode)
   consumption, but adds a `pyarrow`/`pandas`-class dependency for a Phase 3 need that JSONL
   fully satisfies; Parquet remains a reasonable addition for a later phase's specific
   consumption pattern (e.g. a feature-engineering pipeline that wants columnar reads)
   without needing to change the dataclass/`to_dict()` layer underneath it.

### Why This Option

The dataclasses are the actual contract; JSONL is simply the simplest serialization of them
that preserves nested structure, is trivially append-only/streamable, and is directly
`jq`/`python -m json.tool`-inspectable during development (used throughout Phase 3
verification). Adding a Parquet writer later is additive (a new writer class consuming the
same `to_dict()` output), not a redesign.

### Consequences

Row-oriented JSONL is less space/query-efficient than a columnar format for very large
(FULL-mode, tens of millions of rows) datasets — flagged as a known limitation, not
addressed since Phase 3 explicitly scopes large-volume generation behind an opt-in
confirmation (§21) rather than a default workload.

### Revisit When

A later phase (Phase 10 Feature Engineering, Phase 32 MLOps) has a concrete large-dataset
consumption pattern that JSONL measurably underserves.

---

# ADR-035 — Scenarios Are Additive Offsets Applied Through Existing Physics, Never a Second Control Path

### Status

ACCEPTED

### Context

Phase 4 requires failure injection to act on hidden physical state, never overwrite a
sensor value directly (Phase 4 brief §1: `if scenario == "blockage": pressure = 200` is
explicitly forbidden). Without an explicit architectural rule, it would be easy for a future
scenario implementation to take a shortcut — e.g. special-casing `SimulationReading`
construction when a scenario is active — that technically satisfies "looks physically
derived" without actually being derived from the physics layer.

### Decision

Every scenario effect is implemented as an additional parameter passed into a Phase 3
physics function that already existed before Phase 4 and is unaware "scenarios" exist as a
concept: `step_natural_variation(restriction_offset=..., leakage_offset=...)`,
`step_efficiency(efficiency_offset=...)`, `apply_independent_wear(target_health=...)`
(a new function, but one that only ever writes `bearing.health`, the same field
`step_health` already owns), and the cycle controller's
`restriction_offsets`/`reservoir_availability`/`volume_multiplier` parameters. All default
to "no effect" (0.0 offset, 1.0 multiplier), so a `SimulationEngine` constructed with zero
scenario instances is byte-for-byte the Phase 3 healthy code path — there is no `if
scenario:` branch anywhere in `simulator/physics/`.

`simulator/scenarios/effects.py` computes these offsets from active instances' severities
and is structurally forbidden from touching output types: it has no import of
`simulator.engine.output`.

### Alternatives Considered

1. A separate "scenario physics" module that recomputes pressure/flow/vibration/etc. from
   scratch when a scenario is active, falling back to the Phase 3 functions otherwise.
   Rejected — guarantees the two code paths drift apart over time (a Phase 3 physics tweak
   would need a matching Phase 4 tweak, easy to forget), and doubles the surface a bug can
   hide in.
2. Sensor-layer post-processing: let the Phase 3 physics run untouched, then adjust the
   *reading* afterward based on active scenarios. Rejected outright — this is exactly the
   `if scenario: pressure = 200` anti-pattern the brief forbids, just moved one layer later
   (post-physics instead of post-nothing); it would also make `true_value` scenario-aware
   while claiming to represent "the real physical value," breaking the ground-truth
   contract (`docs/SYNTHETIC_DATA_MODEL.md`).

### Why This Option

A reviewer can verify "no scenario ever fakes a sensor value" by inspecting one file
(`effects.py`) for the absence of an import, rather than auditing every physics function for
scenario-awareness. Every relationship Phase 3 already established (restriction → pressure,
efficiency → pressure-rise time, health → vibration) automatically applies to the Phase 4
scenario that drives the same variable, with zero duplicated logic.

### Consequences

Every new scenario type's implementation is "find the existing physics function that reads
the hidden variable this fault should move, add an optional parameter to it" rather than
writing new physics — a real constraint that occasionally required extending physics
functions with a new capability (e.g., raw-vs-delivered flow splitting, ADR-041) rather than
just parameterizing what already existed.

### Revisit When

A future failure mode genuinely cannot be expressed as an offset/target on an existing
hidden-state variable — expected to be rare given the deliberately reduced-order physics
model's small parameter set.

---

# ADR-036 — Six Reusable Progression Profiles as Pure, RNG-Free Functions of Elapsed Time

### Status

ACCEPTED

### Context

Phase 4 brief §4 requires reusable progression profiles (STEP, LINEAR, EXPONENTIAL,
SIGMOID, INTERMITTENT, CYCLIC) shared across failure modes rather than each scenario type
inventing its own timing logic. Determinism (`docs/SIMULATOR.md` §13) must also hold for
scenarios with on/off behavior (Sensor Dropout, Network Failure), not just continuously
ramping ones.

### Decision

`simulator.scenarios.progression.compute_severity(profile, elapsed_s, onset_s, ...)` is a
single pure function covering all six profiles, taking no RNG parameter at all —
`INTERMITTENT`'s on/off pattern is a deterministic square wave
(`(elapsed_s % period_s) / period_s < duty_cycle`), not a randomized coin-flip per tick.

### Alternatives Considered

1. One `ScenarioInstance` subclass per progression type, each with its own `step()` timing
   logic. Rejected — six subclasses for what is fundamentally "one function of elapsed
   time, six different shapes" is unnecessary indirection; the shared function is also
   trivially unit-testable in isolation (`tests/test_scenario_progression.py`) without
   constructing a full `ScenarioInstance`.
2. Randomized `INTERMITTENT` (e.g. a Bernoulli draw per tick with `duty_cycle` probability).
   More "naturally intermittent"-looking, but would need its own RNG draw threaded through
   from the engine, adding a second source of nondeterminism-sensitivity for one profile
   type only; the deterministic square wave is simpler, exactly reproducible without needing
   the seed at all, and still produces a clearly intermittent, testable on/off pattern.

### Why This Option

Determinism becomes trivial to reason about: `compute_severity` is not just seed-independent
but has no notion of "randomness" whatsoever — the *only* source of nondeterminism in the
entire simulator remains the one `random.Random(seed)` instance `SimulationEngine` owns for
sensor noise and healthy natural variation, exactly as Phase 3 established.

### Consequences

`INTERMITTENT`'s on/off windows are perfectly regular (a real square wave), not the more
naturally-varied on/off pattern a randomized approach would produce. Acceptable for a demo
failure signature; a future phase wanting jittered dropout windows would add an optional
`rng` parameter to `compute_severity` for that profile specifically, not change the other
five.

### Revisit When

A specific downstream consumer (e.g. Phase 11 ML training) needs less mechanically regular
intermittent-fault timing to avoid a model overfitting to the exact period.

---

# ADR-037 — Multi-Instance Ground Truth (`scenarios` list) with a Backward-Compatible Singular Summary

### Status

ACCEPTED

### Context

Phase 3's `GroundTruthRecord` had singular `scenario`/`severity`/`affected_component`
fields, populated with the single `HEALTHY` label. Phase 4 brief §16 requires multi-fault
support, and §22 requires the ground truth to record every active scenario's
type/phase/severity/target — a list, not a single value, once more than one scenario can be
active simultaneously.

### Decision

Add `scenarios: tuple[ScenarioGroundTruth, ...]` as the authoritative, complete record (one
entry per active instance). Keep the Phase 3 singular fields, now populated from the
highest-severity active instance (or `"NORMAL"`/`"NONE"`/`None`) — a convenience summary for
simple single-fault cases and Phase 3-era consumers, explicitly documented as non-authoritative
once multiple scenarios are active (`docs/SYNTHETIC_DATA_MODEL.md` §2.1).

### Alternatives Considered

1. Replace the singular fields entirely with the list, breaking any Phase 3-era consumer
   expecting `scenario`/`severity` to exist. Rejected — `docs/SYNTHETIC_DATA_MODEL.md`
   (Phase 3) explicitly promised "the field shape is already in place so Phase 4 does not
   need to change `GroundTruthRecord`'s schema, only what populates it"; removing fields
   would break that promise for no functional benefit, since keeping them as a summary costs
   nothing.
2. Encode multiple scenarios into the singular fields via string concatenation (e.g.
   `scenario="GRADUAL_RESTRICTION,SENSOR_DRIFT"`). Rejected — not machine-readable, loses
   per-scenario severity/target/lifecycle detail, and is exactly the kind of ad hoc encoding
   a typed `tuple[ScenarioGroundTruth, ...]` avoids.

### Why This Option

Both real requirements are satisfied without contradiction: a full, typed, multi-fault
record for anything that needs complete detail, and a stable, simple single-value read for
anything that only cares about "what's the worst thing happening right now."

### Consequences

Any future consumer that only reads the singular fields will silently miss lower-severity
concurrent scenarios during a multi-fault run — acceptable since those consumers are
explicitly documented as reading a "convenience summary," and the full list is one field
away.

### Revisit When

Not expected to change; if a specific downstream phase (e.g. Phase 13 Condition
Intelligence's evaluation harness) finds itself needing the singular fields for anything
beyond human-readable convenience, that is a sign it should be reading `scenarios` instead.

---

# ADR-038 — Scenario Targets Resolve Against the Live Topology via a Static Type-Compatibility Table

### Status

ACCEPTED

### Context

Phase 4 brief §17 requires scenario targets to resolve to real Phase 2 entities and requires
an incompatible target type (e.g. Sensor Drift pointed at a Circuit) to fail validation, not
silently do nothing or crash deep in the physics layer.

### Decision

`simulator.scenarios.types.VALID_TARGET_TYPES` is a plain `dict[ScenarioType,
ScenarioTargetType]` — the single source of truth for which target type each of the 10
catalog scenarios requires. `ScenarioDefinition` validates
`target_type == VALID_TARGET_TYPES[scenario_type]` at YAML-load time (a config-authoring
error surfaces immediately, before any simulation runs). `simulator.scenarios.targeting
.resolve_target` then validates the *runtime* target (an explicit `--target` code/UUID, or
the first available entity when omitted) against the real `MachineTopology`, raising
`ScenarioTargetError` for an unknown code, a UUID not present on the machine, or a real id of
the wrong entity type.

### Alternatives Considered

1. Duck-typed targeting: let each scenario's effect function attempt to look up its target
   in whatever topology collection seems relevant, and silently no-op if not found. Rejected
   outright — this is precisely the "fail validation" requirement's negative case; a
   misconfigured scenario would run for hours before anyone noticed it never targeted
   anything.
2. Encode target-type compatibility as a method on each `ScenarioType` enum member (e.g. a
   `@property`). Rejected — a plain dict keeps the compatibility table visible as one flat,
   reviewable structure (`docs/SCENARIO_ENGINE.md` §6's table is a direct rendering of it)
   rather than scattered across enum member definitions.

### Why This Option

Two independent validation layers (schema-time type-compatibility, runtime target
existence) catch the two different ways a scenario configuration can be wrong, each as early
as it can possibly be caught, both covered by direct unit tests
(`tests/test_scenario_definition.py`, `tests/test_scenario_targeting.py`) rather than only
discoverable via an end-to-end simulation run.

### Consequences

Adding an eleventh scenario type requires one new `VALID_TARGET_TYPES` entry — a one-line,
impossible-to-forget change enforced by
`tests/test_scenario_definition.py::test_every_committed_definition_matches_its_valid_target_type`
failing if it's missed.

### Revisit When

Not expected to change.

---

# ADR-039 — Multi-Fault Precedence: Additive Composition for Numeric Offsets, Fixed Rank Order for Sensor Observability

### Status

ACCEPTED

### Context

Phase 4 brief §16 requires multi-fault support with defined conflict/precedence rules
"where multiple scenarios modify the same hidden state" — without an explicit rule, two
scenarios targeting the same parameter of the same entity (e.g. two restriction-type faults
on one circuit) would have undefined combined behavior, and a sensor simultaneously eligible
for both Sensor Dropout and Network Failure treatment would have an ambiguous reading.

### Decision

Two different composition rules for two different kinds of conflict
(`simulator.scenarios.effects.build_effects` docstring, `docs/SCENARIO_ENGINE.md` §10):

- **Numeric hidden-state offsets** (restriction, leakage, pump efficiency loss): multiple
  active instances on the same target/parameter **sum additively**; the *receiving* physics
  function (not the scenario layer) clips to the physically valid range. Independent
  Bearing Fault (health target) and Over-Lubrication (volume multiplier) use **min**/**max**
  respectively, matching "the more severe instance wins" for a target-value-style effect
  rather than an additive one.
- **Sensor observability** (which quality/observed-value a reading gets this tick):
  a **fixed rank order**, `NETWORK_FAILURE > SENSOR_DROPOUT > SENSOR_DRIFT`, applied when
  collecting readings (`SimulationEngine._collect_readings`), not when aggregating effects.

### Alternatives Considered

1. Last-write-wins based on instance list order. Rejected — silently order-dependent
   (reordering `--scenario` flags on the CLI would change simulation output for reasons
   invisible to the user), and provides no principled reason for any particular order.
2. Reject construction of a `SimulationEngine` if two scenario instances would ever
   conflict. Rejected — overly restrictive (additive composition of, say, restriction +
   leakage on the same circuit is physically sensible and explicitly required to work,
   Phase 4 brief §16), and "would ever conflict" is not statically knowable before running
   the simulation (their active windows might not even overlap).

### Why This Option

Additive composition for continuous physical offsets matches how independent physical
phenomena actually combine (two partial obstructions in series do add resistance); the
sensor-observability rank order matches physical reality directly — a machine with no
network connectivity has no working sensors regardless of any individual sensor's own
state, and a sensor that isn't reporting at all has no drifted value to report. Both rules
are single, reviewable statements (this ADR, the `docs/SCENARIO_ENGINE.md` §10 table, and
the `build_effects` docstring — all three necessarily say the same thing) rather than
implicit behavior a reader would have to reverse-engineer from the code.

### Consequences

Adding an eleventh scenario type that could plausibly coexist with an existing one on the
same target requires an explicit decision about which of the two composition rules (or a
new one) applies — not automatic, but forced to be a conscious, documented choice via this
ADR and `docs/SCENARIO_ENGINE.md` §10.

### Revisit When

A future scenario type's natural combination semantics don't fit either "additive" or
"min/max ceiling" (e.g. a multiplicative interaction) — no evidence of that among the 10
catalog scenarios.

---

# ADR-040 — Nullable `observed_value` and an Expanded `SensorQuality` for Missing/Communication-Loss Semantics

### Status

ACCEPTED

### Context

Phase 3's `SimulationReading.observed_value` was a required `float`. Phase 4 brief §13
explicitly forbids representing a missing observation as `0.0` ("do not use zero as the
default representation of missing data") for Sensor Dropout and Network Failure, while
`true_value` must keep being computed and stored regardless (brief §13-§14: physical truth
continues).

### Decision

`SimulationReading.observed_value` becomes `float | None`. `None` is produced only by Sensor
Dropout (`quality=MISSING`) and Network Failure (`quality=COMMUNICATION_LOSS`) — never by
ordinary sensor noise/clipping, which still always produces a real, if `SUSPECT`-flagged,
number. `SensorQuality` gains `MISSING`, `COMMUNICATION_LOSS`, and (as forward-looking,
currently-unused hooks) `UNCERTAIN`/`INVALID`.

### Alternatives Considered

1. A sentinel float (e.g. `NaN` or `-1.0`) instead of `None`. Rejected — `NaN` would trip
   `SimulationEngine._validate_state`'s `math.isfinite` numerical-stability guard if it ever
   leaked into hidden state by mistake, and any sentinel float risks being silently treated
   as a real value by a downstream consumer that doesn't check `quality` first; `None` fails
   loudly (a `TypeError` on arithmetic) instead of silently producing a wrong number.
2. Omit the row entirely from `SimulationReading` output when unavailable, rather than
   emitting a row with `observed_value=None`. Rejected — loses the `true_value`/`quality`/
   timing information that specific tick's row would otherwise carry, and makes "how many
   ticks was this sensor down" harder to compute (would require diffing against expected
   sensor/tick combinations rather than counting `quality != GOOD` rows directly).

### Why This Option

`None` is the natural, type-checked (mypy strict) representation of "this value does not
exist," and keeping one row per sensor per tick (with `true_value` always populated) means
every consumer of the readings stream sees a complete, regular time series to reason about,
with unavailability as an explicit, queryable field rather than a gap to infer.

### Consequences

Every downstream consumer of `SimulationReading.observed_value` (already true of the CSV
writer, which now writes an empty cell for `None`) must handle the `None` case — a
one-time, mypy-enforced migration cost, paid once in this phase.

### Revisit When

Not expected to change; `UNCERTAIN`/`INVALID` remain reserved for whichever future phase
first needs to produce them (candidates: Phase 5 edge-side data-quality checks, Phase 7 data
quality engine feeding a state back into the simulator for a closed-loop demo — neither
exists yet).

---

# ADR-041 — Circuits Track Raw (Pump-Side) and Delivered (Post-Leak) Flow Separately

### Status

ACCEPTED

### Context

Phase 3's `CircuitOperatingPoint` had one `delivered_flow_cm3_min` figure, used both to
determine reservoir consumption and to decide whether a circuit's bearing should be credited
with a successful lubrication delivery (`CircuitState.last_delivery_confirmed`, checked
against a near-zero absolute threshold of `0.01 cm3/min`). Implementing Leakage in Phase 4
exposed that this collapsed two physically distinct things — "how much the pump drew from
the reservoir" and "how much actually reached the lubrication point" — into one number, and
that the near-zero confirmation threshold meant *any* nonzero leak-reduced flow still counted
as "delivery confirmed," so Leakage could never actually degrade a bearing's
`lubrication_effectiveness` (`tests/test_scenario_signal_signatures.py`'s leakage test failed
against the original implementation during development — see IMPLEMENTATION_STATUS.md).

### Decision

`CircuitOperatingPoint` now carries both `raw_flow_cm3_min` (governed by `restriction_factor`
and pump efficiency only) and `delivered_flow_cm3_min` = `raw_flow_cm3_min * (1 -
leakage_factor)`. Reservoir consumption (`CycleState.delivered_volume_cm3`, despite the
now slightly-imprecise name, kept for minimal disruption to the existing SUCCESS/PARTIAL/
FAILED classification) is driven by the **raw** figure, matching an open-loop pump that draws
what it's told to regardless of downstream leaks. Per-circuit delivery confirmation is now
tracked via a new `CircuitState.delivered_volume_cm3` field (accumulated from the
**delivered**, post-leak figure across a cycle) and compared against that circuit's fair
share of the target volume at cycle completion — not a near-zero threshold — so a circuit
receiving, say, 40% of its expected volume due to leakage is correctly *not* confirmed.

### Alternatives Considered

1. Keep one flow figure, add a separate leakage penalty applied only at the
   confirmation-threshold check. Rejected — would have required leakage to somehow reduce
   "confirmation" without reducing the reservoir-consumption-driving figure, which is not
   expressible without exactly the raw/delivered split this decision makes explicit; trying
   to patch around it would have produced a more convoluted single-figure formula for no
   benefit.
2. Lower the near-zero confirmation threshold instead of switching to a share-of-target
   comparison. Rejected — any fixed absolute threshold is arbitrary and would need
   re-tuning any time flow-capacity config changes; comparing against that circuit's actual
   target share is self-scaling and physically meaningful ("did this circuit get roughly
   what it was supposed to").

### Why This Option

Produces the catalog-required distinction between Leakage and Gradual Restriction
(`docs/FAILURE_MODE_CATALOG.md` §5 vs. §3) as a natural consequence of the physics rather
than a special case: leakage now measurably starves the served bearing's
`lubrication_effectiveness` over time while leaving required pressure — and reservoir
consumption rate — essentially at the healthy baseline, which is what
`tests/test_scenario_distinctness.py` and `tests/test_scenario_signal_signatures.py` verify.

### Consequences

This is a genuine behavior change from Phase 3 (`CircuitState.last_delivery_confirmed`'s
semantics tightened), not purely additive — re-verified that all Phase 3 regression tests
(`tests/test_cycle.py`, `tests/test_engine_healthy_invariants.py`, etc.) still pass under
the new logic, since a *healthy* circuit (near-zero restriction/leakage) still comfortably
clears its target-share threshold every cycle.

### Revisit When

Not expected to change; documented in `docs/SCENARIO_ENGINE.md` §7 as the specific mechanism
behind Leakage's distinctness from Restriction.

---

# ADR-042 — Reservoir Refill Is a Standalone Mechanism, Not Part of Any Scenario's Recovery

### Status

ACCEPTED

### Context

Phase 4 brief §24 requires a synthetic refill operational event, explicitly *not* a failure
mode, to support Low Reservoir recovery. §23 separately requires scenario recovery "where
physically appropriate," noting not all faults need it. A naive design would tie refill
directly into Low Reservoir's own `RecoverySpec` (e.g. a `mode: REFILL` variant), coupling a
general-purpose operational event to one specific scenario type's configuration schema.

### Decision

`simulator.scenarios.scheduler.AutoRefillPolicy` is a standalone class, constructed
independently of any `ScenarioInstance` (CLI: `--refill-threshold`/`--refill-to`/
`--refill-delay`, all optional, default disabled). `SimulationEngine` checks it every tick
regardless of whether any scenario — Low Reservoir or otherwise — is active. Low
Reservoir's own `RecoverySpec.enabled` stays `false` in its YAML (a low reservoir does not
fix itself); pairing it with an `AutoRefillPolicy` at the CLI/test level is how a Low
Reservoir → recovery story is actually assembled.

### Alternatives Considered

1. A `RecoverySpec.mode: "REFILL"` variant specific to reservoir-targeting scenarios,
   triggering a refill automatically when that scenario reaches a configured lifecycle
   state. Rejected — couples a general operational capability (a technician or automated
   system topping off a reservoir) to the scenario-recovery type hierarchy, and would need
   its own special-cased handling in `ScenarioInstance.step()` that every *other* scenario
   type's recovery path doesn't need, breaking the "one recovery mechanism, six-ish
   scenario types" symmetry the rest of `RecoverySpec` has.
2. No standalone mechanism; require every reference dataset that wants a refill to call
   `reservoir_physics.refill()` directly via a test/script. Rejected — leaves no CLI-level
   way to demonstrate refill/recovery behavior in a generated dataset, which §24 requires
   ("Add a synthetic REFILL operational event").

### Why This Option

Refill is, correctly, modeled as what it physically is: an operational event that can
happen regardless of *why* the reservoir got low (Low Reservoir scenario, extended
Over-Lubrication, or just normal long-run consumption in a `TRAINING`/`FULL`-mode dataset)
— not a property of one scenario type. `tests/test_refill.py::test_no_refill_policy_reservoir_never_refills`
proves it works (or rather, correctly doesn't trigger) with zero scenarios active, which
would not be true if refill were scenario-coupled.

### Consequences

A user wanting Low-Reservoir-with-recovery must pass two independent sets of flags
(`--scenario low_reservoir ...` and `--refill-threshold ...`) rather than one — a small CLI
ergonomics cost in exchange for the cleaner architectural separation.

### Revisit When

Not expected to change.

---

# ADR-043 — SQLite (WAL Mode) as the Edge's Persistent Local Buffer

### Status

ACCEPTED

### Context

Phase 5 brief §7 requires a persistent local buffer that survives a process restart with
events still `PENDING` — explicitly not an in-memory-only list. The edge is a single-process,
single-gateway reference implementation (`docs/EDGE_ARCHITECTURE.md`), not a multi-writer
service.

### Decision

`edge.buffering.store.LocalBuffer` uses the Python stdlib `sqlite3` module against a
WAL-mode database file, one file per gateway (`buffer.db_path`, default
`./data/edge/{gateway_id}.db`). No ORM, no migration framework — the schema is created via
`CREATE TABLE IF NOT EXISTS` on every connect, matching the simulator's "plain SQL against a
purpose-built schema" precedent (ADR-030) rather than pulling in SQLAlchemy for a
single-table, single-process embedded store.

### Alternatives Considered

1. An in-memory list/dict — explicitly rejected by the brief; would lose every buffered
   event on crash or restart, defeating store-and-forward entirely.
2. A file-based append-only log (e.g. newline-delimited JSON) with manual offset tracking —
   would need to reimplement exactly what SQLite already gives for free: atomic writes,
   indexed status queries, and a durable primary-key-based dedup mechanism.
3. An embedded key-value store (e.g. `dbm`, `sqlitedict`) — no meaningful advantage over
   SQLite for this schema's query needs (status-filtered scans, ordered replay), and SQLite
   is already a transitive dependency of the platform's tooling ecosystem.
4. A real client/server database (Postgres) reachable from the edge — rejected outright: the
   whole point of the local buffer is that it must work with zero connectivity to anything
   central, including a database server.

### Why This Option

WAL mode gives crash-safe durability (a properly committed write survives an unclean
process kill) without requiring a separate lock/checkpoint story, and `sqlite3` needs no
extra dependency. One file per gateway keeps the failure/backup/inspection unit obviously
scoped to one edge identity.

### Consequences

A single `sqlite3.Connection` is not safe for unserialized concurrent use across threads;
`edge.runtime.runtime.EdgeRuntime` must funnel every buffer call (including
`EnvelopeBuilder.build()`, which calls `next_sequence()`) through one `threading.Lock` — see
ADR-048's Consequences and `docs/EDGE_ARCHITECTURE.md` §15 for a real bug this caused and
fixed during verification.

### Revisit When

Real multi-gateway-per-host deployments or a throughput profile SQLite's single-writer model
cannot sustain (not expected within this reference implementation's scope).

---

# ADR-044 — Per-(Gateway, Sensor) Persisted Sequence Numbers

### Status

ACCEPTED

### Context

Phase 5 brief §5 requires monotonically increasing sequence numbers that support later
gap/duplicate/out-of-order detection and survive a restart.

### Decision

`LocalBuffer.next_sequence(gateway_id, sensor_id)` maintains one counter per
`(gateway_id, sensor_id)` pair in the `sequence_state` table, incremented and committed
atomically with the reading it is assigned to.

### Alternatives Considered

1. A single counter per gateway (all sensors share one sequence) — rejected: a gap in the
   combined stream would not tell you *which* sensor's data was missing without cross-
   referencing every event, and concurrent multi-sensor acquisition would need extra
   coordination to keep the single counter meaningful.
2. An in-memory counter only, seeded from `MAX(sequence_number)` in the events table at
   startup — rejected as strictly worse than a dedicated persisted counter: it still needs a
   query at startup, but additionally breaks if the highest-sequence event was ever
   dead-lettered/pruned in a design that (unlike this one) allowed deletion.

### Why This Option

Per-sensor sequencing gives each physical signal an unambiguous, independently-analyzable
ordering — matching how a real device would sequence its own readings — at the cost of one
extra small table with a trivial primary key.

### Consequences

A consumer wanting a single "gateway-wide" ordering must merge by `(sequence_number,
created_at)` across sensors rather than relying on one global counter; acceptable, since no
Phase 5 consumer needs a single global order.

### Revisit When

Not expected to change within this reference implementation.

---

# ADR-045 — Deterministic `event_id` via `uuid5`, Not Timestamp-Based

### Status

ACCEPTED

### Context

Phase 5 brief §4 requires event ids "suitable for idempotent downstream ingestion" and
explicitly "not timestamp-only."

### Decision

`edge.domain.envelope.make_event_id(gateway_id, sensor_id, sequence_number)` returns
`uuid5(EDGE_EVENT_NAMESPACE, f"{gateway_id}|{sensor_id}|{sequence_number}")`, computed once
at acquisition time and stored with the buffered row; retries/replays resend the same id.

### Alternatives Considered

1. `uuid4()` (random) generated at acquisition time — would still be unique and stable
   across retries (since it's stored, not regenerated), but loses the useful property that
   the id is *reproducible* from its inputs alone — useful for tests and for reasoning about
   "what would this event's id be" without a database lookup.
2. A timestamp-based id (e.g. `f"{gateway_id}-{sensor_id}-{timestamp.isoformat()}"`) —
   rejected per the brief: vulnerable to clock adjustments/replays producing either
   collisions (same timestamp reused) or non-reproducible ids (sub-second precision
   differences), and `clock_offset_seconds` (§6) makes edge-side timestamps deliberately
   adjustable, which would directly undermine a timestamp-derived id's stability.

### Why This Option

`uuid5` is a pure, deterministic function of `(gateway_id, sensor_id, sequence_number)` —
already-unique identity components (ADR-044) — so the id is both globally unique and
independently re-derivable, which is exactly what "idempotent downstream ingestion" needs.

### Consequences

Two different edge processes must never share a `gateway_id` while assigning sequence
numbers independently, or they could mint colliding `event_id`s — enforced by
`edge.runtime.gateway_lock.GatewayLock` (§ Phase 5 brief §20's duplicate-gateway-ID
fail-fast requirement).

### Revisit When

Not expected to change.

---

# ADR-046 — MQTT Topic Hierarchy and QoS 1

### Status

ACCEPTED

### Context

ADR-006 assigned MQTT to sensor/edge communication but did not specify a topic hierarchy or
QoS level. Phase 5 brief §15 requires "a deliberate, documented QoS choice."

### Decision

Topic: `lubrisense/v1/{tenant_id}/{gateway_id}/telemetry` — one topic per gateway; a future
central subscriber uses `lubrisense/v1/+/+/telemetry`. QoS: **1** (at-least-once).

### Alternatives Considered

1. QoS 0 (at-most-once) — rejected: can silently drop a message on a flaky link with no
   retry, which would defeat store-and-forward's entire purpose (an event could vanish
   between a successful local buffer write and an unconfirmed publish).
2. QoS 2 (exactly-once) — rejected: its extra four-way handshake exists to prevent duplicate
   delivery, but this system already has a cheaper, independent duplicate-prevention
   mechanism (`event_id` + `LocalBuffer`'s primary key, ADR-045) — paying QoS 2's overhead
   buys nothing not already covered.
3. A single shared topic for all gateways with gateway id only in the payload — rejected:
   loses topic-level filtering/ACL granularity a real multi-tenant deployment would want, for
   no benefit in this reference implementation.

### Why This Option

QoS 1 matches exactly the durability guarantee store-and-forward needs (broker-side
persistence until acknowledged) without paying for exactly-once semantics the system does
not need, given `event_id`-based dedup already exists at the consumer/buffer layer.

### Consequences

A downstream consumer must itself be idempotent on `event_id` (which every consumer in this
system already is, by design) since QoS 1 can, in principle, redeliver.

### Revisit When

Phase 6 (Telemetry Pipeline) designs the Kafka-side ingestion path and topic-to-Kafka-topic
mapping.

---

# ADR-047 — Buffer Retention: Oldest-`PENDING`-to-`DEAD_LETTER`, Never Delete

### Status

ACCEPTED

### Context

Phase 5 brief §11 requires a configurable retention policy with an explicit,
non-silent-discard behavior when limits (`max_buffered_events`/`max_buffer_age_seconds`) are
breached, and requires acquisition to keep working even under sustained backlog.

### Decision

`LocalBuffer.enforce_retention()` moves the oldest `PENDING` rows to `DEAD_LETTER` status
(never `DELETE`s) when either limit is breached, logs a warning, and increments the
`buffer_overflow_count` health metric. `DEAD_LETTER` rows remain queryable via
`python -m edge buffer list --status dead_letter`.

### Alternatives Considered

1. Backpressure — block/slow acquisition once the buffer is full — rejected: the brief and
   `docs/ARCHITECTURE.md` §5 both require the edge to keep observing the physical process
   regardless of downstream/buffer state; blocking acquisition on buffer pressure would mean
   a sustained outage silently stops local monitoring too, which is worse than losing the
   oldest backlog.
2. Silent deletion of the oldest rows — explicitly forbidden by the brief ("never silently
   delete").
3. Reject new writes once full (return an error to the acquisition loop) — rejected for the
   same reason as backpressure: it couples acquisition's success to buffer capacity.

### Why This Option

Dead-lettering is the same non-silent-discard idea common in real message-queue systems:
data that could not be kept is moved somewhere visible and inspectable, not vaporized, while
the system keeps making forward progress on new data.

### Consequences

A very long outage combined with a small `max_buffered_events` will eventually dead-letter
real telemetry — an inherent trade-off of any bounded local buffer; operators size
`max_buffered_events`/`max_buffer_age_seconds` for their expected outage duration.

### Revisit When

A real deployment's expected outage duration and event rate are known (Phase 30+
commissioning).

---

# ADR-048 — Four-State Connectivity Model with Bounded Jittered Backoff

### Status

ACCEPTED

### Context

Phase 5 brief §12-§13 requires connectivity-state tracking (`ONLINE`/`DEGRADED`/`OFFLINE`/
`RECOVERING`) and bounded exponential backoff with jitter that is deterministically testable
and avoids both infinite tight loops and state flapping.

### Decision

`edge.connectivity.manager.ConnectivityManager` transitions purely from consecutive
transport-level successes/failures: `ONLINE -> DEGRADED` (>=1 failure) `-> OFFLINE`
(`offline_after_failures` consecutive failures, default 3) `-> RECOVERING` (first success
after `OFFLINE`) `-> ONLINE` (`recovered_after_successes` consecutive successes, default 2).
Backoff is `edge.connectivity.backoff.compute_backoff` — a **pure function**
(`uniform(0, min(max, base * factor**attempt))`, full jitter) taking an explicit
`random.Random`, so it is unit-tested with a seeded RNG and no real sleeps.

### Alternatives Considered

1. A simpler two-state (`ONLINE`/`OFFLINE`) model — rejected: loses the ability to
   distinguish "occasionally flaky" from "definitely down," which the brief's `DEGRADED`
   state is meant to capture, and collapses "just reconnected, still proving itself" into
   plain `ONLINE`, hiding a state a real dashboard would want to show differently.
2. Sleeping directly inside the state-transition/backoff logic — rejected: makes the backoff
   curve untestable without real wall-clock delays; kept as a pure function returning a
   delay, with the caller (the sender thread) deciding how to wait.
3. Unbounded exponential backoff — rejected: could grow to impractically long retry
   intervals after a long outage; `max_seconds` caps it.

### Why This Option

Matches the brief's exact state list, keeps the timing math independently and
deterministically testable, and full jitter is a well-understood technique for avoiding
synchronized retry storms (relevant if this pattern is later reused across many gateways).

### Consequences

State thresholds (`offline_after_failures`, `recovered_after_successes`) are currently fixed
defaults, not exposed in `EdgeConfig` — acceptable for this reference implementation; would
need to become configurable for production tuning.

### Revisit When

Real deployment data shows the default thresholds produce too much/too little state
flapping for actual network conditions.

---

# ADR-049 — Local Rule Boundary: Four Fixed Checks, Generic Labels Only

### Status

ACCEPTED

### Context

Phase 5 brief §16-§17 requires "basic edge-local deterministic rules only," explicitly not
the Phase 9 rules engine, with generic alert labels rather than domain-specific diagnoses.

### Decision

`edge.rules.engine.LocalRuleEngine` implements exactly four checks — sensor out-of-range,
critical/empty reservoir, pump-running-without-lubrication-evidence, and
invalid/missing-critical-sensor (debounced) — each producing a `LocalEdgeAlert` with one of
exactly four generic `rule_id`s (`LOCAL_RANGE_VIOLATION`, `LOCAL_WARNING`,
`LOCAL_LUBRICATION_CYCLE_FAILURE`, `LOCAL_SENSOR_FAULT`). There is no rule-authoring
mechanism, no plugin system, no configurable rule set beyond each check's numeric
thresholds.

### Alternatives Considered

1. A small generic rule-authoring DSL/config (arbitrary condition -> alert mappings) —
   rejected: this is architecturally what Phase 9's rules engine is for; building even a
   minimal version here would blur a boundary the brief draws explicitly and create two
   places a future engineer might look for "the rules."
2. Domain-specific rule ids (e.g. `RESTRICTION_SUSPECTED`) — rejected: the edge has no
   diagnostic evidence beyond one threshold crossing; naming it as if it were a diagnosis
   would overstate the edge's actual analytical power and duplicate language
   `docs/FAILURE_MODE_CATALOG.md` reserves for Decision Intelligence.
3. Emitting one alert instance per tick while a condition persists — rejected: floods a
   consumer with redundant events; open/cleared state tracking (one transition per
   condition change) matches `docs/EVENT_CATALOG.md` §4.1's `LocalAlarmRaised`/
   `LocalAlarmCleared` model directly.

### Why This Option

Four fixed, clearly-scoped checks are exactly what "basic, explainable, deterministic
logic" (`docs/ARCHITECTURE.md` §5) means at the edge — enough to protect the asset and the
technician during a cloud outage, without pretending to be a diagnostic system.

### Consequences

Any new local check requires a code change, not a config change — an intentional constraint
for this phase, not an oversight.

### Revisit When

Phase 9 (Rule Engine) is built centrally; this boundary should be re-examined then to make
sure the edge's four checks and the central rules engine do not silently duplicate or
contradict each other.

---

# ADR-050 — Central Pipeline Runs as Separate Worker Processes Inside `backend/`, Not as FastAPI Routes

### Status

ACCEPTED

### Context

ADR-011 assigns telemetry processing to `backend/`, but everything in `backend/app/` before
Phase 6 is FastAPI-request-shaped (routers/services/repositories calling into one async
session per request). A long-running Kafka consumer loop and an MQTT ingestion daemon are a
different runtime shape — background workers, not request handlers — and needed an explicit
module boundary rather than being implied by the existing structure.

### Decision

Pipeline code lives in `app/pipeline/` (`contract.py`, `validation.py`, `enrichment.py`,
`backoff.py`, `metrics.py`, `health.py`, `spool.py`, `mqtt_bridge.py`, `consumer.py`), built
from the same `backend/` Docker image as the FastAPI app, but run as two separate processes
with their own `__main__` entrypoints (`python -m app.pipeline.mqtt_bridge`,
`python -m app.pipeline.consumer`) — analogous to how `edge/` has `python -m edge run`, not
as routes on `api_v1_router`.

### Alternatives Considered

1. A new top-level `pipeline/` service directory (its own `pyproject.toml`, own venv, like
   `simulator/`/`edge/`). Rejected — the pipeline needs the same domain models, repositories,
   config, and logging setup the FastAPI app already has; splitting it out would mean either
   duplicating that code or introducing a cross-service dependency in the wrong direction.
2. FastAPI background tasks / lifespan-started asyncio tasks inside the `backend` process
   itself. Rejected — couples pipeline uptime/restart/scaling to the API server's, and one
   process's failure (e.g. a Kafka consumer crash loop) would take the HTTP API down with it.

### Why This Option

Reuses every piece of `backend/app/` (domain models, repositories, `Database`, `Settings`,
`configure_logging`) that pipeline code needs, while keeping the three processes (API,
bridge, consumer) independently deployable, restartable, and scalable — exactly what
`docker-compose.yml`'s three separate services (`backend`, `mqtt-bridge`,
`telemetry-consumer`) give for free.

### Consequences

Three container images build from one Dockerfile/context with different `command:`
overrides — slightly more Compose configuration than one service, but no code duplication.

### Revisit When

If pipeline throughput ever needs independent scaling/deployment cadence from the rest of
`backend/` (e.g. a separate release pipeline), reconsider the standalone-service split.

---

# ADR-051 — `aiokafka` + `paho-mqtt`-in-a-Thread for the MQTT→Kafka Bridge

### Status

ACCEPTED

### Context

No Kafka or MQTT Python client existed in `backend/` before Phase 6 (Phase 1's
`verify_kafka.sh`/`verify_mqtt.sh` deliberately used `docker exec` + bundled CLI tools to
avoid adding a dependency prematurely — ADR-006's revisit note explicitly flags Phase 6 as
when a real client becomes necessary). The bridge needs both an MQTT subscriber and a Kafka
producer in one process.

### Decision

`aiokafka` (async, matches the backend's existing async SQLAlchemy style) for both the
bridge's producer and the consumer. `paho-mqtt` (already proven in `edge/`) for MQTT,
run with its own network thread (`loop_start()`); `on_message` hands each payload to the
asyncio loop via `asyncio.run_coroutine_threadsafe` rather than mixing the two clients'
threading models directly.

### Alternatives Considered

1. `confluent-kafka` (C-based, sync) for the bridge specifically, since paho-mqtt is also
   sync/callback-based — would avoid the threadsafe-handoff pattern for the bridge, but
   introduces a second, different Kafka client library for the consumer (which benefits from
   `aiokafka`'s async fit with `Database`/async SQLAlchemy) — rejected to keep one Kafka
   client across both workers.
2. `aiomqtt` (asyncio-native MQTT client) instead of paho-mqtt — would avoid the thread
   handoff entirely, but `edge/` already proved paho-mqtt's `CallbackAPIVersion.VERSION2`
   pattern in this exact topic/QoS configuration; reusing it keeps one proven MQTT client
   across the whole repository rather than introducing a second one for symmetry with
   `aiokafka` alone.

### Why This Option

One Kafka client (`aiokafka`) across both workers, one proven MQTT client
(`paho-mqtt`) matching `edge/`'s already-validated configuration. The thread-handoff pattern
(`run_coroutine_threadsafe`) is a well-known, narrow seam rather than a pervasive
threading concern.

### Consequences

The bridge's `on_message`/`on_connect`/`on_disconnect` callbacks run on paho-mqtt's thread
and must only ever schedule work onto the asyncio loop, never touch asyncio-owned state
directly — enforced by keeping those callbacks minimal (just flag updates and
`run_coroutine_threadsafe`).

### Revisit When

If `aiokafka`'s maintenance status or performance becomes a concern at real production
throughput (Phase 33), or if a unified async MQTT+Kafka client emerges that simplifies the
threading model.

---

# ADR-052 — Kafka Partition Key: `tenant_id:gateway_id:sensor_id`

### Status

ACCEPTED

### Context

The brief requires a deliberately chosen Kafka message key that "preserves ordering for a
sensor/device stream." Kafka only guarantees ordering within a partition, and partition
assignment is a hash of the key.

### Decision

`f"{tenant_id}:{gateway_id}:{sensor_id}"`, encoded as UTF-8 bytes.

### Alternatives Considered

1. `event_id` as the key — rejected: it's unique per message, so it would hash to a
   effectively random partition per event, providing no ordering guarantee at all (defeats
   the purpose of choosing a key deliberately).
2. `sensor_id` alone — considered, but including `tenant_id` and `gateway_id` keeps the key
   meaningful and collision-safe even though `sensor_id` (a UUID) is already effectively
   unique per tenant; the fuller key matches the brief's own suggested candidate and reads
   clearly in logs/tooling without a lookup.

### Why This Option

Every reading from the same sensor, on the same gateway, for the same tenant, lands in the
same partition — preserving the one ordering guarantee that matters for a single sensor's
time series, while still spreading load across partitions by sensor/gateway/tenant.

### Consequences

At real fleet scale, partition count should be chosen so this key distributes evenly across
partitions (many sensors → many distinct keys) — not a concern at the current single-topic,
often-single-partition local/demo scale (see ADR-006's revisit note).

### Revisit When

Phase 33 (Performance + Scale Testing) validates actual key distribution and partition count
under realistic fleet size.

---

# ADR-053 — At-Least-Once Transport + Idempotent `(event_id, source_timestamp)` Persistence, Offsets Committed After Durable Write

### Status

ACCEPTED

### Context

The brief mandates the pipeline be idempotent and replay-safe under MQTT QoS 1 redelivery,
Kafka consumer-group rebalance, bridge spool-drain retries, and edge buffer replay — any of
which can deliver the same logical event more than once. It explicitly says not to claim
"true end-to-end exactly-once unless proven."

### Decision

At-least-once transport throughout (MQTT QoS 1, Kafka default delivery, unbounded retry with
backoff on failure) plus idempotent database persistence as the actual duplicate-suppression
mechanism: `INSERT ... ON CONFLICT (event_id, source_timestamp) DO NOTHING`
(`TelemetryRepository.batch_insert_idempotent`). The Kafka consumer uses
`enable_auto_commit=False` and commits offsets only after a batch's DB transaction commits
successfully — never before.

### Alternatives Considered

1. Kafka transactional producer/consumer (exactly-once semantics) — rejected as
   disproportionate: Kafka EOS only covers Kafka-internal delivery, not the MQTT hop or the
   database write, so it would not actually deliver end-to-end exactly-once and would add
   real operational complexity (transactional coordinator, `isolation.level=read_committed`
   consumers) for a guarantee this design doesn't need — idempotent persistence already
   makes duplicates harmless.
2. Deduplicate in application code via an in-memory or Redis-backed seen-set before insert —
   rejected: adds a second source of truth that can itself drift from the database, and
   provides no additional safety over a database-level uniqueness constraint, which is
   already authoritative and race-free under concurrent batches.

### Why This Option

"At-least-once + idempotent persistence" is the standard, provably-correct pattern for this
exact problem, and is honestly describable without overclaiming exactly-once semantics the
implementation doesn't actually provide end to end.

### Consequences

Every insert path (main-topic batch, DLQ-topic drain, spool drain) must route through the
same idempotent insert/insert-or-ignore mechanism — a new ingestion path that bypasses it
would silently reintroduce duplicate risk.

### Revisit When

If a future requirement genuinely needs exactly-once guarantees end to end (unlikely for a
monitoring/telemetry use case), revisit with Kafka transactions plus a two-phase commit-style
coordination with the database.

---

# ADR-054 — Hypertable Partitioned on `source_timestamp`, 1-Day Chunks

### Status

ACCEPTED

### Context

TimescaleDB hypertables need one column chosen as the partitioning ("time") dimension, and a
chunk interval. The `telemetry` table has several candidate timestamp columns (§5 of
`docs/TELEMETRY_PIPELINE.md`): `source_timestamp`, `mqtt_received_timestamp`,
`kafka_published_timestamp`, `consumer_received_timestamp`, `persisted_timestamp`.

### Decision

Partition on `source_timestamp` (event time). Chunk interval: 1 day.

### Alternatives Considered

1. `persisted_timestamp` (arrival/insert time) — rejected: a replayed or outage-buffered
   event can have a `source_timestamp` far in the past relative to when it's actually
   written; partitioning on insert time would scatter such events into "now" chunks,
   defeating time-range queries over the period they actually describe (exactly the outage/
   replay scenarios this phase is required to handle correctly).
2. A shorter (1 hour) or longer (1 week) chunk interval — evaluated against the demo/
   reference workload (a handful of assets, readings on the order of one per few seconds):
   1 day keeps chunk count and per-chunk row count both reasonable without over-fragmenting
   the hypertable at this scale.

### Why This Option

Event time is the physically meaningful, replay-stable choice — a query for "sensor X's
readings between times A and B" returns the same rows regardless of when those readings
were actually ingested.

### Consequences

Chunk interval is a demo-scale choice, explicitly not claimed as universally optimal (brief
§7's own instruction) — real fleet-scale volume testing (Phase 33) may indicate a different
interval, and TimescaleDB supports changing it going forward without rewriting existing
chunks.

### Revisit When

Phase 33 (Performance + Scale Testing) measures actual chunk size/count under realistic
multi-tenant, multi-asset volume.

---

# ADR-055 — Batch Persistence via Size/Time-Triggered `ON CONFLICT DO NOTHING`

### Status

ACCEPTED

### Context

The brief requires the consumer avoid one DB transaction per single telemetry event when it
can safely batch, with configurable batch size/timeout.

### Decision

`AIOKafkaConsumer.getmany()` accumulates up to `PIPELINE_BATCH_SIZE` (default 500) messages
or `PIPELINE_BATCH_TIMEOUT_SECONDS` (default 2.0), whichever comes first. The whole batch is
enriched, split into insert/quarantine rows, and persisted in one transaction via a single
`INSERT ... ON CONFLICT (event_id, source_timestamp) DO NOTHING` (ADR-053) plus per-row
`telemetry_quarantine` inserts, then committed once.

### Alternatives Considered

1. One transaction per message — rejected: the brief explicitly calls this out as something
   to avoid when batching is safe, and it multiplies transaction/round-trip overhead at
   volume for no correctness benefit given the idempotent insert already handles duplicates
   at any batch granularity.
2. A fixed batch size with no timeout (wait until `PIPELINE_BATCH_SIZE` messages arrive) —
   rejected: at low/bursty traffic (the actual demo/reference workload), this could delay
   persistence indefinitely; the timeout ensures bounded latency even for small batches.

### Why This Option

Size-or-timeout batching is the standard pattern for balancing throughput (larger batches,
fewer round trips) against latency (bounded wait even when traffic is sparse), and both
knobs are configurable per-deployment (`PIPELINE_BATCH_SIZE`,
`PIPELINE_BATCH_TIMEOUT_SECONDS`).

### Consequences

A DB failure mid-batch retries the *entire* batch (idempotent insert makes this safe, not
just "acceptable") rather than a per-row retry — simpler failure handling at the cost of
redoing enrichment work for already-processed rows in that batch on retry.

### Revisit When

If per-message latency requirements tighten enough that even the default 2-second timeout is
too slow, or if batch sizes need to scale differently per topic/tenant.

---

# ADR-056 — Dedicated SQLite Durable Spool for the MQTT→Kafka Bridge

### Status

ACCEPTED

### Context

The brief requires the MQTT bridge not silently lose data during a Kafka outage, and
explicitly states "a pure in-memory retry queue is not sufficient for prolonged outage."

### Decision

A dedicated local SQLite file (`app.pipeline.spool.BridgeSpool`,
`PIPELINE_BRIDGE_SPOOL_PATH`), separate from the edge's own buffer database (a different
responsibility — the edge buffers its own acquisition-to-transport gap; the bridge buffers
its own MQTT-receipt-to-Kafka-publish gap). `INSERT OR IGNORE` keyed on `event_id` makes
re-spooling an already-spooled event a no-op. A background task drains oldest-first with
bounded backoff once Kafka is reachable again.

### Alternatives Considered

1. Reuse `edge.buffering.store.LocalBuffer` directly — rejected: it is the edge's
   responsibility-scoped buffer (per-gateway file, sequence-number tracking tied to
   acquisition), and importing the `edge` package would violate ADR-059 (central pipeline
   does not depend on `edge`).
2. A durable queue product (Redis Streams, a local message broker) — rejected as
   disproportionate: a single-process, single-writer durable FIFO is exactly what SQLite
   WAL mode already provides (the same reasoning edge's ADR-043 used for its own buffer),
   with zero additional infrastructure.

### Why This Option

Matches the edge's own precedent (SQLite WAL-mode local buffer) for the same class of
problem, with none of the cross-service coupling reusing the edge's actual buffer
implementation would introduce.

### Consequences

A second SQLite file exists in the deployment (edge buffer + bridge spool) — acceptable
duplication given they serve genuinely different stages of the pipeline and different
processes.

### Revisit When

If the bridge is ever horizontally scaled (multiple bridge instances), a per-instance local
SQLite spool stops being sufficient and a shared durable queue would be needed instead.

---

# ADR-057 — DLQ Topic vs. Quarantine Table, Split by Detecting Component

### Status

ACCEPTED

### Context

The brief allows "Kafka DLQ topic, database quarantine table, or both if justified" for
malformed/rejected telemetry, and requires nothing be silently discarded.

### Decision

Split by which component detects the failure, not by failure category: the MQTT bridge
(stateless/lightweight by design, no DB access) routes structural failures
(`SCHEMA_INVALID`, `UNSUPPORTED_SCHEMA_VERSION`) to the Kafka DLQ topic
(`lubrisense.telemetry.dlq.v1`), with `reason`/`detail` as message headers. The consumer
(has DB access) routes tenant/entity/context failures (`UNKNOWN_TENANT`, `UNKNOWN_SENSOR`,
`UNKNOWN_GATEWAY`, `CONTEXT_CONFLICT`) directly to `telemetry_quarantine`. The consumer also
runs a second concurrent task draining the DLQ topic into the same `telemetry_quarantine`
table, so every rejection ends up queryable in one place regardless of origin.

### Alternatives Considered

1. Give the bridge database access so it can write directly to `telemetry_quarantine` too —
   rejected: keeps the bridge stateless and lightweight (its whole job is MQTT-in,
   Kafka-out, plus a local spool file), avoids a second service holding a DB connection pool
   for a narrow use case, and avoids coupling bridge availability to database availability
   for its primary responsibility.
2. Kafka DLQ topic only, no database table — rejected: tenant/entity/context failures need a
   database lookup to detect in the first place (the consumer already has the session open),
   and a DB table is far more queryable for operator visibility than a Kafka topic in
   practice.

### Why This Option

The split follows each component's actual capabilities rather than an arbitrary category
split, and the DLQ-draining task means the "one queryable place" property still holds
despite the two origins.

### Consequences

A structural failure detected by the bridge takes one extra hop (Kafka DLQ topic → consumer
→ table) to become queryable, versus a direct write — acceptable latency for a rejection
path, not a hot path.

### Revisit When

If the bridge ever needs a database connection for another reason, reconsider having it
write directly to `telemetry_quarantine` instead of routing through the DLQ topic.

---

# ADR-058 — Context Enrichment Resolves via the Sensor's Attachment Column; Conflicts Are Quarantined, Never Overwritten

### Status

ACCEPTED

### Context

The edge only supplies `tenant_id`/`machine_id`/`component_id`/`sensor_id` in a
`ReadingEnvelope` — it cannot resolve the fuller asset-hierarchy path
(`site_id`/`plant_id`/`production_line_id`/`bearing_id`/`lubrication_system_id`/
`circuit_id`/`lubrication_point_id`) itself (`docs/EDGE_ARCHITECTURE.md`). The brief requires
central ingestion to enrich missing context from the authoritative hierarchy, but reject
(not silently overwrite) conflicting supplied context.

### Decision

`ContextEnrichmentService` resolves a sensor's single populated attachment column
(`Sensor.attached_entity_type`/`attached_entity_id` — `machine`/`bearing`/
`lubrication_system`/`reservoir`/`pump`/`circuit`, per ADR-023's exactly-one-attachment
design) up through the real Phase 2 hierarchy tables to fill every null hierarchy field. If
the edge-supplied `machine_id` (always present) or `component_id` (optional) disagrees with
the resolved value, or any hierarchy field the edge did supply disagrees with what enrichment
resolves, the event is quarantined as `CONTEXT_CONFLICT` — the resolved value is never used
to silently correct a disagreeing supplied value.

### Alternatives Considered

1. Trust supplied context when present, only fill in nulls — rejected: this is exactly what
   the brief prohibits ("do not trust client-supplied hierarchy blindly"); a compromised or
   buggy edge could otherwise inject incorrect asset attribution that central ingestion would
   accept at face value.
2. Silently prefer the resolved (authoritative) value on any conflict — rejected: the brief
   requires conflicts be rejected/quarantined with a recorded reason, not silently resolved
   either direction; a conflict is itself a signal worth an operator's attention (stale edge
   config, topology drift, or a genuine data integrity problem).

### Why This Option

Every hierarchy field in a persisted `telemetry` row is either edge-supplied-and-verified or
authoritatively-resolved-and-uncontested — never a value the pipeline silently chose between
two disagreeing sources.

### Consequences

`lubrication_point_id` cannot be resolved this way (no sensor attaches directly to a
`LubricationPoint`) and stays `NULL` — documented as a known limitation
(`docs/TELEMETRY_PIPELINE.md` §19), not silently guessed via an ambiguous circuit → multiple
lubrication-points mapping.

### Revisit When

If a future phase adds an unambiguous way to derive `lubrication_point_id` (e.g. a
lubrication-point-specific sensor attachment type), extend `ContextEnrichmentService`
accordingly.

---

# ADR-059 — Central Pipeline Defines Its Own Wire Contract, Does Not Import the `edge` Package

### Status

ACCEPTED

### Context

The central pipeline's wire contract (`app.pipeline.contract.TelemetryEnvelope`) is
field-for-field identical to the edge's `edge.domain.envelope.ReadingEnvelope`, since real
bytes cross this boundary unchanged. Importing `edge` directly would avoid re-declaring that
shape.

### Decision

The central pipeline defines and validates its own copy of the wire contract, independent of
the `edge` package.

### Alternatives Considered

1. Add `edge` as a dependency of `backend/` and import `ReadingEnvelope` directly — rejected:
   couples the central pipeline's deployability to the edge package's own dependency set
   (including its `lubrisense-simulator` local path dependency, per `edge/Dockerfile`'s own
   comment on why that coupling exists), and couples a schema change on one side to a code
   change on the other even when the wire format itself hasn't changed.
2. A third shared package (`lubrisense-telemetry-contract`) imported by both `edge/` and
   `backend/` — considered, but adds a fourth Python package to install/version/publish for
   a contract that changes rarely and is small enough to keep in sync by convention plus
   `schema_version` gating (§6) rather than a shared dependency.

### Why This Option

`edge/` and `backend/`'s pipeline workers stay independently buildable/deployable/
versionable — exactly the same reasoning ADR-011 already applied to keeping `simulator/`,
`edge/`, and `backend/` as separate top-level packages rather than one monolith.

### Consequences

A wire-contract field change requires updating both `ReadingEnvelope` and
`TelemetryEnvelope`/`SchemaValidator` by hand — mitigated by `schema_version` gating
(unsupported versions are rejected cleanly, not silently misparsed) and by keeping both
definitions small and stable.

### Revisit When

If wire-contract changes become frequent enough that manual duplication becomes a real
maintenance burden, reconsider a shared contract package (alternative 2 above).

---

# ADR-060 — Data-Quality Worker Is a Second, Independent Kafka Consumer Group

### Status

ACCEPTED

### Context

Every telemetry event Phase 6 accepts must eventually get a data-quality assessment (Phase
7), but that assessment must never be allowed to slow down or block real ingestion — a bad
or slow rule evaluation on one event should never delay the moment a technician-visible
telemetry row exists.

### Decision

The data-quality worker (`app.data_quality.worker`) subscribes to the same
`lubrisense.telemetry.v1` topic Phase 6's `telemetry-consumer` reads, but under a completely
separate consumer group (`lubrisense-data-quality`) — Kafka's native fan-out, not a
post-persistence trigger and not a shared transaction with Phase 6's insert.

### Alternatives Considered

1. A PostgreSQL trigger/listener on `INSERT INTO telemetry`, driving quality evaluation
   after Phase 6 commits. Rejected — couples quality-worker liveness to Phase 6's write
   path (a slow or stuck LISTEN/NOTIFY consumer can build up backlog pressure Phase 6 has to
   account for) and makes offline reprocessing (§11 of `docs/DATA_QUALITY.md`) an entirely
   different code path than live processing.
2. Have Phase 6's own consumer call into `QualityEngine` inline, in the same transaction as
   the telemetry insert. Rejected — makes Phase 6's own critical path depend on Phase 7 rule
   evaluation succeeding, exactly the coupling this ADR exists to avoid; also violates the
   phase boundary (Phase 6 must stay data-quality-agnostic).

### Why This Option

Kafka consumer groups are designed exactly for this — multiple independent readers of one
topic, each with their own offset tracking, each unaffected by the others' lag or failure.
Phase 6's consumer never knows Phase 7 exists.

### Consequences

Every valid event is independently re-validated and re-enriched by the quality worker
(duplicate CPU work vs. sharing Phase 6's already-enriched result) — accepted, since sharing
would require the coupling this ADR rejects. Two consumer groups on one topic also means two
independent places offset lag can be observed/alerted on, which is a feature, not a cost.

### Revisit When

If duplicate enrichment work becomes a measurable throughput problem at real scale,
reconsider passing enriched context via a separate lightweight topic instead of
re-enriching independently.

---

# ADR-061 — Per-Event `SAVEPOINT` Isolation, Diverging From Phase 6's Batch-Only Retry

### Status

ACCEPTED

### Context

Phase 6's consumer treats the whole batch as the retry unit: any exception anywhere in a
batch retries the entire batch without committing offsets, because Phase 6 is the system of
record and must never lose a telemetry row. Phase 7's worker needs a different answer to
"what happens when one rule throws on one event" — retrying the whole batch forever over one
bad rule evaluation would make quality processing as fragile as ingestion itself, which is
exactly the coupling ADR-060 exists to avoid.

### Decision

A **batch-level** failure (e.g. the database is unreachable) still retries the whole batch
without committing offsets, identical to Phase 6. But each event's rule evaluation and
persistence runs inside its own `session.begin_nested()` (a SQL `SAVEPOINT`) — a per-event
exception rolls back to that savepoint only, is caught, logged, and counted
(`quality_processing_errors`), and the batch still commits.

### Alternatives Considered

1. Catch per-event exceptions without a savepoint. Rejected — Postgres aborts the entire
   surrounding transaction on any statement error; without a savepoint, every subsequent
   statement in the same transaction would raise
   "current transaction is aborted" and the whole batch would fail anyway, silently
   defeating the intended isolation.
2. Retry the whole batch on any per-event failure too (matching Phase 6 exactly). Rejected
   for the reason in Context — this worker is secondary/advisory, not the system of record,
   and reprocessing (§11) already exists to recover any event skipped this way.

### Why This Option

`SAVEPOINT`-scoped isolation is the correct SQL-level tool for "isolate one statement
group's failure from the rest of an open transaction" — it is not a workaround, it is how
Postgres expects partial-failure-within-a-transaction to be handled.

### Consequences

A poison event (one that always throws) is skipped forever on live processing rather than
blocking the topic — recoverable only via `reprocess.py` after the underlying rule bug is
fixed. Documented explicitly since it is a deliberate, non-obvious divergence from the
Phase 6 precedent a reader might otherwise assume was copied uniformly.

### Revisit When

If poison-event skip-and-log ever needs to become skip-and-alert (e.g. paging on
`quality_processing_errors` crossing a threshold), that is an observability addition, not a
change to this isolation strategy.

---

# ADR-062 — Three-Table Storage Split, Not One Row Per Event

### Status

ACCEPTED

### Context

Persisting a `quality_assessment` row for every telemetry event would 1:1-explode with
telemetry volume — the overwhelming majority of events are perfectly healthy and produce no
issue at all, so a row-per-event design would mostly store "nothing happened" rows forever.

### Decision

Three tables with different write frequencies: `quality_issue` (one row per *actually
detected* issue, sparse), `sensor_quality_state` (one continuously-upserted row per sensor,
bounded by sensor count), `quality_assessment` (persisted for every window-level evaluation
regardless of outcome, and for event-level evaluations that found at least one issue —
never for a trivially healthy single event).

### Alternatives Considered

1. One `quality_assessment` row per event, always. Rejected for the volume reason above.
2. No per-event assessment at all, only `sensor_quality_state`. Rejected — loses the
   auditable "what exactly happened at this specific event" record §5 of
   `docs/DATA_QUALITY.md` requires for anything that actually found an issue.

### Why This Option

Matches write frequency to information value: routine health needs no row (it's already
reflected in `sensor_quality_state`'s freshness), a detected issue needs a durable
audit-trail row, and a periodic window check needs a low-frequency trend row regardless of
outcome.

### Consequences

A caller wanting "the assessment for event X" gets nothing back for a healthy event by
design (not a bug) — the API's sensor-detail endpoint is built around
`sensor_quality_state` plus active issues, not a per-event lookup, for exactly this reason.

### Revisit When

If a future requirement needs a queryable per-event healthy/unhealthy audit trail at full
volume, reconsider (e.g. a cheap append-only log rather than the full `quality_assessment`
schema).

---

# ADR-063 — Event-Level Synchronous Rules vs. Window-Level Periodic Rules

### Status

ACCEPTED

### Context

Some quality judgments need only the current event plus a small amount of cached context
(is this value in range, is this sequence number a gap); others fundamentally need a
time-range view of recent history (is this sensor's mean shifting, is this value stuck,
has this stream gone stale) that a single event can never answer on its own.

### Decision

Event-scoped rules run synchronously inside `QualityEngine`, per Kafka batch, using only the
current event and `SensorContext` (cached on `sensor_quality_state`). Window-scoped rules
run on a separate periodic asyncio task (`WindowEvaluator`), querying a fresh time range
from `TelemetryRepository` every cycle — stateless, restart-safe, no in-memory rolling
buffer to lose.

### Alternatives Considered

1. Maintain an in-memory rolling window per sensor inside the worker process. Rejected —
   lost on restart/redeploy, and multiple worker replicas would each hold an incomplete
   view; a fresh DB query is simple, correct, and already indexed
   (`ix_telemetry_tenant_sensor_time`, Phase 6).
2. Run every rule, including window rules, per-event by querying history inline. Rejected —
   would issue a time-range query on every single event for rules that only need to run
   occasionally, wasting DB load for no additional detection value.

### Why This Option

Matches each rule's actual data need to its actual evaluation cadence, and keeps the worker
trivially horizontally scalable (any replica's window query returns the same answer from the
same source of truth).

### Consequences

Window-level detections lag real-time by up to one evaluation interval (60s default) — an
accepted trade-off explicitly documented, not silently assumed instant.

### Revisit When

If sub-minute window-level detection latency becomes a real product requirement, reconsider
a streaming/incremental-aggregation approach instead of periodic full re-query.

---

# ADR-064 — `quality_state` and `eligibility` Kept as Two Distinct Fields

### Status

ACCEPTED

### Context

The brief explicitly names both "quality state" and "eligibility" as concepts a data-quality
engine should expose, with separate example values for each, rather than asking for one
collapsed field.

### Decision

`quality_state` (`TRUSTED`/`USABLE_WITH_CAUTION`/`UNUSABLE`) describes a sensor's overall
current trustworthiness — what a badge or a person should say. `eligibility`
(`ELIGIBLE`/`ELIGIBLE_WITH_CAUTION`/`INELIGIBLE`) is the specific downstream-consumption
decision a future baseline/rule/ML consumer should check. Both derive from the same issue
set via one policy-configured severity mapping (`eligibility_mapping` — one function, two
label sets), never two independent computations that could silently disagree.

### Alternatives Considered

1. Collapse to a single field, used for both display and downstream gating. Rejected — a
   human-facing "state" label and a machine-facing "may I consume this" decision are
   different questions that happen to correlate today but are conceptually separate, and the
   brief asked for both explicitly.

### Why This Option

Keeps the human-facing and machine-facing questions separately named while guaranteeing they
never drift apart, since both come from one mapping table.

### Consequences

Every consumer (API response, frontend badge, future Phase 8+ gating logic) must pick the
right one of the two fields for its purpose — documented in `docs/DATA_QUALITY.md` §4.

### Revisit When

Not expected to revisit; would only change if a future phase needs `eligibility` to diverge
from a pure function of severity (e.g. per-consumer eligibility rules).

---

# ADR-065 — No Numeric Quality Score for v1

### Status

ACCEPTED

### Context

The brief explicitly permits omitting a numeric quality score to avoid false precision, and
`docs/FAILURE_MODE_CATALOG.md`'s own convention already avoids overstating confidence in
synthetic-data-derived signals.

### Decision

`quality_assessment.quality_score` stays a nullable `Float` column (so the structural
contract described in the brief exists) but is always `NULL` in v1. The categorical
`quality_state` plus the explicit issue list (dimension, type, severity, evidence) is the
actual explainable output.

### Alternatives Considered

1. Compute a weighted composite score from active issue severities. Rejected — a single
   number would imply a precision and comparability across dimensions ("is a 0.6 sensor
   worse than a 0.7 sensor") that the underlying rules do not actually support; the brief's
   own guidance is explicit about avoiding this.

### Why This Option

A categorical state a person can reason about, backed by the specific issues that produced
it, is more honest and more actionable than a number nobody can trace back to a cause.

### Consequences

No single sortable "worst sensor" ranking exists yet — active issue counts and severities
serve that purpose today (`sensor_quality_state.active_issue_count`,
`/data-quality/summary`'s severity rollup).

### Revisit When

If a future phase has a concrete, validated need for a comparable score (e.g. feeding a
downstream model that genuinely needs one continuous input), add it as an explicit,
documented derived value — never as the primary output.

---

# ADR-066 — Issue Lifecycle Applies Differently to Event-Scoped vs. Window-Scoped Issues

### Status

ACCEPTED

### Context

The brief asks for an `ACTIVE`/`RECOVERING`/`RESOLVED` issue lifecycle, but that model only
makes sense for an *ongoing condition* — a single past event's out-of-range value cannot
"recover", it already happened.

### Decision

Window/stream-scoped issues (staleness, communication loss, sensor-drift-suspected,
stuck-sensor-suspected) use the full lifecycle: created `ACTIVE`, degrade to `RECOVERING`
after one clean evaluation cycle, `RESOLVED` after a second consecutive clean cycle (see
ADR for the partial-index mechanics below). Event-scoped issues (out-of-range, invalid,
spike, sequence gap, duplicate, late arrival) are immutable facts about one specific past
event and are created directly as `RESOLVED` — nothing to recover from.

### Alternatives Considered

1. Apply the full lifecycle uniformly to every issue type. Rejected — an event-scoped issue
   would either need to be artificially left `ACTIVE` forever (misleading — implies an
   ongoing condition) or require a separate mechanism to immediately resolve it, which is
   exactly what creating it as `RESOLVED` already achieves directly.

### Why This Option

The lifecycle field means what it says only when applied to things that genuinely have a
lifecycle. Documented explicitly (`docs/DATA_QUALITY.md` §5) so this split isn't misread as
an oversight.

### Consequences

A reader querying `status = 'ACTIVE'` will only ever see window-scoped issues — by design.

### Revisit When

Not expected to revisit.

---

# ADR-067 — Real Scenario Physics Injected at the Edge/Script Level, Not Faked in the Backend

### Status

ACCEPTED

### Decision

`edge/scripts/run_scenario_validation.py` proves SENSOR_DRIFT/SENSOR_DROPOUT/
NETWORK_FAILURE detection using the real Phase 4 `SimulationEngine` and real Phase 5
`EdgeRuntime`/`MqttTransport` classes — `SimulatorTelemetrySource` already accepted a
`scenario_instances` parameter the real edge CLI never exposed a flag for; this script is
that missing "test-level" injection point, built entirely from existing public classes with
zero changes to any accepted Phase 4/5 source.

### Alternatives Considered

1. Hand-craft MQTT payloads that merely *look like* drift/dropout/network-failure (varying
   values/qualities by hand). Rejected for the three failure-mode scenarios specifically —
   the whole point is proving the *real* simulator physics (the actual bias-growth curve,
   the actual intermittent-outage duty cycle) produce a correctly-detected signal, not that
   a hand-picked value sequence happens to trip a rule. (Hand-built payloads are still the
   right tool for the purely-mechanical synthetic cases — late arrival, out-of-order,
   sequence gap, duplicate pattern, spike, stuck-sensor — see `scripts/verify_data_quality.sh`
   and its own documented rationale.)
2. Add a scenario-injection CLI flag to the real `edge` package. Rejected — scope creep on
   an accepted Phase 5 module for a Phase 7 testing need; the constructor parameter already
   existed and is sufficient.

### Consequences

The script must run where `mosquitto`/`postgres` hostnames resolve (inside the compose
network, or via published host ports with `DATABASE_URL`/`EDGE_BROKER_HOST` overrides) and
depends on `WindowEvaluator`'s periodic cycle for the window-scoped assertions
(SENSOR_DRIFT, NETWORK_FAILURE) — see the known window-dilution limitation in
`docs/DATA_QUALITY.md` §14, which this script's own docstring also documents.

### Revisit When

Not expected to revisit.

---

# ADR-068 — Shared Worker Health/Metrics Infra Relocated to `app/observability/`

### Status

ACCEPTED

### Context

`app.pipeline.metrics.PipelineMetrics` and `app.pipeline.health.PipelineHealthServer`
(Phase 6) were already fully generic — no telemetry-specific coupling — and the Phase 7
worker needed the identical `/health`/`/ready`/`/metrics` behavior.

### Decision

Relocated (not duplicated) to `app/observability/metrics.py::WorkerMetrics` and
`app/observability/worker_health.py::WorkerHealthServer` — the already-existing, previously
empty `app/observability/` package. Phase 6's `mqtt_bridge.py`/`consumer.py` imports updated
to match; behavior-preserving, verified by re-running `verify_pipeline.sh` clean immediately
after the move, before any Phase 7 code was built on top of it.

### Alternatives Considered

1. Duplicate ~150 lines of health/metrics code into a new `app/data_quality/` copy.
   Rejected — the code was already generic; duplicating it is pure maintenance burden with
   no benefit.

### Why This Option

One implementation, three workers (`mqtt-bridge`, `telemetry-consumer`,
`data-quality-worker`) using it identically — the `app/observability/` package now serves
the purpose its (previously empty) existence already implied.

### Consequences

A small, justified refactor to Phase 6 files was required before Phase 7 work began — done
once, verified immediately, not repeated or left half-migrated.

### Revisit When

Not expected to revisit.

---

# ADR-069 — Machine-Wide `COMMUNICATION_LOSS` Recorded Against a Representative Sensor

### Status

ACCEPTED

### Context

`QualityIssue.sensor_id` is `NOT NULL` (every other issue type is genuinely single-sensor),
but `COMMUNICATION_LOSS` is inherently machine-scoped — every sensor on the machine reports
it simultaneously, with no single "owning" sensor.

### Decision

The issue is recorded against one deterministically chosen representative sensor on the
machine (the lowest sensor UUID among currently-reporting sensors) for its required
`sensor_id`/idempotency-key value. `machine_id` (already a proper, populated column) is the
intended way to query/filter/attribute this issue — not `sensor_id`.

### Alternatives Considered

1. Make `QualityIssue.sensor_id` nullable to allow a true machine-only row. Rejected — would
   weaken the idempotency key (`tenant_id, sensor_id, rule_id, rule_version`) and the active-
   window partial unique index for every *other* issue type, which are genuinely
   single-sensor, for the sake of one issue type that isn't.

### Why This Option

A minimal, contained accommodation for one dimension's genuinely different shape, rather
than weakening the schema for every other (correctly single-sensor) issue type.

### Consequences

Frontend/API consumers must filter `COMMUNICATION_LOSS` by `machine_id`, not by iterating
`sensor_id` — documented in `docs/DATA_QUALITY.md` §14 and in the rule module's own
docstring (`app/data_quality/rules/communication.py`).

### Revisit When

If a future phase needs true machine-only quality issues to be common (not just this one
type), reconsider a `sensor_id`-nullable variant or a separate machine-quality-issue table.

---

# ADR-070 — Reprocessing Reads Persisted `Telemetry` Directly, Not a Kafka Replay

### Status

ACCEPTED

### Decision

`app.data_quality.reprocess` re-runs event-level rules by reading already-persisted
`Telemetry` rows directly and reconstructing the `ValidatedTelemetry`/`EnrichedContext`
shapes `QualityEngine.process_event` needs from the row's own already-denormalized fields —
not by replaying the original Kafka messages.

### Alternatives Considered

1. Re-publish/replay the original Kafka messages for the target range. Rejected — Kafka's
   default retention would not guarantee an arbitrary historical range is still available,
   and Phase 6 already durably persisted every field reprocessing needs; replaying transport
   messages to reconstruct data already sitting in Postgres adds a dependency for no benefit.

### Why This Option

Every field `ValidatedTelemetry`/`EnrichedContext` needs is already a column on `Telemetry`
(schema_version, correlation_id, full asset-hierarchy ids, gateway/device ids, firmware/
controller versions, source, metadata) — reprocessing is a straightforward, dependency-free
read-and-replay-through-the-engine.

### Consequences

See the known reprocessing-context limitation recorded in `docs/DATA_QUALITY.md` §11/§14
(context-dependent rules use current, not historical, `SensorContext`).

### Revisit When

Not expected to revisit.

---

# ADR-071 — Baseline Schema: One Denormalized `baseline_profile` Table, Strategy as a Row Discriminator

### Status

ACCEPTED

### Context

Phase 8 needs to persist, for every `(sensor, strategy, context)` lineage, a versioned
history of statistics plus enough metadata (state, sample count, window, config/quality
policy version, firmware/controller identity) to drive the contamination-control state
machine (ADR-073) and the fallback hierarchy (ADR-074). The phase brief's own illustrative
schema sketch suggested three tables (`baseline_profiles`/`baseline_statistics`/
`baseline_contexts`), and separately requires engineering limits (`STATIC_ENGINEERING_
REFERENCE`) and learned baselines (`ROLLING_ASSET_BASELINE`/`CONTEXTUAL_ASSET_BASELINE`)
to never overwrite each other.

### Decision

One table, `baseline_profile` (migration `3366bbb38e2a`), with `strategy`
(`BaselineStrategyType`) and `context_key`/`context` (JSONB) as row-level discriminators,
and `statistics`/`candidate_statistics` as JSONB columns on the same row as its
version/state/window metadata. `STATIC_ENGINEERING_REFERENCE` and the two learned
strategies are simply different `strategy` values sharing the same table and the same
`(tenant_id, sensor_id, strategy, context_key)` uniqueness scope — never overwriting each
other because they never share a lineage key. A `metric_kind` column
(`STANDARD`/`RESERVOIR_TREND`/`CYCLE_METRIC`) distinguishes how to interpret `statistics`
without introducing a fourth table.

### Alternatives Considered

1. The brief's illustrative three-table split (`baseline_profiles` metadata,
   `baseline_statistics` numeric columns, `baseline_contexts` dimension rows). Rejected —
   a `BaselineProfile` row *is* one immutable(-once-`ACTIVE`) snapshot; statistics and
   context are always read and written together with the row that owns them, never
   independently, so a join would add cost and code for data with no independent lifecycle.
2. A separate table per `BaselineStrategyType`. Rejected — the three strategies share
   nearly every column (version, state, window, sample count, versioning fields); a
   per-strategy table would duplicate that schema three times and complicate any
   cross-strategy query (e.g. the fallback hierarchy, which needs to look up
   `CONTEXTUAL_ASSET_BASELINE` then `ROLLING_ASSET_BASELINE` then
   `STATIC_ENGINEERING_REFERENCE` for the same sensor in sequence).
3. A wide table with fixed numeric columns (`p05`, `p25`, `median`, ...) instead of a JSONB
   `statistics` blob. Rejected — different `metric_kind`s (a plain distribution vs. a
   reservoir trend vs. a cycle-metric summary) have genuinely different statistic shapes;
   forcing them into one fixed column set would mean many always-null columns per row.
   JSONB keeps each row's shape matched to what it actually measures, at the cost of losing
   SQL-level type-checking on individual statistic fields (acceptable — no SQL query in this
   phase filters/sorts by an individual statistic value).

### Why This Option

Matches how `app.data_quality`'s own schema treats `quality_issue`/`sensor_quality_state`
(structured JSON payload columns alongside typed metadata columns on one row) — a proven,
reviewed pattern in this codebase already, not a new one introduced for this phase alone.

### Consequences

Adding a new statistic to `RobustStatistics` (`domain/statistics.py`) requires no migration
— it is just a new key in the JSONB blob. The tradeoff is that statistics are not
individually queryable/indexable in SQL; no current API or worker query needs that.

### Revisit When

A future phase needs to filter/sort/aggregate across many sensors by a specific statistic
value at the database level (e.g. "all sensors with `p95` above X") — that would justify
promoting specific fields out of JSONB into real columns.

---

# ADR-072 — Baseline Context Dimensions Fold Load/RPM into `operating_state`; No Ambient-Temperature Dimension

### Status

ACCEPTED

### Context

The brief asks for load/RPM conditioning (§9) and temperature context (§10) as candidate
segmentation dimensions, alongside operating-state (§8) and cycle-phase (§11) segmentation,
while also warning against overfitting with too many tiny bins.

### Decision

`BaselineContext` (`app/baselines/domain/context.py`) carries exactly two fields:
`operating_state` and `cycle_phase`. Load and RPM are not modeled as independent
segmentation dimensions — Phase 3's `OperatingProfile` state machine
(`simulator/simulator/physics/machine.py`) already derives `RUNNING_{LOW,NORMAL,HIGH}_LOAD`
from configured load bands before telemetry is ever emitted, so `operating_state` already
carries the load/RPM signal a separate dimension would otherwise reconstruct. No
ambient-temperature conditioning dimension is introduced for any sensor type — no distinct
ambient-temperature measurement type exists in this system to condition on;
`LUBRICANT_TEMPERATURE` instead gets its own baseline like any other sensor type.

### Alternatives Considered

1. Independent continuous load/RPM buckets (the brief's illustrative `0–25% / 25–50% /
   50–75% / 75–100%` scheme), computed by joining each `BEARING_TEMPERATURE`/`VIBRATION_*`
   reading against a same-timestamp `LOAD`/`RPM` sensor reading. Rejected for this reference
   implementation — this fleet's operating profile is a discrete, shift-driven state
   machine, not continuously-varying load; adding a second, redundant continuous dimension
   on top of a state machine that already discretizes load would risk exactly the
   "too many tiny bins" overfitting the brief warns against, for no additional
   distinguishing power over the existing four operating states.
2. A synthetic ambient-temperature conditioning dimension applied to every sensor
   uniformly. Rejected — inventing a dimension with no real measurement backing it would
   violate the "do not fabricate" posture that runs through this whole project; better to
   document the limitation explicitly (`docs/BASELINES.md` §27) than simulate false
   precision.

### Why This Option

Keeps segmentation genuinely explainable and traceable to a real, observable telemetry
signal (`operating_state`, which is itself carried on every `Telemetry` row from Phase 6
onward) rather than a derived/joined approximation, while still satisfying the brief's core
requirement — verified directly (`test_load_dependent_contextual_profiles_differ`:
`RUNNING_HIGH_LOAD` bearing-temperature median is meaningfully higher than
`RUNNING_LOW_LOAD`'s).

### Consequences

A real deployment with genuinely continuous (not discretely shift-banded) load would likely
need true load/RPM buckets, not just `operating_state` — flagged explicitly as a reference-
implementation simplification, not a general claim that load/RPM conditioning is
unnecessary.

### Revisit When

A future machine profile introduces continuously-varying (not discrete-state-banded) load,
or a real ambient-temperature sensor type is added to the domain model.

---

# ADR-073 — Baseline Contamination Control via a Candidate/Stability-Gate Promotion State Machine

### Status

ACCEPTED

### Context

Phase 8 brief §41 makes contamination control mandatory: a developing physical fault (e.g.
Phase 4's gradual restriction) or a slowly drifting sensor must never gradually redefine
what the baseline engine considers "normal." Quality gating (Phase 7's `ELIGIBLE`/
`INELIGIBLE` classification) already excludes sensors flagged as faulty, but a genuine,
still-`GOOD`-quality physical drift (the value is really changing, and Phase 7 correctly has
not flagged it as a sensor fault) is exactly the case quality gating cannot catch by
design — it is real data, not bad data.

### Decision

A pure, database-free state machine (`app/baselines/services/promotion.py::decide`) governs
every statistics update to a `BaselineProfile` row. A fresh cycle's stats can only reach the
`ACTIVE` row's `statistics` field in one of two ways: `REFINE_ACTIVE` (update in place,
no version bump) only when the new stats are still close — within
`candidate_divergence_mad_multiplier` (default `3.0`) robust (MAD-based) distance — to the
**current anchor** itself; or `PROMOTE` (new version, old version marked `SUPERSEDED`) only
after a candidate has diverged from the anchor and then stayed within tolerance of **its own
previous snapshot** for `required_stable_cycles` (default `2`) consecutive refresh cycles.
Any single-cycle divergence that does not repeat resets candidate tracking
(`START_CANDIDATE`) rather than accumulating partial credit toward promotion.

### Alternatives Considered

1. Exponential moving average / exponentially-weighted statistics, continuously blending new
   readings into the active baseline. Rejected outright — this is precisely the
   "boiling frog" failure mode the brief warns against: a slow, continuous drift would
   incrementally pull a moving average along with it, with no discrete point at which
   contamination could be detected or reverted.
2. A fixed cooldown/freeze period after any detected divergence, with no re-confirmation
   requirement. Rejected — a fixed timer promotes a still-actively-drifting value once the
   timer expires, without checking whether the new level has actually settled; measuring
   stability against the *candidate's own prior snapshot* (not just elapsed time) is what
   distinguishes "a fault that is still getting worse" from "a genuine, settled step-change"
   (e.g. after real maintenance).
3. Require re-confirmation against the *original anchor* for every candidate cycle, instead
   of against the previous candidate snapshot. Rejected — this would never allow promotion
   at all for a candidate that has genuinely settled at a new level far from the old anchor
   (by definition it stays far from the anchor forever); comparing consecutive candidate
   snapshots to each other is what correctly detects "stopped changing," independent of how
   far it ended up from where it started.

### Why This Option

Satisfies both required failure modes simultaneously: a single-cycle blip never promotes
(needs sustained confirmation), and a slow continuous drift never creeps the anchor forward
(anchor only moves via an explicit, auditable `PROMOTE`, which itself requires the new level
to have stopped changing, not merely diverged once). Verified directly against live
Postgres: `test_gradual_drift_leaves_active_baseline_anchored` (a Phase-4-style gradual
pressure rise from 9.0 to 18.0 bar leaves the `ACTIVE` row's id and `statistics.median`
completely unchanged one cycle later) and `test_ineligible_sensor_never_updates_learned_
baseline` (the independent Phase 7 quality-gating layer).

### Consequences

A genuine, permanent step-change (e.g. a real sensor recalibration, or documented
maintenance that legitimately changes normal operating levels) takes `required_stable_
cycles` refresh intervals to be recognized as the new normal, rather than being reflected
immediately — an intentional trade-off; §11's firmware/config-change invalidation exists
precisely to give operators an explicit, immediate override path for exactly this case
instead of waiting out the stability gate.

### Revisit When

Live operational experience shows `required_stable_cycles`/`candidate_divergence_mad_
multiplier` are miscalibrated (too eager or too conservative) for a specific sensor type —
both are already per-deployment config (`demo_baseline_policy.yaml`), not hardcoded.

---

# ADR-074 — Baseline Fallback Hierarchy: Exact Context -> Operating-State -> Sensor-Level -> Engineering Reference

### Status

ACCEPTED

### Context

Brief §22 requires that when an exact contextual baseline is unavailable (a sensor is new,
still `BUILDING`, or has no history in a specific operating state), the system fall back
"deliberately" rather than silently returning an unrelated context or nothing at all.

### Decision

`app/baselines/services/fallback.py::resolve_baseline` walks a fixed four-rung hierarchy —
`EXACT_CONTEXT -> OPERATING_STATE -> SENSOR_LEVEL -> ENGINEERING_REFERENCE` — trying each
rung's real, `ACTIVE` row in order and returning as soon as one exists. The caller always
receives which rung actually answered (`BaselineSourceKind`), never just a bare statistics
object with no provenance.

### Alternatives Considered

1. Return the nearest context by some similarity metric (e.g. "closest" operating state)
   rather than a fixed hierarchy. Rejected — introduces a similarity judgment call with no
   clear physical justification (operating states are categorical, not ordered by
   "closeness" for most sensor types), and would obscure exactly which baseline is being
   compared against, undermining explainability.
2. Silently return whatever baseline exists for the sensor, without surfacing which rung
   answered. Rejected outright by the brief itself ("do not silently return unrelated
   context").
3. Return `None`/an error the moment the exact context is unavailable. Rejected — this
   would make the API and any future consumer unable to say anything useful about a newly
   deployed sensor; a coarser, explicitly-labeled fallback is more useful than no answer,
   provided the caller can see it is a fallback.

### Why This Option

Every rung is a real, independently queryable `ACTIVE` row (never a synthesized/interpolated
value), and `BaselineSourceKind` on the response makes the fallback depth an explicit,
API-visible fact rather than a hidden implementation detail — verified via
`test_fallback_hierarchy_prefers_exact_then_coarse_then_sensor_then_reference`.

### Consequences

A consumer of `GET /api/v1/baselines/sensors/{id}/current` must handle `source !=
EXACT_CONTEXT` as a normal, expected state for a newly deployed or rarely-visited-context
sensor, not an error condition.

### Revisit When

Not expected to revisit at this reference implementation's scale.

---

# ADR-075 — Baseline Worker Is a Periodic Scan, Not a Kafka Consumer

### Status

ACCEPTED

### Context

Every prior Phase 6/7 backend worker (`mqtt-bridge`, `telemetry-consumer`, `data-quality-
worker`) is a Kafka consumer, reacting to individual telemetry events. Phase 8 needed an
explicit decision on whether the baseline worker should follow that same shape.

### Decision

`app.baselines.workers.worker` is a periodic `asyncio` loop, not a Kafka consumer group. Each
cycle it discovers currently-tracked sensors from `sensor_quality_state` (the same
cross-tenant discovery pattern `app.data_quality.worker` already uses), refreshes any sensor
whose measurement-type-specific `refresh_interval_seconds` has elapsed, refreshes cycle-level
baselines once per machine seen, then sweeps for staleness.

### Alternatives Considered

1. A Kafka consumer on `lubrisense.telemetry.v1` (the same topic the data-quality worker
   already reads), recomputing statistics on every event. Rejected — a baseline is a
   statistic over a rolling window, not a per-event judgment; recomputing full window
   statistics on every single telemetry event would be enormously wasteful compared to a
   bounded periodic scan, for no correctness benefit (the brief's own §29 asks for
   configurable, sensor-type-aware refresh cadence, which a per-event trigger cannot express
   cleanly).
2. A hybrid: a lightweight Kafka consumer that only marks sensors "dirty" and defers actual
   recomputation to a periodic sweep. Rejected as unnecessary complexity for this reference
   implementation's scale — a plain periodic scan over `sensor_quality_state` already visits
   every tracked sensor at the correct configured cadence without needing a second
   coordination mechanism.

### Why This Option

Directly reuses the exact same `BaselineEngine.refresh_sensor` method for both live
(periodic, recent-window) and historical (`backfill.py`, explicit-range) operation — the
"simple architecture that supports both live and historical operation" the brief asks for
(§28) — and avoids re-running the simulator or duplicating Phase 6/7's event-processing
machinery for a workload that is fundamentally window-based, not event-based.

### Consequences

A newly eligible sensor is picked up at the next worker cycle (bounded by
`BASELINE_WORKER_CYCLE_SECONDS`), not instantaneously on its first telemetry event — an
acceptable latency given baselines themselves require `min_sample_count` eligible samples
before producing any statistics at all, which already implies a multi-event delay.

### Revisit When

A future phase needs sub-cycle-latency baseline updates (no such requirement exists through
Phase 13).

---

# ADR-076 — Robust (Median/MAD) Statistics as the Primary Summary, Mean/Stddev Retained as Secondary

### Status

ACCEPTED

### Context

Brief §13 explicitly warns against relying only on mean/stddev for skewed or
outlier-contaminated distributions — a handful of transient spikes or a brief sensor hiccup
should not dominate a baseline's summary the way it would a plain mean.

### Decision

`app/baselines/domain/statistics.py::compute_robust_statistics` computes median, MAD (scaled
by the standard `1.4826` normal-consistency constant), and `p05`/`p25`/`p75`/`p95`
linear-interpolation quantiles as the primary robust summary. Mean and (population) stddev
are still computed and stored on every `RobustStatistics` row, but only used as a fallback —
`app/baselines/domain/deviation.py::compute_deviation` uses the MAD-based standardized
distance whenever `mad > 0`, falling back to a stddev-based distance only when `mad == 0`
(e.g. `CYCLE_COMPLETION`, a boolean-valued signal), and to a degenerate constant-value check
if both are zero.

### Alternatives Considered

1. Mean/stddev only (the simplest, most familiar summary). Rejected outright — this is
   exactly what brief §13 forbids; a single transient spike can distort a plain stddev
   enough to make the deviation helper (ADR-073's stability gate depends on the same
   robust-distance primitive) either miss real drift or over-trigger on noise.
2. Full distributional modeling (e.g. fitting a parametric distribution per sensor type).
   Rejected as over-engineering for a reference implementation — median/MAD/quantiles are
   distribution-agnostic, require no fitting step, and are exactly as fast to compute
   incrementally as mean/stddev.

### Why This Option

Gives both the contamination-control stability gate (ADR-073) and the deviation helper
(§18) an outlier-resistant distance measure by default, while keeping mean/stddev available
for roughly-symmetric signals (`LOAD`, `RPM`) and as an explicit, labeled fallback
(`method="stddev_fallback"` in `DeviationResult`) rather than silently switching behavior.

### Consequences

Every statistics computation does slightly more work than a plain mean/stddev pass (a sort
for quantiles/median, a second pass for MAD) — negligible at this reference
implementation's per-window sample counts (hundreds, not millions).

### Revisit When

Not expected to revisit.

---

# ADR-077 — Rules Engine Persistence: One Denormalized `rule_finding` Table, CANDIDATE Prepended to Phase 7's Lifecycle

### Status

ACCEPTED

### Context

Phase 9 needs to persist, per `(machine, component, rule)` lineage, a versioned evidence
finding with structured evidence/limitations and a debounce/hysteresis lifecycle. The brief's
illustrative schema sketch suggested three tables (`rule_findings`/`rule_finding_evidence`/
`rule_state`), and separately requires a CANDIDATE stage before a finding may be treated as
confirmed (brief §7/§20).

### Decision

One table, `rule_finding` (migration `615a5631e98e`) — the same denormalization choice
Phase 8's `BaselineProfile` made (ADR-071) and for the identical reason: a finding's
evidence/limitations/quality_context are always read and written together with the row that
owns them. Lifecycle mirrors `QualityIssue`'s (Phase 7) ACTIVE/RECOVERING/RESOLVED
window-scoped pattern with one CANDIDATE stage prepended — a partial unique index
(`uq_rule_finding_active_scope`, `state IN ('CANDIDATE','ACTIVE','RECOVERING')`) enforces at
most one non-terminal row per lineage, exactly as Phase 7's own partial index does.

### Alternatives Considered

1. The brief's three-table sketch. Rejected for the same reason ADR-071 rejected it for
   baselines — no independent lifecycle for evidence vs. the row that owns it.
2. Reuse `quality_issue`'s exact ACTIVE/RECOVERING/RESOLVED lifecycle without a CANDIDATE
   stage, treating "not yet confirmed" as simply "not created yet." Rejected — this loses the
   ability to track *how close* a developing pattern is to confirmation
   (`candidate_stable_cycles`), which brief §7 explicitly wants surfaced.

### Why This Option

Directly reuses two already-reviewed patterns (Phase 7's partial-index lifecycle mechanism,
Phase 8's denormalized-JSONB-evidence schema) rather than inventing a third persistence
shape for a third domain area.

### Consequences

Adding a new evidence field to any rule requires no migration — it is a new JSONB key.

### Revisit When

A future phase needs to filter/aggregate across many findings by a specific evidence field
value at the database level.

---

# ADR-078 — Rules Worker Is a Periodic Scan, Not a Kafka Consumer

### Status

ACCEPTED

### Context

Every Phase 6/7 worker is a Kafka consumer; Phase 8's baseline worker broke that pattern
(ADR-075) because a baseline is a window statistic, not a per-event judgment. Phase 9 needed
its own explicit decision, since rules additionally *depend on* Phase 8 baselines.

### Decision

`app.rules_engine.workers.worker` is a periodic `asyncio` loop
(`RULES_WORKER_CYCLE_SECONDS`, default 300s), discovering tracked machines from Phase 7's
`sensor_quality_state` (mirroring Phase 8's own discovery pattern) rather than consuming
Kafka.

### Alternatives Considered

1. A Kafka consumer on `lubrisense.telemetry.v1`, re-evaluating rules on every event.
   Rejected — a rule finding is a judgment over a window of evidence, and every rule already
   depends on Phase 8 baselines that are themselves only refreshed on a multi-minute cadence;
   an event-triggered rules worker would routinely race ahead of the baselines it needs,
   evaluating against baseline data that hasn't caught up yet.
2. Trigger a rules cycle immediately after each baseline-worker cycle (a dependency chain
   instead of two independent periodic loops). Rejected as unnecessary coupling for this
   reference implementation's scale — two independently-scheduled periodic loops reading the
   same tables achieve the same effective freshness without one worker needing to know the
   other exists.

### Why This Option

Directly reuses `RuleEngine.evaluate_machine` for both live (periodic) and historical
(reprocess CLI, explicit range) operation — the same "one method, two callers" shape Phase 8
established — and avoids racing ahead of the Phase 8 baselines every rule depends on.

### Consequences

A newly-eligible machine is picked up at the next worker cycle (bounded by
`RULES_WORKER_CYCLE_SECONDS`), not instantaneously — acceptable given baselines themselves
already impose a multi-minute-scale freshness ceiling.

### Revisit When

A future phase needs sub-cycle-latency finding updates.

---

# ADR-079 — Per-Candidate SAVEPOINT Isolation Inside One Machine's Rule Evaluation

### Status

ACCEPTED

### Context

Phase 7/8 workers isolate failures per *sensor*/*event* with a `SAVEPOINT`, so one bad item
never blocks a whole batch. Phase 9's initial implementation isolated failures only per
*machine* (matching that precedent at the coarsest matching granularity) — but a real bug
found during live verification (`scripts/verify_rules.sh`: a reservoir depletion-rate
distance computed as `float("inf")` when a perfectly-linear synthetic baseline produced a
zero MAD, which is not valid JSON) demonstrated that a single bad *finding* within one
machine's evaluation could roll back every other valid finding computed for that same
machine in that same cycle, since `_apply_lifecycle` originally ran all candidates in one
implicit transaction scope.

### Decision

`RuleEngine._apply_lifecycle` wraps each candidate's persistence (and each
previously-current row's recovery/resolution check) in its own `session.begin_nested()`
`SAVEPOINT`, catching and logging any exception per-item (`EvaluationResult.findings_errors`,
surfaced through `rule_processing_errors` metric) rather than letting it propagate and abort
the whole machine's cycle. Nested inside the live worker's own per-machine `SAVEPOINT`
(Phase 7/8 precedent), so isolation now exists at both granularities.

### Alternatives Considered

1. Leave machine-level isolation only, and simply fix the specific `float("inf")` bug (which
   was also fixed, in `single_signal.classify_reservoir_trend_deviation` and
   `rule_engine._build_cycle_evaluation`'s `mad_distance` consumption). Rejected as
   insufficient on its own — the next unanticipated pathological input to any single rule
   would reproduce the identical failure mode (silently losing every other correct finding
   for that machine that cycle) until specifically caught and fixed, rather than being
   structurally contained the way Phase 7/8 already contain per-event/per-sensor failures.

### Why This Option

Matches the depth of isolation Phase 7/8 already apply one level down (per-event, per-sensor)
— a per-candidate failure should have exactly the same blast radius as a per-event/per-sensor
failure does in those phases: itself, not its siblings.

### Consequences

Slightly more `SAVEPOINT` overhead per cycle (one per candidate rather than one per machine)
— negligible at this reference implementation's per-machine finding-candidate counts (tens,
not thousands).

### Revisit When

Not expected to revisit.

---

# ADR-080 — Quality Gating and ACTIVE-Baseline-Only Consumption Reuse Phase 7/8 Directly, No New Policy Layer

### Status

ACCEPTED

### Context

Phase 9 brief §4/§43 require rules to respect Phase 7 eligibility and consume only ACTIVE
Phase 8 baselines. A new rules-specific quality/baseline-trust policy could have been
introduced.

### Decision

No new trust-policy layer. Per-signal quality gating reads `SensorQualityState.eligibility`
directly (Phase 7's own field, no rules-side re-derivation); baseline resolution reuses
Phase 8's `deviation_service`/`BaselineProfileRepository` directly, which structurally only
ever return `ACTIVE` rows. The only rules-specific addition is the *machine-level* aggregate
gate (`minimum_eligible_sensor_fraction` → `INSUFFICIENT_TRUSTED_DATA`), which has no Phase
7/8 precedent to reuse since neither phase reasons about "enough of a machine's sensors."

### Alternatives Considered

1. A rules-owned copy of eligibility/baseline-state logic, re-evaluated independently.
   Rejected — would let Phase 7/8's and Phase 9's judgments about the same sensor silently
   diverge, and duplicates logic that already has a single owner.

### Why This Option

Keeps "is this sensor trustworthy" and "is this baseline current" each owned by exactly one
phase, with Phase 9 as a pure consumer — a real bug class (divergent judgments about the same
sensor) is prevented structurally rather than by convention.

### Consequences

A future change to Phase 7's eligibility mapping or Phase 8's ACTIVE-only resolution
automatically propagates to Phase 9 rules without a corresponding rules-side change — usually
desirable, but means Phase 9 cannot special-case its own trust threshold for eligibility
itself (only for the aggregate machine-level fraction, which is genuinely rules-specific).

### Revisit When

A future phase needs rule-specific trust semantics that diverge from Phase 7/8's own.

---

# ADR-081 — Evidence Strength and Severity Are Two Separate, Explicitly-Ordered Computations

### Status

ACCEPTED

### Context

Brief §8/§23/§24 require an evidence-strength model distinct from ML probability, a severity
model, and an explicit rule that criticality affects severity/priority but never whether
evidence exists.

### Decision

Two-step, one-directional computation: `evidence_strength` (`LOW`/`MODERATE`/`STRONG`) is
computed purely from Phase 8's deviation classification (plus a caution cap) — criticality is
never an input to this step. `severity` (`INFO`/`WARNING`/`HIGH`/`CRITICAL`) is computed
*from* `evidence_strength` via a policy-configured base mapping, then optionally escalated
one level by `Machine`/`Bearing.criticality` (Phase 2) — criticality can only ever act on an
already-computed severity, never on evidence_strength or on whether a `RuleFindingCandidate`
is produced at all.

### Alternatives Considered

1. A single combined score factoring in criticality from the start. Rejected outright —
   this is exactly what brief §24 forbids ("criticality may influence priority/severity but
   not whether physical evidence exists"); collapsing the two into one computation makes that
   separation unauditable.

### Why This Option

The one-directional dependency (evidence_strength → severity, criticality → severity only)
is enforced by the code's own call order (`_severity_for` takes an already-built
`RuleFindingCandidate`, never the reverse), not merely a documented convention.

### Consequences

A `CRITICAL`-severity finding always traces back to a `STRONG`-evidence-strength finding on
a `HIGH`/`CRITICAL`-criticality component — never a `LOW`-evidence-strength finding
"promoted" to `CRITICAL` by criticality alone.

### Revisit When

Not expected to revisit.

---

# ADR-082 — Cross-Signal Pattern Differentiation via Policy-Configured Require/Exclude/Support Sets

### Status

ACCEPTED

### Context

Brief §12-§15 require restriction, leakage, and pump degradation to be distinguishable from
each other and from an undifferentiated multi-signal deviation, using the physical signature
differences `docs/SCENARIO_ENGINE.md`/`docs/FAILURE_MODE_CATALOG.md` already document
(restriction raises pressure; leakage does not; pump degradation slows the rise without
raising the peak).

### Decision

Each cross-signal pattern is a declarative `requires`/`supporting`/`excludes` set of
single-signal finding types, evaluated against the set that already fired *this same cycle*
(`RulesPolicy.cross_signal`, `app.rules_engine.rules.cross_signal._evaluate_pattern`) — never
a bespoke conditional per pattern. `excludes` is what makes leakage and pump degradation
structurally unable to collapse into restriction: `PRESSURE_ABOVE_CONTEXTUAL_BASELINE`
appearing at all rules both of them out for that cycle. A generic
`LUBRICATION_PATH_DEGRADATION_PATTERN` catch-all fires only when no specific pattern matched,
so evidence is never double-counted into two findings.

### Alternatives Considered

1. One bespoke conditional function per pattern with inline signal checks. Rejected — makes
   the require/exclude relationships implicit in code logic rather than an inspectable,
   independently-testable configuration, and would need a code change (not a config change)
   to retune which signals count as supporting vs. required.

### Why This Option

The `excludes` mechanism is what makes the differentiation requirement structurally
enforced rather than merely documented — verified directly:
`test_leakage_pattern_excluded_when_pressure_also_elevated`,
`test_pump_degradation_pattern_excluded_when_pressure_elevated`, and live via
`scripts/verify_rules.sh` (restriction correctly never fires without a FLOW signal, even
though pressure and pump current are both clearly elevated on the real flagship topology).

### Consequences

Retuning which signals corroborate vs. exclude a pattern is a `demo_rules_policy.yaml`
change, not a code change — matching every other threshold in this project's demo-policy
convention.

### Revisit When

A future phase's real failure-label data suggests a different require/exclude combination
than this reference implementation's physics-derived one.

---

# ADR-083 — Historical Reprocessing Reads Persisted Telemetry Directly, Not a Kafka Replay

### Status

ACCEPTED

### Context

Phase 9 brief §31 requires historical rule reprocessing. Phase 6-8 each faced (and resolved)
the identical question for their own domain.

### Decision

`python -m app.rules_engine.workers.reprocess` calls `RuleEngine.evaluate_machine` directly
against already-persisted `telemetry`/`sensor_quality_state`/`baseline_profile`, with an
explicit `--start`/`--end` window — no Kafka replay, matching Phase 7's reprocessing
(ADR-070) and Phase 8's backfill (ADR-075's "one method, two callers") precedent exactly.

### Alternatives Considered

Same alternatives Phase 7's ADR-070 already considered and rejected (a Kafka replay
mechanism) — not re-litigated here; the reasoning transfers directly since Phase 9's inputs
are the same already-persisted tables.

### Why This Option

Consistency with three prior phases' identical decision, and every field
`RuleEngine._build_context` needs is already present on `Telemetry`/`SensorQualityState`/
`BaselineProfile` — no replay dependency chain required.

### Consequences

Same known limitation as Phase 7/8: reprocessing reads a sensor's *current* eligibility/
baseline state, not its historical point-in-time state.

### Revisit When

Not expected to revisit — would only change if Phase 7/8's own equivalent decisions changed.

---

# ADR-084 — One Shared Point-in-Time Feature Engine for Historical and Online Use

### Status

ACCEPTED

### Context

Separate offline and online formulas create train/serve skew and make leakage fixes easy to
apply to only one path.

### Decision

`FeatureEngine.compute` plus the database-free `compute_feature_values` core is the only
implementation. Historical CLI, periodic materialization, online latest computation, and
tests all delegate to it.

### Alternatives Considered

Separate SQL training transforms and a Python serving transform; rejected because semantic
parity would rely on duplicated implementation and tests rather than shared code.

### Why This Option

Parity is structural. Differences are limited to selecting the as-of timestamp and whether
the resulting vector is persisted.

### Consequences

Both workloads share the same Python performance envelope and version-release lifecycle.

### Revisit When

Fleet-scale training requires a distributed execution backend; that backend must still
execute or compile the same registered definitions.

---

# ADR-085 — Source-Time Windows and Strict As-Of Filtering

### Status

ACCEPTED

### Context

Buffered/replayed events can be persisted long after the physical observation. Arrival-time
windows would misplace those values and permit historical leakage.

### Decision

All physical feature windows use `source_timestamp`, inclusive at T, never
`persisted_timestamp`. Source loading enforces `source_timestamp <= T`, baselines with
future physical window ends are excluded, and rule evidence must have been active by T.

### Alternatives Considered

Persisted-time windows and post-query filtering; rejected because both can scan/use future
physical data incorrectly.

### Why This Option

Matches Phase 6's hypertable event-time decision (ADR-054) and real inference availability.

### Consequences

Late arrivals do not retroactively enter an already-materialized vector unless that vector
is deliberately recomputed; idempotent storage then keeps the prior logical vector unchanged.

### Revisit When

A correction/version mechanism for late historical restatement is designed.

---

# ADR-086 — Preserve Missingness and Reuse Existing Trust Owners

### Status

ACCEPTED

### Context

Zero-filling absent/bad sensors creates false physical evidence. Re-deriving quality or
baseline status in Phase 10 would diverge from Phase 7/8 ownership.

### Decision

Numeric equipment features require Phase 7 `ELIGIBLE`/`ELIGIBLE_WITH_CAUTION` plus a GOOD,
non-null reading. Missing/suppressed values are absent from `feature_values` and listed in
`missing_features`; explicit availability/quality features remain. Baselines must be Phase
8 ACTIVE. Phase 9 findings are evidence features only.

### Alternatives Considered

Generic zero fill, forward fill, a feature-owned quality score, and candidate/stale baseline
fallback; all rejected as either misleading or a duplicate trust policy.

### Why This Option

Keeps the existing quality/baseline/rule contracts authoritative and makes uncertainty
model-visible without fabricating normal values.

### Consequences

Later models must explicitly support nulls or apply a separately versioned training-time
imputation transform. Phase 10 performs no complex imputation.

### Revisit When

A specific model requires a validated, versioned imputation strategy.

---

# ADR-087 — Code Registry with Explicit Semantic and Feature-Set Versions

### Status

ACCEPTED

### Context

Phase 10 needs maintainable definitions and set membership but not a commercial feature
store or a mutable authoring database.

### Decision

Definitions are immutable Python data in `app.features.definitions`, exposed read-only by
API and rendered to `docs/FEATURE_CATALOG.md`. Each definition and each set has its own
semantic version.

### Alternatives Considered

Database-authored registry and an external feature-store product; rejected as operational
scope without a current authoring or serving requirement.

### Why This Option

Definitions are reviewed, tested, deployed, and reproduced with code while remaining
machine-readable.

### Consequences

Definition changes require a code release and deliberate version bump.

### Revisit When

Non-developer feature authoring or independent feature deployment becomes a requirement.

---

# ADR-088 — Hybrid On-Demand and Idempotent Materialized Feature Storage

### Status

ACCEPTED

### Context

Persisting every intermediate statistic multiplies storage, while recomputing every
historical training matrix loses auditability and is expensive.

### Decision

Latest online vectors compute on demand. Historical/training and scheduled validation
snapshots persist as one denormalized JSONB `feature_vector` row with provenance. A
deterministic UUID plus a logical unique constraint prevents duplicates; conflicts never
overwrite the existing row.

### Alternatives Considered

Compute-only and materialize-everything; rejected respectively for weak reproducibility and
unnecessary storage/query amplification.

### Why This Option

Preserves training evidence where valuable without turning Phase 10 into a feature-store
platform.

### Consequences

JSONB feature-value analytics may require extraction or export for large training jobs.

### Revisit When

Materialization volume or model-training access patterns justify columnar/offline storage.

---

# ADR-089 — Periodic Feature Worker with Bulk Per-Vector Source Queries

### Status

ACCEPTED

### Context

Most features are multi-minute/hour windows and depend on periodic baselines/rules. An
event-triggered calculation would race dependencies and repeatedly recompute the same window.

### Decision

A periodic worker materializes latest vectors. One source-repository call bulk-loads the
maximum telemetry window, quality state, ACTIVE baselines, quality issues, rules, and asset
context; computation performs no query per feature. The worker exposes liveness, DB-backed
readiness, metrics, and per-machine/set failure isolation.

### Alternatives Considered

Kafka-per-event computation and one SQL query per feature; rejected for dependency races and
obvious query explosion.

### Why This Option

Matches Phase 8/9's periodic intelligence-worker precedent and scales query count with
vectors, not definition count.

### Consequences

Freshness is bounded by the worker interval; online callers can compute a fresher vector on
demand.

### Revisit When

Sub-minute online feature freshness becomes necessary.

---

# Pending Decisions (Deferred to Later Phases)

Resolved by Phase 1 and removed from this list: exact service boundaries within `backend/`
(§11 module structure — see `docs/ARCHITECTURE.md` §11), Kafka deployment approach
(ADR-015), PostgreSQL/TimescaleDB/pgvector local approach (ADR-014), Python dependency
management (ADR-016), frontend package manager (ADR-017), structured logging approach
(ADR-018), environment configuration approach (ADR-019), local networking strategy
(ADR-020), health/readiness semantics (ADR-021).

Resolved by Phase 3 and removed from this list: simulator topology-loading strategy
(ADR-030), simulator state/lag model (ADR-031), ground-truth/telemetry separation
(ADR-032), simulator determinism strategy (ADR-033), simulator output format (ADR-034).

Resolved by Phase 4 and removed from this list: scenario composition/application strategy
(ADR-035), failure progression model (ADR-036), multi-fault ground-truth representation
(ADR-037), scenario targeting strategy (ADR-038), multi-fault precedence rules (ADR-039),
missing/communication-loss quality representation (ADR-040), raw-vs-delivered flow
modeling (ADR-041), refill mechanism design (ADR-042).

Resolved by Phase 5 and removed from this list: edge persistence choice (ADR-043), edge
sequence strategy (ADR-044), edge event-id strategy (ADR-045), MQTT topic hierarchy/QoS
(ADR-046), edge buffer retention policy (ADR-047), connectivity-state model (ADR-048), edge
local-rule boundary (ADR-049).

Resolved by Phase 6 and removed from this list: central pipeline worker/module boundary
(ADR-050), MQTT-Kafka bridge client design (ADR-051), Kafka partition key (ADR-052),
delivery/idempotency semantics (ADR-053), hypertable time column/chunk interval (ADR-054),
batch persistence strategy (ADR-055), bridge durable-spool design (ADR-056), DLQ/quarantine
split (ADR-057), context enrichment strategy (ADR-058), wire-contract ownership (ADR-059).
Event schema versioning format (previously listed for Phase 2) is also resolved, by
`schema_version` gating in `app.pipeline.validation.SchemaValidator` (§6 of
`docs/TELEMETRY_PIPELINE.md`).

Resolved by Phase 7 and removed from this list: data-quality worker consumer-group design
(ADR-060), critical-path-vs-best-effort failure isolation (ADR-061), quality storage model
(ADR-062), event-level/window-level rule split (ADR-063), quality-state/eligibility field
separation (ADR-064), numeric quality score deferral (ADR-065), issue lifecycle scope
(ADR-066), scenario validation harness (ADR-067), shared worker observability relocation
(ADR-068), communication-loss attribution (ADR-069), reprocessing data source (ADR-070).

Resolved by Phase 8 and removed from this list: baseline schema/strategy-separation design
(ADR-071), baseline context-dimension scope (ADR-072), baseline contamination-control
state machine (ADR-073), baseline fallback hierarchy (ADR-074), baseline worker
architecture (ADR-075), baseline robust-statistics choice (ADR-076).

Resolved by Phase 9 and removed from this list: rules-engine finding persistence/lifecycle
design (ADR-077), rules worker architecture (ADR-078), per-candidate isolation granularity
(ADR-079), rules quality-gating/baseline-trust reuse strategy (ADR-080), evidence-strength/
severity separation (ADR-081), cross-signal pattern differentiation strategy (ADR-082),
rules reprocessing design (ADR-083).

Resolved by Phase 10 and removed from this list: shared feature architecture/train-serve
parity (ADR-084), point-in-time/event-time semantics (ADR-085), quality/baseline/rule usage
and missing values (ADR-086), registry/feature-set versioning (ADR-087), hybrid materialized
storage/idempotency (ADR-088), and periodic bulk-query worker architecture (ADR-089).
Health-score calculation strategy (below) remains open — Phase 7 deliberately does not
compute one (ADR-065); that entry still applies to a future condition-intelligence phase.

Still not blocking Phase 1 acceptance; to be resolved when the relevant phase begins:

- telemetry **retention** (drop/downsample-old-chunks) policy — Phase 6 resolved the
  hypertable *partitioning*/chunk-interval strategy (ADR-054) but not a retention policy;
  still flagged as a risk in docs/ARCHITECTURE.md §14, revisit at Phase 33 or when storage
  cost becomes a real constraint
- health-score calculation strategy (Phase 13, Condition Intelligence)
- model registry implementation (Phase 32, MLOps)
- job queue implementation (introduced when a Phase actually needs background job
  processing — none does yet)
- full authentication/RBAC implementation for the demo environment (explicitly deferred
  past Phase 1 per LOOP.md; Phase 1 only establishes the OIDC/OAuth2-compatible
  architecture boundary — `backend/app/auth/` — without implementing it)
- frontend charting library (Phase 28)
- RAG embedding provider/model (Phase 18)
- LLM provider abstraction (Phase 18/19)
- Kubernetes packaging strategy (post-Phase 1, if/when needed)

Do not accept these decisions without reviewing their trade-offs when their phase begins.
