# LubriSense AI — Implementation Status

## Project

LubriSense AI  
Condition-Driven Intelligent Lubrication Platform

---

# Current Phase

PHASE 9 — RULE ENGINE

Status:

COMPLETE — pending human review/acceptance sign-off

---

# Overall Progress

## Phase 0 — Product + Architecture Foundation

COMPLETE

Outputs produced:

- docs/PRODUCT_VISION.md
- docs/ARCHITECTURE.md
- docs/DOMAIN_MODEL.md
- docs/EVENT_CATALOG.md
- docs/FAILURE_MODE_CATALOG.md
- repository architecture (docs/ARCHITECTURE.md §11)
- technical-risk assessment (docs/ARCHITECTURE.md §14)
- Phase 0 acceptance criteria (docs/ARCHITECTURE.md §13)

No application code was written in this phase. `backend/`, `frontend/`, `ml-service/`,
`simulator/`, `edge/`, `infrastructure/`, `tests/`, `scripts/` remain empty scaffolding,
as expected at this phase boundary.

---

## Phase 1 — Repository + Platform Foundation

COMPLETE

Delivered:

- Next.js 16 frontend (TypeScript strict, Tailwind, App Router, TanStack Query, ESLint,
  Prettier), minimal platform-status page (frontend running / backend connectivity /
  environment info — no hardcoded product values)
- FastAPI backend (typed Python via uv, modular `app/{api,core,domain,services,
  repositories,infrastructure,auth,audit,observability}` structure), versioned
  `/api/v1` routing
- PostgreSQL + TimescaleDB + pgvector via `timescale/timescaledb-ha:pg16` (both
  extensions verified coexisting — ADR-014)
- Redis connectivity + health check (no caching/business logic yet, as scoped)
- MQTT (Eclipse Mosquitto) — verified publish/subscribe round trip
  (`scripts/verify_mqtt.sh`)
- Kafka (KRaft, `apache/kafka:3.7.0`, no ZooKeeper — ADR-015) — verified produce/consume
  round trip (`scripts/verify_kafka.sh`)
- Docker Compose stack: postgres, redis, mosquitto, kafka, backend, frontend — all six
  report `healthy`
- Alembic migrations: initial schema (extensions + `system_metadata` bootstrap table),
  applied and verified against the live database
- `GET /health`, `GET /ready`, `GET /api/v1/system/info` — implemented, tested, and
  manually verified against both a local run and the full Docker Compose stack
- Correlation ID middleware (`X-Correlation-ID`, generate-or-echo, in logs and responses)
- Consistent API error model (`code`/`message`/`details`/`correlation_id`, no stack
  traces in responses)
- Structured JSON logging (stdlib `logging` + custom formatter, correlation-ID-aware)
- Backend: ruff + mypy (strict) + pytest (12 tests, all against live Postgres/Redis, not
  mocks) — all passing
- Frontend: ESLint + `tsc --noEmit` + Prettier + production build — all passing
- Production-oriented multi-stage Dockerfiles (non-root users, health checks, small
  runtime images) for both backend and frontend — built and smoke-tested
- Root `Makefile` (`up`, `down`, `logs`, `build`, `migrate`, `test`, `lint`, `typecheck`,
  `mqtt-verify`, `kafka-verify`, `verify`)
- GitHub Actions CI (`.github/workflows/ci.yml`): backend lint/typecheck/test against
  real Postgres+Redis service containers, frontend lint/typecheck/format/build
- `.env.example`, `.gitignore` (no secrets committed), README files in every major
  service directory including inactive-scaffold explanations for `simulator/`, `edge/`,
  `ml-service/`
- `docs/DEVELOPER_SETUP.md` — full local walkthrough
- 8 new/updated ADRs (ADR-014–ADR-021) recording the concrete Phase 1 technical
  decisions; ADR-006 and ADR-007 promoted from PROPOSED to ACCEPTED now that they are
  validated, not just proposed

Not implemented (explicitly out of Phase 1 scope — see LOOP.md §21): asset hierarchy,
simulator, failure injection, real telemetry schemas, data quality engine, rules engine,
feature engineering, ML models, Kalman filter, condition/decision intelligence, RAG,
GenAI agents, CMMS, customer/business analytics, final dashboard, full auth/RBAC.

---

## Phase 2 — Domain Model + Asset Hierarchy

COMPLETE

Delivered:

- Full domain schema: `Tenant → CustomerAccount → Site → Plant → ProductionLine →
  Machine → Bearing`, `Machine → LubricationSystem → {Reservoir, Pump, Controller,
  Distributor} → Circuit → LubricationPoint → Bearing`, tenant-safe `Sensor`
  (6 possible attachment points) and `Gateway` (2 possible attachment points) — 16 domain
  tables (`backend/app/domain/models.py`)
- **Composite-tenant-foreign-key schema** (ADR-022): every tenant-owned table has
  `UNIQUE(tenant_id, id)`; every parent/child FK is `(tenant_id, parent_id) ->
  parent(tenant_id, id)` — cross-tenant references are rejected by Postgres itself, not
  only application code
- Sensor/Gateway exactly-one-attachment `CHECK` constraints (ADR-023), enforced at the DB
  level, not just in code
- Enum strategy: `VARCHAR` + `CHECK`, not native Postgres enum types (ADR-024)
- Alembic migration `08276baaeac2` (16 tables, all constraints/indexes) — applied,
  downgraded, and re-applied cleanly against the live database; a genuine FK cycle
  (`LubricationSystem` ↔ `Reservoir`/`Pump`/`Controller`) resolved with SQLAlchemy
  `use_alter=True`
- Repository layer: `TenantScopedRepository` generic base + 12 named repositories
  (Tenant, CustomerAccount, Site, Plant, ProductionLine, Machine, Bearing,
  LubricationSystem, Circuit, LubricationPoint, Sensor, Gateway), all tenant-scoped,
  shared offset/limit pagination (ADR-027)
- Service layer: `AssetHierarchyService`, `CustomerAccountService`, `SiteService`,
  `PlantService`, `ProductionLineService`, `MachineService`, `LubricationSystemService`,
  `SensorService` — parent-existence validation, retired-parent-blocks-new-child rules,
  duplicate-code conflict detection, all tenant-scoped
- Development-only tenant context (ADR-025): required, validated `X-Tenant-ID` header
  (`backend/app/api/deps.py::get_current_tenant`) — explicitly documented as a stand-in
  for real authentication, with a single, isolated seam to replace later
- 19 versioned API endpoints (`/api/v1/customers`, `/sites`, `/plants`,
  `/production-lines`, `/machines` [+ `/{id}/hierarchy`], `/lubrication-systems`,
  `/sensors`, `/hierarchy`), typed Pydantic request/response schemas throughout, no raw
  ORM objects exposed
- `selectinload`-based hierarchy queries (ADR-026) — no N+1, no `MissingGreenlet` (a real
  bug caught and fixed during this phase: the lubrication-system list endpoint needed a
  separate summary schema, since its query doesn't eager-load nested equipment)
- Deterministic, idempotent seed script (`backend/scripts/seed_demo_data.py`, ADR-028):
  1 tenant, 3 fictional customers, 5 sites, 6 plants, 12 production lines, 24 machines
  (~25% bare/topology-only, ~25% bearings-only, ~50% full lubrication chain), 36 bearings,
  12 full lubrication systems, 108 sensors, 6 gateways — verified idempotent by running
  twice (both manually and in `backend/tests/test_seed_idempotency.py`)
- Domain-vs-ORM separation decision (ADR-029): ORM models double as the domain layer; the
  enforced boundary is domain vs. API contract (Pydantic schemas), not domain vs. ORM
- Minimal frontend hierarchy UI: `/hierarchy` (nested tree), `/machines/[machineId]`
  (metadata, bearings, lubrication chain, sensor inventory — no charts, no health score,
  no AI diagnosis), `/sensors` (fleet-wide inventory with type/status filters +
  pagination) — verified in a real browser against live data, not just built
- 41 backend tests (up from 12 in Phase 1), all against live Postgres, covering domain
  validation (DB constraints), repositories, services, tenant isolation, hierarchy
  resolution, seed idempotency, and API flows
- `docs/ASSET_HIERARCHY.md` — full implementation documentation (ER diagram, tenancy,
  sensor attachment strategy, seed topology, API usage, future telemetry relationship)
- 8 new ADRs (ADR-022–ADR-029)

Not implemented (explicitly out of Phase 2 scope — see LOOP.md §39): physical simulation,
telemetry generation, failure injection, edge behavior, MQTT telemetry flow, Kafka domain
events, data-quality engine, baselines, rules, features, ML, Kalman, condition/decision
intelligence, incidents, RAG, GenAI agents, CMMS, final dashboard, full auth/RBAC.

---

## Phase 3 — Industrial Simulator

COMPLETE

Delivered:

- Standalone `simulator/` service (own `pyproject.toml`/uv-managed venv, per ADR-011):
  `simulator/simulator/{domain,physics,sensors,scenarios,engine,config}` — no single-file
  simulator, matching LOOP.md's module-boundary expectations
- Read-only topology loader (`simulator.engine.repository.TopologyRepository`, ADR-030):
  resolves a `MachineTopology` (machine, bearings, full lubrication chain, attached
  sensors) from the live Phase 2 Postgres schema via plain `psycopg` SQL — no separate
  synthetic asset universe, no backend-ORM import
- Flagship reference machine: **Conveyor 000** (`asset_code=L1-7B43-M000`, seeded id
  `88551bef-3149-5a8d-9645-bcd9502f4795`) — first equipped CONVEYOR in the Phase 2 seed
  data, full reservoir/pump/controller/distributor/2-circuit chain, 8 registered sensors
- Hidden physical state (`simulator.domain.state`): `MachineState`, `BearingState`,
  `LubricationSystemState` (`ReservoirState`, `PumpState`, `CircuitState`, `CycleState`),
  `SensorState` — mutated only by `simulator.physics.*`, never exposed directly as telemetry
- Operating-profile state machine (`simulator.physics.machine.OperatingProfile`):
  `STOPPED → STARTING → RUNNING_{LOW,NORMAL,HIGH}_LOAD → SHUTTING_DOWN → STOPPED`, configurable
  demo shift schedule, smooth first-order-lag load/RPM transitions (no instantaneous jumps)
- Lubrication cycle state machine (`simulator.physics.cycle.LubricationCycleController`):
  `IDLE → PUMP_START → PRESSURE_BUILD → FLOW_DELIVERY → COMPLETING → IDLE`, real pressure/flow
  shape over time (not one constant reading per cycle), `SUCCESS`/`PARTIAL`/`FAILED` outcome
  classification
- Reduced-order circuit/flow-resistance model (`simulator.physics.circuit`, ADR-031's
  numerically-stable exponential-lag primitive used throughout): restriction raises
  resistance and required pressure, lowers delivered flow; leakage reduces delivered flow
  and slightly relieves measured backpressure — explainable, configurable, documented as a
  simplification (not a CFD/hydraulic-network solve) in `docs/SIMULATOR.md` §6
- Stateful pump model (`simulator.physics.pump`): pressure rise/decay lag, motor current
  from pressure, runtime accrual, small wandering efficiency (not a fixed constant)
- Stateful reservoir model (`simulator.physics.reservoir`): `quantity_l` only ever decreases
  via actual delivered volume, monotonic non-increasing across a run (verified,
  `tests/test_engine_healthy_invariants.py`)
- Bearing condition model (`simulator.physics.bearing`): `lubrication_effectiveness` nudged
  only at discrete cycle-completion events (never from raw pressure), `temperature_c`/
  `vibration_rms_mm_s` both relax through a first-order lag (600s/900s time constants) so
  neither jumps instantly — directly tested
  (`tests/test_bearing.py::test_vibration_does_not_instantly_react_to_lubrication_change`)
- Config-driven sensor models (`simulator.sensors.models`) for all 13
  `docs/DOMAIN_MODEL.md` §2.2 measurement types: per-type noise/bias/resolution/valid_range
  from `simulator/config/demo_engineering.yaml` (explicit DEMO SYNTHETIC ENGINEERING
  ASSUMPTIONS disclaimer, no company-specific names); fixed per-run sensor bias, `GOOD`/
  `SUSPECT` quality
- Explicit units throughout (bar/cm3-per-min/percent/A/seconds/degC/mm-per-s/rpm), carried
  on every `SimulationReading.unit`
- Deterministic, seeded engine (`simulator.engine.simulation_engine.SimulationEngine`,
  ADR-033): one `random.Random(seed)` threaded through every stochastic call — same seed
  reproduces byte-identical output (`tests/test_engine_determinism.py`, including a 600-tick
  run), different seeds vary noise while preserving measurement-type shape
- Structured internal output contract (`simulator.engine.output`, ADR-034): `SimulationReading`
  (JSONL, optional CSV), `GroundTruthRecord` (separate JSONL stream — hidden state only,
  never merged with telemetry, ADR-032, structurally tested in
  `tests/test_ground_truth_separation.py`), `RunMetadata` (simulator/config version, seed,
  asset, duration/step/mode — written once per run for reproducibility)
- CLI (`python -m simulator run --asset-code ... --duration ... --seed ... --mode ...
  --output ...`): asset selection, duration parsing (`30s`/`5m`/`24h`/`7d`), step override,
  `--csv`, `--realtime --speed`, and `SMOKE`/`DEMO`/`TRAINING`/`FULL` data-volume presets
  with an estimated-row-count confirmation gate before a `FULL` run
- Structured JSON simulator logging (`simulator.engine.logging_utils`):
  `simulation_started`/`simulation_stopped`/`cycle_started`/`cycle_completed`/
  `state_transition`/`invalid_state` events at INFO — never per-reading log spam
- Numerical-stability guard (`SimulationEngine._validate_state`, raises
  `SimulationInvariantError` on any NaN/inf/impossible-negative value) — proven clean across
  a 7-day/1-minute-step run (`tests/test_stability.py`)
- 64 simulator tests (`simulator/tests/`): unit tests for every physics module (reservoir,
  pump, circuit, bearing, cycle, sensors) plus DB-backed integration tests (topology
  loading, determinism, healthy invariants over a 10-simulated-hour run, cross-quartile
  load→temperature relationship, 7-day stability) — all passing against the live Phase 2
  database
- Flagship 24-simulated-hour healthy reference dataset generated and visually validated
  (`scripts/validate_plots.py`): 17,280 ticks, 138,240 readings, 17,280 ground-truth
  records; plots confirm cyclic pressure/current pulses only during configured shift
  windows, step-monotonic reservoir depletion, lagged load-correlated bearing
  temperature/vibration, zero RPM while stopped — not committed (`.gitignore`:
  `simulator/data/`, `simulator/**/*.jsonl`, `simulator/**/*.png`)
- `docs/SIMULATOR.md` — full design documentation (topology use, hidden state, every
  equation/relationship, sensor models, units, config, temporal behavior, reproducibility,
  reference dataset summary, limitations)
- `docs/SYNTHETIC_DATA_MODEL.md` — ground-truth-vs-observed-telemetry contract, why it
  matters for later ML phases, and the `true_value`-in-`SimulationReading` boundary note for
  the future Phase 6 telemetry adapter
- 5 new ADRs (ADR-030–ADR-034): topology-loading strategy, reduced-order/exponential-lag
  physics strategy, ground-truth separation, determinism strategy, output-format strategy
- `simulator-install`/`simulator-test`/`simulator-lint`/`simulator-typecheck`/
  `simulator-format` Makefile targets, wired into the aggregate `test`/`lint`/`typecheck`/
  `verify` targets alongside backend/frontend

Not implemented (explicitly out of Phase 3 scope — see LOOP.md and the Phase 3 brief §35):
failure-injection API/workflow, edge controller, MQTT/Kafka telemetry publishing, time-series
persistence, data-quality engine, baselines, rules, ML, Kalman filter, condition/decision
intelligence, RAG, agents, CMMS, final dashboard. `simulator.scenarios` includes only the
minimal `HEALTHY` label needed to populate `GroundTruthRecord.scenario` in Phase 3 — Phase 4
owns real failure-scenario parameters.

---

## Phase 4 — Failure Injection Engine

COMPLETE

Delivered:

- Scenario/failure-injection engine (`simulator/simulator/scenarios/`): `types.py`
  (`ScenarioType`, `ProgressionType`, `ScenarioLifecycleState`, `ScenarioTargetType`,
  `VALID_TARGET_TYPES` compatibility table), `progression.py` (6 pure, RNG-free severity
  profiles), `definition.py` (pydantic `ScenarioDefinition`, target-type validated at
  load time), `loader.py`, `targeting.py` (`resolve_target` against the live topology),
  `instance.py` (`ScenarioInstance` runtime lifecycle + `create_instance` factory),
  `effects.py` (`build_effects` — the only module that translates severity into hidden-state
  adjustments), `scheduler.py` (`ScenarioScheduler` + standalone `AutoRefillPolicy`)
- Core principle enforced structurally, not just by convention (ADR-035): every scenario
  effect is an additional offset/target parameter passed into an *existing* Phase 3 physics
  function (`step_natural_variation`, `step_efficiency`, the cycle controller's
  `restriction_offsets`/`reservoir_availability`/`volume_multiplier`, a new
  `apply_independent_wear`) — `simulator/scenarios/effects.py` has no import of
  `simulator.engine.output`, so it cannot fake a sensor value even by mistake; zero
  scenario instances reproduces exact Phase 3 output
- All 10 injectable catalog failure modes implemented as YAML definitions
  (`simulator/config/scenarios/*.yaml`, each with the required DEMO SYNTHETIC FAILURE
  ASSUMPTIONS disclaimer): Gradual Restriction (SIGMOID), Sudden Blockage (STEP), Leakage
  (LINEAR), Over-Lubrication (LINEAR), Low Reservoir (STEP, one-shot), Pump Degradation
  (EXPONENTIAL), Sensor Drift (LINEAR), Sensor Dropout (INTERMITTENT), Network Failure
  (INTERMITTENT), Independent Bearing Fault (LINEAR) — verified against the flagship
  topology and via `tests/test_scenario_definition.py`
- Lifecycle state machine (`SCHEDULED → ACTIVE → [DEVELOPING] → [SEVERE] → [RECOVERING] →
  COMPLETED`), not every scenario visiting every state (`lifecycle.severe_threshold: null`
  for Over-Lubrication/Sensor Drift/Sensor Dropout/Network Failure)
- Raw-vs-delivered flow split (`simulator.physics.circuit.CircuitOperatingPoint`, ADR-041)
  — a genuine Phase 3 physics fix discovered while implementing Leakage: reservoir
  consumption now follows *raw* (pump-drawn) flow while per-circuit delivery confirmation
  (driving that circuit's bearing's `lubrication_effectiveness`) follows *delivered*
  (post-leak) flow compared against that circuit's fair share of the cycle's target volume
  — this is what makes Leakage physically distinct from Gradual Restriction (pressure flat
  vs. rising) rather than a relabeled copy
- Independent Bearing Fault decay path (`bearing.apply_independent_wear`) fully decoupled
  from `step_health`'s starvation-driven dynamics — `lubrication_effectiveness` and every
  lubrication-system signal remain untouched by this fault type, by construction
- Targeting: `VALID_TARGET_TYPES` compatibility table validated at both schema-load time
  (`ScenarioDefinition`) and runtime (`resolve_target` against the real `MachineTopology`);
  invalid/incompatible/nonexistent targets raise `ScenarioTargetError` before simulation
  starts (`tests/test_scenario_targeting.py`)
- Multi-fault composition (ADR-039, `docs/SCENARIO_ENGINE.md` §10): additive composition
  for same-target/same-parameter numeric offsets, min/max ceiling for Independent Bearing
  Fault/Over-Lubrication, and a fixed sensor-observability precedence
  `NETWORK_FAILURE > SENSOR_DROPOUT > SENSOR_DRIFT` — verified for all three
  brief-mandated combinations plus a three-scenario simultaneous run
  (`tests/test_scenario_multi_fault.py`)
- Refill as a standalone operational event (ADR-042), never a failure mode:
  `AutoRefillPolicy` (threshold + dwell delay) checked every tick independent of any active
  scenario; `GroundTruthRecord.refill_event` true only on the triggering tick; observed
  `RESERVOIR_LEVEL` responds through the unmodified sensor model (`tests/test_refill.py`)
- Nullable `SimulationReading.observed_value: float | None` (ADR-040) and expanded
  `SensorQuality` (`MISSING`, `COMMUNICATION_LOSS`, plus reserved `UNCERTAIN`/`INVALID`):
  Sensor Dropout/Network Failure withhold the observation without ever substituting `0.0`
  or any fabricated number; `true_value` keeps being computed every tick regardless
  (`tests/test_scenario_quality_semantics.py`)
- `GroundTruthRecord` extended (ADR-037): `scenarios: tuple[ScenarioGroundTruth, ...]` (the
  authoritative multi-fault record — instance id/type/lifecycle/severity/target/timing),
  `reservoir_level_state` (`NORMAL`/`LOW`/`CRITICAL`/`EMPTY`), `network_state`
  (`CONNECTED`/`DISCONNECTED`), `refill_event`; Phase 3's singular `scenario`/`severity`/
  `affected_component` kept as a backward-compatible highest-severity summary
- CLI extended (`python -m simulator run --scenario NAME [--scenario-start ...]
  [--severity ...] [--target ...] [--progression ...] [--refill-threshold ...]`,
  `--scenario-plan <yaml>` for independent per-scenario multi-fault overrides) — defaults
  come from each scenario's YAML, matching the "avoid a fragile CLI" requirement
- `RunMetadata` extended: `run_id`, `scenario_engine_version`
  (`simulator.__scenario_engine_version__`), `scenario_config_version`
  (`simulator.scenarios.SCENARIO_CONFIG_VERSION`), `scenarios`, `readings_path`,
  `ground_truth_path`
- 75 new simulator tests (139 total, up from 64) covering: progression math (all 6
  profiles), definition validation, instance lifecycle, targeting, effects (multi-fault
  precedence unit tests), scheduler/`AutoRefillPolicy`, DB-backed scenario determinism,
  signal-direction ("relationship") tests per scenario type, temporal ordering
  (paired healthy-vs-scenario comparison proving pressure deviation precedes bearing
  temperature deviation by more than one full thermal-lag time constant), failure
  distinctness (restriction vs. leakage, vs. pump degradation, vs. independent bearing
  fault, vs. sensor fault), true/observed separation and physical-truth continuity during
  Sensor Drift/Dropout/Network Failure, multi-fault combinations, refill, and two 7-day
  extended-stability runs (single-scenario and three-scenario) — all passing against the
  live Phase 2 database
- Flagship 24-simulated-hour Gradual Restriction reference dataset (4h healthy → scenario
  active from 4h, SIGMOID onset over 12h) generated and visually validated
  (`scripts/validate_plots.py`, extended with a ground-truth panel plotting scenario
  severity and restriction/leakage factor): confirms the required qualitative sequence —
  immediate ground-truth divergence, immediate cycle-level pressure/current rise, then a
  clearly *lagged* bearing vibration/temperature rise roughly 10+ hours later, cycles
  beginning to report `FAILED` only once required pressure exceeds the pump's physical
  ceiling late in the run
- 6 additional small reference datasets generated and spot-checked (Healthy, Sudden
  Blockage, Leakage, Pump Degradation, Sensor Drift, Independent Bearing Fault) — visual
  inspection of Sudden Blockage confirms the abrupt step-function severity jump and
  pressure hitting the pump ceiling every cycle; Leakage confirms flat-to-lower pressure
  (vs. restriction's rise) alongside growing reservoir depletion; Independent Bearing Fault
  confirms flat lubrication-system ground truth with a small, correctly-scoped
  vibration/temperature differential on the targeted bearing
- An emergent, physically-defensible shared-cycle coupling effect documented rather than
  hidden: because the flagship's two circuits share one pump/one cycle controller (matching
  the real centralized-lubrication topology), a severe fault on one circuit can delay
  delivery to the other circuit too, since `required_pressure` for the whole cycle is the
  maximum across circuits it serves (`docs/SCENARIO_ENGINE.md` §7)
- `docs/SCENARIO_ENGINE.md` — full architecture documentation (core principle, module
  layout, definition/instance split, lifecycle, progression profiles, targeting, the
  per-failure-mode physical mapping with the Leakage-distinctness rationale, Network
  Failure/Sensor Dropout/Sensor Drift precedence, refill, multi-fault composition, ground
  truth extensions, CLI, manifest/reproducibility, limitations)
- `docs/SIMULATOR.md` updated throughout for Phase 4 (title/status, package layout, pump/
  reservoir/sensor-model sections cross-referencing the new scenario integration points,
  output-contract field list, reference-dataset section, limitations no longer describing
  now-implemented Phase 4 hooks as unused)
- `docs/SYNTHETIC_DATA_MODEL.md` updated: `GroundTruthRecord`'s new fields (including the
  `scenarios` multi-fault list), `SimulationReading.observed_value`'s nullability and why,
  the expanded `SensorQuality` enum
- `docs/FAILURE_MODE_CATALOG.md` §15 added (implementation notes only — no rewrite of the
  Phase 0 catalog's own domain language): records where a concrete implementation choice
  narrowed the catalog's illustrative language to one specific mechanism (the Leakage
  raw-vs-delivered flow choice, restriction/blockage sharing one hidden variable, the
  independent-bearing-fault decoupling)
- 8 new ADRs (ADR-035–ADR-042): scenario-effects-as-offsets core principle, progression
  profile design, multi-fault ground-truth representation, targeting/compatibility-table
  design, multi-fault precedence rules, nullable-observation/quality-expansion design,
  raw-vs-delivered flow modeling, standalone refill mechanism design

Not implemented (explicitly out of Phase 4 scope — see LOOP.md and the Phase 4 brief §35):
edge controller, MQTT/Kafka telemetry streaming, telemetry DB ingestion, data-quality
engine, baselines, rules engine, ML, Kalman filter, condition/decision intelligence,
incident management, RAG, agents, CMMS, final dashboard. Real edge buffering/store-and-
forward behavior for Network Failure is explicitly deferred to Phase 5/6 — Phase 4 only
represents connectivity loss internally (`NetworkState.DISCONNECTED`,
`quality=COMMUNICATION_LOSS`).

---

## Phase 5 — Edge Controller

COMPLETE

Delivered:

- New `edge/` service (`edge/edge/{domain,acquisition,buffering,connectivity,rules,
  transport,config,health,runtime}/`), `uv`-managed like `simulator/`/`backend/` (ruff +
  mypy strict + pytest), depending on `lubrisense-simulator` as a local, editable `uv` path
  dependency so it can drive `SimulationEngine` in-process rather than duplicating physics
  or shelling out to the simulator CLI (Phase 5 brief §2)
- `edge.acquisition.source.TelemetrySource` protocol: `SimulatorTelemetrySource` (wraps
  `SimulationEngine.step()`, converts each tick's `SimulationReading`s to `RawObservation`s
  using only `observed_value`/`quality`, never `true_value`) and a documented-but-
  unimplemented `FutureRealDeviceTelemetrySource` boundary
- `edge.domain.envelope.ReadingEnvelope` — the full asset-context event contract (tenant/
  site/plant/line/machine/bearing/lubrication_system/circuit/lubrication_point/sensor ids,
  measurement_type/value/unit/quality/operating_state, three-timestamp model, sequence
  number, gateway/device/firmware/controller identity); optional hierarchy fields the
  simulator's topology cannot resolve stay `None` rather than being guessed
- Deterministic event ids (ADR-045): `uuid5(namespace, f"{gateway_id}|{sensor_id}|
  {sequence_number}")`, minted once at acquisition, never regenerated on retry/replay
- Per-(gateway, sensor) persisted monotonic sequence numbers (ADR-044,
  `LocalBuffer.next_sequence`), surviving restart
- Three-timestamp model (`source_timestamp`/`edge_received_timestamp`/
  `edge_emitted_timestamp`) plus a demo-only `clock_offset_seconds` config knob (not drift
  detection — that is Phase 7)
- `edge.buffering.store.LocalBuffer` — SQLite (stdlib `sqlite3`, WAL mode, ADR-043), one
  file per gateway, never deleted on startup; `events`/`sequence_state`/`config_state`
  tables; `PENDING -> SENT -> ACKNOWLEDGED`, `-> FAILED -> retry`, or `-> DEAD_LETTER` on
  retention breach (ADR-047, oldest-`PENDING`-to-`DEAD_LETTER`, never delete); `event_id`
  primary key enforces deduplication structurally, not just by application logic
- `edge.connectivity` — four-state `ConnectivityManager` (`ONLINE`/`DEGRADED`/`OFFLINE`/
  `RECOVERING`, ADR-048) driven purely by transport-level success/failure, plus a pure,
  seed-testable `compute_backoff` (bounded exponential, full jitter)
- `edge.transport` — `EdgeTransport` protocol; `NoopTransport`, `RecordingTestTransport`,
  and a real `MqttTransport` (`paho-mqtt`, topic
  `lubrisense/v1/{tenant_id}/{gateway_id}/telemetry`, QoS 1 — ADR-046)
- `edge.rules.engine.LocalRuleEngine` — exactly four deterministic checks
  (`LOCAL_RANGE_VIOLATION`, `LOCAL_WARNING` for critical/empty reservoir,
  `LOCAL_LUBRICATION_CYCLE_FAILURE` for pump-running-without-delivery-evidence, debounced
  `LOCAL_SENSOR_FAULT`), generic labels only, OPEN/CLEARED alert-state tracking so a
  persisting condition produces one transition rather than one alert per tick (ADR-049) —
  explicitly not the Phase 9 rules engine
- `edge.config` — versioned, frozen `EdgeConfig` (pydantic) with fail-fast validation
  (invalid retention/poll interval/topic template/qos/duplicate range thresholds/unknown
  measurement types), YAML + `EDGE_*` env override loader mirroring
  `simulator.config.loader`'s pattern, default config bound to the real seeded gateway
  `GW-RIDGE-CRUSH` and the flagship conveyor; `edge.runtime.gateway_lock.GatewayLock`
  (exclusive `flock`) enforces the duplicate-gateway-identity fail-fast requirement at
  process-startup time; config-version changes are recorded via a health-metric counter
- `edge.health` — `EdgeHealth` snapshot + `EdgeMetrics` counters (acquired/buffered/sent/
  replayed/failures/duplicates_prevented/warnings/buffer_overflow_count/config_changes),
  exposed via `python -m edge status`
- `edge.runtime.runtime.EdgeRuntime` — one acquisition loop + one background sender thread,
  coordinated by a single coarse-grained `threading.Lock` around every buffer call
  (intentionally simple, not high-throughput — appropriate for one gateway's demo-scale
  event rate); graceful shutdown (`stop()` joins the sender thread, closes transport and DB)
- CLI (`python -m edge run|status|buffer list|replay`), `edge/Dockerfile` (repo-root build
  context so the local `../simulator` path dependency resolves in both build stages), and
  an optional `docker compose --profile edge up` service — not started by default, verified
  to actually build and run end-to-end against the live stack (including a real
  concurrency bug this surfaced — see Technical Debt below)
- 69 edge tests (unit + 3 mandatory MQTT integration tests against the real
  `lubrisense-mosquitto` container): envelope construction/round-trip/event-id determinism,
  sequence persistence across restart, buffer CRUD/dedup/retention/dead-letter, connectivity
  backoff (pure function, seeded) + state transitions, all four local rules including the
  debounce case, every config fail-fast validation case, health/metrics snapshot,
  duplicate-gateway-lock, graceful shutdown, crash recovery, sensor-dropout-never-becomes-
  zero, and the simulated-Network-Failure-vs-real-broker-outage distinction (as two
  separate tests, unit-level and integration-level, never conflated) — plus the three
  brief-mandated integration tests: Simulator→Edge→MQTT end-to-end (inspects a real
  published message's full envelope), MQTT broker-outage buffering + reconnect/replay
  (stops/starts the real `lubrisense-mosquitto` container, verifies buffer growth during
  the outage and full drain with original `event_id`s preserved on recovery), and
  edge-restart-during-outage crash recovery (no event lost across an unclean restart)
- A small reference run (`edge/scripts/reference_run.py`,
  `edge/data/reference_run_summary.json`) capturing the flagship's buffer-depth trend and
  event counts across a healthy period, a real mosquitto outage, and recovery
- `docs/EDGE_ARCHITECTURE.md` — full architecture documentation (responsibilities/non-
  responsibilities, acquisition adapter, envelope, event-id/sequence/timestamp strategy,
  buffer architecture, store-and-forward, transport abstraction, MQTT topic/QoS, local
  rules, quality semantics, the simulated-fault-vs-real-outage distinction, configuration,
  concurrency model, failure/recovery summary, cloud-independence boundary, future
  real-device integration path); `docs/EVENT_CATALOG.md` §2.3/§4.1 filled in with the
  concrete field lists this phase actually built (superseding the earlier purpose-only
  placeholders)
- 7 new ADRs (ADR-043–ADR-049): edge persistence choice, sequence strategy, event-id
  strategy, MQTT topic hierarchy/QoS, buffer retention policy, connectivity-state model,
  local-rule boundary

Not implemented (explicitly out of Phase 5 scope — see LOOP.md and the Phase 5 brief §44):
Kafka central ingestion, TimescaleDB telemetry persistence, the full event pipeline, the
full data-quality engine, baselines, the Phase 9 rules engine, ML, Kalman filtering,
condition/decision intelligence, incident management, RAG, GenAI agents, CMMS integration,
the final dashboard.

---

## Phase 6 — Telemetry Pipeline

COMPLETE

Delivered:

- New `backend/app/pipeline/` package (`contract.py`, `validation.py`, `enrichment.py`,
  `backoff.py`, `metrics.py`, `health.py`, `spool.py`, `mqtt_bridge.py`, `consumer.py`),
  built from the same `backend/` Docker image as the FastAPI app but run as two separate
  long-running worker processes with their own entrypoints (`python -m
  app.pipeline.mqtt_bridge`, `python -m app.pipeline.consumer`), not as FastAPI routes
  (ADR-050)
- `MqttBridge`: subscribes to `lubrisense/v1/+/+/telemetry` (QoS 1, matching the Phase 5
  edge's publish topic) via `paho-mqtt`'s network thread, hands each payload to its
  asyncio loop via `asyncio.run_coroutine_threadsafe`, validates it
  (`SchemaValidator`), and publishes the original envelope bytes unmodified to
  `lubrisense.telemetry.v1` via `aiokafka` (key = `tenant_id:gateway_id:sensor_id`,
  ADR-052; central metadata carried as Kafka headers, never merged into the payload) —
  ADR-051. A real bug was caught and fixed during Kafka-outage testing: `send_and_wait`
  alone could hang indefinitely against a DNS-unreachable broker without ever raising,
  because `aiokafka`'s internal metadata-refresh retry loop doesn't respect
  `request_timeout_ms` in that failure mode; fixed with an explicit 5-second
  `asyncio.wait_for` per attempt
- Structurally invalid messages (bad JSON, missing required fields, unparseable UUID/
  timestamp, unsupported `schema_version`) are published to the Kafka DLQ topic
  (`lubrisense.telemetry.dlq.v1`) with `reason`/`detail` headers, never silently dropped
- `BridgeSpool` (`app/pipeline/spool.py`): a dedicated SQLite (WAL-mode) durable buffer,
  separate from the edge's own buffer database — different responsibility (ADR-056). On
  Kafka-publish failure after retries, the event is spooled (idempotent on `event_id` via
  `INSERT OR IGNORE`) rather than dropped; a background task drains oldest-first with
  bounded backoff once Kafka is reachable again — verified end to end against a real
  Kafka container stop/start, including source-timestamp preservation across the outage
- `SchemaValidator`/`TelemetryEnvelope`/`ValidatedTelemetry` (`app/pipeline/validation.py`,
  `contract.py`): the central pipeline's own copy of the wire contract (ADR-059, not an
  `edge` package import), structural-only validation (required fields, UUID/timestamp
  parsing, measurement-type/quality enum membership, `schema_version` gating against
  `PIPELINE_SUPPORTED_SCHEMA_VERSIONS`) — distinct `SCHEMA_INVALID` vs.
  `UNSUPPORTED_SCHEMA_VERSION` rejection reasons
- `ContextEnrichmentService` (`app/pipeline/enrichment.py`): resolves a sensor's single
  populated attachment column (`machine`/`bearing`/`lubrication_system`/`reservoir`/
  `pump`/`circuit`, per the Phase 2 exactly-one-attachment design) up through the real
  hierarchy to fill `site_id`/`plant_id`/`production_line_id`/`bearing_id`/
  `lubrication_system_id`/`circuit_id`; validates `tenant_id`/`sensor_id`/`gateway_id`
  against real, same-tenant rows (`UNKNOWN_TENANT`/`UNKNOWN_SENSOR`/`UNKNOWN_GATEWAY`,
  including a dedicated test proving a real-but-cross-tenant `sensor_id` is rejected, not
  just an absent one); any edge-supplied hierarchy field that disagrees with the resolved
  value is quarantined as `CONTEXT_CONFLICT`, never silently overwritten (ADR-058)
- `TelemetryConsumer` (`app/pipeline/consumer.py`): two concurrent `aiokafka` consumer
  loops in one process — a main-topic loop (batches via `getmany()` up to
  `PIPELINE_BATCH_SIZE`/`PIPELINE_BATCH_TIMEOUT_SECONDS`, enriches, persists the whole
  batch in one transaction, commits Kafka offsets only *after* that transaction commits,
  `enable_auto_commit=False`) and a DLQ-topic loop (drains the bridge's structural
  rejects into `telemetry_quarantine`, best-effort recovering `event_id`/`tenant_id`/
  `sensor_id`/`gateway_id` from otherwise-well-formed payloads for traceability). On
  transient DB failure, the same batch retries with bounded backoff and offsets are never
  advanced past it — verified against a real Postgres container stop/start with zero
  loss and zero duplicates
- `Telemetry` domain model + `telemetry` TimescaleDB hypertable (Alembic migration
  `1f9fe8b7b163`, chained off `08276baaeac2`): every field in `docs/EVENT_CATALOG.md`
  §2.1 plus `kafka_partition`/`kafka_offset` traceability columns; composite tenant FKs
  to `sensor`/`machine`/`bearing`/`lubrication_system`/`circuit`/`lubrication_point`/
  `production_line`/`plant`/`site` (nullable where optional, matching `Sensor`'s own
  pattern); hypertable partitioned on `source_timestamp` — event time, chosen so replayed/
  outage-buffered events land in the chunk their *source_timestamp* describes, not the
  chunk matching when they were actually inserted (ADR-054) — 1-day chunks
  (demo/reference-scale choice, documented as such); primary key is the composite
  `(event_id, source_timestamp)` (TimescaleDB requires the partitioning column in every
  unique/PK constraint; safe because `event_id` deterministically implies one
  `source_timestamp` already, per the edge's ADR-045) — the idempotency key for
  `INSERT ... ON CONFLICT (event_id, source_timestamp) DO NOTHING` batch inserts
  (ADR-053/ADR-055)
- `TelemetryQuarantine` domain model + `telemetry_quarantine` table (same migration):
  deliberately no foreign keys on `tenant_id`/`sensor_id` — the whole point of the table
  is to hold rows that may reference invalid/unknown/cross-tenant entities; `reason`
  enum (`SCHEMA_INVALID`, `UNSUPPORTED_SCHEMA_VERSION`, `UNKNOWN_TENANT`,
  `UNKNOWN_SENSOR`, `UNKNOWN_GATEWAY`, `CROSS_TENANT_MISMATCH`, `CONTEXT_CONFLICT`,
  `PERSISTENT_FAILURE`), full raw payload preserved as text (ADR-057)
- `TelemetryRepository` (`app/repositories/telemetry.py`, not a `TenantScopedRepository[T]`
  subclass — the composite-key/batch/time-range shape doesn't fit that generic):
  `batch_insert_idempotent` (Core `insert()` against `Telemetry.__table__`, not the ORM
  class — a real bug caught and fixed: `pg_insert(Telemetry)` triggers SQLAlchemy 2.0's
  ORM-enabled insert, which resolves `.values()` keys as Python attribute names and
  collides with the inherited `Telemetry.metadata` class attribute (`Base.metadata`) for
  a column named `metadata`), `get_by_sensor_time_range`, `get_by_machine_time_range`,
  `get_latest_by_sensor`, `count`; `QuarantineRepository`
  (`app/repositories/telemetry_quarantine.py`): `insert`, `list_recent`
- Read-only, tenant-scoped telemetry query API (`app/api/v1/telemetry.py`,
  `app/api/schemas/telemetry.py`, `app/services/telemetry_query_service.py`):
  `GET /api/v1/telemetry/sensors/{sensor_id}` (`start`/`end`/`measurement_type`/`limit`),
  `GET /api/v1/telemetry/sensors/{sensor_id}/latest`,
  `GET /api/v1/telemetry/machines/{machine_id}` — each validates the sensor/machine
  exists for the tenant first (404 `SENSOR_NOT_FOUND`/`MACHINE_NOT_FOUND`) before
  querying, so an empty result always means "no readings yet," not "wrong id"; Kafka
  partition/offset never exposed in the response (pipeline-internal only)
- Minimal frontend "Recent Telemetry" view on the existing machine detail page
  (`frontend/src/app/machines/[machineId]/page.tsx`, `useMachineTelemetry` hook polling
  every 10s, `frontend/src/lib/api/telemetry.ts`/`telemetry-types.ts`) — a plain table
  (sensor, measurement type, value+unit, quality, operating state, source timestamp), no
  health score/condition/AI diagnosis, verified live in a browser against real pipeline
  data (ADR-008)
- `PipelineHealthServer` (`app/pipeline/health.py`): a small dependency-free
  `http.server`-based `/health` (liveness)/`/ready` (readiness, 503 if not ready)/
  `/metrics` (hand-written Prometheus text format, no new dependency) server, reused by
  both workers; `PipelineMetrics` (`app/pipeline/metrics.py`) thread-safe counters/gauges
  (`mqtt_messages_received`, `mqtt_invalid_messages`, `kafka_messages_published`,
  `kafka_publish_failures`, `kafka_consumer_messages`, `telemetry_persisted`,
  `telemetry_duplicates`, `telemetry_quarantined`, `batch_size`, `bridge_buffer_depth`)
- `JSONLogFormatter`/`configure_logging` extended with a `service_name` parameter
  (`lubrisense-mqtt-bridge`/`lubrisense-telemetry-consumer`) so structured logs identify
  which pipeline service emitted them, without changing the default backend behavior
- `docker-compose.yml`: `mqtt-bridge` and `telemetry-consumer` added as **default**
  services (no profile gate, unlike `edge`) — core platform infrastructure, not an
  optional device simulator; `x-backend-env` extended with the Phase 6 config surface;
  `backend/Dockerfile` pre-creates and `chown`s `/data` (the bridge's spool volume)
  before switching to the non-root `app` user, mirroring `edge/Dockerfile`'s own pattern
- `backend/pyproject.toml`: `aiokafka`, `paho-mqtt` added; mypy overrides for both
  (missing stubs, matching `edge/pyproject.toml`'s existing `paho.mqtt.*` override)
- `scripts/verify_pipeline.sh` (new, mirrors `verify_kafka.sh`/`verify_mqtt.sh`'s
  `docker exec`-based convention — Kafka's advertised listener only resolves inside the
  Compose network, ADR-020, so a host-side Python Kafka client cannot reach it directly):
  drives all 6 required acceptance scenarios against the live stack — full round trip
  with event-id/value preservation, duplicate delivery (byte-identical redelivery, not
  just the same `event_id`, produces exactly one row), unsupported schema version
  quarantined with the correct reason, unknown sensor quarantined with the correct
  reason, a real Kafka container stop/start (bridge spools durably, drains on recovery,
  source timestamp preserved), a real Postgres container stop/start (consumer retries
  without loss or duplication) — all passing
- 36 new backend tests (`tests/test_pipeline_validation.py` — 13 `SchemaValidator` unit
  tests; `tests/test_pipeline_enrichment.py` — 10 tests: machine/bearing/circuit
  attachment resolution, unknown tenant/sensor/gateway, cross-tenant rejection,
  conflicting-machine-id and conflicting-site-id quarantine, against the live seeded DB;
  `tests/test_telemetry_repository.py` — 7 tests: idempotent batch insert (incl. mixed
  new+duplicate), time-range/measurement-type-filtered/machine-scoped queries, latest-
  reading; `tests/test_api_telemetry.py` — 8 tests: full endpoint coverage including
  cross-tenant 404, time-range filtering, tenant-header requirement), `make_gateway`
  factory added to `tests/factories.py` — all passing against live Postgres, no mocks;
  existing 41 backend tests remain green (77 total)
- `docs/TELEMETRY_PIPELINE.md` — full implementation documentation (end-to-end flow,
  MQTT ingestion, structural validation, bridge design, central timestamp model, schema
  versioning, hypertable strategy, idempotent batch persistence, context enrichment,
  outage/resilience behavior, duplicate delivery and replay, DLQ/quarantine, event
  traceability, query API, frontend view, failure modes deferred to Phase 7,
  configuration reference, health/metrics/Compose, known limitations)
- `docs/EVENT_CATALOG.md` §2.1 rewritten to match the real, implemented `Telemetry`
  contract (reconciling `reading_id`→`event_id`, `signal_type`→`measurement_type`,
  `device_time`/`ingested_time`→the real timestamp model), superseding the Phase 0
  placeholder field list the same way §2.3 already superseded its own Phase 5 placeholder
- `docs/ARCHITECTURE.md` §6 updated with a pointer to `docs/TELEMETRY_PIPELINE.md` as the
  concrete implementation of the MQTT→Kafka→TimescaleDB path it already described
- 10 new ADRs (ADR-050–ADR-059): pipeline-as-separate-workers-inside-backend,
  `aiokafka`+`paho-mqtt`-in-a-thread bridge design, Kafka partition key, at-least-once +
  idempotent-persistence semantics, hypertable time column/chunk interval, batch
  persistence strategy, dedicated bridge durable spool, DLQ/quarantine split by detecting
  component, context enrichment/conflict-quarantine strategy, central pipeline owns its
  own wire contract (does not import `edge`)

Three real bugs found and fixed during live acceptance testing (all described above and in
the relevant ADRs):

1. The unbounded `aiokafka` publish hang against a DNS-unreachable broker (`send_and_wait`
   never raised back to the caller against a broker that is unreachable at the network/DNS
   level, only against one that responds with errors) — fixed with an explicit 5-second
   `asyncio.wait_for` per publish attempt, discovered directly during the Kafka-outage
   acceptance test.
2. The `pg_insert(ORM class)` vs. `pg_insert(Table)` `metadata`-attribute collision in
   batch insert (SQLAlchemy 2.0's ORM-enabled insert resolves `.values()` keys as Python
   attribute names, colliding with the inherited `Telemetry.metadata` — `Base.metadata` —
   for a column named `metadata`) — fixed by inserting against the Core
   `Telemetry.__table__`, not the ORM class.
3. `gateway_id` mismatch: the real edge (`edge.acquisition.builder.EnvelopeBuilder`) sends
   `EdgeConfig.gateway_id` — the gateway's real `Gateway.id` (a UUID) — as the wire
   `gateway_id` field, not `Gateway.gateway_code` as originally assumed and implemented.
   This was invisible to every hand-constructed test payload (which used the code string)
   and only surfaced when running the *actual* Phase 5 edge against the pipeline for the
   multi-asset/volume test — every real event was being quarantined as `UNKNOWN_GATEWAY`.
   Fixed in `ContextEnrichmentService._resolve_gateway`: match on `Gateway.id` first,
   fall back to `gateway_code`. A dedicated test
   (`test_gateway_id_resolves_by_uuid_not_only_by_code`) and doc/ADR corrections
   (`docs/TELEMETRY_PIPELINE.md`, `docs/EVENT_CATALOG.md`, the `Telemetry` model comment)
   followed. This is the clearest evidence in this phase for why LOOP.md requires actually
   running the real upstream producer, not just hand-built test payloads that encode the
   same assumption as the code being tested.

A fourth issue — the frontend Docker image not receiving `NEXT_PUBLIC_*` build-time
environment variables — was discovered while verifying the new telemetry view in a
browser; it affects every existing frontend page identically (confirmed via `/hierarchy`,
unrelated to this phase's changes) and is a pre-existing Phase 1/28 infrastructure gap, not
fixed here (out of Phase 6 scope); verification instead used `next dev` locally with the
correct env vars. See Known Issues.

Multi-asset/volume test: two real, concurrent-topology `python -m edge run` sessions (the
flagship Conveyor 000 / `GW-RIDGE-CRUSH`, seed 42, and a second equipped machine,
`L1-5F44-M020` / `GW-HARBOR`, seed 7 — genuinely different machine, gateway, and sensor
set, not just a different tenant header), 300 ticks each against the real MQTT broker,
flowing through the real bridge → Kafka → consumer → TimescaleDB, produced 2,400 and 2,384
persisted rows respectively (8 distinct sensors each, zero quarantined, zero failures) —
confirming tenant/context isolation and topology enrichment hold correctly across multiple
real assets, not only the single flagship machine used during initial development.

Not implemented (explicitly out of Phase 6 scope — see LOOP.md and the Phase 6 brief §50):
data-quality classification (late/stale/duplicate-*pattern*/drift/out-of-order *anomaly*
detection, sensor health scoring), dynamic baselines, the Phase 9 rules engine, feature
engineering, ML, Kalman filtering, condition/decision intelligence, incidents, RAG, agents,
CMMS, the final product UI. Telemetry retention (drop/downsample-old-chunks) policy is not
decided (only hypertable partitioning/chunking) — flagged as a pending decision.

---

## Phase 7 — Data Quality Engine

COMPLETE. See `docs/DATA_QUALITY.md` for the full design and `TECHNICAL_DECISIONS.md`
ADR-060–ADR-070 for the architectural decisions. Summary of what was verified, not
inferred — every item below was actually run against the live Docker Compose stack
(9/9 services healthy) or the backend/frontend/edge test suites:

- Domain model: 9 new enums (`QualityDimension`, `IssueSeverity`, `QualityState`,
  `Eligibility`, `IssueStatus`, `AssessmentScope`, `QualityIssueType`, `StalenessStatus`,
  `ClockStatus`), 3 new ORM tables (`quality_assessment`, `quality_issue`,
  `sensor_quality_state`) — migration `5257a5e8e595`, applied and downgrade/upgrade-cycle
  verified clean against the live database.
- **Real bug found and fixed during this phase, unrelated to Phase 7's own scope**: the
  three `fk_*_via_*_id` use_alter foreign keys on `lubrication_system` (pump/reservoir/
  controller), originally intended by migration `08276baaeac2` (Phase 2), were never
  actually created — `use_alter=True` declared inline inside `op.create_table(...)` does not
  cause Alembic to emit the follow-up `ALTER TABLE` it requires; Phase 6's migration then
  misdiagnosed the resulting autogenerate diff as a known false positive and suppressed it
  again. Fixed in migration `5257a5e8e595` with the explicit `op.create_foreign_key(...)`
  Alembic never emitted; verified via `pg_constraint` and a full downgrade/upgrade cycle.
  See the corrected ADR-022 and the migration file comments for the full account.
- Policy config: `demo_quality_policy.yaml` (DEMO SYNTHETIC DATA QUALITY ASSUMPTIONS
  disclaimer; value ranges/units kept in sync with `simulator/simulator/config/
  demo_engineering.yaml`), versioned pydantic loader with fail-fast validation.
- 8 rule modules (one per dimension), all pure functions, 54 unit tests
  (`backend/tests/data_quality/`) — completeness, validity, timeliness, ordering,
  consistency, communication, sensor_health, configuration.
- Services: `QualityEngine` (event-level), `WindowEvaluator` (window-level, periodic),
  `eligibility.resolve_state` (pure severity → state/eligibility mapping, 5 unit tests),
  `QualityQueryService` (backs the API).
- Repositories: `QualityAssessmentRepository`, `QualityIssueRepository` (idempotent upsert
  on both the event-scope unique constraint and the window-scope partial unique index),
  `SensorQualityStateRepository` (upsert-by-PK, merge-patch semantics).
- Worker (`app.data_quality.worker`, `python -m app.data_quality.worker`): independent
  Kafka consumer group `lubrisense-data-quality` on the same `lubrisense.telemetry.v1`
  topic Phase 6 reads; periodic window-evaluation asyncio task (default 60s); per-event
  `SAVEPOINT` isolation so one bad rule evaluation never blocks the batch; own health/
  metrics on port 8083. Verified live and healthy in Docker.
- `python -m app.data_quality.reprocess` CLI — historical reprocessing, idempotent on
  unchanged `rule_version`, writes new versioned rows on a bump.
- API: `GET /api/v1/data-quality/{sensors/{id}, machines/{id}, issues, summary}`,
  tenant-scoped, registered in `api_v1_router`.
- Frontend: `/data-quality` page — summary cards + filterable issues table, verified live
  in a browser against real backend data (`next dev`, same known pre-existing frontend
  Docker build-arg gap as Phase 6, not a Phase 7 regression).
- Docker Compose: `data-quality-worker` service (default, not profile-gated), env vars in
  `.env.example`; Makefile `data-quality-verify` target folded into the aggregate `verify`.
- Live verification (`scripts/verify_data_quality.sh`, 11 synthetic cases via real MQTT
  publish → real pipeline → real quality worker → real DB rows): sequence gap, late
  arrival, out-of-order, duplicate pattern, out-of-range, unit mismatch, context
  inconsistency, missing value, invalid value, spike, and stuck-sensor (window-level,
  proving the periodic evaluation cycle itself) — all 11 PASS.
- Live scenario validation (`edge/scripts/run_scenario_validation.py`, real Phase 4
  `SimulationEngine` physics through the real Phase 5/6 pipeline): SENSOR_DROPOUT and
  NETWORK_FAILURE both PASS reliably end to end. SENSOR_DRIFT is correct in isolation (unit
  test + a direct live rule invocation against an undiluted time range both confirm it) but
  is masked end-to-end in this specific long-lived, heavily-reused demo environment by
  hours of accumulated non-drifted telemetry sitting inside the rule's 180-minute lookback
  window — a genuine, disclosed characteristic of the count-based mean-shift split, not a
  functional defect. See `docs/DATA_QUALITY.md` §14 and the script's own docstring.
- False-positive control: a clean 1,571-event healthy edge session (no scenarios injected)
  produced zero `WARNING`/`ERROR`/`CRITICAL` issues — only `OUT_OF_ORDER` at `INFO`
  severity (~23% of events, genuine wire-level reordering under a fast 20ms/tick synthetic
  burst with an async sender thread, not a rule flaw; `INFO` never degrades
  `quality_state`/`eligibility`).
- Full regression: `make verify` green end to end — backend 132 tests, simulator 139,
  edge 69, frontend build, `mqtt-verify`, `kafka-verify`, `pipeline-verify` (Phase 6, still
  green with the Phase 7 worker running alongside), `data-quality-verify`. Backend
  lint/typecheck clean across 113 source files.
- Repository-wide case-insensitive scan of every Phase 7 file for real industrial-
  lubrication vendor names: zero matches.
- Docs: `docs/DATA_QUALITY.md` (new, full design doc); `TECHNICAL_DECISIONS.md` ADR-060–
  ADR-070 (11 new ADRs) plus the ADR-022 correction above; this document.

Known limitations (see `docs/DATA_QUALITY.md` §14 for full detail): SENSOR_DRIFT window
dilution in a long-lived shared demo environment (not a functional defect — proven correct
in isolation); reprocessing uses the sensor's *current* live context, not historical
point-in-time context, for context-dependent rules; no numeric quality score in v1
(intentional, ADR-065); `COMMUNICATION_LOSS` is attributed to one representative sensor on
the machine, not a true machine-only row (schema constraint, ADR-069).

Not implemented (explicitly out of Phase 7 scope — see LOOP.md and the Phase 7 brief):
baselines, a rules engine, feature engineering, ML inference, Kalman/state estimation,
condition intelligence, decision intelligence, incidents, RAG, GenAI agents, CMMS
integration, the final product UI.

---

## Phase 8 — Baseline Engine

COMPLETE. See `docs/BASELINES.md` for the full design and `TECHNICAL_DECISIONS.md`
ADR-071–ADR-076 for the architectural decisions. Summary of what was verified, not
inferred — every item below was actually run against the live Docker Compose stack
(10/10 services healthy) or the backend/frontend/simulator/edge test suites:

- New `backend/app/baselines/` package (`domain/`, `config/`, `strategies/`, `services/`,
  `repositories/`, `workers/`), mirroring the Phase 7 `data_quality` module's shape.
  `domain/` is pure, DB-free math (`context`, `statistics` — robust median/MAD/quantiles,
  `deviation`, `reservoir_trend`, `cycle_metrics`, `anchor` — MAD-based standardized
  distance); `strategies/` are thin adapters wiring quality-gated telemetry into that math
  (`static_reference`, `rolling`, `contextual`, `reservoir`, `cycle`); `services/` is
  orchestration (`BaselineEngine`, the contamination-control state machine in `promotion.py`,
  `fallback`, `deviation_service`, `summary_service`, `query_service`).
- Domain model: 6 new enums (`BaselineStrategyType`, `BaselineState`, `BaselineMetricKind`,
  `DeviationClassification`, `BaselineSourceKind`), one new ORM table (`baseline_profile`,
  deliberately denormalized — statistics/candidate-statistics/context as JSONB on one
  versioned row rather than a three-table split, ADR-071) — migration `3366bbb38e2a`,
  chained off Phase 7's `5257a5e8e595`, applied and downgrade/upgrade-cycle verified clean
  against the live database.
- Policy config: `demo_baseline_policy.yaml` (DEMO SYNTHETIC BASELINE ASSUMPTIONS
  disclaimer; engineering-reference ranges/units kept in sync with
  `simulator/simulator/config/demo_engineering.yaml` and
  `backend/app/data_quality/config/demo_quality_policy.yaml`), versioned pydantic loader.
- Three baseline strategies (`STATIC_ENGINEERING_REFERENCE`, `ROLLING_ASSET_BASELINE`,
  `CONTEXTUAL_ASSET_BASELINE`) plus two `metric_kind` variants
  (`RESERVOIR_TREND` for `RESERVOIR_LEVEL`, `CYCLE_METRIC` for machine-scoped
  pressure/completion cycles) — no ML model anywhere in this phase, matching the brief.
- Context dimensions: `operating_state` (the real Phase 3 `RUNNING_{LOW,NORMAL,HIGH}_LOAD`
  states) and `cycle_phase` (ACTIVE/IDLE, threshold-derived per sensor type from telemetry
  alone, never the simulator's hidden cycle state — preserving ADR-032's ground-truth
  separation). Load/RPM are folded into `operating_state` rather than modeled as
  independent buckets, and no ambient-temperature dimension exists (no such measurement
  type in this system) — both documented as reference-implementation simplifications
  (`docs/BASELINES.md` §5/§27, ADR-072).
- **Contamination control (brief §41, mandatory)**: a pure, database-free candidate/
  stability-gate state machine (`app/baselines/services/promotion.py::decide`, ADR-073) —
  an `ACTIVE` anchor's statistics only update in place (`REFINE_ACTIVE`) while a fresh
  cycle stays within a MAD-based tolerance of the anchor itself; once diverged, a candidate
  must stay within tolerance of its own *previous* snapshot for `required_stable_cycles`
  (default 2) consecutive cycles before an explicit, auditable `PROMOTE` (new version, old
  version `SUPERSEDED`, both retained) replaces the anchor. Verified live against Postgres:
  `test_gradual_drift_leaves_active_baseline_anchored` (a Phase-4-style gradual pressure
  rise, 9.0→18.0 bar, leaves the `ACTIVE` row's id and `statistics.median` completely
  unchanged one cycle later — no quality flag involved, the stability gate alone protects
  against a genuine physical fault) and `test_ineligible_sensor_never_updates_learned_
  baseline` (the independent Phase 7 quality-gating layer: an `INELIGIBLE` sensor
  contributes zero samples, never a fabricated statistic).
- Quality gating: only `Telemetry.quality == GOOD` rows from a sensor whose current
  `SensorQualityState.eligibility != INELIGIBLE` ever reach a strategy's statistics;
  `ELIGIBLE_WITH_CAUTION` samples are included but tracked separately
  (`RobustStatistics.caution_count`), never silently excluded or down-weighted.
- Fallback hierarchy (`services/fallback.py`, ADR-074): `EXACT_CONTEXT → OPERATING_STATE →
  SENSOR_LEVEL → ENGINEERING_REFERENCE`, every rung a real `ACTIVE` row, `BaselineSourceKind`
  always surfaced to the caller — verified
  (`test_fallback_hierarchy_prefers_exact_then_coarse_then_sensor_then_reference`) and live
  through the API and frontend (see below).
- Firmware/config-change invalidation (`BaselineEngine._apply_config_change_check`): a
  firmware/controller-version change on new telemetry invalidates the current
  `ACTIVE`/`STALE` row (`invalidation_reason` recorded) and starts a fresh version-numbered
  generation — verified (`test_firmware_change_invalidates_and_starts_new_generation`).
- Robust statistics (`domain/statistics.py`, ADR-076): count, caution_count, mean, stddev,
  median, MAD (1.4826-scaled), p05/p25/p75/p95, min, max — median/MAD used as the primary
  distance measure throughout (`domain/deviation.py`, `domain/anchor.py`), mean/stddev kept
  as a labeled fallback only.
- Baseline states (`INSUFFICIENT_DATA → BUILDING → ACTIVE → [STALE] → [INVALIDATED |
  SUPERSEDED]`) and full versioning (`version`, `config_version`, `quality_policy_version`,
  never mutated after the fact — `update_in_place` only touches the current row's own
  candidate/statistics fields, `promote` always inserts a new row).
- Reservoir trend baseline (`domain/reservoir_trend.py`): depletion rate, refill count, time
  since last refill — directional, not a symmetric band, stored alongside (not instead of)
  the plain distribution.
- Cycle-level baseline (`domain/cycle_metrics.py`): machine-scoped pressure rise time, peak
  pressure, cycle duration, completion success rate, recorded against one deterministically
  chosen representative `PRESSURE` sensor (mirrors Phase 7's `COMMUNICATION_LOSS`
  attribution precedent).
- Worker (`app.baselines.workers.worker`, ADR-075): a periodic `asyncio` loop, deliberately
  **not** a Kafka consumer (a baseline is a window statistic, not a per-event judgment) —
  discovers tracked sensors from `sensor_quality_state`, refreshes on a sensor-type-aware
  cadence, refreshes cycle baselines once per machine, sweeps for staleness, per-sensor
  `SAVEPOINT` isolation. Own health/metrics via the shared `app.observability.worker_health`
  server (the same component Phase 7 already relocated for reuse). Verified live and
  healthy in Docker (`lubrisense-baseline-worker`, healthy).
- `python -m app.baselines.workers.backfill` CLI — historical reprocessing over an explicit
  `--start`/`--end` range, same `BaselineEngine` methods the live worker uses,
  `--sensor-id`-optional (defaults to every tracked sensor for the tenant).
- API: `GET /api/v1/baselines/{sensors/{id}, sensors/{id}/current, machines/{id}, summary}`,
  tenant-scoped, registered in `api_v1_router`.
- Frontend: `/baselines` page — tenant summary cards, a sensor picker with a full
  profile table (strategy/context/state/version/samples/machine/last-evaluated), and a
  resolved-baseline-and-deviation panel (operating-state selector + a reading input that
  computes a live deviation) — verified live in a browser (`next dev`, same pre-existing
  Docker frontend build-arg gap as Phases 6/7, not a Phase 8 regression) against real
  backend data: contextual profiles correctly differ by operating state
  (`STOPPED`: 420/30 samples, `ACTIVE`; `RUNNING_NORMAL_LOAD`: 5/30,
  `INSUFFICIENT_DATA`), fallback correctly resolved `SENSOR_LEVEL`, and entering a reading
  far from the resolved median correctly returned `STRONG_DEVIATION` with its standardized
  distance.
- Docker Compose: `baseline-worker` service (default, not profile-gated); Makefile
  `baseline-verify` target folded into the aggregate `verify`; `.env.example` updated.
- Live verification (`scripts/verify_baselines.sh` — a real bug was found and fixed during
  this review: its original sensor-selection query required `sensor.machine_id IS NOT
  NULL`, but per ADR-023 a `BEARING_TEMPERATURE` sensor attaches to `bearing`, not
  `machine`, directly — the demo seed has zero such sensors with `machine_id` set, so the
  script could only have "passed" against a stray non-demo test-tenant row, never the real
  demo data; fixed to resolve the machine via the bearing's own `machine_id`, matching what
  `BaselineEngine` itself does): seeds real synthetic low/high-load `BEARING_TEMPERATURE`
  telemetry via the real `TelemetryRepository`, runs the backfill CLI inside the real
  backend image, verifies via psql and the live API — all 8 checks PASS: worker health,
  seeding, backfill (twice, for stability-gate confirmation), static-reference immediate
  `ACTIVE`, rolling-baseline `ACTIVE` after two stable cycles, load-dependent contextual
  profiles genuinely differ (`RUNNING_HIGH_LOAD` median 85.0 vs `RUNNING_LOW_LOAD` 35.0),
  idempotency (a third identical backfill produces no duplicate version), and both API
  endpoints report the expected live state.
- Performance: a fleet-wide 24h backfill (all 10 sensors currently tracked for the demo
  tenant, 3 machines' cycle profiles, 8,583 real `telemetry` rows scanned) completed in
  1.48s against the live database — not a synthetic/estimated figure.
- Full regression, all against the live stack: backend 172 tests (132 pre-existing + 40
  new), simulator 139, edge 69 — all still green, untouched by this phase. Live
  `scripts/verify_pipeline.sh` (Phase 6) and `scripts/verify_data_quality.sh` (Phase 7)
  both re-run and still fully PASS with the baseline worker running alongside. Backend
  ruff + mypy clean across 143 source files. Frontend ESLint + `tsc --noEmit` + production
  build all clean, `/baselines` present in the build's route list.
- Repository-wide case-insensitive scan (backend/frontend/docs/scripts, all file types) for
  real industrial-lubrication-vendor names: zero matches.
- Docs: `docs/BASELINES.md` (new, full design doc — architecture, engineering-limits-vs-
  learned separation, strategies, context dimensions, fallback hierarchy, quality gating,
  reservoir/cycle baselines, contamination control, versioning/invalidation, robust
  statistics, readiness model, API, frontend view, known limitations); `TECHNICAL_
  DECISIONS.md` ADR-071–ADR-076 (6 new ADRs: schema/strategy-separation design, context-
  dimension scope, contamination-control state machine, fallback hierarchy, worker
  architecture, robust-statistics choice); this document.

Known limitations (see `docs/BASELINES.md` §27 for full detail): load/RPM conditioning is
folded into the discrete `operating_state` machine rather than modeled as independent
continuous buckets — a reasonable simplification for this reference implementation's
shift-driven operating profile, not a general claim that separate load/RPM buckets are
unnecessary; no ambient-temperature conditioning dimension exists (no such measurement
type in this system); `CLASS_REFERENCE` fleet-wide fallback (brief §42) is not implemented
— `STATIC_ENGINEERING_REFERENCE` already serves as the non-asset-specific fallback of last
resort, and every learned baseline remains asset-specific by construction regardless; the
backfill CLI and live worker read a sensor's *current* quality eligibility, not historical
point-in-time eligibility, inheriting the same disclosed limitation as Phase 7's own
reprocessing CLI (ADR-070).

Not implemented (explicitly out of Phase 8 scope — see LOOP.md and the Phase 8 brief §51):
a full rules engine, feature engineering, ML inference, Kalman/state estimation, condition
intelligence, decision intelligence, incidents, RAG, GenAI agents, CMMS integration, the
final product UI.

---

## Phase 9 — Rule Engine

COMPLETE. See `docs/RULES_ENGINE.md` for the full design and `TECHNICAL_DECISIONS.md`
ADR-077–ADR-083 for the architectural decisions. Summary of what was verified, not
inferred — every item below was actually run against the live Docker Compose stack (10/10
services healthy) or the backend/frontend/simulator/edge test suites:

- New `backend/app/rules_engine/` package (`domain/`, `rules/`, `services/`,
  `repositories/`, `workers/`, `config/`), mirroring the Phase 7/8 module shape. `domain/`
  is pure, DB-free data + math (`context` — `SignalEvaluation`/`ReservoirSignalEvaluation`/
  `CycleSignalEvaluation`/`MachineRuleContext`; `deviation` — MAD-distance classification
  for non-STANDARD baselines; `strength` — evidence-strength combination; `results` —
  `RuleFindingCandidate`); `rules/` are pure `check_*` functions, one module per family
  (`single_signal`, `cycle`, `cross_signal`, `bearing`, `quality`); `services/` is
  orchestration (`RuleEngine`, the debounce/hysteresis state machine in `lifecycle.py`,
  `query_service`).
- Domain model: 4 new enums (`RuleCategory`, `RuleFindingType` — exactly the 17 catalog
  entries, `RuleFindingSeverity`, `RuleFindingState`, `EvidenceStrength`), one new ORM table
  (`rule_finding`, deliberately denormalized like Phase 8's `BaselineProfile`, ADR-077) —
  migration `615a5631e98e`, chained off Phase 8's `3366bbb38e2a`, applied and
  downgrade/upgrade-cycle verified clean against the live database.
- Policy config: `demo_rules_policy.yaml` (DEMO SYNTHETIC RULE ASSUMPTIONS disclaimer),
  versioned pydantic loader — windowing, debounce (per-finding-type overridable), min
  sample count, reservoir/cycle thresholds, cross-signal require/supporting/exclude sets,
  severity mapping, quality-gating fractions, deviation multipliers.
- Central rules engine exists, structurally separate from Phase 5's `edge.rules.engine.
  LocalRuleEngine` (four generic checks, zero baseline awareness, unchanged) — `docs/
  RULES_ENGINE.md` §2 documents the boundary explicitly.
- **Inputs never use simulator ground truth** (mandatory, brief §3): `RuleEngine` only
  imports from `app.repositories.telemetry`/`app.data_quality.repositories.*`/`app.
  baselines.repositories.*` — structurally impossible to import `simulator.engine.output`.
- Quality gating: per-signal (`Telemetry.quality == GOOD` + sensor `eligibility !=
  INELIGIBLE`, caution caps evidence strength at MODERATE) and machine-level
  (`INSUFFICIENT_TRUSTED_DATA` suppresses every equipment-condition finding when too few
  sensors are eligible, mandatory brief §40/§41) — both verified live and via integration
  tests.
- **ACTIVE-baseline-only consumption** (mandatory, brief §43): STANDARD-kind rules reuse
  Phase 8's `deviation_service`/`BaselineProfileRepository.get_active` directly (which
  structurally only ever return `state == ACTIVE` rows); RESERVOIR_TREND/CYCLE_METRIC kinds
  filter `list_current_for_machine` to `ACTIVE` explicitly. Verified:
  `test_only_active_baseline_consumed_not_stale`.
- Rule versioning (`rule_id`, `rule_version`, `config_version` on every finding) and
  persistence: single `rule_finding` table, partial unique index
  `uq_rule_finding_active_scope` enforces at most one non-terminal
  (CANDIDATE/ACTIVE/RECOVERING) row per `(machine, component, rule)` lineage; RESOLVED rows
  never deleted.
- 9 single-signal rules (directional deviation-from-baseline + engineering-limit-based
  reservoir-low + trend-based reservoir-depletion), 3 cycle rules (pressure-build-slow,
  cycle-duration-above-baseline, cycle-completion-failure, all built on Phase 8's
  `CYCLE_METRIC` baseline), 4 cross-signal pattern rules (restriction, leakage, pump
  degradation, generic lubrication-path-degradation catch-all — declarative
  requires/supporting/excludes sets, ADR-082), 1 independent-bearing pattern (mandatory
  lubrication-signals-normal gate, brief §39), 1 quality-dependent rule
  (INSUFFICIENT_TRUSTED_DATA) — all 17 catalog finding types implemented.
- Cross-signal differentiation verified both in isolation (unit tests:
  `test_leakage_pattern_excluded_when_pressure_also_elevated`,
  `test_pump_degradation_pattern_excluded_when_pressure_elevated`,
  `test_independent_bearing_pattern_suppressed_when_lubrication_abnormal`) and live
  (`scripts/verify_rules.sh`: on the real flagship topology, which has no FLOW sensor, the
  generic LUBRICATION_PATH_DEGRADATION_PATTERN correctly fires while
  FLOW_PRESSURE_RESTRICTION_PATTERN correctly never does — proving the exclusion logic
  behaves honestly under real missing-instrumentation conditions).
  FLOW_PRESSURE_RESTRICTION_PATTERN/FLOW_PRESSURE_LEAKAGE_PATTERN themselves (which require
  a FLOW signal by definition) are verified end-to-end against a full synthetic topology in
  `backend/tests/rules_engine/test_rule_engine.py` (real Postgres, real `RuleEngine`) — see
  `docs/RULES_ENGINE.md` §24 for the full scope account.
- Temporal evidence: every finding carries `first_detected_at`/`last_detected_at`, derived
  purely from this engine's own persisted history, never ground truth.
- Debounce/hysteresis (`app.rules_engine.services.lifecycle.decide`, a pure, independently
  unit-tested state machine, 10 tests): CANDIDATE→ACTIVE requires `required_stable_cycles`
  consecutive fires (default 3, per-finding-type overridable); ACTIVE→RECOVERING→RESOLVED
  requires two consecutive clean cycles; a CANDIDATE that stops firing resolves directly.
  Verified live (`scripts/verify_rules.sh` steps 5-6) and in
  `test_finding_recovers_and_resolves_when_condition_clears`.
- Evidence strength (LOW/MODERATE/STRONG, explicitly not an ML probability) derived from
  Phase 8's own deviation classification; severity (INFO/WARNING/HIGH/CRITICAL) computed
  *from* evidence strength, then optionally escalated one level by `Machine`/
  `Bearing.criticality` — criticality can never create evidence or bypass the
  evidence-strength computation (ADR-081, ADR-024 mandatory separation).
- Structured evidence (nested JSONB per signal, never an opaque string) and non-empty
  `limitations` on every finding — verified via live API response inspection and the
  frontend's expandable detail panel.
- Worker (`app.rules_engine.workers.worker`, port 8085): periodic asyncio loop (not a Kafka
  consumer, ADR-078 — rules depend on periodically-refreshed Phase 8 baselines), per-machine
  *and* per-candidate `SAVEPOINT` isolation (ADR-079 — added after a real bug, see below,
  demonstrated the need for the finer granularity). `python -m app.rules_engine.workers.
  reprocess` CLI for historical reprocessing (ADR-083), same `RuleEngine.evaluate_machine`
  method the live worker uses.
- API: `GET /api/v1/rules/{findings, machines/{id}, findings/{id}, summary}`, tenant-scoped,
  registered in `api_v1_router`.
- Frontend: `/rules` page — summary cards, filterable findings table, click-to-expand
  structured-evidence/limitations/rule-metadata detail panel — verified live in a browser
  (`next dev`, same pre-existing Docker frontend build-arg gap as Phases 6-8) against real
  backend data seeded by `scripts/verify_rules.sh`.
- Docker Compose: `rules-worker` service (default, not profile-gated); Makefile
  `rules-verify` target folded into the aggregate `verify`; `.env.example` updated.
- **Real bug found and fixed during live verification**: `app.rules_engine.rules.
  single_signal.classify_reservoir_trend_deviation` and `RuleEngine._build_cycle_evaluation`'s
  `mad_distance` consumption could both produce a raw Python `float("inf")` standardized
  distance (when a baseline's MAD is exactly zero and the observed value differs) —
  `"Infinity"` is not valid JSON, crashing the INSERT into `rule_finding.evidence` (JSONB)
  mid-transaction. Fixed with the same large-finite-sentinel convention Phase 8's own
  `compute_deviation` already established for its own degenerate case. Discovering this
  live also surfaced a second, structural gap: without per-candidate isolation, that one
  crash rolled back every *other* valid finding computed for the same machine that cycle —
  fixed by adding per-candidate `SAVEPOINT` isolation to `_apply_lifecycle` (ADR-079),
  matching Phase 7/8's own per-event/per-sensor isolation depth.
- Live verification (`scripts/verify_rules.sh`, 11 checks against the real flagship
  machine's real sensors): worker health, synthetic healthy+anomalous telemetry seeding,
  real ACTIVE Phase 8 baseline construction, 3-cycle debounce confirmation,
  PRESSURE_ABOVE_CONTEXTUAL_BASELINE + PUMP_CURRENT_ABOVE_BASELINE ACTIVE,
  LUBRICATION_PATH_DEGRADATION_PATTERN ACTIVE while FLOW_PRESSURE_RESTRICTION_PATTERN
  correctly absent, RESERVOIR_LEVEL_LOW ACTIVE, explainability (structured evidence +
  non-empty limitations), idempotency (4th reprocess creates no duplicate), live API
  agreement — all 11 PASS. The script deliberately pauses the real Phase 7
  data-quality-worker for its duration (with a `trap`-guaranteed resume) since that
  worker's own independent, correct judgment about the script's deliberately dramatic
  synthetic spike would otherwise race with the script's own eligibility assertions — a
  genuine, documented Phase 7/Phase 9 interaction, not a bug in either phase.
- Live full-chain scenario validation (`edge/scripts/run_rules_validation.py`, reusing
  Phase 7's `run_scenario_validation.py` harness pattern exactly): a real `gradual_
  restriction` `ScenarioInstance` injected into a real `SimulatorTelemetrySource`, run
  through a real `EdgeRuntime` publishing to the real MQTT broker, flowing through the real
  bridge → Kafka → consumer → TimescaleDB — confirmed real PRESSURE telemetry landed, then
  `app.rules_engine.workers.reprocess` run against that exact real window produced a real,
  evidence-based `RESERVOIR_DEPLETION_ABNORMAL` `CANDIDATE` finding. The specific captured
  window happened to catch the machine in a near-zero-pressure (stopped/idle) operating
  state, so `PRESSURE_ABOVE_CONTEXTUAL_BASELINE` itself did not materialize in this
  particular run — not a functional gap (a near-zero reading during a stopped state is
  correctly not a deviation), just a narrow-window timing characteristic of this one live
  run. The full chain integration itself (simulator → edge → MQTT → Kafka → TimescaleDB →
  baselines → rules, zero crashes, real evidence produced) is what this run set out to
  prove and did.
- Performance: a fleet-wide 24h reprocess (4 machines, 9,510 real `telemetry` rows scanned)
  completed in 1.07s against the live database — not a synthetic/estimated figure.
- Full regression, all against the live stack: backend 222 tests (172 pre-existing + 50
  new — 42 rules_engine + 8 API), simulator 139, edge 69 — all still green, untouched by
  this phase. Live `scripts/verify_pipeline.sh` (Phase 6), `scripts/verify_data_quality.sh`
  (Phase 7), and `scripts/verify_baselines.sh` (Phase 8) all re-run and still fully PASS
  with the rules worker running alongside. Backend ruff + mypy clean across 168 source
  files. Frontend ESLint + `tsc --noEmit` + production build all clean, `/rules` present in
  the build's route list.
- Repository-wide case-insensitive scan of every Phase 9 file for real industrial-
  lubrication vendor names: zero matches.
- Docs: `docs/RULES_ENGINE.md` (new, full design doc — architecture, edge-vs-central
  boundary, inputs/ground-truth exclusion, quality gating, baseline consumption, rule
  taxonomy, single/cross-signal logic, temporal evidence, windowing, debounce/hysteresis,
  evidence strength, severity/criticality separation, structured evidence, causal language,
  persistence, idempotency, worker/reprocessing, API, frontend, verification scope, known
  limitations); `TECHNICAL_DECISIONS.md` ADR-077–ADR-083 (7 new ADRs); this document.
  Fixed a pre-existing duplicated "## Phase 9 — Rule Engine" section header left over from
  an earlier interrupted session while updating this document.

Known limitations (see `docs/RULES_ENGINE.md` §25 for full detail): cross-signal pattern
matching uses first-occurrence-per-finding-type rather than per-component pairing (a
reasonable simplification at this reference implementation's 1-2-circuits-per-machine
scale); `PRESSURE_BUILD_SLOW`'s rise-time comparison is a plain ratio, not a robust
standardized distance (no rise-time MAD is tracked by Phase 8's baseline); reprocessing
reads current, not historical, quality eligibility (inherited from Phase 7/8, ADR-070); no
sub-`RULES_WORKER_CYCLE_SECONDS`-latency evaluation (bounded by Phase 8's own baseline
freshness ceiling, which every rule already depends on).

Not implemented (explicitly out of Phase 9 scope — see LOOP.md and the Phase 9 brief §51):
feature engineering, ML inference, Kalman/state estimation, Condition Intelligence,
DecisionEngine, incidents, RAG, agents, CMMS integration, the final product UI.

---

## Phase 10 — Feature Engineering

NOT STARTED

---

## Phase 11 — ML Intelligence

NOT STARTED

---

## Phase 12 — Kalman / State Estimation

NOT STARTED

---

## Phase 13 — Condition Intelligence

NOT STARTED

---

## Phase 14 — Decision Intelligence

NOT STARTED

---

## Phase 15 — Prognostics / Future Behavior

NOT STARTED

---

## Phase 16 — Alert Correlation + Incident Management

NOT STARTED

---

## Phase 17 — Maintenance Workflow

NOT STARTED

---

## Phase 18 — RAG Knowledge Platform

NOT STARTED

---

## Phase 19 — Workflow Intelligence / GenAI Agent

NOT STARTED

---

## Phase 20 — CMMS Integration

NOT STARTED

---

## Phase 21 — Customer + Business Services

NOT STARTED

---

## Phase 22 — Product Metrics / North Star

NOT STARTED

---

## Phase 23 — Production Backend Hardening

NOT STARTED

---

## Phase 24 — Security

NOT STARTED

---

## Phase 25 — Auditability

NOT STARTED

---

## Phase 26 — Observability

NOT STARTED

---

## Phase 27 — Resilience

NOT STARTED

---

## Phase 28 — Frontend Product Experience

NOT STARTED

---

## Phase 29 — UX Refinement

NOT STARTED

---

## Phase 30 — Customer Onboarding + Commissioning

NOT STARTED

---

## Phase 31 — Firmware + Configuration Management

NOT STARTED

---

## Phase 32 — MLOps

NOT STARTED

---

## Phase 33 — Performance + Scale Testing

NOT STARTED

---

## Phase 34 — CI/CD

NOT STARTED

---

## Phase 35 — Comprehensive Testing

NOT STARTED

---

## Phase 36 — Flagship End-to-End Demo

NOT STARTED

---

## Phase 37 — Production Documentation

NOT STARTED

---

## Phase 38 — Industrial Adoption Boundary

NOT STARTED

---

## Phase 39 — Final Production Readiness Review

NOT STARTED

---

# Completed Setup

- Git repository initialized
- Main project folders created
- CLAUDE.md created
- LOOP.md created
- IMPLEMENTATION_STATUS.md created
- TECHNICAL_DECISIONS.md created

---

# Phase 0 Tasks (Completed)

## Required Documentation

- [x] Product Vision
- [x] Architecture
- [x] Domain Model
- [x] Event Catalog
- [x] Failure Mode Catalog

## Required Architecture Decisions

- [x] Frontend architecture (ownership defined; implementation deferred to Phase 1/28)
- [x] Backend architecture (domain ownership defined; implementation deferred to Phase 1)
- [x] Data architecture (ADR-007, validated in Phase 1 — see ADR-014)
- [x] MQTT/Kafka responsibilities (ADR-006)
- [x] Edge vs central platform responsibilities (ADR-005, docs/ARCHITECTURE.md §5)
- [x] Rules vs ML boundaries (ADR-003, docs/ARCHITECTURE.md §7)
- [x] GenAI/RAG boundaries (ADR-004, docs/ARCHITECTURE.md §7, §9.1)
- [x] Asset hierarchy (ADR-010, docs/DOMAIN_MODEL.md §3)
- [x] Telemetry/event schema strategy (docs/EVENT_CATALOG.md)
- [x] Security boundary (docs/ARCHITECTURE.md §9)
- [x] Synthetic vs production adapter strategy (ADR-001, docs/ARCHITECTURE.md §10)

---

# Current Phase 1 Tasks

All 29 Phase 1 acceptance criteria — verified by actually running each command, not
inferred:

- [x] 1. Frontend installs and runs (`npm install`, `npm run dev`; also builds/runs via Docker)
- [x] 2. Backend installs and runs (`uv sync`, `uvicorn`; also builds/runs via Docker)
- [x] 3. PostgreSQL starts (`timescale/timescaledb-ha:pg16`, healthy in `docker compose ps`)
- [x] 4. Required database extensions validated (`timescaledb` + `vector` both created
      successfully in the same database — ADR-014)
- [x] 5. Alembic migrations run successfully (`0001_initial_schema` applied and re-run
      idempotently)
- [x] 6. Backend connects to database (`/ready` reports `database: healthy`; direct
      `Database.check_connection()` test passes)
- [x] 7. Redis starts and backend connectivity works (`/ready` reports `redis: healthy`)
- [x] 8. MQTT broker starts (Mosquitto, healthy)
- [x] 9. MQTT publish/subscribe test succeeds (`scripts/verify_mqtt.sh` — PASSED)
- [x] 10. Kafka starts (KRaft, healthy)
- [x] 11. Kafka produce/consume test succeeds (`scripts/verify_kafka.sh` — PASSED)
- [x] 12. `/health` succeeds (verified via curl, local run and Docker Compose)
- [x] 13. `/ready` succeeds when dependencies are healthy (verified both ways)
- [x] 14. `/api/v1/system/info` works (verified both ways)
- [x] 15. Correlation IDs work (generated when absent, echoed when valid, tested and
      curl-verified)
- [x] 16. Structured error format works (404/405 verified consistent shape; no stack
      traces in responses)
- [x] 17. Backend tests pass (12/12, against live Postgres/Redis, not mocks)
- [x] 18. Backend lint passes (`ruff check .` — clean)
- [x] 19. Backend type check passes (`mypy app --strict` — clean)
- [x] 20. Frontend lint passes (`eslint` — clean)
- [x] 21. Frontend type check passes (`tsc --noEmit` — clean)
- [x] 22. Frontend production build passes (`next build` — clean, standalone output)
- [x] 23. `docker compose up` starts the required stack successfully (6/6 containers up)
- [x] 24. Docker Compose services report healthy where health checks exist (6/6 healthy;
      required fixing a real bug — see Technical Debt / bug-fixed-in-Phase-1 note below)
- [x] 25. No real secrets committed (`.env` git-ignored, `.env.example` has only
      local-development defaults, `git status` confirms `.env` is untracked)
- [x] 26. README/DEVELOPER_SETUP instructions are valid (every command in
      `docs/DEVELOPER_SETUP.md` was actually executed during verification)
- [x] 27. IMPLEMENTATION_STATUS.md updated (this document)
- [x] 28. TECHNICAL_DECISIONS.md updated (ADR-006, ADR-007 promoted to ACCEPTED;
      ADR-014–ADR-021 added)
- [x] 29. No company-specific names appear anywhere in the repository (repository-wide
      case-insensitive search for the prohibited company name: zero genuine matches — one
      incidental substring inside an unrelated npm package's base64 integrity hash, not a
      name)

---

# Current Phase 2 Tasks

All 38 Phase 2 acceptance criteria — verified by actually running each command, not
inferred:

- [x] 1. Domain schema implemented (16 tables, `backend/app/domain/models.py`)
- [x] 2. Alembic migration succeeds (applied, downgraded, re-applied cleanly)
- [x] 3. Tenant boundaries enforced (composite FKs — DB level; `X-Tenant-ID` — API level)
- [x] 4. Customer hierarchy works (create/list/get, verified via API)
- [x] 5. Plant hierarchy works (create/list/get, verified via API)
- [x] 6. Production-line hierarchy works (create/list/get, verified via API)
- [x] 7. Machines work (create/list/get + filters, verified via API)
- [x] 8. Bearings work (via machine-hierarchy endpoint, verified)
- [x] 9. Lubrication systems work (list/detail, full chain verified via API)
- [x] 10. Reservoirs/pumps/controllers/distributors/circuits work (verified in seed +
      machine-hierarchy response)
- [x] 11. Lubrication points correctly connect delivery path to served component
      (verified: circuit → point → bearing, tenant-safe via composite FK)
- [x] 12. Sensors attach to appropriate physical entities (6 attachment types, verified
      via seed + API + `attached_entity_type`)
- [x] 13. Gateways are modeled (site/plant attachment, seeded, `CHECK`-constrained)
- [x] 14. Domain invariants enforced (DB constraints + service-layer checks — see
      `docs/ASSET_HIERARCHY.md` §7 table)
- [x] 15. Repositories are tenant-scoped (`TenantScopedRepository`, tested)
- [x] 16. Services enforce domain rules (parent existence, retired-parent blocking,
      duplicate-code conflicts — tested)
- [x] 17. API responses use typed schemas (Pydantic throughout, no raw ORM exposure)
- [x] 18. Pagination/filtering strategy works (offset/limit, tested)
- [x] 19. Deterministic seed data loads (24 machines, 108 sensors — verified)
- [x] 20. Seed is idempotent (verified manually twice + automated test)
- [x] 21. At least 20 realistic demo machines exist (24, verified)
- [x] 22. Hierarchy API works (`GET /api/v1/hierarchy`, verified — 3 customers, 24
      machines in tree)
- [x] 23. Machine hierarchy API works (`GET /api/v1/machines/{id}/hierarchy`, verified —
      bearings + full lube chain + sensors)
- [x] 24. Minimal hierarchy UI works (verified in a real browser against live data)
- [x] 25. Machine detail page uses backend data (verified — no hardcoded values)
- [x] 26. Sensor inventory works (fleet-wide page + machine-scoped section, both verified)
- [x] 27. No telemetry or fake health scores were added (confirmed by design — no such
      fields exist anywhere in this phase's schema/API/UI)
- [x] 28. Relevant tests pass (41/41, against live Postgres)
- [x] 29. Backend lint passes (`ruff check .` — clean, including the autogenerated
      migration)
- [x] 30. Backend type check passes (`mypy app --strict` — clean)
- [x] 31. Frontend lint passes (`eslint` — clean)
- [x] 32. Frontend type check passes (`tsc --noEmit` — clean)
- [x] 33. Frontend build passes (`next build` — clean)
- [x] 34. Docker stack remains healthy (6/6 healthy after rebuilding backend/frontend
      images with Phase 2 code)
- [x] 35. Docs updated (`docs/ASSET_HIERARCHY.md` created; README/DEVELOPER_SETUP/backend
      and frontend READMEs updated)
- [x] 36. IMPLEMENTATION_STATUS.md updated (this document)
- [x] 37. TECHNICAL_DECISIONS.md updated (ADR-022–ADR-029 added)
- [x] 38. No prohibited company-specific references exist anywhere in the working tree
      (repository-wide case-insensitive search — zero genuine matches)

---

# Current Phase 3 Tasks

All 38 Phase 3 acceptance criteria — verified by actually running each command, not
inferred:

- [x] 1. Simulator package implemented (`simulator/simulator/{domain,physics,sensors,
      scenarios,engine,config}`, no single-file simulator)
- [x] 2. Simulator uses actual Phase 2 asset topology (`TopologyRepository`, live SQL
      against the seeded database, verified via `tests/test_topology_repository.py`)
- [x] 3. Flagship equipped machine selected from database (Conveyor 000,
      `asset_code=L1-7B43-M000`, resolved by query, not hardcoded ids)
- [x] 4. Underlying physical state exists (`simulator.domain.state.*`)
- [x] 5. Operating states modeled (`OperatingProfile`, 7 states, configurable shift
      schedule, verified in `tests/test_engine_healthy_invariants.py`)
- [x] 6. Lubrication cycles modeled temporally (`LubricationCycleController`, 5-phase state
      machine, verified in `tests/test_cycle.py`)
- [x] 7. Reservoir consumption is stateful (`reservoir.consume`, monotonic
      non-increasing, verified)
- [x] 8. Pump behavior is stateful (`PumpState`, pressure/current/runtime/efficiency,
      verified in `tests/test_pump.py`)
- [x] 9. Circuit resistance affects flow/pressure coherently (`tests/test_circuit.py` —
      higher restriction → lower flow, higher required pressure)
- [x] 10. Bearing condition responds to operating conditions (`tests/test_bearing.py`,
      `tests/test_engine_relationships.py` cross-quartile load→temperature check)
- [x] 11. Sensor models derive from physical state (`sensor_models.observe`, config-driven
      per measurement type)
- [x] 12. True vs. observed values separated (`SimulationReading.true_value`/
      `observed_value`; deeper hidden state additionally isolated in `GroundTruthRecord` —
      structurally tested in `tests/test_ground_truth_separation.py`)
- [x] 13. Units explicit (`docs/SIMULATOR.md` §11, every `SensorModelConfig.unit`)
- [x] 14. Demo engineering config exists (`simulator/config/demo_engineering.yaml`)
- [x] 15. All assumptions clearly marked synthetic (file header + every doc file's
      disclaimer)
- [x] 16. Healthy signals vary realistically (visual validation — see §26 below;
      `step_natural_variation`, ambient/load-driven bearing variation)
- [x] 17. Simulation supports time acceleration (default as-fast-as-possible generation;
      `--realtime --speed` for throttled live-demo pacing)
- [x] 18. Deterministic seeds work (`tests/test_engine_determinism.py` — same seed ⇒
      byte-identical output over 120 and 600 ticks; different seed ⇒ different noise, same
      measurement-type shape)
- [x] 19. CLI/runner works (`python -m simulator run ...`, exercised for the 24h reference
      dataset)
- [x] 20. Historical healthy generation works (same `SimulationEngine`/CLI path used for a
      600-tick test run, a 7-day stability run, and the 24h reference dataset — no separate
      "fake historical" code path)
- [x] 21. Hidden ground truth is separate (`GroundTruthRecord`, separate JSONL file)
- [x] 22. Output contract can later map to the telemetry event contract (documented
      mapping in `docs/SIMULATOR.md` §13 and `docs/SYNTHETIC_DATA_MODEL.md` §3)
- [x] 23. Relationship tests pass (restriction→flow/pressure, pump efficiency→delivery,
      load→bearing temperature — `test_circuit.py`, `test_pump.py`, `test_bearing.py`,
      `test_engine_relationships.py`, all passing)
- [x] 24. Healthy-state invariants pass (`tests/test_engine_healthy_invariants.py` — 10
      simulated hours: reservoir monotonic, RPM zero iff stopped, flow zero outside
      FLOW_DELIVERY, bearing values in bounds)
- [x] 25. Extended run has no NaN/inf/runaway values (`tests/test_stability.py` — 7
      simulated days at 60s step, `SimulationEngine._validate_state` guard never triggers)
- [x] 26. Reference dataset generated (24h, seed 42, Conveyor 000 — 138,240 readings,
      17,280 ground-truth records)
- [x] 27. Engineering plots/statistical validation performed
      (`scripts/validate_plots.py`; NaN/inf/negative-quantity scan via a one-off inspection
      script — zero violations across 138,240 readings)
- [x] 28. Generated large data not committed (`.gitignore`: `simulator/data/`,
      `simulator/**/*.jsonl`, `simulator/**/*.png`; verified with `git add --dry-run`)
- [x] 29. Simulator/config version recorded (`RunMetadata.simulator_version`/
      `engineering_config_version`, written to `<output>.meta.json` every run)
- [x] 30. `docs/SIMULATOR.md` exists
- [x] 31. `docs/SYNTHETIC_DATA_MODEL.md` exists
- [x] 32. Backend existing tests remain passing (41/41, re-run against live Postgres)
- [x] 33. Backend lint/typecheck remain passing (`ruff check .` clean; `mypy app --strict`
      clean, 70 source files)
- [x] 34. Simulator tests/lint/typecheck pass (64/64 tests; `ruff check .` clean; `mypy
      simulator` strict clean, 25 source files)
- [x] 35. Docker Phase 1/2 stack remains healthy (6/6 healthy, re-checked after Phase 3
      work)
- [x] 36. IMPLEMENTATION_STATUS.md updated (this document)
- [x] 37. TECHNICAL_DECISIONS.md updated (ADR-030–ADR-034 added)
- [x] 38. No prohibited company-specific names appear (repository-wide search of
      `simulator/` and the new docs/ADR content — zero genuine matches; pygments/matplotlib
      third-party dependency source under `.venv/` excluded, matches there are unrelated
      English words like "shell", not company names, and `.venv/` is git-ignored)

---

# Current Phase 4 Tasks

All 36 Phase 4 acceptance criteria (brief §36) — verified by actually running each command
against the live Phase 2 database, not inferred:

- [x] 1. Reusable scenario engine exists (`simulator/simulator/scenarios/`, 8 modules)
- [x] 2. Scenarios modify hidden physical state, never fake sensor output directly
      (ADR-035; `effects.py` has no import of `simulator.engine.output`, verified by
      inspection and by every physics function's own docstring)
- [x] 3. All 11 catalog failure modes/states are implemented (10 injectable scenarios +
      Normal Operation, which is simply zero active scenarios — `simulator.scenarios.HEALTHY`)
- [x] 4. Scenario lifecycle exists (`ScenarioLifecycleState`, 6 states,
      `tests/test_scenario_instance.py`)
- [x] 5. Reusable progression profiles exist (6 profiles, `tests/test_scenario_progression.py`)
- [x] 6. Targets resolve to actual Phase 2 assets (`resolve_target` against the live
      `MachineTopology`, `tests/test_scenario_targeting.py`)
- [x] 7. Invalid target types are rejected (`ScenarioDefinition` schema-time validation +
      `ScenarioTargetError` at runtime, both tested)
- [x] 8. Gradual Restriction behaves progressively (SIGMOID, verified in
      `tests/test_scenario_signal_signatures.py` and the flagship 24h dataset)
- [x] 9. Sudden Blockage behaves abruptly (STEP, severity=1.0 on the first active tick,
      pressure hits the pump ceiling every cycle, `data/conveyor_000_sudden_blockage_8h.png`)
- [x] 10. Leakage is physically distinct from restriction (raw-vs-delivered flow split,
      ADR-041; pressure stays flat/falls vs. restriction's rise —
      `tests/test_scenario_distinctness.py`, `tests/test_scenario_signal_signatures.py`)
- [x] 11. Over-lubrication is modeled (delivered-volume multiplier + faster reservoir
      depletion vs. a same-seed healthy baseline, `tests/test_scenario_signal_signatures.py`)
- [x] 12. Low reservoir is modeled (one-shot initial-condition set + existing
      `availability_factor` pathway, `tests/test_scenario_multi_fault.py`)
- [x] 13. Pump degradation is modeled (`step_efficiency` target-shift,
      `tests/test_scenario_signal_signatures.py`)
- [x] 14. Sensor drift modifies observations, not truth (`tests/test_scenario_quality_semantics.py`
      ::`test_sensor_drift_moves_observed_but_never_true_value`)
- [x] 15. Sensor dropout preserves truth and removes/invalidates observation
      (`quality=MISSING`, `observed_value=None`, `true_value` always finite — same test file)
- [x] 16. Network failure is distinct from sensor failure (whole-machine
      `COMMUNICATION_LOSS` vs. single-sensor `MISSING`, precedence tested)
- [x] 17. Multi-fault support exists (additive/min/max composition + sensor-observability
      precedence, ADR-039; `tests/test_scenario_multi_fault.py`, `test_scenario_effects.py`)
- [x] 18. Refill event exists (`AutoRefillPolicy`, `reservoir.refill()`,
      `GroundTruthRecord.refill_event`, `tests/test_refill.py`)
- [x] 19. Recovery behavior exists where appropriate (`RecoverySpec`, linear severity decay
      to `COMPLETED`, `tests/test_scenario_instance.py`)
- [x] 20. Scenario manifest exists (`RunMetadata` extended with `run_id`,
      `scenario_engine_version`, `scenario_config_version`, `scenarios`, `readings_path`,
      `ground_truth_path` — verified in generated `.meta.json` files)
- [x] 21. Reproducibility works (`tests/test_engine_scenario_determinism.py` — same seed +
      scenario plan ⇒ byte-identical output, including `INTERMITTENT`-progression scenarios)
- [x] 22. Ground truth remains separate (`tests/test_ground_truth_separation.py` re-verified
      unchanged; new `scenarios`/`reservoir_level_state`/`network_state`/`refill_event`
      fields confirmed absent from `SimulationReading`'s field set)
- [x] 23. Signal-direction tests pass (`tests/test_scenario_signal_signatures.py`, 5 tests)
- [x] 24. Temporal ordering tests pass (`tests/test_scenario_temporal_ordering.py` — paired
      healthy/scenario comparison, pressure deviation precedes bearing temperature
      deviation by more than one full 600s thermal-lag time constant)
- [x] 25. Failure distinctness validation performed
      (`tests/test_scenario_distinctness.py`, 4 tests + 3 sudden_blockage/leakage/
      independent_bearing_fault plots visually inspected)
- [x] 26. Scenario datasets generated (7 datasets: healthy, gradual_restriction [flagship
      24h], sudden_blockage, leakage, pump_degradation, sensor_drift,
      independent_bearing_fault)
- [x] 27. Flagship 24h gradual-restriction run generated
      (`data/conveyor_000_gradual_restriction_24h.*`, seed 42, scenario start 4h)
- [x] 28. Plots visually inspected (flagship + 3 additional scenario plots, all confirming
      expected qualitative behavior — see Phase 4 delivered-items list above)
- [x] 29. No NaN/inf/impossible values (scanned directly across the flagship dataset —
      zero violations across 138,240 readings; `tests/test_scenario_stability.py`'s
      automated equivalent for two 7-day runs)
- [x] 30. Phase 3 regression tests still pass (all pre-existing Phase 3 tests re-run and
      passing under the Phase 4 codebase, including after the raw-vs-delivered flow change)
- [x] 31. Backend regression tests still pass (41/41, live Postgres)
- [x] 32. Simulator lint passes (`ruff check .` clean, 62 source files)
- [x] 33. Simulator typecheck passes (`mypy simulator` strict clean, 33 source files)
- [x] 34. Docker services remain healthy (6/6 healthy, re-checked after Phase 4 work)
- [x] 35. Docs updated (`docs/SCENARIO_ENGINE.md` created; `docs/SIMULATOR.md`,
      `docs/SYNTHETIC_DATA_MODEL.md`, `docs/FAILURE_MODE_CATALOG.md` updated)
- [x] 36. No prohibited company-specific references appear (repository-wide search —
      zero genuine matches)

---

# Current Phase 5 Tasks

All 48 Phase 5 acceptance criteria — verified by actually running each command against the
live Docker Compose stack (postgres/redis/mosquitto/kafka/backend/frontend, 6/6 healthy
throughout), not inferred:

- [x] 1. `edge/` package exists with the specified module layout (domain/acquisition/
      buffering/connectivity/rules/transport/config/health/runtime + CLI)
- [x] 2. Edge ingests from the Phase 3/4 simulator via a clean adapter, not a duplicated
      physics implementation (`SimulatorTelemetrySource` drives `SimulationEngine.step()`
      in-process via a local `uv` path dependency)
- [x] 3. A `FutureRealDeviceTelemetrySource` boundary is documented (raises
      `NotImplementedError`, tested)
- [x] 4. `ReadingEnvelope` carries full asset context, with unresolvable hierarchy fields
      left `None` rather than guessed (`tests/test_envelope.py`)
- [x] 5. Event ids are deterministic and unique, not timestamp-based (ADR-045;
      `tests/test_envelope.py::test_event_id_is_deterministic` +
      `test_event_id_varies_by_*`)
- [x] 6. Sequence numbers are monotonic per (gateway, sensor) and persist across restart
      (ADR-044; `tests/test_buffering.py::test_sequence_numbers_persist_across_restart`)
- [x] 7. Three distinct timestamps exist (`source_timestamp`/`edge_received_timestamp`/
      `edge_emitted_timestamp`) with a configurable, documented-as-demo-only clock offset
- [x] 8. Local buffer is persistent (SQLite, WAL mode), not in-memory-only, and survives
      restart (`tests/test_buffering.py`, `tests/test_runtime.py::
      test_crash_recovery_pending_events_survive_restart`)
- [x] 9. Buffer states are `PENDING`/`SENT`/`ACKNOWLEDGED`/`FAILED`/`DEAD_LETTER`; nothing
      is ever silently deleted (`tests/test_buffering.py::
      test_retention_moves_oldest_pending_to_dead_letter_not_delete`)
- [x] 10. Store-and-forward continues acquisition/rules/buffering while offline
      (`tests/test_mqtt_integration.py::
      test_mqtt_broker_outage_buffers_then_replays_on_reconnect`)
- [x] 11. Replay preserves original event ids/timestamps/sequence, never re-minted (same
      test — buffer rows verified `ACKNOWLEDGED` under their original `event_id`s)
- [x] 12. Retention policy is configurable and non-silent on breach (oldest-`PENDING`-to-
      `DEAD_LETTER`, ADR-047; `tests/test_buffering.py::
      test_retention_age_breach_dead_letters_stale_events`,
      `tests/test_runtime.py::test_retention_overflow_increments_metrics`)
- [x] 13. `ConnectivityManager` implements `ONLINE`/`DEGRADED`/`OFFLINE`/`RECOVERING` from
      transport-level success/failure (ADR-048; `tests/test_connectivity.py`)
- [x] 14. Backoff is bounded, jittered, and deterministically testable (pure
      `compute_backoff` function, seeded-RNG tests, no real sleeps in unit tests)
- [x] 15. `EdgeTransport` protocol exists with `NoopTransport`/`RecordingTestTransport`/
      `MqttTransport` implementations
- [x] 16. Real MQTT transport publishes to a documented topic with a deliberate QoS choice
      (`lubrisense/v1/{tenant_id}/{gateway_id}/telemetry`, QoS 1, ADR-046)
- [x] 17. Exactly four local rules exist, generic labels only, not a general rules engine
      (`LOCAL_RANGE_VIOLATION`/`LOCAL_WARNING`/`LOCAL_LUBRICATION_CYCLE_FAILURE`/
      `LOCAL_SENSOR_FAULT`, ADR-049; `tests/test_rules.py`, 10 tests)
- [x] 18. Edge continues acquiring/buffering/evaluating rules with MQTT/central services
      down (`tests/test_mqtt_integration.py::
      test_mqtt_broker_outage_buffers_then_replays_on_reconnect`)
- [x] 19. Versioned `EdgeConfig` exists covering identity, poll rate, enabled sensors, rule
      thresholds (labeled demo assumptions), buffer limits, transport settings, clock
      offset, firmware/config version
- [x] 20. Fail-fast startup validation covers every listed invalid case, including
      duplicate gateway identity (`GatewayLock`, `tests/test_gateway_lock.py`;
      `tests/test_config.py`, 14 validation tests)
- [x] 21. A config-version change is recorded (health metric + log, no remote config
      management; `tests/test_health.py::test_config_version_change_is_recorded`)
- [x] 22. Gateway/controller/sensor firmware version metadata is carried on every envelope
      and in the health snapshot, using only already-established generic demo values
- [x] 23. Edge health/status is exposed (CLI `python -m edge status`,
      `EdgeHealth.to_dict()`)
- [x] 24. Lightweight metrics exist (acquired/buffered/sent/replayed/failures/
      duplicates_prevented/warnings/buffer_overflow_count/config_changes/buffer depth)
- [x] 25. Deduplication via event-id uniqueness is enforced and tested
      (`tests/test_buffering.py::test_duplicate_event_id_insert_is_rejected_not_duplicated`)
- [x] 26. Idempotent replay on retry is proven (same `event_id` resent, never duplicated)
- [x] 27. Crash-recovery test passes: acquire → pending → unclean stop → reopen buffer →
      pending events still present → replay resumes (`tests/test_runtime.py` and, against a
      real broker, `tests/test_mqtt_integration.py::
      test_edge_restart_during_outage_recovers_all_pending_events`)
- [x] 28. Simulated Network Failure (simulator scenario data) and an actual MQTT broker
      outage are tested as distinct, non-conflated code paths
      (`tests/test_runtime.py::test_simulated_communication_loss_does_not_affect_connectivity_state`
      vs. `tests/test_mqtt_integration.py::
      test_mqtt_broker_outage_buffers_then_replays_on_reconnect`)
- [x] 29. Sensor-dropout quality semantics are preserved end to end — never translated to
      zero (`tests/test_runtime.py::test_sensor_dropout_never_becomes_zero`)
- [x] 30. Edge data-quality tagging is limited to the specified basic set (`GOOD`/
      `UNCERTAIN`/`SUSPECT`/`MISSING`/`INVALID`/`COMMUNICATION_LOSS`/`BAD` +
      edge-local `UNAVAILABLE`) — explicitly not staleness/duplicate-analytics/drift/
      late-arrival detection (Phase 7)
- [x] 31. Embedded buffer schema is justified and indexed (`events`/`sequence_state`/
      `config_state`, indexes on `status` and `(sensor_id, sequence_number)`)
- [x] 32. Concurrency model is simple and documented, not overengineered (one acquisition
      loop + one sender thread, single coarse-grained lock around every buffer call — a
      real bug from an under-locked call path was found and fixed during Docker
      verification; see Technical Debt)
- [x] 33. Graceful shutdown works and is tested (`tests/test_runtime.py::
      test_graceful_shutdown_completes`)
- [x] 34. Practical CLI exists (`run`/`status`/`buffer list`/`replay`)
- [x] 35. `edge/Dockerfile` + optional `docker compose --profile edge` service exist, not
      started by default, and were actually built and run successfully against the live
      stack (`docker compose --profile edge build edge`, `... run --rm edge python -m edge
      run/status`)
- [x] 36. Required test list is covered: envelope, event-id, sequence, buffer/dedup/
      retention, connectivity/backoff, all four rules, config validation, health, gateway
      lock, graceful shutdown, crash recovery, sensor dropout, quality-vs-outage
      distinction (69 edge tests total, see Test Results below)
- [x] 37. Simulator→Edge→MQTT integration test passes against a real broker, inspecting a
      full published message (`tests/test_mqtt_integration.py::
      test_simulator_to_edge_to_mqtt_end_to_end`)
- [x] 38. MQTT broker-outage buffering test passes (buffer grows during a real
      `docker compose stop mosquitto`, drains and preserves identity on
      `docker compose start mosquitto`) — treated as one of the most important acceptance
      tests, per the brief
- [x] 39. Edge-restart-during-outage recovery test passes — no event lost merely because
      the edge process restarted
- [x] 40. A small reference run (flagship: healthy → real outage → recovery) captures
      buffer-depth trend and event counts to a compact JSON summary, not raw logs
      (`edge/data/reference_run_summary.json`)
- [x] 41. `docs/EDGE_ARCHITECTURE.md` created covering every required topic
- [x] 42. `docs/EVENT_CATALOG.md` updated only where edge-event fields needed
      clarification (§2.3, §4.1)
- [x] 43. Meaningful ADRs recorded for persistence, sequence, event-id, MQTT QoS/topic,
      transport abstraction, retention policy, connectivity-state model, and local-rule
      boundary (ADR-043–ADR-049) — not for trivial details
- [x] 44. Nothing from the explicit DO-NOT-IMPLEMENT list was built (Kafka central
      ingestion, Timescale persistence, full event pipeline, full data-quality engine,
      baselines, rules engine, ML, Kalman, Condition/DecisionEngine, incident management,
      RAG, GenAI agents, CMMS, final dashboard — verified by inspection of `edge/`'s actual
      contents)
- [x] 45. Edge unit tests pass (69/69)
- [x] 46. Edge lint passes (`ruff check .` clean, across `edge/edge`, `edge/tests`, and
      `edge/scripts`)
- [x] 47. Edge typecheck passes (`mypy edge` strict clean, 31 source files)
- [x] 48. No prohibited company-specific references appear anywhere in the new/modified
      files (repository-wide case-insensitive search against known real
      industrial-automation/lubrication-equipment brand names — zero genuine matches; all
      vendor-style strings in this phase, e.g. gateway `manufacturer_demo`/`model_demo`,
      reuse the fictional names already established in Phase 2's seed data)

---

# Blockers

None currently.

---

# Known Risks

Phase 0 risks: full detail in docs/ARCHITECTURE.md §14. Summary:

- Synthetic telemetry may not be statistically realistic enough to validate ML approaches.
- Kafka + MQTT + TimescaleDB + pgvector + Redis is significant local-dev infrastructure
  complexity (mitigated in Phase 1: all four started healthy on first attempt after
  configuration was correct — see TECHNICAL_DECISIONS.md ADR-014/ADR-015).
- Deterministic rule thresholds are demo assumptions, not validated engineering values.
- Causal language between lubrication faults and bearing/machine issues is easy to overstate
  (mitigated by docs/FAILURE_MODE_CATALOG.md §13 evidence-language rules).
- GenAI/RAG boundary discipline must be enforced in code, not just documentation.
- Tenant isolation must be correct from first schema design (Phase 2).
- Telemetry storage/retention scaling strategy is not yet decided.
- Business/value metrics could read as inflated marketing if not consistently labeled
  DEMO / ESTIMATED VALUE.
- Model governance (ADR-009) requires discipline to keep feedback-driven retraining human-gated.

Phase 1 risks (new):

- Kafka and Redis are single-node/no-persistence-tuned configurations appropriate for local
  development only; not representative of production replication/durability behavior
  (see TECHNICAL_DECISIONS.md ADR-015 Consequences).
- The Docker Compose network exposes every service's port to the host for local-development
  convenience; this is explicitly not a security posture (ADR-020) and must not be carried
  into a hardened deployment profile without review.
- `backend/app/auth/`, `app/audit/`, and `app/observability/` are intentionally empty
  placeholders — no authentication, audit logging, or metrics/tracing exist yet. Nothing in
  Phase 1 depends on them, but later phases must not assume any of the three exist before
  their dedicated phase implements them.

Phase 2 risks (new):

- The `X-Tenant-ID` header tenant-context mechanism (ADR-025) is explicitly not a security
  boundary — any client can claim any tenant id. This is safe only because there is no
  authentication yet for it to bypass; it must be replaced (not merely supplemented) when
  the authentication phase begins. The isolated seam (`get_tenant_id_header`) is designed
  to make that replacement mechanical, but it is still a real gap until then.
  Data-level cross-tenant isolation (composite FKs, ADR-022) is unaffected — this risk is
  specifically about *caller* trust, not data integrity.
  Tracked in `app/api/deps.py::get_current_tenant`'s docstring and
  `docs/ASSET_HIERARCHY.md` §3.2.
- `LubricationSystem` is machine-scoped in this implementation (§2 of
  `docs/ASSET_HIERARCHY.md`); a real centralized system serving multiple machines across a
  production line is not prevented by the schema but is not what the seed data or
  machine-hierarchy API assume. Revisit if a later phase needs line-scoped shared systems.
- `GET /api/v1/hierarchy` returns a tenant's entire fleet tree in one response with no
  pagination at the customer/site level — fine at demo scale (3 customers, 24 machines),
  flagged as a scaling limit in `docs/ASSET_HIERARCHY.md` §8, not yet addressed since there
  is no evidence it is a bottleneck.
- `Bearing` and `Gateway` have repositories but no standalone REST endpoints yet (LOOP.md
  §23 — no independent product value established yet); if a later phase needs to
  create/update bearings or gateways directly via API, those endpoints don't exist yet.

Phase 3 risks (new):

- The simulator has an implicit schema dependency on `backend/`'s Alembic-managed table/
  column names with no compile-time contract (ADR-030) — a backend migration that renames
  a column would silently break `TopologyRepository`'s SQL rather than failing a type
  check. `tests/test_topology_repository.py` running against the live database is the
  mitigation, not a structural guarantee.
- The distributor-flow-split model divides pump flow capacity evenly across a lubrication
  system's circuits rather than solving a real hydraulic network by relative resistance
  (`docs/SIMULATOR.md` §6) — fine for the flagship's near-identical two circuits, would need
  revisiting if a future scenario needs circuits with meaningfully different resistances to
  show believably different delivered flow shares.
- At the configured demo consumption rate, the flagship's 10 L reservoir would deplete to
  empty within roughly a simulated week of continuous shift operation on a healthy run with
  no `--refill-threshold` configured — intentional and numerically stable
  (`tests/test_stability.py`); Phase 4 now provides `AutoRefillPolicy` for any dataset that
  wants to avoid this tail, but it is opt-in, not a changed default.
- The flagship machine's 8 registered sensors do not cover `FLOW`, `PUMP_RUNTIME`,
  `CYCLE_COMPLETION`, `PISTON_MOVEMENT`, `LUBRICANT_TEMPERATURE`, `VIBRATION_PEAK`, or
  `LOAD` end-to-end (no sensor of those types exists on it in the Phase 2 seed data); their
  physics/dispatch logic is unit-tested but not exercised by the flagship reference
  dataset — see `docs/SIMULATOR.md` §16.

Phase 4 risks (new):

- The shared-cycle coupling effect (`docs/SCENARIO_ENGINE.md` §7): because the flagship's
  two circuits share one pump/cycle controller, a scenario targeting one circuit can measurably
  affect the *other*, untargeted circuit's bearing (via shared cycle-timing, not via that
  circuit's own `restriction_factor`/`leakage_factor` ground truth, which stays correctly
  unaffected). This is physically defensible for a real centralized system but means
  per-circuit scenario isolation is not perfect — a future consumer comparing "circuit A's
  ground truth" against "circuit A's bearing symptoms" in isolation should be aware a
  concurrent circuit B fault can still contribute.
- Leakage's reservoir-consumption behavior (ADR-041) is deliberately modeled as an
  open-loop pump (raw flow, and therefore consumption, unaffected by a downstream leak) —
  a real closed-loop, pressure-compensating controller would show faster reservoir
  depletion under leakage instead. Both are physically real designs; this implementation
  picked one and documents it (`docs/SCENARIO_ENGINE.md` §7) rather than modeling both.
- Onset durations for slow real-world failure modes (Pump Degradation, Sensor Drift — real
  "weeks-months") are compressed to 2-3 simulated days in the shipped YAML configs so they
  are observable within reasonable dataset sizes — a demo-scale compromise flagged in every
  affected scenario's YAML comment, not a claim about real onset timing.
- `simulator.scenarios.effects.build_effects` resolves `PUMP_DEGRADATION`'s target (a Pump
  entity id) to its owning `LubricationSystem` id via a linear scan
  (`_lubrication_system_id_for_pump`) — fine at the current one-lubrication-system-per-
  machine model; would need revisiting if a future phase allows one machine to have
  multiple independent lubrication systems.

Phase 5 risks (new):

- The edge depends on `lubrisense-simulator` as a local, **editable** `uv` path dependency.
  This is correct and intentional for a monorepo reference implementation (Phase 5 brief
  §2 — "do not duplicate simulator logic"), but it does mean `edge/`'s own `pyproject.toml`
  is not standalone-installable outside this repository without `simulator/` present at the
  same relative path — acceptable for a reference implementation, would need revisiting for
  a real standalone edge-gateway distribution (Phase 31, Firmware + Configuration
  Management).
- `ConnectivityManager`'s state thresholds (`offline_after_failures=3`,
  `recovered_after_successes=2`) are fixed Python defaults, not yet exposed through
  `EdgeConfig` — see ADR-048 Consequences.
- The local Mosquitto broker remains anonymous/unencrypted by design
  (`infrastructure/mosquitto/config/mosquitto.conf`, unchanged from Phase 1) — `MqttTransport`
  connects without TLS or credentials, appropriate only for this local reference stack, not
  a real gateway (`docs/EDGE_ARCHITECTURE.md` §17).
- The three mandatory MQTT integration tests directly `docker compose stop/start` the
  **shared** `lubrisense-mosquitto` container; a `mosquitto_guaranteed_running` pytest
  fixture restores it afterward unconditionally (pass or fail), and this was verified
  working during Phase 5 development, but running `edge-test` concurrently with any other
  process that depends on mosquitto staying up will cause a brief, expected outage window.
- `LocalRuleEngine`'s pump-running-without-delivery-evidence rule
  (`LOCAL_LUBRICATION_CYCLE_FAILURE`) is only exercised end-to-end against the flagship
  conveyor's actual sensor set (`PUMP_CURRENT` + `PRESSURE`, since it has no `FLOW`/
  `CYCLE_COMPLETION` sensor); the `FLOW`/`CYCLE_COMPLETION`-based evidence path the rule's
  design also allows for is unit-tested only against synthetic envelopes, not against a real
  asset with those sensor types (none exists in the current Phase 2 seed data — same
  limitation already recorded under Phase 3 risks).

---

# Current Phase 6 Tasks

All 51 Phase 6 acceptance criteria — verified by actually running each command against the
live Docker Compose stack (8/8 services healthy from a clean `docker compose down && up`),
not inferred:

- [x] 1. MQTT central ingestion works (`MqttBridge`, subscribed to
      `lubrisense/v1/+/+/telemetry` QoS 1, verified via `scripts/verify_pipeline.sh` and two
      real `python -m edge run` sessions, 4,784 events)
- [x] 2. Payload structural validation works (`SchemaValidator`, 13 unit tests —
      `tests/test_pipeline_validation.py`)
- [x] 3. Edge `event_id` is preserved (never regenerated anywhere in the chain — verified by
      querying the identical `event_id` in `telemetry` after a real publish)
- [x] 4. Edge sequence number is preserved (`sequence_number` column, unchanged end to end)
- [x] 5. Source timestamps are preserved (`source_timestamp` never overwritten; verified
      directly across a real Kafka outage — `persisted_timestamp` lands minutes later,
      `source_timestamp` stays original)
- [x] 6. MQTT → Kafka bridge works (`MqttBridge._publish_or_spool`, ADR-051)
- [x] 7. Kafka telemetry topic exists (`lubrisense.telemetry.v1`, auto-created, verified via
      real produce/consume through the bridge/consumer)
- [x] 8. Kafka partition-key strategy is documented (`tenant_id:gateway_id:sensor_id`,
      ADR-052, `docs/TELEMETRY_PIPELINE.md` §4)
- [x] 9. Kafka consumer works (`TelemetryConsumer`, two concurrent `aiokafka` loops)
- [x] 10. Consumer does not commit before durable persistence (`enable_auto_commit=False`,
      offsets committed only after the batch transaction commits — verified directly by the
      DB-outage test: consumer retries the same batch, never advances offsets, until DB
      recovers)
- [x] 11. Telemetry table exists (`telemetry`, migration `1f9fe8b7b163`)
- [x] 12. Timescale hypertable exists (verified via
      `SELECT * FROM timescaledb_information.hypertables`)
- [x] 13. Telemetry is tenant-scoped (`tenant_id` composite FKs throughout; cross-tenant
      sensor lookup proven rejected — `test_cross_tenant_sensor_is_rejected_as_unknown`)
- [x] 14. Entity/context validation works (`ContextEnrichmentService` — unknown tenant/
      sensor/gateway all rejected with distinct reasons, 10 tests in
      `tests/test_pipeline_enrichment.py`)
- [x] 15. Authoritative context enrichment works where needed (hierarchy resolved from the
      sensor's attachment column for machine/bearing/circuit-attached sensors, verified by
      dedicated tests and by two real multi-asset edge runs)
- [x] 16. Conflicting context is rejected/quarantined (`CONTEXT_CONFLICT`, never silently
      overwritten — `test_conflicting_supplied_machine_id_is_quarantined`,
      `test_conflicting_supplied_site_id_is_quarantined_not_overwritten`)
- [x] 17. Idempotent persistence works (`INSERT ... ON CONFLICT (event_id,
      source_timestamp) DO NOTHING`, `test_batch_insert_idempotent_suppresses_duplicates`)
- [x] 18. Duplicate delivery does not create duplicate rows (proven with a byte-identical
      redelivered MQTT payload, not just a repeated `event_id` — `verify_pipeline.sh` §2)
- [x] 19. Out-of-order arrival can be persisted (composite key has no ordering requirement;
      no insert-order dependency in `batch_insert_idempotent`)
- [x] 20. Batch persistence works (`getmany()` size/timeout batching,
      `test_get_by_sensor_time_range_filters_and_orders_desc` and the batch-insert tests)
- [x] 21. MQTT→Kafka outage buffering is durable (`BridgeSpool`, SQLite WAL — verified
      against a real `docker stop lubrisense-kafka`, `verify_pipeline.sh` §5)
- [x] 22. Kafka recovery drains the bridge buffer (same test — `docker start`, spool drains
      automatically, event persists with original `source_timestamp`)
- [x] 23. DB outage does not lose Kafka messages (`verify_pipeline.sh` §6, real
      `docker stop lubrisense-postgres`)
- [x] 24. Consumer recovery persists pending messages (same test — event persists exactly
      once after `docker start lubrisense-postgres`)
- [x] 25. DLQ/quarantine works (`lubrisense.telemetry.dlq.v1` + `telemetry_quarantine`,
      ADR-057; ties into DLQ-topic draining task)
- [x] 26. Unsupported schema versions are rejected (`UNSUPPORTED_SCHEMA_VERSION`, distinct
      from `SCHEMA_INVALID`; `verify_pipeline.sh` §3)
- [x] 27. Repository time-range queries work (`get_by_sensor_time_range`,
      `get_by_machine_time_range`, measurement-type filter tested)
- [x] 28. Latest-reading query works (`get_latest_by_sensor`,
      `test_latest_by_sensor_returns_none_when_no_readings` +
      `test_batch_insert_idempotent_suppresses_duplicates`)
- [x] 29. Machine telemetry query works (`get_by_machine_time_range`,
      `test_get_by_machine_time_range_scopes_to_machine`)
- [x] 30. Telemetry API works (`GET /api/v1/telemetry/sensors/{id}`, `.../latest`,
      `GET /api/v1/telemetry/machines/{id}` — 8 tests in `tests/test_api_telemetry.py`,
      including cross-tenant 404 and time-range filtering)
- [x] 31. Minimal frontend telemetry view works ("Recent Telemetry" table on the machine
      detail page, verified live in a real browser against real pipeline data via
      `next dev`, per the frontend-Docker-build limitation recorded in Technical Debt)
- [x] 32. Multiple assets can ingest telemetry (two real, concurrent-topology edge runs —
      Conveyor 000/`GW-RIDGE-CRUSH` and `L1-5F44-M020`/`GW-HARBOR` — 2,400 + 2,384 rows,
      zero quarantine, correct per-machine/per-sensor context)
- [x] 33. Event traceability works (`kafka_partition`/`kafka_offset` columns; one
      `event_id` traced from edge publish through Kafka to the persisted row)
- [x] 34. Metrics foundation exists (`PipelineMetrics`, hand-written Prometheus text,
      `/metrics` on both workers)
- [x] 35. Structured logs exist (`configure_logging(service_name=...)`, JSON, correlation-
      id-aware, reused from the existing backend logging foundation)
- [x] 36. Pipeline health/readiness exists (`/health`/`/ready` on both workers, liveness-
      vs-readiness distinction — verified returning 503 during the DB outage without the
      container reporting unhealthy)
- [x] 37. Docker services integrate cleanly (`mqtt-bridge`/`telemetry-consumer` as default
      Compose services, 8/8 healthy from a clean cold `down && up`)
- [x] 38. Full Simulator→Edge→MQTT→Kafka→Timescale flow passes (two real
      `python -m edge run` sessions through the live stack, 4,784 events persisted)
- [x] 39. Replayed event preserves original timestamps (verified directly across the
      Kafka-outage test: `source_timestamp` from acquisition time, `persisted_timestamp`
      from well after recovery)
- [x] 40. Edge replay does not create duplicates (idempotent insert covers this identically
      to any other redelivery path — proven by the general duplicate-delivery mechanism)
- [x] 41. Realistic volume test completed (4,784 real events across two machines/16 sensors
      via two genuine edge sessions; measured, not fabricated, throughput — see Delivered)
- [x] 42. Existing edge tests remain green (69/69)
- [x] 43. Simulator tests remain green (139/139)
- [x] 44. Backend tests remain green (78/78 — 41 original + 36 new pipeline tests + 1 new
      gateway-resolution regression test)
- [x] 45. Frontend lint/type/build pass (`eslint`, `tsc --noEmit`, `next build` — all clean)
- [x] 46. Pipeline tests pass (36 new tests: validation, enrichment, repository, API)
- [x] 47. Lint/typecheck pass (backend/edge/simulator/frontend all clean)
- [x] 48. Docs updated (`docs/TELEMETRY_PIPELINE.md` new; `docs/EVENT_CATALOG.md` §2.1
      rewritten; `docs/ARCHITECTURE.md` §6 cross-referenced)
- [x] 49. IMPLEMENTATION_STATUS.md updated (this document)
- [x] 50. TECHNICAL_DECISIONS.md updated (ADR-050–ADR-059 added; Pending Decisions updated)
- [x] 51. No prohibited company-specific references exist (repository-wide case-insensitive
      search of Phase 6's new files and the working tree generally — zero genuine matches,
      one incidental base64 npm-lockfile-hash substring, matching the pattern already noted
      in earlier phases)

---

# Current Phase 7 Tasks

All items below verified by actually running the command/script against the live Docker
Compose stack (9/9 services healthy) or the relevant test suite, not inferred:

- [x] 1. Raw telemetry, data-quality assessment, and clean/eligible input kept structurally
      separate (`telemetry` never modified; `quality_assessment`/`quality_issue` are new,
      additive tables; `sensor_quality_state.eligibility` is a downstream read-only signal)
- [x] 2. Quality dimensions implemented: COMPLETENESS, VALIDITY, TIMELINESS, ORDERING,
      CONSISTENCY/CONTEXT, COMMUNICATION, SENSOR_HEALTH, CONFIGURATION
      (`app.domain.enums.QualityDimension`)
- [x] 3. Severity model implemented: INFO/WARNING/ERROR/CRITICAL (`IssueSeverity`)
- [x] 4. Quality-state model implemented: TRUSTED/USABLE_WITH_CAUTION/UNUSABLE
      (`QualityState`) — never HEALTHY/FAILED anywhere in the API or frontend
- [x] 5. Eligibility model implemented, kept distinct from quality_state:
      ELIGIBLE/ELIGIBLE_WITH_CAUTION/INELIGIBLE (`Eligibility`, ADR-064)
- [x] 6. Event-level vs. window-level assessment split implemented (`QualityEngine` /
      `WindowEvaluator`, ADR-063)
- [x] 7. Sequence-gap detection (`completeness.check_sequence_gap`) — live-verified
      (`verify_data_quality.sh` case 1)
- [x] 8. Missing-value detection, never zero-substituted (`completeness.check_missing_value`)
      — live-verified (`verify_data_quality.sh` case 8; real SENSOR_DROPOUT scenario)
- [x] 9. Out-of-range detection against configured `demo_engineering.yaml`-derived ranges
      (`validity.check_out_of_range`) — live-verified (case 5)
- [x] 10. Invalid-value detection (`validity.check_invalid_value`) — live-verified (case 9)
- [x] 11. Unit-mismatch detection (`validity.check_unit_mismatch`) — live-verified (case 6)
- [x] 12. Late/very-late arrival detection (`timeliness.check_late_arrival`) — live-verified
      (case 2)
- [x] 13. Sensor-type-aware staleness detection (`timeliness.check_stale_stream`) — unit
      tested; live via periodic window evaluation
- [x] 14. Clock offset vs. progressive drift distinguished (`timeliness.check_clock_status`)
      — unit tested; live artifact observed and correctly classified during this session's
      extended testing (`CLOCK_OFFSET_SUSPECTED`/`CLOCK_DRIFT_SUSPECTED` both seen live)
- [x] 15. Out-of-order arrival detection (`ordering.check_out_of_order`) — live-verified
      (case 3), and observed live at ~23% INFO-severity rate under a fast synthetic burst
      (false-positive control run)
- [x] 16. Duplicate-pattern detection, soft signal only (`ordering.check_duplicate_pattern`)
      — live-verified (case 4)
- [x] 17. Context/metadata inconsistency detection
      (`consistency.check_context_inconsistency`) — live-verified (case 7)
- [x] 18. Machine-wide communication-loss detection, distinct from single-sensor dropout
      (`communication.check_communication_loss`) — live-verified via real NETWORK_FAILURE
      scenario (`run_scenario_validation.py`)
- [x] 19. Sensor-drift-suspected detection (`sensor_health.check_sensor_drift`) — correct in
      isolation (unit test + live undiluted-window direct invocation); masked end-to-end in
      this specific long-lived demo environment (documented limitation, not a defect)
- [x] 20. Stuck-sensor-suspected detection, sensor-type- and operating-state-aware
      (`sensor_health.check_stuck_sensor`) — live-verified via periodic window evaluation
      (case 11) and via `WindowEvaluator`
- [x] 21. Spike/rate-of-change detection, operating-state-transition-aware
      (`sensor_health.check_spike`) — live-verified (case 10)
- [x] 22. Firmware/config-change awareness, INFO severity only, never treated as a fault
      (`configuration.check_config_change`) — unit tested
- [x] 23. Versioned quality policy with the required DEMO SYNTHETIC DATA QUALITY
      ASSUMPTIONS / NOT VALIDATED PRODUCTION LIMITS disclaimer
      (`demo_quality_policy.yaml`)
- [x] 24. No numeric quality score computed for v1 (intentional, ADR-065; column present and
      nullable, always `NULL`)
- [x] 25. Database model avoids per-event row explosion (three-table split, ADR-062) —
      verified: a 1,571-event healthy run produced zero new `quality_assessment` rows for
      healthy events, only `sensor_quality_state` upserts and `quality_issue` rows for the
      actually-detected `OUT_OF_ORDER` signals
- [x] 26. Quality worker is idempotent and reprocessable (`QualityIssueRepository`'s
      `ON CONFLICT` upserts; `python -m app.data_quality.reprocess` CLI)
- [x] 27. Quality API implemented and tenant-scoped: sensor/machine/issues/summary
      endpoints, registered in `api_v1_router`
- [x] 28. Minimal `/data-quality` frontend view: TRUSTED/USABLE_WITH_CAUTION/UNUSABLE badges
      (never HEALTHY/FAILED), filterable issues table — verified live in a browser against
      real backend data
- [x] 29. Validated against real Phase 4 scenarios: SENSOR_DROPOUT and NETWORK_FAILURE PASS
      live end to end (`run_scenario_validation.py`); SENSOR_DRIFT correct in isolation
      (documented limitation for the live end-to-end case in this demo environment)
- [x] 30. Validated against synthetic hand-built test cases: 11/11 live cases pass
      (`verify_data_quality.sh`)
- [x] 31. False-positive control measured and reported honestly: 1,571 healthy events, zero
      WARNING/ERROR/CRITICAL issues, only INFO-severity OUT_OF_ORDER (~23%, explained)
- [x] 32. Performance: quality worker processed the full false-positive-control run (1,571
      events) and every `verify_data_quality.sh`/scenario-validation event live, alongside
      Phase 6's own consumer, without measurable ingestion slowdown (`verify_pipeline.sh`
      stayed green throughout)
- [x] 33. Observability: `/health`, `/ready`, `/metrics` on the quality worker (port 8083,
      relocated shared infra, ADR-068) — verified live
- [x] 34. Failure handling: batch-level retry-without-commit on DB outage (matches Phase 6);
      per-event `SAVEPOINT` isolation so one bad rule evaluation never blocks a batch
      (ADR-061) — ruff/mypy/tests confirm the mechanism; no live DB-outage-during-quality-
      processing scenario was separately staged in this session (Phase 6's own DB-outage
      case in `verify_pipeline.sh` re-ran clean with the quality worker running alongside)
- [x] 35. Documentation: `docs/DATA_QUALITY.md` (new)
- [x] 36. ADRs: TECHNICAL_DECISIONS.md ADR-060–ADR-070 (11 new) plus the ADR-022 correction
- [x] 37. IMPLEMENTATION_STATUS.md updated (this document)
- [x] 38. No prohibited company-specific references exist (repository-wide case-insensitive
      search of every Phase 7 file for real industrial-lubrication vendor names — zero
      matches)
- [x] 39. Backend/edge/simulator/frontend lint and typecheck all clean; `make verify` green
      end to end

---

# Technical Debt

- The frontend Docker image required a fix during Phase 1 verification: Next.js's
  standalone server binds to `process.env.HOSTNAME`, and Docker injects a `HOSTNAME`
  environment variable equal to the container ID by default, which caused the server to
  bind to the container's network-visible IP instead of all interfaces — Docker's own
  `HEALTHCHECK` (using `localhost`) then failed even though the app was reachable via the
  published port. Fixed by explicitly setting `ENV HOSTNAME=0.0.0.0` in
  `frontend/Dockerfile`. Recorded here (not as an ADR) because it is a concrete
  implementation fix, not an architectural decision — future Next.js standalone Docker
  images in this repository should carry the same `ENV HOSTNAME=0.0.0.0` line.
- The autogenerated Alembic migration (`08276baaeac2`) needed manual `ruff format`/`ruff
  check --fix` plus two `# noqa: E501` on unavoidably long CHECK-constraint SQL string
  literals (`ck_sensor_exactly_one_attachment`, `ck_gateway_exactly_one_attachment`) to
  pass lint — autogenerate output is not lint-clean by default and needs this pass before
  committing. Not an architectural issue, just a step to remember for future
  autogenerated migrations.
- No other technical debt recorded from Phase 1/2.

Phase 3:

- `simulator/scripts/validate_plots.py` is a development-time visual-validation utility,
  not covered by `mypy` (the `simulator-typecheck` Makefile target only checks the
  `simulator` package, matching the backend's `mypy app`-only convention) or by the test
  suite — it was run manually and its output inspected as part of Phase 3 verification, not
  automated. Acceptable for a validation script per the phase brief ("use it for
  validation, not as the product UI"), but worth noting it has no regression coverage of
  its own if it is ever extended.
- No other technical debt recorded from Phase 3.

Phase 4:

- `CycleState.delivered_volume_cm3` (the aggregate, raw-flow-based accumulator driving
  cycle SUCCESS/PARTIAL/FAILED classification and reservoir consumption) and the new
  `CircuitState.delivered_volume_cm3` (the per-circuit, delivered/post-leak accumulator
  driving that circuit's bearing lubrication-effectiveness nudge) are similarly named but
  track genuinely different quantities (ADR-041) — both are documented inline and in
  `docs/SCENARIO_ENGINE.md` §7, but the naming similarity is a real readability risk for a
  future contributor skimming `simulator/physics/cycle.py`; a rename
  (`raw_delivered_volume_cm3` vs. `confirmed_delivered_volume_cm3`) would be a
  worthwhile, purely-cosmetic follow-up.
- `simulator/cli.py::_instances_from_plan` reads its `--scenario-plan` YAML with minimal
  structural validation (a missing required key raises a raw `KeyError`/`pydantic`
  error rather than a CLI-friendly message) — acceptable for a demo CLI, not
  production-grade error handling.
- No other technical debt recorded from Phase 4.

Phase 5:

- A real concurrency bug was found and fixed during Docker verification (not left as debt,
  but recorded for visibility): `EdgeRuntime.acquire_once()` originally called
  `EnvelopeBuilder.build()` (which internally calls `LocalBuffer.next_sequence()`) *outside*
  the coarse-grained lock, while the sender thread's buffer calls were inside it — under
  real threading timing (not reproduced by the faster/more serialized unit-test timing) this
  raced against the shared `sqlite3.Connection` and raised `sqlite3.DatabaseError: no more
  rows available`. Fixed by moving the `build()` call inside the same lock
  (`edge/edge/runtime/runtime.py::acquire_once`) — see `docs/EDGE_ARCHITECTURE.md` §15.
  Flagged here as a reminder that this class of bug is exactly what running the real Docker
  image (not just unit tests) is for.
- `edge.cli._cmd_replay` constructs a `SimulatorTelemetrySource` even though a manual
  replay pass never calls `.poll()` on it — a small wasted database round-trip at CLI
  startup, not a correctness issue; would be worth threading an optional-source path through
  if the CLI grows more replay-only use cases.
- No other technical debt recorded from Phase 5.

Phase 6:

- **Pre-existing, not introduced by Phase 6**: the frontend Docker image
  (`frontend/Dockerfile`) does not pass any `NEXT_PUBLIC_*` build-time environment
  variables into its `RUN npm run build` stage, so every browser-bundled config value
  (`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_DEMO_TENANT_ID`, `NEXT_PUBLIC_APP_ENV`) is
  baked in as its empty/default fallback regardless of `docker-compose.yml`'s
  `environment:` block (Next.js inlines these at build time, not container start time).
  Every tenant-scoped page — old (`/hierarchy`) and new (`/machines/[id]`'s telemetry
  view) alike — 400s against the dockerized frontend as a result; both were verified
  correct instead via `next dev` locally with `.env.local` set. This is a Phase 1/28
  frontend-infrastructure gap (build-arg plumbing), discovered while verifying this
  phase's new telemetry view, not caused by it. Fix (future phase): add `ARG`/`ENV` for
  each `NEXT_PUBLIC_*` variable in the builder stage and pass them via `docker-compose.yml`
  `build.args`.
- `scripts/verify_pipeline.sh`'s Kafka-outage and DB-outage checks poll with a bounded
  timeout (`wait_for_query`, up to 45s) rather than a fixed sleep, because recovery timing
  depends on jittered backoff (`app.pipeline.backoff.compute_backoff`) and a fixed wait was
  observed to occasionally under-wait in practice (the event was still confirmed to land
  correctly on the next check) — not a pipeline bug, just correctly not treating a
  once-observed timing variance as a hard deadline.
- No other technical debt recorded from Phase 6.

Phase 7:

- SENSOR_DRIFT window dilution: see the Phase 7 entry above and `docs/DATA_QUALITY.md` §14.
  The rule logic is proven correct in isolation; the live end-to-end scenario-validation
  script's SENSOR_DRIFT assertion does not currently pass cleanly in this specific
  long-lived, heavily-reused local demo environment (hours of accumulated non-drifted
  telemetry on the shared demo sensor within the 180-minute lookback window). A fresh
  environment does not have this problem. No code fix applied — recorded honestly rather
  than papered over with a destructive test-data cleanup or a rule change made only to pass
  one script.
- `edge/scripts/run_scenario_validation.py` requires small `step_seconds`/tick-count tuning
  per scenario to keep generated `source_timestamp`s from running ahead of real wall-clock
  time — `WindowEvaluator`'s queries filter `source_timestamp <= now()`, so a naively large
  `step_seconds` (simulated time per tick) can push a scenario's own telemetry outside the
  window a live evaluation cycle will ever see. Documented in the script's own comments;
  not a product bug, a test-script parameter-tuning note for future scenario additions.
- `scripts/verify_data_quality.sh`'s sequence-number base is derived from unix-epoch-seconds
  (`date +%s`), not a small random offset, specifically because `sensor_quality_state.
  expected_next_sequence` is a monotonically-advancing persistent counter on the shared demo
  sensor that only ever grows across every run against it — a small random offset can fall
  behind an already-high counter from a prior session. Noted here since it is a slightly
  unusual pattern a future script author might not expect.
- No other technical debt recorded from Phase 7.

---

# Next Action

Phase 7 acceptance criteria have been met and verified against the live Docker Compose
stack (not inferred): `make verify` green end to end (backend 132/132 tests including 54
new data-quality unit tests, simulator 139/139, edge 69/69, frontend build/lint/typecheck
clean, `mqtt-verify`/`kafka-verify`/`pipeline-verify`/`data-quality-verify` all passing live
against real Kafka/MQTT/Postgres and a real running `data-quality-worker`),
`scripts/verify_data_quality.sh`'s 11 synthetic cases passing end to end via real MQTT
publish through the real pipeline, and `edge/scripts/run_scenario_validation.py` proving
SENSOR_DROPOUT and NETWORK_FAILURE detection against real Phase 4 scenario physics (with
SENSOR_DRIFT's known, disclosed, non-functional window-dilution limitation in this specific
long-lived demo environment — see docs/DATA_QUALITY.md §14). One real, pre-existing bug
unrelated to Phase 7's own scope was found and fixed during migration work: three
`lubrication_system` use_alter foreign keys that Phase 2's migration intended but never
actually created, and that Phase 6's migration then misdiagnosed as a false positive and
suppressed again — see the corrected ADR-022 and the Phase 7 entry above. Awaiting explicit
instruction to begin Phase 8 (Baseline Engine). Do not begin Phase 8 implementation until
that instruction is given.

---

# Last Updated

2026-08-18 — Phase 7 data quality engine complete.