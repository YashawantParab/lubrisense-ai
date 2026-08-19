"""Supervised label schema (Phase 11 brief §9-§11) and the scenario-type -> label mapping.

This module is the ONLY place that maps a simulator scenario type name (a plain string
read from ground-truth JSONL, never an imported simulator type — `ml_service` does not
depend on `simulator`) onto a `FailureLabel`. The mapping is a label-derivation concern,
never a feature. See `docs/ML_ARCHITECTURE.md` "Label schema" for the documented rationale
for each choice, in particular:

- `SENSOR_DRIFT`/`SENSOR_DROPOUT` merge into `SENSOR_FAULT` (§10): both are sensing-path
  problems, not equipment-lubrication problems, and the observable evidence (missingness,
  quality flags) does not reliably distinguish which specific sensor fault occurred.
- `NETWORK_FAILURE` is NOT mapped into any equipment-failure label (§10): connectivity loss
  is a data-quality state (already handled by the Phase 7 quality engine), not an equipment
  condition. Runs using it are excluded from supervised classification training/evaluation
  and used only for anomaly-model / robustness evaluation.
- `OVER_LUBRICATION` and `LOW_RESERVOIR` are real simulator failure modes but fall outside
  the 8-class schema the Phase 11 brief fixes (§9). Rather than inventing a 9th/10th class
  the brief does not ask for, both map to `UNKNOWN` — the same bucket used for genuinely
  ambiguous/low-confidence model output (§11). This is a deliberate, documented choice, not
  an omission.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class FailureLabel(StrEnum):
    NORMAL = "NORMAL"
    RESTRICTION = "RESTRICTION"
    BLOCKAGE = "BLOCKAGE"
    LEAKAGE = "LEAKAGE"
    PUMP_DEGRADATION = "PUMP_DEGRADATION"
    SENSOR_FAULT = "SENSOR_FAULT"
    INDEPENDENT_BEARING_ISSUE = "INDEPENDENT_BEARING_ISSUE"
    UNKNOWN = "UNKNOWN"


#: Scenario type names that must never be used to derive a supervised label — the run may
#: still exist in a dataset (e.g. for anomaly/robustness evaluation) but its samples are
#: excluded from classifier training/evaluation via `EXCLUDED_FROM_SUPERVISED`.
EXCLUDED_FROM_SUPERVISED: frozenset[str] = frozenset({"NETWORK_FAILURE"})

_SCENARIO_TO_LABEL: dict[str, FailureLabel] = {
    "GRADUAL_RESTRICTION": FailureLabel.RESTRICTION,
    "SUDDEN_BLOCKAGE": FailureLabel.BLOCKAGE,
    "LEAKAGE": FailureLabel.LEAKAGE,
    "PUMP_DEGRADATION": FailureLabel.PUMP_DEGRADATION,
    "SENSOR_DRIFT": FailureLabel.SENSOR_FAULT,
    "SENSOR_DROPOUT": FailureLabel.SENSOR_FAULT,
    "INDEPENDENT_BEARING_FAULT": FailureLabel.INDEPENDENT_BEARING_ISSUE,
    "OVER_LUBRICATION": FailureLabel.UNKNOWN,
    "LOW_RESERVOIR": FailureLabel.UNKNOWN,
}


def label_for_scenario_type(scenario_type: str) -> FailureLabel:
    """Maps a bare scenario-type string onto its `FailureLabel`, ignoring lifecycle/severity.

    Used for dataset-level bookkeeping that needs a label-shaped grouping key without a
    ground-truth tick to resolve (e.g. `ml_service.datasets.builder`'s run-stratification
    group key) — never for per-sample labeling, which must go through
    `label_for_ground_truth` so lifecycle state and multi-scenario severity are respected.
    """
    return _SCENARIO_TO_LABEL.get(scenario_type, FailureLabel.UNKNOWN)


#: Ground-truth lifecycle states (`simulator.scenarios.types.ScenarioLifecycleState` values,
#: read as plain strings) that count as "the fault is evidenced enough to label the tick
#: with it." `SCHEDULED` (not yet started) and a bare `ACTIVE` immediately at onset with
#: ~zero severity are treated as still-`NORMAL` for labeling purposes — matching
#: `developing_threshold` being the point the simulator itself calls a fault meaningfully
#: present. `COMPLETED` scenarios (self-recovered) are also not labeled as their fault.
_LABELED_LIFECYCLE_STATES = frozenset({"DEVELOPING", "SEVERE", "RECOVERING"})


def label_for_ground_truth(
    scenarios: list[dict[str, Any]],
) -> tuple[FailureLabel | None, str | None]:
    """Resolve one tick's supervised label from its `GroundTruthRecord.scenarios` list
    (already parsed from JSON — each entry has `scenario_type`, `lifecycle_state`,
    `severity`). Returns `(label, source_scenario_type)`; `source_scenario_type` is the raw
    scenario-type string used only for dataset bookkeeping/reporting, never as a feature.

    Returns `(None, None)` when the tick belongs to a `NETWORK_FAILURE`-only run (excluded
    from supervised labels entirely — the caller must drop the sample from classification
    datasets, not label it `NORMAL`, which would be actively wrong).

    Multiple simultaneously active scenarios (multi-fault composition, §55): this returns
    the label of the single highest-severity active scenario. Single-label classifiers
    cannot represent true multi-fault ground truth — this is a documented limitation
    (`docs/MODEL_CARD.md` "Known limitations"), not a claim that multi-fault is solved.
    """
    active = [s for s in scenarios if s.get("lifecycle_state") in _LABELED_LIFECYCLE_STATES]
    if not active:
        return FailureLabel.NORMAL, None

    non_network = [s for s in active if s.get("scenario_type") not in EXCLUDED_FROM_SUPERVISED]
    if not non_network:
        return None, None

    best = max(non_network, key=lambda s: float(s.get("severity", 0.0)))
    scenario_type = str(best["scenario_type"])
    return _SCENARIO_TO_LABEL.get(scenario_type, FailureLabel.UNKNOWN), scenario_type
