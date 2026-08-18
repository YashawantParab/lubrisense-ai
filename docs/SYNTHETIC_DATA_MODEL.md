# Synthetic Data Model — Ground Truth vs. Observed Telemetry

Status: PHASE 4 — DRAFT FOR ACCEPTANCE
Last updated: 2026-08-17

This document defines the boundary the simulator enforces between **physical ground
truth** (the simulator's internal, hidden state) and **observed telemetry** (what a
sensor — real or synthetic — actually reports). This distinction is required by the Phase 3
brief §18 and is critical for every later ML phase: a model trained on hidden ground-truth
variables instead of realistically-noisy observed telemetry would report unrealistically
good performance that a real deployment (with only observed telemetry, never ground truth)
could never reproduce. Phase 4 (`docs/SCENARIO_ENGINE.md`) populates this same contract with
real scenario/fault data instead of always-healthy defaults — the boundary itself did not
change.

---

## 1. The two channels

| | Ground truth | Observed telemetry |
|---|---|---|
| Type | `simulator.domain.state.*` (mutable, internal) | `simulator.engine.output.SimulationReading` |
| Who sees it | The simulator itself, and (for evaluation only) `GroundTruthRecord` | Everything downstream: data quality, rules, ML, dashboards |
| Contains | `restriction_factor`, `leakage_factor`, `pump_efficiency`, `bearing_health`, `lubrication_effectiveness`, `sensor_bias`, exact `reservoir_quantity_l`, ... | `observed_value` per sensor: noisy, biased, quantized, range-clipped |
| Written to | `<output>.ground_truth.jsonl` (separate file) | `<output>.readings.jsonl` (separate file) |
| ML may use it as a feature? | **Never.** | Yes — this is the only legitimate feature source. |

The two are never merged into one record type. `simulator.engine.output.SimulationReading`
and `GroundTruthRecord` are distinct dataclasses with disjoint field sets — proven
structurally in `tests/test_ground_truth_separation.py`, not just documented.

---

## 2. Ground truth (`GroundTruthRecord`)

One record per machine per tick. Fields:

`simulation_timestamp`, `tenant_id`, `asset_id`, `scenario` (highest-severity active
scenario's type, or `"NORMAL"` when none is active — see §2.1), `severity` (that scenario's
lifecycle state, or `"NONE"`), `affected_component` (that scenario's target id, or `null`),
`operating_state`, `load_percent`, `ambient_temperature_c`, `pump_efficiency`,
`reservoir_quantity_l`, `reservoir_capacity_l`, `reservoir_level_state`
(`NORMAL`/`LOW`/`CRITICAL`/`EMPTY`, Phase 4), `network_state` (`CONNECTED`/`DISCONNECTED`,
Phase 4), `refill_event` (`bool`, Phase 4 — true only on the tick a refill is triggered),
and, nested per bearing/circuit: `lubrication_effectiveness`, `health` (bearings),
`restriction_factor`, `leakage_factor` (circuits).

Ground truth exists for exactly one purpose: **evaluating** a later model or rule against
what was actually true in the simulation (e.g., "did the anomaly detector flag this window
when `restriction_factor` was actually elevated?"). It is never an input to a model.

### 2.1 `scenarios` (Phase 4) — the authoritative multi-fault record

`scenarios: tuple[ScenarioGroundTruth, ...]` carries one entry per currently-*active*
scenario instance: `instance_id`, `scenario_type`, `lifecycle_state`, `severity`,
`target_type`, `target_id`, `started_at_sim_seconds`, `elapsed_seconds`. When more than one
scenario is simultaneously active (`docs/SCENARIO_ENGINE.md` §10), this list — not the
singular `scenario`/`severity`/`affected_component` fields above — is the complete,
attributable ground truth; the singular fields are kept only as a convenience summary of
the single highest-severity instance, for readability and Phase-3-era backward
compatibility.

---

## 3. Observed telemetry (`SimulationReading`)

One record per sensor per tick — only for sensors that actually exist in the Phase 2
database for that machine (`docs/SIMULATOR.md` §3). Fields: `simulation_timestamp`,
`tenant_id`, `asset_id`, `component_id` (the specific entity the sensor is attached to —
e.g. a specific bearing or circuit id, not just the machine), `sensor_id`,
`measurement_type`, `true_value`, `observed_value: float | None`, `unit`, `quality`,
`operating_state`, `cycle_id`, `simulation_state`.

`observed_value` is `None` precisely when Phase 4's Sensor Dropout or Network Failure
scenarios make that tick's observation genuinely unavailable (`quality` is `MISSING` or
`COMMUNICATION_LOSS` respectively — `docs/SCENARIO_ENGINE.md` §8). `true_value` is **never**
`None` in that case — the simulator keeps computing the real physical value every tick
regardless of whether anything downstream would actually receive it; only the *observation*
is withheld. This is a deliberate, structural way of avoiding the anti-pattern the Phase 4
brief warns against directly: "do not use zero as the default representation of missing
data."

**Why does `SimulationReading` carry `true_value` if this document says ground truth and
telemetry are separate?** `true_value` here is the *unnoised physical value a specific
sensor would be measuring* (e.g., the actual circuit pressure before that pressure sensor's
noise/bias/quantization/clipping is applied) — it is a per-sensor quantity, not the deeper
hidden state (`restriction_factor`, `pump_efficiency`, etc.) that produced it. It is
included in the internal engine contract (Phase 3 brief §17) so Phase 3's own tests can
verify the sensor model is behaving correctly (`observed_value` should track `true_value`
within the configured noise/bias bounds) and so a future model-evaluation harness can
measure sensor-level noise characteristics. **A Phase 6 telemetry adapter must drop
`true_value` when converting a `SimulationReading` into a `TelemetryReading`
(`docs/EVENT_CATALOG.md` §2.1) — only `observed_value` maps onto `TelemetryReading.value`.**
This is the one place this document draws a distinction *within* the observed-telemetry
channel: "internal engine contract" (both values, for testing/evaluation) vs. "what a real
deployment's telemetry pipeline actually carries" (`observed_value` only).

---

## 4. Why this separation matters

- **Unrealistic ML performance**: a fault-detection model that could see
  `restriction_factor` directly wouldn't need to detect anything — it would trivially
  threshold the ground-truth variable itself. Real deployments never have this variable;
  training or evaluating against it would produce a model that looks excellent in this
  reference implementation and fails immediately against real sensors.
- **Honest data-quality/rules testing**: rules and the Phase 7 data-quality engine must
  work from the same `observed_value` noise characteristics a real sensor would produce —
  testing them against clean ground truth would hide bugs that only appear with real noise.
- **Model evaluation still needs ground truth** — just as a separate, clearly-labeled
  channel used only to *score* predictions after the fact, never to *make* them.

---

## 5. Simulator-internal `SensorQuality` vs. the Phase 7 Data Quality Engine

`SimulationReading.quality` (`GOOD` / `SUSPECT` / `MISSING` / `COMMUNICATION_LOSS` / `BAD` /
`UNCERTAIN` / `INVALID`) is a coarse signal the simulator itself can assert: `SUSPECT` when
a reading clips its valid range (Phase 3), `MISSING`/`COMMUNICATION_LOSS` when Sensor
Dropout/Network Failure withhold the observation entirely (Phase 4,
`docs/SCENARIO_ENGINE.md` §8) — `UNCERTAIN`/`INVALID`/`BAD` remain reserved, not yet
produced by any Phase 3/4 code path. This is **not**
the Phase 7 `DataQualityAssessment` (`docs/EVENT_CATALOG.md` §2.2), which independently
evaluates completeness/staleness/plausibility from the observed telemetry stream itself,
with no access to the simulator's internal state. The two must stay conceptually separate:
Phase 7 should be able to compute a `DataQualityAssessment` from `SimulationReading`s (or
real telemetry) alone, never by reaching into `GroundTruthRecord`.

---

## 6. Summary diagram

```
GROUND TRUTH (hidden)                         OBSERVED TELEMETRY (what downstream sees)
──────────────────────                        ──────────────────────────────────────────
restriction_factor        ─┐
leakage_factor             │  physics layer     true_value  ──sensor model──> observed_value
pump_efficiency            ├─ (simulator.physics) │  (noise, bias,              │
bearing_health             │                      │   resolution,               │
lubrication_effectiveness ─┘                      │   valid_range clip)         │
                                                    ▼                            ▼
                                          SimulationReading.true_value   SimulationReading.observed_value
                                          (internal contract only)       (-> TelemetryReading.value, Phase 6)

GroundTruthRecord (separate file/stream) ── evaluation only, never an ML feature source
```
