"""Plain-data snapshots rules operate on — never live ORM objects, so every rule stays a
pure function testable without a database (Phase 9 brief §2's "keep rule logic out of API
handlers", mirroring `app.data_quality.domain.context`/`app.baselines.domain.context`'s own
convention).

Built by `app.rules_engine.services.rule_engine.RuleEngine` from persisted `Telemetry`
(Phase 6), `SensorQualityState` (Phase 7), and `BaselineProfile` (Phase 8) — never from the
simulator's ground truth (Phase 9 brief §3, mandatory).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import DeviationClassification


@dataclass(frozen=True)
class SignalEvaluation:
    """One measurement type on one component, evaluated against its resolved (ACTIVE-only,
    Phase 9 brief §43) `STANDARD`-kind baseline via `app.baselines.services.
    deviation_service` — the unit every single-signal deviation rule
    (`app.rules_engine.rules.single_signal`) consumes."""

    measurement_type: str
    component_type: str
    component_id: uuid.UUID | None

    sample_count_in_window: int
    eligible: bool
    """`False` means fewer than `min_sample_count` eligible (GOOD-quality, non-INELIGIBLE)
    readings were found in the window — rules must not fire on this signal at all."""
    caution: bool
    """`True` if any window sample came from an `ELIGIBLE_WITH_CAUTION` sensor — caps
    evidence strength at `RulesPolicy.quality.caution_caps_evidence_strength_at`."""

    latest_value: float | None
    latest_event_id: uuid.UUID | None
    latest_timestamp: datetime | None
    latest_operating_state: str | None

    baseline_profile_id: uuid.UUID | None
    baseline_version: int | None
    baseline_median: float | None
    """Lets a rule determine *direction* (above/below), which the classification alone
    (a magnitude) does not carry."""
    deviation_classification: DeviationClassification | None
    deviation_distance: float | None


@dataclass(frozen=True)
class ReservoirSignalEvaluation:
    """`RESERVOIR_LEVEL` — directional/trending, not a symmetric band (Phase 9 brief §10
    item 9, mirroring Phase 8's own `RESERVOIR_TREND` metric kind)."""

    component_type: str
    component_id: uuid.UUID | None

    eligible: bool
    latest_level_percent: float | None
    latest_timestamp: datetime | None

    recent_depletion_rate_percent_per_hour: float | None
    """Freshly computed over a short recent window — the value being judged."""
    baseline_profile_id: uuid.UUID | None
    baseline_version: int | None
    baseline_depletion_rate_percent_per_hour: float | None
    deviation_classification: DeviationClassification | None
    deviation_distance: float | None


@dataclass(frozen=True)
class CycleSignalEvaluation:
    """Machine-scoped lubrication-cycle metrics (Phase 9 brief §10 items 3/6/7), mirroring
    Phase 8's `CYCLE_METRIC` baseline scope — recorded against one representative `PRESSURE`
    sensor, but the finding itself belongs to the machine/lubrication system, not that one
    sensor."""

    component_type: str
    component_id: uuid.UUID | None

    eligible: bool
    recent_cycle_count: int
    recent_median_duration_seconds: float | None
    recent_median_rise_time_seconds: float | None
    recent_completion_success_rate: float | None
    source_event_ids: list[str] = field(default_factory=list)

    baseline_profile_id: uuid.UUID | None = None
    baseline_version: int | None = None
    baseline_median_duration_seconds: float | None = None
    baseline_median_rise_time_seconds: float | None = None
    duration_deviation_classification: DeviationClassification | None = None
    duration_deviation_distance: float | None = None
    rise_time_ratio: float | None = None
    """`recent / baseline` rise time — `None` if either side is unavailable. No MAD is
    stored for rise time (`app.baselines.domain.cycle_metrics.CycleBaselineStatistics`
    tracks a MAD for duration only), so this is a plain ratio against a configured
    multiplier, not a robust standardized distance — documented in
    `docs/RULES_ENGINE.md` as a deliberate, narrower simplification than the duration
    comparison."""


@dataclass(frozen=True)
class MachineRuleContext:
    """Everything one worker cycle's evaluation of one machine needs, already
    quality-gated and baseline-resolved — every rule function takes this (or a narrower
    slice of it) plus `RulesPolicy`, nothing else."""

    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    machine_criticality: str
    bearing_criticality: dict[str, str]
    """Keyed by bearing_id string — a machine may have more than one bearing."""

    now: datetime
    window_start: datetime
    window_end: datetime

    signals: list[SignalEvaluation]
    reservoir: ReservoirSignalEvaluation | None
    cycle: CycleSignalEvaluation | None

    tracked_sensor_count: int
    eligible_sensor_fraction: float
    """Fraction of this machine's currently-tracked sensors that are not INELIGIBLE this
    cycle — below `RulesPolicy.quality.minimum_eligible_sensor_fraction`, only
    `INSUFFICIENT_TRUSTED_DATA` may fire (Phase 9 brief §40/§41, mandatory)."""

    def signals_for(self, measurement_type: str) -> list[SignalEvaluation]:
        return [s for s in self.signals if s.measurement_type == measurement_type]
