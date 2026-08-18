# Edge Architecture — Phase 5 Implementation

Status: PHASE 5 — DRAFT FOR ACCEPTANCE
Last updated: 2026-08-17

This document describes the edge-controller reference implementation delivered in Phase 5:
local acquisition, deterministic local rules, persistent buffering/store-and-forward, and
MQTT publishing — the concrete realization of the responsibilities `docs/ARCHITECTURE.md`
§5 already assigned to the edge layer. It supersedes that section only in implementation
detail; the conceptual edge/central split is unchanged.

---

## 1. Responsibilities and non-responsibilities

The edge (`edge/edge/`) implements, exactly:

- local sensor-reading acquisition (from a `TelemetrySource`)
- deterministic local rules (four checks only — §11)
- local timestamping and per-sensor sequence numbering
- a persistent local buffer with store-and-forward semantics
- connectivity-state tracking with bounded backoff
- MQTT publishing
- local health/status reporting

It explicitly does **not** implement (Phase 5 brief §44 — these are later phases'
responsibility, listed in `IMPLEMENTATION_STATUS.md`): Kafka central ingestion, TimescaleDB
telemetry persistence, the full event pipeline, the full data-quality engine, baselines,
the Phase 9 rules engine, ML, Kalman filtering, condition/decision intelligence, incident
management, RAG, GenAI agents, CMMS integration, or the final dashboard.

**Cloud-independence boundary**: every acquisition/rules/buffering code path runs
identically whether or not the MQTT broker or the database is reachable — only the sender
thread's `send()` calls fail during an outage; `EdgeRuntime.acquire_once()` never depends on
`EdgeTransport.health()`. This is what makes "basic edge monitoring continues without cloud
AI" (`CLAUDE.md` — Graceful Degradation) concretely true rather than aspirational, proven
by `tests/test_mqtt_integration.py::test_mqtt_broker_outage_buffers_then_replays_on_reconnect`.

---

## 2. Simulator-to-edge integration (acquisition adapter)

`edge.acquisition.source.TelemetrySource` is the clean boundary the Phase 5 brief §2
requires. `SimulatorTelemetrySource` drives Phase 3/4's `simulator.engine.simulation_engine.
SimulationEngine` **in-process** — it imports and calls `SimulationEngine.step()` directly,
resolving topology via `simulator.engine.repository.TopologyRepository` and engineering
config via `simulator.config.loader.load_engineering_config`. There is no second physics
implementation and no shelling out to the simulator CLI: `edge` depends on
`lubrisense-simulator` as a local, editable `uv` path dependency (`edge/pyproject.toml`
`[tool.uv.sources]`).

Each `poll()` call converts that tick's `SimulationReading`s into `RawObservation`s, using
**only** `observed_value`/`quality` — never `true_value`
(`docs/SYNTHETIC_DATA_MODEL.md` §3; verified by
`tests/test_acquisition_source.py::test_simulator_source_never_exposes_true_value_field`,
which asserts the field is structurally absent, not just unused).

`FutureRealDeviceTelemetrySource` documents, but does not implement, the real-device
integration boundary: a real implementation would read from an actual PLC/edge protocol
and produce the same `RawObservation` shape, requiring no change to buffering, rules, or
transport.

---

## 3. Event envelope

`edge.domain.envelope.ReadingEnvelope` carries the full asset-hierarchy context a future
`TelemetryReading` (`docs/EVENT_CATALOG.md` §2.1) will need, but only populates fields the
edge can honestly resolve from `simulator.domain.topology.MachineTopology`: `tenant_id`,
`machine_id`, `component_id`, `sensor_id`. `site_id`/`plant_id`/`line_id`/`bearing_id`/
`lubrication_system_id`/`circuit_id`/`lubrication_point_id` stay `None` — the topology
repository does not resolve them, and force-populating them would be a guess, not data
(Phase 5 brief §3).

Full field list: `event_id`, `schema_version`, `correlation_id`, `tenant_id`, `site_id`,
`plant_id`, `line_id`, `machine_id`, `bearing_id`, `lubrication_system_id`, `circuit_id`,
`lubrication_point_id`, `component_id`, `sensor_id`, `measurement_type`, `value` (nullable),
`unit`, `quality`, `operating_state`, `source_timestamp`, `edge_received_timestamp`,
`edge_emitted_timestamp` (nullable until first send attempt), `sequence_number`,
`gateway_id`, `device_id`, `firmware_version`, `controller_version`, `source`, `metadata`.

---

## 4. Event id strategy (ADR-045)

`event_id = uuid5(EDGE_EVENT_NAMESPACE, f"{gateway_id}|{sensor_id}|{sequence_number}")`,
generated once at acquisition time (`edge.acquisition.builder.EnvelopeBuilder`) and never
regenerated. This is what makes replay idempotent: resending the same buffered row always
carries the same `event_id`, so a downstream consumer's own dedup (or this repo's SQLite
primary key) sees the retry as the same event, not a new one.

---

## 5. Sequence strategy (ADR-044)

Monotonic, persisted **per (gateway_id, sensor_id)** in the SQLite buffer's
`sequence_state` table, incremented and committed atomically with the reading it is
assigned to. A restart resumes exactly where it left off — proven by
`tests/test_buffering.py::test_sequence_numbers_persist_across_restart`. Per-sensor (not a
single per-gateway counter) was chosen so gap/duplicate/out-of-order detection has an
unambiguous per-signal meaning, matching how a real device would sequence its own readings.

---

## 6. Timestamp model

Three distinct timestamps, never conflated:

- `source_timestamp` — the simulator's own `simulation_timestamp` (stands in for real
  device/PLC time).
- `edge_received_timestamp` — wall-clock time the acquisition loop received the reading.
- `edge_emitted_timestamp` — wall-clock time set at each send attempt (mutable, not part of
  the envelope's identity; a retry updates it without changing `event_id`).

`EdgeConfig.clock_offset_seconds` is added to both edge-side timestamps to simulate clock
skew for demo purposes only — this is **not** drift detection (that is Phase 7's job).

---

## 7. Local buffer implementation (ADR-043, ADR-047)

SQLite (stdlib `sqlite3`, WAL mode), one file per gateway
(`buffer.db_path` template, default `./data/edge/{gateway_id}.db`), never deleted on
startup. Schema:

```
events(event_id PK, sequence_number, sensor_id, gateway_id, payload, status, attempt_count,
       created_at, last_attempt_at, acknowledged_at, error)
sequence_state(gateway_id, sensor_id, last_sequence)
config_state(gateway_id, config_version)
```

Indexes on `status` (fast "get pending") and `(sensor_id, sequence_number)` (ordering/gap
analysis). `payload` stores the full serialized `ReadingEnvelope` JSON, so replay
reconstructs the exact original event — never rewritten as a new event.

Status values: `PENDING -> SENT -> ACKNOWLEDGED`, or `PENDING -> FAILED -> (retry) ->
SENT -> ACKNOWLEDGED`, or `PENDING -> DEAD_LETTER` on retention breach. Rows are **never**
deleted by this implementation.

**Retention (ADR-047)**: when `max_buffered_events` or `max_buffer_age_seconds` is
breached, the oldest `PENDING` rows are moved to `DEAD_LETTER` — logged, counted
(`buffer_overflow_count` metric), and still inspectable via
`python -m edge buffer list --status dead_letter`. Acquisition never blocks on a full
buffer: a full buffer sheds its oldest data via dead-lettering, not by refusing new
readings (a real edge must keep observing the physical process even under sustained
backlog).

**Deduplication**: `event_id` is the primary key. `LocalBuffer.insert_pending()` returns
`False` (a no-op, not an error, not a duplicate row) if the id already exists —
`tests/test_buffering.py::test_duplicate_event_id_insert_is_rejected_not_duplicated`.

---

## 8. Offline behavior / store-and-forward

`EdgeRuntime` runs one acquisition loop and one background sender thread. Acquisition never
checks connectivity — it always writes `PENDING` rows. The sender thread's `_drain_once()`
reads `PENDING`/`FAILED` rows ordered by `sequence_number` (deterministic replay order),
attempts `EdgeTransport.send()`, and on failure marks the row `FAILED` and backs off
(`edge.connectivity.backoff.compute_backoff` — bounded exponential with full jitter, a pure
function unit-tested without real sleeps) before retrying. `ConnectivityManager` tracks
`ONLINE -> DEGRADED -> OFFLINE -> RECOVERING -> ONLINE` from consecutive
transport-level successes/failures only (ADR-048) — ticks with `quality=COMMUNICATION_LOSS`
data are unrelated to this state machine (§13 below).

---

## 9. MQTT transport, topic, and QoS (ADR-046)

Topic: `lubrisense/v1/{tenant_id}/{gateway_id}/telemetry` — one topic per gateway; a central
subscriber would use `lubrisense/v1/+/+/telemetry`. **QoS 1** (at-least-once): the broker
persists the message until acknowledged, which is exactly the durability store-and-forward
needs; `event_id`-based consumer-side dedup already absorbs any duplicate delivery QoS 2's
extra handshake would otherwise exist to prevent, so QoS 2 buys nothing here. QoS 0 is
rejected outright — it can silently drop on a flaky link, defeating this entire phase's
purpose.

`edge.transport.base.EdgeTransport` is a `Protocol` (`send`/`health`/`close`);
`NoopTransport` (discard, local dev), `RecordingTestTransport` (in-memory + settable
failure mode, unit tests), and `MqttTransport` (`paho-mqtt`, real broker) all implement it.
A Phase 6 Kafka-bridge transport would implement the same protocol without touching
acquisition, buffering, or rules.

---

## 10. Local rules (ADR-049)

`edge.rules.engine.LocalRuleEngine` implements exactly four deterministic checks — **not**
the Phase 9 rules engine (no rule authoring, no plugin mechanism, no ML):

1. **Out-of-range** (`LOCAL_RANGE_VIOLATION`) — configured min/max per measurement type.
2. **Reservoir critical/empty** (`LOCAL_WARNING`, `CRITICAL` severity) — `RESERVOIR_LEVEL`
   at/below a configured percent.
3. **Pump running with no evidence of lubrication delivery**
   (`LOCAL_LUBRICATION_CYCLE_FAILURE`) — `PUMP_CURRENT` above a "running" threshold
   sustained while `PRESSURE` stays near zero for a configured duration. The flagship
   conveyor has no `FLOW`/`CYCLE_COMPLETION` sensor, so this rule is built generically off
   whichever signals a given asset actually has; on an asset with neither `PRESSURE` nor
   `PUMP_CURRENT` registered, the rule is simply inactive (a documented limitation, not a
   bug).
4. **Invalid/missing critical sensor** (`LOCAL_SENSOR_FAULT`) — `quality` in
   `{MISSING, COMMUNICATION_LOSS, INVALID}` for a configured critical-sensor list, debounced
   (must persist `sensor_fault_debounce_ticks` consecutive readings) to avoid flapping on a
   single dropped tick.

Rule ids are deliberately generic — never a domain-specific diagnosis like "restriction
detected." Each rule tracks its own OPEN/CLEARED state so a persisting condition produces
one alert transition, not one alert per tick, matching `docs/EVENT_CATALOG.md` §4.1's
`LocalAlarmRaised`/`LocalAlarmCleared` model. `LocalEdgeAlert` is structurally separate from
any future `ConditionAssessment`.

Thresholds are DEMO SYNTHETIC ENGINEERING ASSUMPTIONS — NOT VALIDATED PRODUCTION LIMITS
(`edge/edge/config/demo_edge.yaml`), matching `simulator/simulator/config/
demo_engineering.yaml`'s disclaimer convention.

---

## 11. Sensor-dropout / quality semantics

`SimulationReading.quality=MISSING` (Sensor Dropout) or `COMMUNICATION_LOSS` (Network
Failure) always carries `observed_value=None`. The edge preserves this all the way through:
`RawObservation.value`, `ReadingEnvelope.value`, and the buffered payload all stay `None` —
**never** substituted with `0.0` (proven directly by
`tests/test_runtime.py::test_sensor_dropout_never_becomes_zero`). The edge's own quality
tagging is limited to passing through `{GOOD, UNCERTAIN, SUSPECT, MISSING, INVALID,
COMMUNICATION_LOSS, BAD}` (mirroring `simulator.domain.enums.SensorQuality`) plus an
edge-local `UNAVAILABLE` (reserved for when the acquisition adapter itself cannot reach the
source — not used by `SimulatorTelemetrySource`, which always gets *some* quality-tagged
reading back from the simulator). This is deliberately **not** the Phase 7 Data Quality
Engine: no staleness detection, no duplicate analytics, no clock-drift detection, no
late-arrival detection, no sensor-drift detection.

---

## 12. Simulated fault vs. real transport outage — the critical distinction

Two completely different things can make a reading or a send "fail," and this
implementation keeps them as different code paths, never conflated:

| | Simulated Network Failure (Phase 4 scenario) | Real MQTT broker outage |
|---|---|---|
| What happens | The **simulator** reports `quality=COMMUNICATION_LOSS`, `value=None`, every tick, for every sensor on the affected machine | The edge's **own transport** (`MqttTransport.send()`) raises `TransportError` |
| Edge acquisition | Continues normally — this is just data content flowing through `poll()` | Unaffected — acquisition never touches the transport |
| `ConnectivityManager` | **Never moves** — it only tracks transport-level successes/failures | Moves through `DEGRADED -> OFFLINE -> RECOVERING -> ONLINE` |
| Buffer | Readings are still buffered and sent as normal (`value=None`, `quality=COMMUNICATION_LOSS`) | `PENDING` count grows because `send()` keeps failing |
| Proven by | `tests/test_runtime.py::test_simulated_communication_loss_does_not_affect_connectivity_state` | `tests/test_mqtt_integration.py::test_mqtt_broker_outage_buffers_then_replays_on_reconnect` (stops/starts the real `lubrisense-mosquitto` container) |

A machine can simultaneously be mid-Network-Failure-scenario (data content) while its edge
gateway has a perfectly healthy MQTT connection (transport), and vice versa — the two are
independent by construction, not just by convention.

---

## 13. Configuration

`edge.config.models.EdgeConfig` (versioned, pydantic, frozen) — see
`edge/edge/config/demo_edge.yaml` for the full default (bound to the real seeded gateway
`GW-RIDGE-CRUSH` and the flagship conveyor `L1-7B43-M000`). YAML + `EDGE_*` env var
overrides (`edge.config.loader`), mirroring `simulator.config.loader`'s pattern.

**Fail-fast validation** (raises before `EdgeRuntime` starts): non-positive
`poll_interval_seconds`; non-positive `max_buffered_events`/`max_buffer_age_seconds`;
unknown measurement types in `enabled_measurement_types` or `range_thresholds` (rejected by
the `EdgeMeasurementType` enum itself); duplicate `range_thresholds` entries for the same
measurement type; `min_value >= max_value`; a `topic_template` missing `{tenant_id}` or
`{gateway_id}`; an invalid transport `mode`/`qos`; empty identity fields. See
`tests/test_config.py` for the full list, one test per case.

**Duplicate gateway identity** (brief §20) is enforced at process-startup time, not
config-parse time: `edge.runtime.gateway_lock.GatewayLock` takes an exclusive `flock` on a
sidecar file next to the buffer DB — a second process claiming the same `gateway_id`
against the same buffer file fails fast with `GatewayLockHeldError` rather than letting two
writers share one SQLite file.

**Config-version tracking**: `LocalBuffer.get_config_version`/`set_config_version` persist
the last-seen `config_version` per gateway; `EdgeRuntime` compares it at startup and
increments the `config_changes` health metric (logged) on a genuine change — no remote
config management exists.

---

## 14. Health, metrics, and CLI

`python -m edge status --gateway <id>` and the JSON printed at the end of
`python -m edge run` expose `EdgeHealth`: runtime status, connected sensor count, last
acquisition time, buffer depth (`PENDING` count), oldest buffered event age, connectivity
state, last transport success, open local alert count, config version, firmware version,
plus `EdgeMetrics` counters (`acquired`, `buffered`, `sent`, `replayed`, `failures`,
`duplicates_prevented`, `warnings`, `buffer_overflow_count`, `config_changes`). This is a
lightweight foundation, not a Prometheus/observability-platform integration (that is Phase
26).

CLI: `python -m edge run --gateway <code> --asset-code <code> [--transport noop|test|mqtt]
[--ticks N] [--interval S]`, `status --gateway <id>`, `buffer list [--status ...]`,
`replay --gateway <id>`.

---

## 15. Concurrency model

One acquisition loop (the calling thread) and one background sender thread, coordinated by
a single coarse-grained `threading.Lock` around **every** buffer call — including
`EnvelopeBuilder.build()`, since it calls `LocalBuffer.next_sequence()` on the same shared
`sqlite3.Connection` the sender thread also uses (a real concurrency bug — unlocked
`next_sequence()` racing the locked sender-thread calls raised `sqlite3.DatabaseError` under
real Docker timing — was found and fixed during Phase 5 verification; see
`edge/edge/runtime/runtime.py::acquire_once`). This is deliberately the simplest model that
is still correct: one gateway's demo-scale event rate does not need a thread pool or async
I/O, and a small, obviously-correct lock is what this phase's acceptance criteria (crash
recovery, no lost events, no duplicate rows) actually need — not throughput.

**Graceful shutdown** (`EdgeRuntime.stop()`): stop acquisition, signal the sender thread to
finish its current attempt and exit, join it with a timeout, close the transport, close the
buffer's DB connection.

---

## 16. Failure/recovery summary

- **Broker outage**: acquisition/rules/buffering continue unaffected; sender thread backs
  off and retries; buffer grows; on reconnect, the sender thread drains everything in
  original sequence order, preserving `event_id`/timestamps — proven end-to-end against a
  real `lubrisense-mosquitto` outage (`tests/test_mqtt_integration.py`).
- **Process crash/restart**: `PENDING` rows survive because SQLite (WAL mode) is durable
  across process death; a freshly-constructed `LocalBuffer` against the same file sees every
  previously-buffered row and can resume sending immediately — proven both at the fake-
  transport unit level (`tests/test_runtime.py::test_crash_recovery_pending_events_survive_restart`)
  and against a real broker (`tests/test_mqtt_integration.py::
  test_edge_restart_during_outage_recovers_all_pending_events`).
- **Sensor dropout / simulated network failure**: represented as data (`quality`, `value=None`),
  never as a transport-level event — see §12.

---

## 17. Future real-device integration path

A real deployment replaces `SimulatorTelemetrySource` with an implementation of the same
`TelemetrySource` protocol reading from an actual PLC/gateway protocol (OPC-UA, Modbus, a
vendor SDK, ...) — no other module changes. `FutureRealDeviceTelemetrySource` documents this
boundary without implementing it (Phase 5 explicitly does not build real-device I/O). Real
gateway hardware would also need: TLS/authenticated MQTT (the local Mosquitto broker is
anonymous/unencrypted by design, per `infrastructure/mosquitto/config/mosquitto.conf` —
see `docs/ARCHITECTURE.md` §10), validated (not demo) rule thresholds, and real firmware/
controller version reporting instead of the `0.9.0-demo` placeholder.

---

## 18. Running it

```
make edge-install
make edge-test           # unit + the 3 mandatory MQTT integration tests (needs docker compose up)
docker compose --profile edge up      # not started by default
docker compose --profile edge run --rm edge python -m edge status
```
