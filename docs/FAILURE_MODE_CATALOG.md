# LubriSense AI — Failure Mode Catalog

Status: PHASE 0 — DRAFT FOR ACCEPTANCE
Last updated: 2026-08-17

This catalog defines the initial synthetic failure-mode library used by the simulator
(`simulator/`, Phase 3–4), the rule engine (Phase 9), and ML failure classification (Phase 11).
It is the shared vocabulary between Machine & Sensor Intelligence (`docs/ARCHITECTURE.md` §4.1)
and the `ConditionAssessment.condition` field (`docs/EVENT_CATALOG.md` §3.3).

**All numeric ranges, durations, and signal signatures below are synthetic demo assumptions
created for this reference implementation.** They are not proprietary industrial specifications and must never be
presented as validated industrial thresholds (`docs/DOMAIN_MODEL.md` §2.3,
`TECHNICAL_DECISIONS.md` ADR-001). Every value is illustrative of *shape* (which signals move,
in which direction, over what kind of timescale), not an authoritative number. Real deployments
must replace these with validated, asset-specific engineering limits.

---

## 1. Catalog Overview

| # | Failure Mode | Primary Domain | Typical Onset |
|---|---|---|---|
| 1 | Normal Operation | Lubrication system | — (baseline) |
| 2 | Gradual Restriction | Lubrication system | Slow (days–weeks) |
| 3 | Sudden Blockage | Lubrication system | Fast (minutes–hours) |
| 4 | Leakage | Lubrication system | Slow–moderate |
| 5 | Over-Lubrication | Lubrication system | Moderate |
| 6 | Low Reservoir | Lubrication system | Slow (predictable) |
| 7 | Pump Degradation | Lubrication system | Slow (weeks) |
| 8 | Sensor Drift | Data quality | Slow (weeks–months) |
| 9 | Sensor Dropout | Data quality | Sudden |
| 10 | Network Failure | Data quality / connectivity | Sudden |
| 11 | Bearing Issue Independent of Lubrication | Machine condition | Variable |

Modes 1–7 concern the lubrication-delivery system itself (§2.1 of `docs/DOMAIN_MODEL.md`). Modes
8–10 concern the observability chain, not the physical asset. Mode 11 concerns the protected
machine/bearing without implicating lubrication.

---

## 2. Normal Operation

- **Description**: All lubrication-system and machine-condition signals within configured
  baseline ranges; pump cycles complete on schedule; no fault codes.
- **Signal signature (demo)**: reservoir level within normal band; pressure and flow stable
  around baseline per cycle; pump current within expected range; bearing temperature and
  vibration stable/low relative to asset baseline.
- **Evidence language**: "All monitored signals consistent with normal operation."
- **Decision Intelligence default**: no incident raised.

## 3. Gradual Restriction

- **Description**: Progressive narrowing of flow path (e.g., partial line/circuit obstruction),
  reducing delivered lubricant over time without full blockage.
- **Signal signature (demo)**: line/circuit pressure trending upward while flow trends downward
  over a multi-day/multi-week window; cycle-completion time increasing; downstream lubrication
  point(s) show gradually reduced delivery confirmation.
- **Evidence language**: "Pressure/flow trend is consistent with a developing restriction in the
  [circuit/line]; evidence suggests gradual onset over [window]."
- **Decision Intelligence default**: `WARNING`, moderate priority, recommended window scaled to
  observed trend rate — earlier if trend is accelerating.

## 4. Sudden Blockage

- **Description**: Abrupt, near-complete obstruction of a line, distributor, or circuit.
- **Signal signature (demo)**: sharp pressure spike (or drop, depending on sensor position)
  and flow collapse within a single cycle or a few cycles; cycle-completion failure; possible
  controller fault code.
- **Evidence language**: "Signal pattern is consistent with a sudden blockage; abrupt onset
  observed within [short window]."
- **Decision Intelligence default**: `CRITICAL`, urgent priority — downstream bearing(s) are at
  immediate risk of lubricant starvation.

## 5. Leakage

- **Description**: Loss of lubricant from the line, distributor, or fitting before reaching the
  intended lubrication point.
- **Signal signature (demo)**: pressure below expected for a given pump output; reservoir level
  depleting faster than the consumption model predicts; possible flow/return-signal mismatch
  where instrumented.
- **Evidence language**: "Reservoir depletion and pressure pattern are consistent with possible
  leakage; further physical inspection recommended to confirm."
- **Decision Intelligence default**: `WARNING`→`CRITICAL` depending on depletion rate; consider
  environmental/safety impact (spilled lubricant) in priority.

## 6. Over-Lubrication

- **Description**: Excess lubricant delivered relative to the bearing's requirement, which can
  cause seal damage, increased friction/heat, or contamination.
- **Signal signature (demo)**: cycle frequency/volume above configured normal range; bearing
  temperature elevated without a corresponding load/RPM increase; reservoir depleting faster than
  expected for reasons other than leakage (i.e., pump delivering more per cycle than baseline).
- **Evidence language**: "Delivery volume/frequency is above the configured normal range;
  pattern is consistent with over-lubrication."
- **Decision Intelligence default**: `WARNING`, moderate priority; recommend controller
  cycle-parameter review (human-executed, never auto-changed — see §12 and
  `docs/ARCHITECTURE.md` §9.1).

## 7. Low Reservoir

- **Description**: Lubricant supply approaching depletion under otherwise-normal consumption.
- **Signal signature (demo)**: reservoir level trending toward a configured low threshold at a
  predictable, roughly linear rate consistent with historical consumption.
- **Evidence language**: "Reservoir level trending toward configured minimum; forecast depletion
  date is [date] at current consumption rate."
- **Decision Intelligence default**: `INFO`→`WARNING`, scheduled priority — this is the primary
  driver of refill-planning value (`docs/ARCHITECTURE.md` §12.2).

## 8. Pump Degradation

- **Description**: Progressive mechanical/electrical wear reducing pump performance
  (e.g., worn seals, motor wear, valve wear).
- **Signal signature (demo)**: pump current or runtime-per-cycle trending upward (working harder
  for the same output) while delivered pressure/flow trends downward, over a multi-week window;
  possible intermittent fault codes late in progression.
- **Evidence language**: "Pump current/runtime trend relative to delivered pressure is
  consistent with gradual pump degradation."
- **Decision Intelligence default**: `WARNING`, priority increasing as trend approaches a
  configured degradation threshold; recommend pump inspection/service window before failure.

## 9. Sensor Drift

- **Description**: A sensor's reported value slowly diverges from ground truth without an
  outright failure (e.g., calibration drift).
- **Signal signature (demo)**: slow, monotonic offset growth relative to cross-checked signals
  or historical baseline, without the step-change pattern seen in sudden faults; typically
  detected via multi-signal consistency checks (e.g., a pressure sensor drifting while
  correlated flow/pump-current signals remain consistent with the old baseline).
- **Evidence language**: "Signal is consistent with gradual sensor drift; confidence in
  downstream condition assessments for this signal is reduced accordingly."
- **Decision Intelligence default**: Not a machine-condition incident by itself; raises
  `data_quality` degradation, lowers `confidence` on any condition assessment relying on the
  affected signal, and may raise a Service Engineer–facing maintenance task for the sensor
  itself.

## 10. Sensor Dropout

- **Description**: A sensor stops reporting entirely (vs. drifting).
- **Signal signature (demo)**: readings stop arriving for a given `sensor_id` beyond the
  expected reporting interval; `DataQualityAssessment.staleness` exceeds threshold; distinct from
  Network Failure because other sensors on the same edge controller continue reporting normally.
- **Evidence language**: "Sensor [id] has not reported since [time]; treated as a data-quality
  event, not a physical-condition event, unless corroborated by other evidence."
- **Decision Intelligence default**: Same handling family as Sensor Drift — data-quality flag,
  confidence reduction on dependent assessments, Service Engineer task.

## 11. Network Failure

- **Description**: Loss of connectivity between edge and central platform (or between sensor and
  edge), affecting multiple/all signals from a given edge controller simultaneously.
- **Signal signature (demo)**: simultaneous staleness/dropout across many-to-all signals from one
  edge controller/gateway, distinguishing it from a single Sensor Dropout; `EdgeHeartbeat` events
  missing; `EdgeBufferStatus` (once reconnected) shows buffered backlog consistent with an outage
  window.
- **Evidence language**: "Connectivity loss detected for edge controller [id] from [time] to
  [time]; monitoring continued locally per edge deterministic rules; backlog received and
  reconciled on reconnect."
- **Decision Intelligence default**: No physical-condition incident from absence of data alone;
  system relies on edge local alarms (`docs/ARCHITECTURE.md` §5) during the outage and
  reconciles buffered data afterward.

## 12. Bearing Issue Independent of Lubrication

- **Description**: Machine-condition deterioration (e.g., misalignment, imbalance, fatigue,
  contamination from a non-lubrication source) that is not caused by the lubrication-delivery
  system, even though it may coexist with normal lubrication-system signals.
- **Signal signature (demo)**: vibration RMS/peak and/or bearing temperature trending outside
  baseline while all lubrication-system signals (reservoir, pressure, flow, cycle completion)
  remain within normal range — the key differentiator from Gradual Restriction/Leakage, which
  show correlated lubrication-system abnormality.
- **Evidence language**: "Machine-condition signals indicate developing bearing issue; monitored
  lubrication-system signals remain within normal range, so evidence does not support a
  lubrication-related cause. Further mechanical inspection recommended."
- **Decision Intelligence default**: `WARNING`→`CRITICAL` based on vibration/temperature
  severity; recommended action routed as a general mechanical/reliability concern, not a
  lubrication work order.

---

## 13. Causal-Language Rules

Because lubrication-system faults and machine-condition symptoms can correlate without one
causing the other, and because misattributing causality can send a technician to fix the wrong
thing, every piece of evidence and every generated explanation must observe these rules
(originating in `CLAUDE.md` "Failure Modes"):

- **Never claim direct causality from simple correlation.**
- Use calibrated language such as:
  - "evidence is consistent with…"
  - "possible lubrication-related contribution…"
  - "further inspection recommended…"
  - "insufficient evidence…"
- When lubrication-system signals are normal and only machine-condition signals are abnormal
  (Failure Mode 12), evidence must explicitly state that lubrication-related causes are *not*
  supported by current evidence, rather than remaining silent on the distinction.
- Confidence and uncertainty must always accompany a condition/decision — never present a
  single deterministic-sounding diagnosis without its confidence.
- These rules apply identically to rule-based, ML-based, and GenAI-generated language — GenAI
  explanations must reflect the same evidence and confidence as the underlying
  `ConditionAssessment`/`Decision`, never invent additional certainty
  (`docs/ARCHITECTURE.md` §7).

---

## 14. Extensibility

This catalog is the Phase 0 baseline. Future phases (Phase 4 Failure Injection Engine, Phase 11
ML Intelligence) may add finer-grained sub-modes (e.g., splitting "Pump Degradation" into
seal-wear vs. motor-wear signatures) as long as they remain within the domain boundaries defined
here and continue to observe the causal-language rules in §13 and the demo-assumption labeling
policy in `docs/DOMAIN_MODEL.md` §2.3. Any new failure mode must specify: description, signal
signature, evidence language, and Decision Intelligence default.

---

## 15. Phase 4 Implementation Notes

Phase 4 (`simulator/simulator/scenarios/`, documented in full in `docs/SCENARIO_ENGINE.md`)
implements modes 2-12 above as an injectable scenario each, driving the Phase 3 physics
model's hidden state rather than any sensor value directly. This section records where a
concrete implementation choice had to pick one specific mechanism among several this
catalog's illustrative language could support — narrowing scope for reproducibility, not
asserting a new domain fact.

- **Leakage (§5)**: this catalog's "reservoir level depleting faster than the consumption
  model predicts" is implemented as *delivered* (post-leak) flow dropping while *raw*
  (pump-drawn) flow — and therefore reservoir consumption — stays at its healthy baseline,
  representing an open-loop positive-displacement pump that draws a fixed metered volume per
  stroke regardless of a downstream leak (a common real-world lubrication-system design).
  This makes Leakage's reservoir-consumption *rate* look ordinary while its *delivered*
  lubrication (and therefore bearing condition over time) degrades — still consistent with
  "further inspection recommended," just via a different observable path than a closed-loop,
  flow-compensating controller would produce. A future phase modeling closed-loop controllers
  should treat this as the open-loop variant, not a contradiction of it.
- **Gradual Restriction vs. Sudden Blockage (§3-§4)**: implemented as the same underlying
  hidden-state parameter (`restriction_factor`) with different progression profiles (smooth
  sigmoid vs. instantaneous step) and different magnitude ceilings — not two independent
  mechanisms. This is a deliberate simplification per `docs/SCENARIO_ENGINE.md` §5.
- **Bearing Issue Independent of Lubrication (§12)**: implemented via a hidden-state
  variable (`bearing.health`) decayed on a dedicated pathway fully decoupled from every
  lubrication-path variable — chosen specifically so this mode cannot, by construction, ever
  move a lubrication-system signal, which is the property §12's differentiation depends on.
