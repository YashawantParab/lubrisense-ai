# Simulator — Phase 3 + Phase 4 Implementation

Status: PHASE 4 — DRAFT FOR ACCEPTANCE
Last updated: 2026-08-17

This document describes the physics-informed industrial simulator implemented in
`simulator/`: its purpose, physical abstraction, hidden state, equations/relationships,
sensor models, units, configuration, temporal behavior, reproducibility, and limitations.
Phase 4's scenario/failure-injection engine is documented separately and in full in
`docs/SCENARIO_ENGINE.md`; this document covers only where Phase 4 changed Phase 3 behavior
(§18 below) and how to invoke a scenario from this simulator's perspective.

**Everything this simulator produces is DEMO / SYNTHETIC ENGINEERING DATA.** No numeric
range, coefficient, or threshold here is a validated industrial specification — see
`simulator/config/demo_engineering.yaml`'s header disclaimer and
`docs/DOMAIN_MODEL.md` §2.3.

---

## 1. Purpose

`simulator/` stands in for real sensors, lubrication controllers, and the physical asset
model (`TECHNICAL_DECISIONS.md` ADR-001, `docs/ARCHITECTURE.md` §10) until real industrial
integrations exist. It does not generate random telemetry; it maintains an underlying
physical/operating state per machine and derives sensor observations from that state, so
the resulting synthetic data is realistic enough to later support data quality, rules,
anomaly detection, fault classification, forecasting, Kalman/state estimation, and
condition/decision intelligence (Phases 7-14).

Phase 3 built the physical simulation; Phase 4 added a controlled, deterministic
scenario/failure engine on top of it (`docs/SCENARIO_ENGINE.md`) — still no MQTT/Kafka
publishing (Phase 6), no persistence of telemetry into application tables, no edge
buffering (Phase 5). See `IMPLEMENTATION_STATUS.md`.

---

## 2. Package layout

```
simulator/
  simulator/
    domain/     topology (read-only asset structure) + hidden physical state dataclasses
    physics/    reduced-order equations: reservoir, pump, circuit, bearing, cycle, machine
    sensors/    generic sensor model (noise/bias/resolution/valid_range) per measurement type
    scenarios/  Phase 4 scenario/failure-injection engine — see docs/SCENARIO_ENGINE.md
    engine/     repository (DB topology loader), SimulationEngine, output records, logging
    config/     demo_engineering.yaml + typed pydantic loader
    cli.py      `python -m simulator run ...`
  tests/        unit tests (no DB) + integration tests (live Phase 2 Postgres)
  scripts/      validate_plots.py — engineering visual-validation utility
```

---

## 3. Using the real Phase 2 asset topology

`simulator.engine.repository.TopologyRepository` connects directly to the same PostgreSQL
database Phase 2 seeded (`DATABASE_URL`, same variable name/default as
`backend/app/core/config.py::Settings`) and resolves a `MachineTopology` — machine, its
bearings, its lubrication system (reservoir/pump/controller/distributor/circuits/
lubrication points), and every attached sensor — via plain read-only SQL. It deliberately
does not import the backend's SQLAlchemy ORM (`TECHNICAL_DECISIONS.md` ADR-030): the
simulator is a separate service with its own `pyproject.toml`, matching
`TECHNICAL_DECISIONS.md` ADR-011 (repository architecture mirrors the intelligence chain).

Only sensors that actually exist in the database produce readings — the simulator never
invents a sensor. If a machine has no `FLOW` sensor registered, no `FLOW` readings are
produced for it, even though the physics layer computes a true flow value internally
(useful for e.g. `PRESSURE`'s backpressure calculation).

### Flagship reference machine

**Conveyor 000** (`asset_code = L1-7B43-M000`, seeded id
`88551bef-3149-5a8d-9645-bcd9502f4795`) — the first equipped machine in the Phase 2 seed
data (Ridgeline Crushing Plant, Line A, Northstar Industrial). Topology (all ids from the
live database, not hardcoded separately):

```
Conveyor 000
├── Drive End Bearing ───────┐
├── Non Drive End Bearing ───┼── each served by its own Lubrication Point
└── Lubrication System (PROGRESSIVE)
    ├── Reservoir (10 L, NLGI 2 grease (demo))
    ├── Pump (Progressive)
    ├── Controller (Timer-based)
    ├── Distributor (Modular piston)
    └── Circuits C1, C2 → Lubrication Points LP1, LP2 → Drive End / Non Drive End Bearings
```

8 sensors are registered on this machine in the Phase 2 seed data: `PRESSURE` (circuit 1),
`RESERVOIR_LEVEL`, `PUMP_CURRENT`, `BEARING_TEMPERATURE` × 2, `VIBRATION_RMS` × 2, `RPM`.
Any machine (or any of the other 11 fully-equipped demo machines) can be simulated the same
way via `--asset-code`/`--asset-id`; not every seeded machine needs active simulation
(several are intentionally "bare" or "bearings-only" per `docs/ASSET_HIERARCHY.md` §10).

---

## 4. Hidden physical state and operating profile

`simulator.domain.state` holds the GROUND TRUTH the engine mutates every tick — never
exposed directly as a sensor reading (§9, §10 below). Per machine:

- `MachineState`: `operating_state`, `load_percent`, `rpm`, `ambient_temperature_c`
- `BearingState` (per bearing): `lubrication_effectiveness`, `health`, `temperature_c`,
  `vibration_rms_mm_s`, `vibration_peak_mm_s`
- `LubricationSystemState`: `ReservoirState` (`quantity_l`, `lubricant_temperature_c`),
  `PumpState` (`efficiency`, `pressure_bar`, `motor_current_a`, `runtime_s`, `is_on`), one
  `CircuitState` per circuit (`restriction_factor`, `leakage_factor`, `flow_cm3_min`), and
  one `CycleState` (current lubrication cycle phase/progress)
- `SensorState` (per sensor): a fixed `bias`, drawn once per run from the seed

### Operating states (`simulator.physics.machine.OperatingProfile`)

`STOPPED -> STARTING -> RUNNING_{LOW,NORMAL,HIGH}_LOAD -> SHUTTING_DOWN -> STOPPED`, driven
by a configurable demo shift schedule (`operating_profile.shift_windows_hours`, default two
daily shifts: 06:00-14:00 and 15:00-22:00 simulated time). `load_percent` and `rpm` never
jump instantaneously — both relax toward their target through a first-order lag
(`simulator.physics.util.exp_relax`, time constant `machine.load_lag_time_constant_s`).
Within a RUNNING state, a new target load is drawn (seeded RNG) every
`load_target_change_interval_s`, producing the staircase-shaped load/RPM pattern visible in
the reference plot (§14).

`MAINTENANCE` remains an unused enum member — no Phase 4 scenario transitions a machine into
it either (a scenario degrades hidden physical state, not the machine's own operating-state
machine); it stays reserved for a later phase.

---

## 5. Lubrication cycle model (`simulator.physics.cycle`)

One `LubricationCycleController` per lubrication system drives a cycle through:

```
IDLE -> PUMP_START -> PRESSURE_BUILD -> FLOW_DELIVERY -> COMPLETING -> IDLE
```

- **IDLE**: waiting for `cycle.interval_minutes` of simulated time to elapse (default 20
  min) *and* the machine to be in a RUNNING state — a cycle never starts while stopped.
- **PUMP_START**: a brief (1s) startup delay; the pump switches on.
- **PRESSURE_BUILD**: pump pressure rises toward the required pressure for the circuit's
  current resistance (§6), via a first-order lag — see `simulator.physics.pump.step_pressure`.
  Once pressure reaches `cycle.pressure_build_target_ratio` (default 90%) of the required
  pressure, the cycle proceeds; if `cycle.max_duration_s` elapses first, the cycle is marked
  `FAILED`.
- **FLOW_DELIVERY**: lubricant flows to each circuit (the distributor's nominal flow
  capacity is split evenly across circuits — see §6's "reduced-order" note), the reservoir
  is consumed by the delivered volume, and the distributor's piston-stroke counter
  increments every `cycle.piston_stroke_period_s`. Once cumulative delivered volume reaches
  `cycle.base_volume_per_cycle_cm3` (or the cycle times out), the result is classified
  `SUCCESS` / `PARTIAL` / `FAILED` against `success_delivery_ratio`/`partial_delivery_ratio`.
- **COMPLETING**: pump switches off, pressure decays back toward zero.

A cycle's pressure/flow is represented as a genuine shape over time (rise, hold, decay) —
never collapsed into one constant reading per cycle, per the phase brief.

---

## 6. Circuit / flow-resistance model (`simulator.physics.circuit`)

A deliberately simple, explainable, reduced-order model — **not** a CFD simulation and
**not** a proprietary hydraulic model:

- `resistance_ratio = 1 + restriction_factor * resistance_gain_restriction` (>= 1.0; 1.0 at
  zero restriction).
- `required_pressure_bar = base_operating_pressure_bar * resistance_ratio` — a more
  restricted circuit needs more pressure to push the same flow (an electrical-resistance
  analogy: pressure ~ voltage, flow ~ current, resistance ~ resistance).
- `delivered_flow_cm3_min = (nominal_flow_capacity_cm3_min * pump_efficiency /
  resistance_ratio) * (1 - leakage_factor)` — flow falls as resistance rises; a leak
  reduces delivered flow directly.
- Measured circuit backpressure is slightly lower than pump pressure when leaking
  (`leakage_pressure_loss_gain`), representing lubricant escaping before the sensor.
- The distributor splits the pump's nominal flow capacity evenly across the circuits it
  feeds (`docs/DOMAIN_MODEL.md` §2.1) — a documented simplification; a full hydraulic
  network solve (unequal splits by relative resistance) is out of scope for this reference
  implementation.

Healthy circuits are not perfectly static: `step_natural_variation` applies a small,
bounded, mean-reverting random walk around the configured default restriction/leakage so
"normal" telemetry has believable variation (phase brief §14) without drifting into
fault-signature territory (`docs/FAILURE_MODE_CATALOG.md` §3's Gradual Restriction starts
well above this bounded healthy range).

---

## 7. Pump model (`simulator.physics.pump`)

- Pressure rises toward its target with time constant
  `pressure_rise_time_constant_s / pump.efficiency` while on (a degraded pump builds
  pressure more slowly — the same symptom `docs/FAILURE_MODE_CATALOG.md` §8 describes for
  Pump Degradation; Phase 4's Pump Degradation scenario is exactly this parameter driven
  down over time, see `docs/SCENARIO_ENGINE.md` §7) and decays toward zero with a separate,
  efficiency-independent `pressure_decay_time_constant_s` while off (decay is governed by
  line/circuit relief, not the pump itself).
- Motor current = `current_running_base_a + current_pressure_gain_a_per_bar * pressure_bar`
  while on, `current_idle_a` while off.
- `efficiency` wanders very slightly around `efficiency_default` on a healthy run (not a
  fixed constant); Phase 4's Pump Degradation scenario shifts the relaxation *target* this
  wandering happens around, via `step_efficiency(efficiency_offset=...)`
  (`docs/SCENARIO_ENGINE.md` §7) — the same function, no new code path.
- `runtime_s` accumulates only while the pump is actually on.

---

## 8. Reservoir model (`simulator.physics.reservoir`)

`quantity_l` only ever decreases via `consume(delivered_volume_cm3)`, called once per tick
with that tick's actual delivered volume during `FLOW_DELIVERY` — never decremented on a
timer or randomly — and only ever increases via an explicit `refill(to_percent)`. Phase 3
left `refill()` unused; Phase 4 calls it from two places: the Low Reservoir scenario's
one-shot initial-condition set, and the standalone `AutoRefillPolicy`
(`docs/SCENARIO_ENGINE.md` §9) — neither is a "failure mode" overwriting a sensor value, both
just set the same hidden `quantity_l` the healthy path already owns. `level_state()` and
`availability_factor()` (Phase 4 additions) derive a qualitative NORMAL/LOW/CRITICAL/EMPTY
band and a flow-reduction factor purely from `quantity_l` — the latter is what makes Low
Reservoir's consequences (reduced delivery) emerge from ordinary cycle physics rather than a
special case. `lubricant_temperature_c` slowly tracks ambient with a small additional rise
while the pump runs (friction heat, a lagged simplification, not a thermal simulation).

---

## 9. Bearing condition model (`simulator.physics.bearing`)

Two design choices directly implement the phase brief's "do NOT make vibration instantly
rise whenever pressure rises" requirement:

1. `lubrication_effectiveness` is nudged only at discrete cycle-completion events
   (`on_cycle_result`) — up by `lubrication_recovery_step` if that bearing's circuit
   confirmed delivery, down by `lubrication_decay_step` otherwise — never from raw
   instantaneous pressure/flow.
2. `temperature_c` and `vibration_rms_mm_s` both relax toward their targets through a
   first-order lag (`temperature_lag_time_constant_s` = 600s, `vibration_lag_time_constant_s`
   = 900s — vibration lags further behind than temperature, matching typical bearing
   thermal vs. mechanical response). Even a full, instantaneous swing in
   `lubrication_effectiveness` therefore produces a negligible single-tick change in either
   signal (see `tests/test_bearing.py::test_vibration_does_not_instantly_react_to_
   lubrication_change`).

Targets: `temperature_target = baseline + load_gain*(load/100) +
lubrication_gain*(1 - lubrication_effectiveness) + ambient_gain*(ambient - 22)`;
`vibration_target` follows the same shape plus a `(1 - health) * 3.0` degradation term.
`health` itself only degrades under *sustained* starvation (`lubrication_effectiveness`
below 0.3 for an extended period) and slowly recovers otherwise — a single missed cycle in
the healthy scenario never meaningfully moves it.

Machine-condition variation independent of lubrication (`docs/FAILURE_MODE_CATALOG.md`
§12) is supported by this same architecture (`health` degradation is not gated on
lubrication signals alone) even though Phase 3 itself only exercises the healthy case.

---

## 10. Sensor models (`simulator.sensors.models`)

Every measurement type gets its own config-driven model
(`observed = round(true_value + bias + noise, resolution)`, clipped to `valid_range`):

| Type | Unit | noise_std | bias_std | resolution | valid_range |
|---|---|---|---|---|---|
| PRESSURE | bar | 0.05 | 0.03 | 0.01 | [0, 25] |
| FLOW | cm3/min | 3.0 | 2.0 | 0.1 | [0, 500] |
| RESERVOIR_LEVEL | percent | 0.3 | 0.2 | 0.1 | [0, 100] |
| PUMP_CURRENT | A | 0.03 | 0.02 | 0.01 | [0, 10] |
| PUMP_RUNTIME | seconds | 0 | 0 | 1 | [0, ~1e9] |
| CYCLE_COMPLETION | boolean | 0 | 0 | 1 | [0, 1] |
| PISTON_MOVEMENT | count | 0 | 0 | 1 | [0, ~1e6] |
| LUBRICANT_TEMPERATURE | degC | 0.2 | 0.15 | 0.1 | [-10, 90] |
| VIBRATION_RMS | mm/s | 0.04 | 0.03 | 0.01 | [0, 30] |
| VIBRATION_PEAK | mm/s | 0.06 | 0.04 | 0.01 | [0, 60] |
| BEARING_TEMPERATURE | degC | 0.3 | 0.2 | 0.1 | [-20, 150] |
| RPM | rpm | 2.0 | 1.0 | 1 | [0, 10000] |
| LOAD | percent | 0.5 | 0.3 | 0.1 | [0, 120] |

`bias` is drawn once per sensor at simulation start (fixed calibration offset for the run)
and reused every tick unless a Phase 4 Sensor Drift scenario targets that sensor, in which
case its *effective* bias for that tick is computed fresh each time
(`docs/SCENARIO_ENGINE.md` §7) — `sensor_models.observe()` itself is unchanged either way;
it always just receives "a bias value." `noise` is fresh Gaussian noise each tick.
Discrete/counter signals (`CYCLE_COMPLETION`, `PISTON_MOVEMENT`, `PUMP_RUNTIME`) are
configured noise-free rather than receiving the same blind Gaussian treatment as continuous
analog signals. A reading whose raw (pre-clip) value falls outside `valid_range` is marked
`SUSPECT` quality instead of `GOOD` — the simulator's own coarse device-side signal, not the
Phase 7 data-quality engine's independent assessment. Phase 4 adds `MISSING` (Sensor
Dropout) and `COMMUNICATION_LOSS` (Network Failure) — both pair with `observed_value=None`,
never a fabricated number (`docs/SCENARIO_ENGINE.md` §8); `UNCERTAIN` and `INVALID` are
defined on `SensorQuality` as forward-looking hooks not yet produced by any Phase 3/4 code
path.

---

## 11. Units

pressure=bar, flow=cm3/min, reservoir level=percent (capacity/quantity tracked internally
in liters), pump current=A, runtime=seconds, temperature=degC, vibration=mm/s, RPM=rpm,
load=percent. All explicit via `SensorModelConfig.unit` and carried through to
`SimulationReading.unit` — never implicitly mixed.

---

## 12. Configuration (`simulator/config/demo_engineering.yaml`)

Single source of truth for every coefficient referenced above — healthy ranges, cycle
timing, noise parameters, load/temperature effects, pump/circuit characteristics — loaded
and validated by `simulator.config.loader.load_engineering_config` into a frozen, typed
`EngineeringConfig` (pydantic, `extra="forbid"`, so a typo'd key fails loudly rather than
silently being ignored). The file's header explicitly disclaims: **DEMO SYNTHETIC
ENGINEERING ASSUMPTIONS. NOT VALIDATED PRODUCTION LIMITS.** No company-specific names appear
anywhere in it.

---

## 13. Temporal behavior, determinism, and the output contract

- **Timestep**: configurable (`--step`, default 5s from `simulation.default_step_seconds`).
- **Time acceleration**: default mode generates ticks as fast as Python can compute them
  (appropriate for historical/offline dataset generation); `--realtime --speed N` throttles
  with `time.sleep` between ticks to approximate live wall-clock pacing for a demo.
- **Determinism**: one `random.Random(seed)` instance is created per `SimulationEngine` and
  threaded through every physics/sensor call — nothing reads the global `random` module.
  Same seed + config + topology + start state => byte-identical output
  (`tests/test_engine_determinism.py`).
- **Output contract** (`simulator.engine.output`): `SimulationReading` (one row per sensor
  per tick — `simulation_timestamp`, `tenant_id`, `asset_id`, `component_id`, `sensor_id`,
  `measurement_type`, `true_value`, `observed_value: float | None`, `unit`, `quality`,
  `operating_state`, `cycle_id`, `simulation_state` — `observed_value` is `None` only when
  Phase 4's Sensor Dropout/Network Failure make the observation genuinely unavailable, never
  a fabricated number, see `docs/SCENARIO_ENGINE.md` §8) and `GroundTruthRecord` (§ below,
  extended in Phase 4 with the `scenarios` list — see `docs/SCENARIO_ENGINE.md` §11), written
  as JSON Lines (`--csv` also emits a CSV copy of readings for quick inspection — not the
  architecture boundary). `RunMetadata` (`run_id`, `simulator_version`,
  `scenario_engine_version`, `engineering_config_version`, `scenario_config_version`, `seed`,
  `asset_id`, `start_timestamp`, `duration_seconds`, `step_seconds`, `mode`, `scenarios`) is
  written once per run as `<output>.meta.json` for reproducibility.
- **Mapping to the future telemetry contract**: a Phase 6 telemetry adapter maps
  `SimulationReading.observed_value` -> `TelemetryReading.value` and
  `measurement_type` -> `signal_type` (`docs/EVENT_CATALOG.md` §2.1) directly;
  `true_value` is dropped at that boundary (see `docs/SYNTHETIC_DATA_MODEL.md`).

---

## 14. Reference healthy dataset

Generated via:

```
uv run python -m simulator run --asset-code L1-7B43-M000 --duration 24h --seed 42 \
    --mode DEMO --output data/conveyor_000_24h
```

24 simulated hours, 5s step -> 17,280 ticks, 138,240 readings (8 sensors/tick), 17,280
ground-truth records. Visual validation
(`uv run python scripts/validate_plots.py --readings data/conveyor_000_24h.readings.jsonl
--output data/conveyor_000_24h.png`) confirms:

- **Pressure/pump current**: flat near zero outside the two configured shift windows
  (06:00-14:00, 15:00-22:00), sharp cyclic pulses (~20 min apart) during them.
- **Reservoir level**: monotonically step-decreasing only during operating periods, flat
  while stopped — 100% -> ~79% over 24h at this machine's configured consumption rate (a
  demo assumption; at this rate a 10 L reservoir would need refilling within roughly a
  simulated week of continuous shift operation, not a numerical-stability issue — see
  `tests/test_stability.py`). Phase 4 exercises exactly this precursor with the Low
  Reservoir scenario and the standalone refill mechanism — see `docs/SCENARIO_ENGINE.md`
  §7, §9, and its own flagship reference dataset in §14 there.
- **Vibration RMS / bearing temperature**: both bearings track together, rise smoothly with
  load during RUNNING periods with a visible lag (no instant step), return to baseline
  while STOPPED.
- **RPM**: staircase pattern during RUNNING periods (new load target roughly every 15
  simulated minutes), exactly zero while STOPPED.
- **Flow**: no data for this machine — Phase 2's seed data did not register a `FLOW` sensor
  on Conveyor 000 (only `PRESSURE` on circuit 1); the simulator correctly emits nothing for
  a measurement type with no corresponding sensor row rather than inventing one. `FLOW`'s
  physics and sensor model are exercised directly in `tests/test_circuit.py` and would
  produce readings automatically for any machine that does have a `FLOW` sensor registered.

Generated datasets are not committed (`.gitignore`: `simulator/data/`, `simulator/**/*.jsonl`,
`simulator/**/*.png`) — regenerate with the command above.

---

## 15. Reproducibility

Every run records `run_id`, `simulator_version`, `scenario_engine_version`,
`engineering_config_version`, `scenario_config_version`, `seed`, `asset_id`,
`start_timestamp`, `duration_seconds`, `step_seconds`, `mode`, and the activated
`scenarios` list in `<output>.meta.json`. Re-running the same command against the same
database and config files reproduces the same `SimulationReading`/`GroundTruthRecord`
stream exactly, scenario or no scenario (`tests/test_engine_determinism.py`,
`tests/test_engine_scenario_determinism.py`).

---

## 16. Limitations

- Single, reduced-order hydraulic model — not a validated fluid-dynamics simulation; a
  distributor's flow is split evenly across circuits rather than solved per relative
  resistance (this is also why a scenario on one circuit can affect a sibling circuit's
  cycle timing — see `docs/SCENARIO_ENGINE.md` §7).
- Sensor bias is fixed per run on a healthy run (a calibration-offset model); Phase 4's
  Sensor Drift scenario is exactly the mechanism that makes it time-varying — see
  `docs/SCENARIO_ENGINE.md` §7.
- No refill happens on a healthy run (`reservoir.refill()` is only ever called by a Phase 4
  Low Reservoir scenario or the standalone `AutoRefillPolicy` — `docs/SCENARIO_ENGINE.md`
  §9); reservoir level is monotonically non-increasing except on the specific tick a refill
  is triggered.
- `MAINTENANCE` operating state remains unused — no Phase 3 or Phase 4 code transitions a
  machine into it; it stays reserved for a later phase. `NetworkState.DEGRADED` and
  `SensorQuality.UNCERTAIN`/`INVALID` are similarly still-reserved hooks — Phase 4 only ever
  produces `CONNECTED`/`DISCONNECTED` and `GOOD`/`SUSPECT`/`MISSING`/`COMMUNICATION_LOSS`.
- Bearing `health`/`lubrication_effectiveness` dynamics are calibrated for plausible
  *shape*, not validated against real bearing wear data.
- The flagship machine's 8 registered sensors do not include `FLOW`, `PUMP_RUNTIME`,
  `CYCLE_COMPLETION`, `PISTON_MOVEMENT`, `LUBRICANT_TEMPERATURE`, `VIBRATION_PEAK`, or
  `LOAD` — those measurement types' end-to-end behavior is proven via targeted physics/unit
  tests rather than the flagship reference dataset; picking a different seeded machine with
  those sensors attached (or extending the seed data in a later phase) would exercise them
  end-to-end too.

---

## 17. How future real telemetry replaces simulator output

`SimulationReading` and the future `TelemetrySource.MQTTTelemetrySource`/
`KafkaTelemetrySource`/`OPCUATelemetrySource` adapters (`TECHNICAL_DECISIONS.md` ADR-001,
`docs/ARCHITECTURE.md` §10) are designed to produce the same downstream shape
(`observed_value`, `measurement_type`, asset/sensor ids, `quality`) — a Phase 6 telemetry
adapter converts either source into the same `TelemetryReading` contract
(`docs/EVENT_CATALOG.md` §2.1), so nothing downstream of ingestion needs to know whether a
reading originated from `simulator/` or a real sensor, other than the `source` field
(`synthetic` vs `edge-real`).
