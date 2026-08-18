# Scenario Engine — Phase 4 Implementation

Status: PHASE 4 — DRAFT FOR ACCEPTANCE
Last updated: 2026-08-17

This document describes the failure-injection / scenario engine implemented in
`simulator/simulator/scenarios/`: architecture, progression profiles, targeting, the
per-failure-mode physical mapping, multi-fault composition rules, recovery, the ground-truth
extensions, and known limitations.

**Everything this engine produces is a DEMO / SYNTHETIC SCENARIO.** Every numeric severity
coefficient, onset duration, and threshold in `simulator/config/scenarios/*.yaml` is a
simulation coefficient chosen to demonstrate believable *shape* — never a validated
production failure threshold. See each YAML file's header disclaimer and
`docs/DOMAIN_MODEL.md` §2.3.

---

## 1. Core principle

Phase 4's one non-negotiable rule (brief §1): a scenario **never** writes a sensor value.

```
NOT THIS:                              THIS:
if scenario == "blockage":             scenario computes severity(t)
    pressure = 200                     → severity shifts a hidden physical parameter
    flow = 0                             (e.g. circuit.restriction_factor)
                                        → the existing Phase 3 physics model (unchanged)
                                          derives pressure/flow from that parameter
                                        → the existing Phase 3 sensor model (unchanged)
                                          derives an observed reading from the physics
```

Every scenario effect in this codebase is implemented as an additional **offset or target**
passed into a Phase 3 physics function that already existed before Phase 4
(`step_natural_variation(restriction_offset=...)`, `step_efficiency(efficiency_offset=...)`,
`apply_independent_wear(target_health=...)`, the cycle controller's
`reservoir_availability`/`volume_multiplier`). None of those functions know what a
"scenario" is — they only ever receive a number that happens to differ from its healthy
default (0.0, or the default coefficient). This is enforced structurally: search
`simulator/scenarios/effects.py` — it never imports `simulator.engine.output` or touches a
`SimulationReading`.

---

## 2. Architecture

```
simulator/scenarios/
  types.py       ScenarioType, ProgressionType, ScenarioLifecycleState, ScenarioTargetType,
                 VALID_TARGET_TYPES (the targeting compatibility table)
  progression.py compute_severity(profile, elapsed_s, onset_s, ...) -> float in [0,1]
                 (pure, deterministic, no RNG)
  definition.py  ScenarioDefinition (pydantic) — the YAML-loaded shape of one failure mode
  loader.py      load_scenario_definition(name) / list_available_scenarios()
  targeting.py   resolve_target(topology, target_type, explicit) -> real Phase 2 entity id
  instance.py    ScenarioInstance (mutable runtime: lifecycle/severity) + create_instance()
  effects.py     build_effects(instances, topology, config, activation_edge)
                 -> ScenarioEffects (aggregated hidden-state adjustments for one tick)
  scheduler.py   ScenarioScheduler (owns instances, steps them, aggregates effects) +
                 AutoRefillPolicy (standalone, not a scenario — see §9)
```

`SimulationEngine` (`simulator/engine/simulation_engine.py`) owns one `ScenarioScheduler`.
Each tick: `scheduler.advance()` steps every instance's lifecycle, the engine captures any
newly-activated Sensor Drift instance's starting bias, `scheduler.build_effects()` produces
one `ScenarioEffects` snapshot, and the engine passes that snapshot's values into the
existing physics functions in the same order Phase 3 already called them.

---

## 3. Scenario definition vs. scenario instance

- **`ScenarioDefinition`** (config, immutable, one per YAML file): scenario type, target
  type, default progression/severity/lifecycle/recovery, and `effect_params` (numeric
  magnitude coefficients specific to that scenario type — see §5).
- **`ScenarioInstance`** (runtime, mutable, one per active fault in a given simulation run):
  a definition bound to a specific resolved target id, start time, and severity ceiling,
  carrying its own `severity`/`lifecycle_state` that change every tick.

This split is what makes `--scenario gradual_restriction --severity 0.6 --target C2` work:
the same definition, instantiated with different runtime parameters, without editing the
YAML file.

---

## 4. Lifecycle

```
SCHEDULED -> ACTIVE -> [DEVELOPING] -> [SEVERE] -> [RECOVERING] -> COMPLETED
```

- **SCHEDULED**: `sim_seconds < start_seconds`. Severity is 0.
- **ACTIVE**: the instance has started; severity follows its progression profile.
- **DEVELOPING**: severity has crossed `lifecycle.developing_threshold`.
- **SEVERE**: severity has crossed `lifecycle.severe_threshold` — `null` for scenario types
  that never escalate to a severe state by design (Over-Lubrication, Sensor Drift, Sensor
  Dropout, Network Failure — see each YAML file).
- **RECOVERING** / **COMPLETED**: only reachable when `recovery.enabled: true` (most
  catalog scenarios leave this `false` — see §9). Severity decays linearly from its peak
  back to 0 over `recovery.duration_seconds`; the instance then permanently stops
  (`is_active` becomes `False`) — Phase 4 does not re-trigger a completed instance.

## 5. Progression profiles

`simulator.scenarios.progression.compute_severity` implements all six required profiles as
pure, deterministic functions of elapsed time (no RNG — determinism, §13):

| Profile | Shape | Used by (default) |
|---|---|---|
| `STEP` | Instant full severity | Sudden Blockage, Low Reservoir (one-shot trigger) |
| `LINEAR` | Even ramp over `onset_seconds` | Leakage, Over-Lubrication, Sensor Drift, Independent Bearing Fault |
| `EXPONENTIAL` | Slow start, accelerating, ~95% by `onset_seconds` | Pump Degradation |
| `SIGMOID` | S-curve, slow-fast-slow | Gradual Restriction |
| `INTERMITTENT` | Deterministic square wave (`period_s`, `duty_cycle`) | Sensor Dropout, Network Failure |
| `CYCLIC` | Smooth 0↔1 oscillation | (available; no catalog scenario defaults to it) |

The scenario's own `effect_params` coefficient then scales this generic `[0,1]` severity
into a physical unit (e.g. `severity * max_restriction_factor`).

---

## 6. Targeting

`simulator.scenarios.types.VALID_TARGET_TYPES` is the compatibility table Phase 4 brief §17
requires:

| Scenario type | Target type |
|---|---|
| Gradual Restriction, Sudden Blockage, Leakage | `CIRCUIT` |
| Over-Lubrication | `LUBRICATION_SYSTEM` |
| Low Reservoir | `RESERVOIR` |
| Pump Degradation | `PUMP` |
| Sensor Drift, Sensor Dropout | `SENSOR` |
| Network Failure | `MACHINE` |
| Independent Bearing Fault | `BEARING` |

`ScenarioDefinition` itself validates `target_type == VALID_TARGET_TYPES[scenario_type]` at
load time (a config-authoring error fails immediately, not at runtime).
`simulator.scenarios.targeting.resolve_target` then resolves an instance's *actual* target
against the live `MachineTopology`: an explicit `--target` (a human-readable code — bearing
position, circuit code, sensor code — or a UUID string) is validated against the real
entities of the required type on that machine; omitting `--target` selects the first
available entity of that type. An unknown code, a random UUID, or a real id of the *wrong*
entity type (e.g. a circuit id passed where a bearing was required) all raise
`ScenarioTargetError` before the simulation starts.

---

## 7. Per-failure-mode physical mapping

Every mapping below is additive on top of the Phase 3 healthy default (0 severity ⇒
identical to Phase 3 behavior) and clipped to a valid physical range by the *receiving*
physics function, never by the scenario code itself.

| Failure mode | Hidden-state effect | Physics pathway |
|---|---|---|
| **Gradual Restriction** / **Sudden Blockage** | `circuit.restriction_factor` += `severity * max_restriction_factor` | `circuit.step_natural_variation` shifts its mean-reversion target; `solve_operating_point` derives higher required pressure + lower raw/delivered flow |
| **Leakage** | `circuit.leakage_factor` += `severity * max_leakage_factor` | Same `step_natural_variation` call, different parameter; `solve_operating_point` derives lower *delivered* flow only — required pressure (governed by `restriction_factor` alone) is untouched, which is the deliberate physical distinction from restriction (see below) |
| **Pump Degradation** | `pump.efficiency` target -= `severity * max_efficiency_loss` | `pump.step_efficiency`'s relaxation target is shifted down; pressure-rise time and achievable flow degrade through the *existing* efficiency-dependent equations |
| **Over-Lubrication** | Delivered/raw flow ×= `1 + severity * max_extra_volume_fraction`; a small extra bearing-temperature term ×= severity | `LubricationCycleController.step(volume_multiplier=...)`; `bearing.step_temperature(over_lubrication_severity=...)` |
| **Low Reservoir** | One-shot: `reservoir.quantity_l` set to `100% - severity*(100% - min_target_level_percent)` *at activation only* | `reservoir_physics.refill()` (same function §9 uses); consequences (`reservoir_physics.availability_factor`) then emerge from **unmodified** ongoing consumption |
| **Independent Bearing Fault** | `bearing.health` relaxes toward `1 - severity * max_health_loss` via a *dedicated* time constant | `bearing.apply_independent_wear` — completely decoupled from `step_health`'s starvation-driven degradation; `lubrication_effectiveness` is never touched |
| **Sensor Drift** | Effective sensor bias = `drift_base_bias + sign * severity * max_bias_fraction_of_range * (valid_range span)` | Passed as the `bias` argument to `sensor_models.observe()` for that tick only — `true_value` is computed identically to a healthy run |
| **Sensor Dropout** | That sensor's reading this tick: `observed_value=None`, `quality=MISSING` | Reading collection (`SimulationEngine._collect_readings`) — `true_value` still computed normally |
| **Network Failure** | Every sensor on the machine, this tick: `observed_value=None`, `quality=COMMUNICATION_LOSS` | Same collection path, machine-wide instead of one sensor |

### Why Leakage is not "Restriction with a different name" (brief §8)

Flow is split into two figures (`simulator.physics.circuit.CircuitOperatingPoint`):
`raw_flow_cm3_min` (what the pump draws from the reservoir — governed by
`restriction_factor` and pump efficiency only) and `delivered_flow_cm3_min` =
`raw_flow_cm3_min * (1 - leakage_factor)` (what reaches the lubrication point). Restriction
reduces *both* together and raises required pressure; leakage reduces only the delivered
figure and leaves required pressure — and therefore raw/reservoir-side consumption —
essentially at its healthy baseline. This produces the opposite pressure signature
(restriction: pressure rises; leakage: pressure stays flat or slightly falls via
`circuit_backpressure_bar`'s leak-relief term) and is what
`tests/test_scenario_distinctness.py` and `tests/test_scenario_signal_signatures.py` verify.

Per-circuit delivery confirmation (which drives that circuit's bearing's
`lubrication_effectiveness` via `on_cycle_result`) is judged against that circuit's own fair
share of the cycle's target volume (`CircuitState.delivered_volume_cm3` vs.
`base_volume_per_cycle_cm3 / circuit_count`) — not merely "any nonzero flow" — so Leakage's
reduced delivered volume is what actually starves the served bearing over time, even though
the overall cycle (judged by raw/commanded volume, matching what a real progressive
controller can actually detect) may still report `SUCCESS`.

### Emergent shared-cycle coupling

The flagship's two circuits share one pump and one `LubricationCycleController` (matching
the real centralized-lubrication topology, `docs/DOMAIN_MODEL.md` §2.1: one controller
drives the whole distributor). `required_pressure` for the *cycle* is the maximum across all
circuits it serves. A severe fault on one circuit (e.g. Sudden Blockage on C1) can therefore
delay or fail delivery to the *other*, unaffected circuit (C2) too, since both circuits
deliver during the same `FLOW_DELIVERY` window and a `PRESSURE_BUILD` timeout blocks the
whole cycle. Visually validated in `data/conveyor_000_sudden_blockage_8h.png`: both bearings'
vibration/temperature rise, the targeted one measurably more. This is a real, physically
defensible consequence of a shared centralized system, not a bug — flagged here so it is not
mistaken for cross-circuit effect "leakage" in the ground truth (the *leakage_factor* /
*restriction_factor* ground-truth fields for the untargeted circuit remain unchanged; only
its *delivery timing*, a shared-resource effect, is affected).

---

## 8. Network Failure vs. Sensor Dropout vs. Sensor Drift

All three are "data quality" faults (`docs/FAILURE_MODE_CATALOG.md` §9-§11), deliberately
represented with different mechanisms:

- **Sensor Drift**: the sensor keeps reporting every tick; only its bias grows.
  `quality` stays `GOOD` (or `SUSPECT` if the drifted value clips its valid range) — a data
  consumer sees plausible-looking but increasingly wrong numbers, exactly the "not
  necessarily a machine fault" case the brief highlights.
- **Sensor Dropout**: one sensor stops reporting (`quality=MISSING`, `observed_value=None`);
  every other sensor on the machine continues normally.
- **Network Failure**: *every* sensor on the machine stops reporting at once
  (`quality=COMMUNICATION_LOSS`) — the whole-machine simultaneity is the distinguishing
  signal from a single Sensor Dropout (`docs/FAILURE_MODE_CATALOG.md` §11).

**Precedence** when more than one of these could apply to the same sensor in the same tick
(`simulator.scenarios.effects.build_effects` docstring, enforced in
`SimulationEngine._collect_readings`): **Network Failure > Sensor Dropout > Sensor Drift.**
A sensor with no connectivity has no working value regardless of its own dropout/drift
state; a sensor that isn't reporting at all has no drifted value to report. Verified in
`tests/test_scenario_quality_semantics.py::test_network_failure_outranks_sensor_dropout_for_the_same_sensor`.

Real edge buffering/store-and-forward behavior for Network Failure is explicitly **not**
implemented in Phase 4 (brief §14) — `NetworkState.DISCONNECTED` is recorded in ground truth
as the hook Phase 5 (Edge Controller) and Phase 6 (Telemetry Pipeline) will attach real
buffering logic to.

---

## 9. Refill (not a failure mode)

Per brief §24, reservoir refill is a synthetic **operational** event, architecturally
separate from the scenario engine:

- `simulator.physics.reservoir.refill(reservoir, to_percent)` — already existed in Phase 3,
  unused until now.
- `simulator.scenarios.scheduler.AutoRefillPolicy` — a standalone policy (level threshold +
  dwell delay) the engine checks every tick regardless of whether any scenario is active
  (`--refill-threshold`/`--refill-to`/`--refill-delay` CLI flags). Low Reservoir's own YAML
  sets `recovery.enabled: false` — a low reservoir does not fix itself; only an explicit
  refill (policy-driven or a direct `reservoir.refill()` call, e.g. in a test) restores it.
- `GroundTruthRecord.refill_event: bool` is `True` on exactly the tick a refill occurs
  (`tests/test_refill.py::test_refill_is_recorded_in_ground_truth_only_on_the_triggering_tick`),
  never retroactively.

The observed `RESERVOIR_LEVEL` sensor responds to a refill through the ordinary sensor
model — there is no special-cased "refill reading."

---

## 10. Multi-fault composition and precedence

`simulator.scenarios.effects.build_effects` aggregates every active instance each tick.
Composition rules (also documented as the function's own docstring, so the code and this
document cannot silently drift apart):

1. **Independent parameters on the same target compose freely.** A circuit can be both
   restricted and leaking at once — `circuit_restriction_offset` and
   `circuit_leakage_offset` are tracked separately and both applied.
2. **The same parameter, same target, multiple instances: sums additively**, then the
   *receiving* physics function clips to its valid range (e.g. `restriction_factor` clipped
   to `[0, 1]`) — composition can saturate but never overflow or go non-physical.
3. **Independent Bearing Fault**: multiple instances on the same bearing take the *minimum*
   target health (the more severe fault wins — health cannot be un-degraded by a milder
   concurrent instance).
4. **Over-Lubrication**: multiple instances on the same lubrication system take the
   *maximum* volume multiplier.
5. **Sensor observability** (§8): `NETWORK_FAILURE > SENSOR_DROPOUT > SENSOR_DRIFT`.
6. **Low Reservoir**: fires only on the tick an instance's `activation_edge` occurs (first
   tick it becomes active) — a second Low Reservoir instance targeting the same reservoir
   later would re-trigger the one-shot set, which is intentional (representing a second,
   independent depletion-to-low event).

Verified for at least the three brief-mandated combinations (§16) in
`tests/test_scenario_multi_fault.py`: restriction+sensor drift, low-reservoir+network-failure,
bearing-issue+sensor-dropout, plus a three-scenario simultaneous smoke test.

---

## 11. Ground truth extensions

`GroundTruthRecord` (Phase 3) gains (Phase 4 brief §22):

- `scenarios: tuple[ScenarioGroundTruth, ...]` — every *active* instance's
  `instance_id`, `scenario_type`, `lifecycle_state`, `severity`, `target_type`, `target_id`,
  `started_at_sim_seconds`, `elapsed_seconds`. This is the authoritative multi-fault record.
- `scenario`/`severity`/`affected_component` (Phase 3 singular fields) are kept, populated
  from the *highest-severity* active instance (or `"NORMAL"`/`"NONE"`/`None` when nothing is
  active) — a convenience summary, not the source of truth once more than one scenario is
  active.
- `reservoir_level_state: str | None` — `NORMAL`/`LOW`/`CRITICAL`/`EMPTY`, computed purely
  from `level_percent` (`simulator.physics.reservoir.level_state`).
- `network_state: str` — `CONNECTED`/`DISCONNECTED` (Phase 4 only ever produces these two;
  `DEGRADED` is a reserved hook for Phase 5+).
- `refill_event: bool` — true only on the triggering tick (§9).

None of these fields, nor any Phase 3 ground-truth field, ever appears on
`SimulationReading` — enforced structurally by
`tests/test_ground_truth_separation.py` (unchanged from Phase 3) and re-verified for the new
fields' *absence* from the reading schema.

---

## 12. CLI

```
python -m simulator run --asset-code L1-7B43-M000 --duration 24h --seed 42 \
    --scenario gradual_restriction --scenario-start 4h --severity 1.0 \
    --output data/conveyor_000_gradual_restriction_24h
```

- `--scenario NAME` (repeatable): activate a failure mode using its YAML defaults.
- `--scenario-start`/`--severity`/`--target`/`--progression`: override every `--scenario`
  given (the common single-fault case). For independent per-scenario overrides in a
  multi-fault run, use `--scenario-plan <yaml>` instead (a list of scenario entries, each
  with its own overrides) — it takes priority over `--scenario` if both are given.
- `--refill-threshold`/`--refill-to`/`--refill-delay`: configure the standalone
  `AutoRefillPolicy` (disabled by default).

Defaults come from each scenario's YAML file, not required CLI flags — a bare
`--scenario gradual_restriction` is a complete, valid invocation (brief §20: "avoid a
fragile CLI with dozens of mandatory parameters").

## 13. Manifest / reproducibility

`RunMetadata` (Phase 3) gains `run_id`, `scenario_engine_version`
(`simulator.__scenario_engine_version__` — bumped independently of the overall
`simulator_version` when scenario semantics change), `scenario_config_version`
(`simulator.scenarios.SCENARIO_CONFIG_VERSION`), `scenarios` (the list of activated
scenario names), and `readings_path`/`ground_truth_path` — matching Phase 4 brief §21 in
full. Re-running the same CLI invocation against the same database and config files
reproduces byte-identical `SimulationReading`/`GroundTruthRecord` streams
(`tests/test_engine_scenario_determinism.py`), including for `INTERMITTENT`-progression
scenarios (Sensor Dropout, Network Failure), since `compute_severity` is a pure function of
elapsed time with no RNG.

---

## 14. Flagship reference dataset and visual validation

Generated via:

```
uv run python -m simulator run --asset-code L1-7B43-M000 --duration 24h --seed 42 \
    --scenario gradual_restriction --scenario-start 4h --severity 1.0 \
    --output data/conveyor_000_gradual_restriction_24h

uv run python scripts/validate_plots.py \
    --readings data/conveyor_000_gradual_restriction_24h.readings.jsonl \
    --ground-truth data/conveyor_000_gradual_restriction_24h.ground_truth.jsonl \
    --output data/conveyor_000_gradual_restriction_24h.png
```

24 simulated hours, 15s implicit DEMO-mode step reused (5s actual — `--mode` defaults
apply), 4 healthy hours before the scenario starts. Visual validation (plot committed only
as this document's description, not the underlying dataset — see §"Generated datasets") shows
exactly the qualitative sequence Phase 4 brief §18/§29 requires:

1. **0-4h (healthy)**: normal shift-driven cyclic pressure/current pulses, flat ground truth.
2. **4h+ (scenario active, ground truth diverges immediately)**: `GRADUAL_RESTRICTION`
   severity and the targeted circuit's `restriction_factor` begin climbing (sigmoid shape);
   the *other*, untargeted circuit's ground truth stays flat — confirming per-circuit
   targeting precision.
3. **6h+ (machine running, lubrication-path deviation visible immediately)**: each
   completed cycle's peak `PRESSURE` and `PUMP_CURRENT` climb cycle-over-cycle as
   restriction grows — a real, sensor-visible trend within the first few affected cycles.
4. **~14-16h+ (bearing consequence, clearly lagged)**: both bearings' `VIBRATION_RMS` and
   `BEARING_TEMPERATURE` rise well after the pressure/current trend was already visible
   (the targeted circuit's own bearing rising further than the other — see §7's
   "shared-cycle coupling" note for why the other bearing is affected at all, just less).
5. **~21h+ (severe)**: cycles begin reporting `FAILED` (pressure-build timeout) as required
   pressure exceeds the pump's `max_pressure_bar` ceiling.

Reservoir level, RPM/load: unaffected by the scenario, exactly matching the healthy Phase 3
pattern — confirming the scenario's effect is scoped to what it should touch. No NaN/inf/
negative-impossible values across the dataset (scanned directly, matching
`tests/test_scenario_stability.py`'s automated equivalent).

Additional small reference datasets generated the same way, one per remaining catalog
scenario (`sudden_blockage`, `leakage`, `over_lubrication` — implicit via tests,
`low_reservoir` — implicit via tests, `pump_degradation`, `sensor_drift`,
`sensor_dropout`/`network_failure` — implicit via tests, `independent_bearing_fault`), each
visually confirming its own distinct signature (§7, §10) — `sudden_blockage` and `leakage`
and `independent_bearing_fault` plots were inspected directly; `over_lubrication`,
`low_reservoir`, `sensor_dropout`, and `network_failure` were validated via their automated
signal-signature/quality-semantics tests (`tests/test_scenario_signal_signatures.py`,
`tests/test_scenario_quality_semantics.py`) rather than individually plotted, since their
required signatures (reservoir depletion rate, missing-observation quality labels) are
exact numeric assertions better suited to automated tests than visual inspection.

Generated datasets are not committed (`.gitignore`: `simulator/data/`,
`simulator/**/*.jsonl`, `simulator/**/*.png`) — regenerate with the commands above.

---

## 15. Limitations

- The distributor-flow-split model (Phase 3, unchanged) divides pump capacity evenly across
  circuits; a scenario targeting one circuit therefore affects the *shared cycle timing* for
  all circuits on that lubrication system (§7's "emergent shared-cycle coupling"), which is
  physically defensible but means per-circuit isolation is not perfect.
- Sensor Drift's magnitude is specified as a fraction of the sensor's configured
  `valid_range` — a reasonable, unit-agnostic default, but not calibrated against any real
  sensor's actual drift characteristics.
- Onset durations for slow real-world failure modes (Pump Degradation, Sensor Drift: real
  "weeks-months") are compressed to 2-3 simulated days so they are observable within
  `TRAINING`-mode dataset sizes — explicitly a demo-scale compromise, not a claim about real
  onset timing.
- Recovery (§4) is a simple linear severity decay when enabled; only `low_reservoir`-style
  scenarios use the standalone refill mechanism instead. No scenario models a partial,
  technician-driven repair sequence (that is Phase 17, Maintenance Workflow's territory).
- Network Failure/Sensor Dropout do not yet interact with any edge buffering or
  store-and-forward concept — that is Phase 5/6, as scoped (brief §14, §35).
- `ScenarioLifecycleState.SEVERE`'s threshold is per-scenario-type config, not derived from
  any validated engineering limit — see each YAML file's disclaimer.
