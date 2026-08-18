"""`RuleEngine` — the per-machine evaluation orchestrator (Phase 9 brief §2/§30).

Consumes only persisted Phase 6 `telemetry`, Phase 7 `sensor_quality_state`, and Phase 8
`BaselineProfile` (ACTIVE only, via `app.baselines.services.deviation_service`/
`BaselineProfileRepository.get_active`/`list_current_for_machine` filtered to `ACTIVE`) —
never the simulator's ground truth (brief §3, mandatory). Called by both the live worker
(`app.rules_engine.workers.worker`, recent-window evaluation) and the historical reprocess
CLI (`app.rules_engine.workers.reprocess`, an explicit `--start`/`--end` range) — the same
method serves both, mirroring `app.baselines.services.baseline_engine.BaselineEngine`'s own
"one method, two callers" shape.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.anchor import mad_distance
from app.baselines.domain.context import BaselineContext
from app.baselines.domain.cycle_metrics import (
    CompletionSample,
    PressureSample,
    compute_cycle_baseline,
)
from app.baselines.domain.reservoir_trend import compute_reservoir_trend
from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.baselines.services import deviation_service
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import (
    BaselineMetricKind,
    BaselineState,
    Eligibility,
    RuleFindingSeverity,
    RuleFindingType,
    SensorType,
    TelemetryQuality,
)
from app.domain.models import BaselineProfile, Sensor, Telemetry
from app.repositories.bearing import BearingRepository
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository
from app.repositories.telemetry import TelemetryRepository
from app.rules_engine.config.policy import RulesPolicy
from app.rules_engine.domain.context import (
    CycleSignalEvaluation,
    MachineRuleContext,
    ReservoirSignalEvaluation,
    SignalEvaluation,
)
from app.rules_engine.domain.deviation import classify_distance
from app.rules_engine.domain.results import RuleFindingCandidate
from app.rules_engine.repositories.rule_finding_repository import RuleFindingRepository
from app.rules_engine.rules.bearing import check_independent_bearing_pattern
from app.rules_engine.rules.cross_signal import (
    FindingMap,
    check_leakage_pattern,
    check_lubrication_path_degradation_pattern,
    check_pump_degradation_pattern,
    check_restriction_pattern,
)
from app.rules_engine.rules.cycle import (
    check_cycle_completion_failure,
    check_cycle_duration_above_baseline,
    check_pressure_build_slow,
)
from app.rules_engine.rules.quality import check_insufficient_trusted_data
from app.rules_engine.rules.single_signal import (
    check_bearing_temperature_above_contextual_baseline,
    check_flow_below_contextual_baseline,
    check_pressure_above_contextual_baseline,
    check_pump_current_above_baseline,
    check_pump_runtime_above_baseline,
    check_reservoir_depletion_abnormal,
    check_reservoir_level_low,
    check_vibration_above_contextual_baseline,
    classify_reservoir_trend_deviation,
)
from app.rules_engine.services.lifecycle import LifecycleAction, decide

logger = logging.getLogger("app.rules_engine.rule_engine")

_TELEMETRY_QUERY_LIMIT = 2000

_SINGLE_SIGNAL_MEASUREMENT_TYPES = (
    "FLOW",
    "PRESSURE",
    "PUMP_CURRENT",
    "PUMP_RUNTIME",
    "BEARING_TEMPERATURE",
    "VIBRATION_RMS",
    "VIBRATION_PEAK",
)

_SINGLE_SIGNAL_CHECKS = {
    "FLOW": check_flow_below_contextual_baseline,
    "PRESSURE": check_pressure_above_contextual_baseline,
    "PUMP_CURRENT": check_pump_current_above_baseline,
    "PUMP_RUNTIME": check_pump_runtime_above_baseline,
    "BEARING_TEMPERATURE": check_bearing_temperature_above_contextual_baseline,
    "VIBRATION_RMS": check_vibration_above_contextual_baseline,
    "VIBRATION_PEAK": check_vibration_above_contextual_baseline,
}

# Category used purely to pick a window size (RulesPolicy.window_minutes_for) — a light,
# best-effort mapping, not the same taxonomy `RuleFindingCandidate.category` uses.
_WINDOW_CATEGORY_BY_MEASUREMENT_TYPE = {
    "FLOW": "HYDRAULIC",
    "PRESSURE": "HYDRAULIC",
    "PUMP_CURRENT": "PUMP",
    "PUMP_RUNTIME": "PUMP",
    "BEARING_TEMPERATURE": "BEARING_CONDITION",
    "VIBRATION_RMS": "BEARING_CONDITION",
    "VIBRATION_PEAK": "BEARING_CONDITION",
}


def _component_for_row(row: Telemetry) -> tuple[str, uuid.UUID | None]:
    """Every relevant hierarchy field is already resolved onto `Telemetry` by Phase 6's
    `ContextEnrichmentService` — never a fresh lookup here. Most-specific-first."""
    if row.bearing_id is not None:
        return "BEARING", row.bearing_id
    if row.circuit_id is not None:
        return "CIRCUIT", row.circuit_id
    if row.lubrication_system_id is not None:
        return "LUBRICATION_SYSTEM", row.lubrication_system_id
    return "MACHINE", row.machine_id


@dataclass(frozen=True)
class EvaluationResult:
    machine_id: uuid.UUID
    signals_evaluated: int
    findings_created: int
    findings_updated: int
    findings_resolved: int
    findings_errors: int = 0


class RuleEngine:
    def __init__(
        self, session: AsyncSession, baseline_policy: BaselinePolicy, rules_policy: RulesPolicy
    ) -> None:
        self.session = session
        self.baseline_policy = baseline_policy
        self.rules_policy = rules_policy
        self._telemetry_repo = TelemetryRepository(session)
        self._quality_state_repo = SensorQualityStateRepository(session)
        self._sensor_repo = SensorRepository(session)
        self._machine_repo = MachineRepository(session)
        self._bearing_repo = BearingRepository(session)
        self._baseline_repo = BaselineProfileRepository(session)
        self._finding_repo = RuleFindingRepository(session)

    async def evaluate_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        now: datetime,
        *,
        window_override: tuple[datetime, datetime] | None = None,
    ) -> EvaluationResult:
        context = await self._build_context(tenant_id, machine_id, now, window_override)
        candidates = await self._evaluate_all_rules(context)
        return await self._apply_lifecycle(tenant_id, machine_id, context, candidates, now)

    # -- context building -----------------------------------------------------------------

    async def _build_context(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        now: datetime,
        window_override: tuple[datetime, datetime] | None,
    ) -> MachineRuleContext:
        machine = await self._machine_repo.get(tenant_id, machine_id)
        bearings = await self._bearing_repo.list_by_machine(tenant_id, machine_id)
        bearing_criticality = {str(b.id): b.criticality.value for b in bearings}

        tracked = await self._quality_state_repo.list_for_machine(tenant_id, machine_id)
        tracked_sensor_count = len(tracked)
        eligible_count = sum(1 for t in tracked if t.eligibility != Eligibility.INELIGIBLE)
        eligible_fraction = eligible_count / tracked_sensor_count if tracked_sensor_count else 0.0

        active_baselines = [
            p
            for p in await self._baseline_repo.list_current_for_machine(tenant_id, machine_id)
            if p.state == BaselineState.ACTIVE
        ]

        signals: list[SignalEvaluation] = []
        reservoir: ReservoirSignalEvaluation | None = None
        window_start_seen: datetime | None = None
        window_end_seen: datetime | None = None

        for state in tracked:
            sensor = await self._sensor_repo.get(tenant_id, state.sensor_id)
            if sensor is None:
                continue
            measurement_type = sensor.sensor_type.value
            if measurement_type == SensorType.RESERVOIR_LEVEL.value:
                start, end = window_override or self._window_for(now, "RESERVOIR")
                reservoir = await self._build_reservoir_evaluation(
                    tenant_id, sensor, state, active_baselines, start, end
                )
                window_start_seen, window_end_seen = start, end
                continue
            if measurement_type not in _SINGLE_SIGNAL_MEASUREMENT_TYPES:
                continue
            category = _WINDOW_CATEGORY_BY_MEASUREMENT_TYPE[measurement_type]
            start, end = window_override or self._window_for(now, category)
            signal = await self._build_signal_evaluation(tenant_id, sensor, state, start, end)
            signals.append(signal)
            window_start_seen, window_end_seen = start, end

        cycle_start, cycle_end = window_override or self._window_for(now, "LUBRICATION_CYCLE")
        cycle = await self._build_cycle_evaluation(
            tenant_id, machine_id, active_baselines, cycle_start, cycle_end
        )

        return MachineRuleContext(
            tenant_id=tenant_id,
            machine_id=machine_id,
            machine_criticality=machine.criticality.value if machine else "MEDIUM",
            bearing_criticality=bearing_criticality,
            now=now,
            window_start=window_start_seen or (now - timedelta(minutes=30)),
            window_end=window_end_seen or now,
            signals=signals,
            reservoir=reservoir,
            cycle=cycle,
            tracked_sensor_count=tracked_sensor_count,
            eligible_sensor_fraction=eligible_fraction,
        )

    def _window_for(self, now: datetime, category: str) -> tuple[datetime, datetime]:
        minutes = self.rules_policy.window_minutes_for(category)
        return now - timedelta(minutes=minutes), now

    async def _quality_gate_rows(
        self, tenant_id: uuid.UUID, rows: list[Telemetry]
    ) -> list[Telemetry]:
        sensor_ids = {r.sensor_id for r in rows}
        eligible_by_sensor: dict[uuid.UUID, bool] = {}
        for sensor_id in sensor_ids:
            state = await self._quality_state_repo.get(tenant_id, sensor_id)
            eligible_by_sensor[sensor_id] = state is None or (
                state.eligibility != Eligibility.INELIGIBLE
            )
        return [r for r in rows if eligible_by_sensor[r.sensor_id]]

    def _cycle_phase_for(self, measurement_type: str, value: float | None) -> str | None:
        if value is None or not self.baseline_policy.uses_cycle_phase(measurement_type):
            return None
        threshold = self.baseline_policy.cycle_phase_idle_threshold_for(measurement_type)
        if threshold is None:
            return None
        return "ACTIVE" if value > threshold else "IDLE"

    async def _build_signal_evaluation(
        self,
        tenant_id: uuid.UUID,
        sensor: Sensor,
        quality_state: object,
        window_start: datetime,
        window_end: datetime,
    ) -> SignalEvaluation:
        measurement_type = sensor.sensor_type.value
        rows = await self._telemetry_repo.get_by_sensor_time_range(
            tenant_id,
            sensor.id,
            start=window_start,
            end=window_end,
            measurement_type=sensor.sensor_type,
            limit=_TELEMETRY_QUERY_LIMIT,
        )
        eligibility = getattr(quality_state, "eligibility", Eligibility.ELIGIBLE)
        eligible = eligibility != Eligibility.INELIGIBLE
        caution = eligibility == Eligibility.ELIGIBLE_WITH_CAUTION
        good_rows = (
            await self._quality_gate_rows(
                tenant_id, [r for r in rows if r.quality == TelemetryQuality.GOOD]
            )
            if eligible
            else []
        )
        sample_count = len(good_rows)

        if not eligible or sample_count < self.rules_policy.min_sample_count or not good_rows:
            fallback_component: tuple[str, uuid.UUID | None] = ("MACHINE", None)
            if rows:
                fallback_component = _component_for_row(rows[0])
            return SignalEvaluation(
                measurement_type=measurement_type,
                component_type=fallback_component[0],
                component_id=fallback_component[1],
                sample_count_in_window=sample_count,
                eligible=False,
                caution=caution,
                latest_value=None,
                latest_event_id=None,
                latest_timestamp=None,
                latest_operating_state=None,
                baseline_profile_id=None,
                baseline_version=None,
                baseline_median=None,
                deviation_classification=None,
                deviation_distance=None,
            )

        latest = max(good_rows, key=lambda r: r.source_timestamp)
        component_type, component_id = _component_for_row(latest)
        context = BaselineContext(
            operating_state=latest.operating_state,
            cycle_phase=self._cycle_phase_for(measurement_type, latest.value),
        )
        lookup = await deviation_service.evaluate(
            self.session, self.baseline_policy, tenant_id, sensor, context, latest.value
        )
        deviation = lookup.deviation
        profile = lookup.resolved.profile
        baseline_median = (
            profile.statistics.get("median")
            if profile is not None and profile.statistics is not None
            else None
        )
        return SignalEvaluation(
            measurement_type=measurement_type,
            component_type=component_type,
            component_id=component_id,
            sample_count_in_window=sample_count,
            eligible=True,
            caution=caution,
            latest_value=latest.value,
            latest_event_id=latest.event_id,
            latest_timestamp=latest.source_timestamp,
            latest_operating_state=latest.operating_state,
            baseline_profile_id=profile.id if profile is not None else None,
            baseline_version=profile.version if profile is not None else None,
            baseline_median=baseline_median,
            deviation_classification=deviation.classification if deviation else None,
            deviation_distance=deviation.standardized_distance if deviation else None,
        )

    async def _build_reservoir_evaluation(
        self,
        tenant_id: uuid.UUID,
        sensor: Sensor,
        quality_state: object,
        active_baselines: list[BaselineProfile],
        window_start: datetime,
        window_end: datetime,
    ) -> ReservoirSignalEvaluation:
        rows = await self._telemetry_repo.get_by_sensor_time_range(
            tenant_id,
            sensor.id,
            start=window_start,
            end=window_end,
            measurement_type=SensorType.RESERVOIR_LEVEL,
            limit=_TELEMETRY_QUERY_LIMIT,
        )
        eligibility = getattr(quality_state, "eligibility", Eligibility.ELIGIBLE)
        eligible = eligibility != Eligibility.INELIGIBLE
        good_rows = (
            await self._quality_gate_rows(
                tenant_id, [r for r in rows if r.quality == TelemetryQuality.GOOD]
            )
            if eligible
            else []
        )
        component_type, component_id = (
            _component_for_row(good_rows[-1]) if good_rows else ("LUBRICATION_SYSTEM", None)
        )

        latest_level: float | None = None
        latest_ts: datetime | None = None
        if good_rows:
            latest = max(good_rows, key=lambda r: r.source_timestamp)
            latest_level, latest_ts = latest.value, latest.source_timestamp

        points = sorted(
            ((r.source_timestamp, r.value) for r in good_rows if r.value is not None),
            key=lambda p: p[0],
        )
        recent_trend = compute_reservoir_trend(points) if len(points) >= 2 else None

        baseline = next(
            (p for p in active_baselines if p.metric_kind == BaselineMetricKind.RESERVOIR_TREND),
            None,
        )
        baseline_rate = baseline_mad = None
        if baseline is not None and baseline.statistics is not None:
            baseline_rate = baseline.statistics.get("median_depletion_rate_percent_per_hour")
            baseline_mad = baseline.statistics.get("depletion_rate_mad")

        classification = distance = None
        if recent_trend is not None and baseline_rate is not None and baseline_mad is not None:
            classification, distance = classify_reservoir_trend_deviation(
                recent_trend.median_depletion_rate_percent_per_hour,
                baseline_rate,
                baseline_mad,
                self.rules_policy,
            )

        return ReservoirSignalEvaluation(
            component_type=component_type,
            component_id=component_id,
            eligible=eligible,
            latest_level_percent=latest_level,
            latest_timestamp=latest_ts,
            recent_depletion_rate_percent_per_hour=(
                recent_trend.median_depletion_rate_percent_per_hour if recent_trend else None
            ),
            baseline_profile_id=baseline.id if baseline else None,
            baseline_version=baseline.version if baseline else None,
            baseline_depletion_rate_percent_per_hour=baseline_rate,
            deviation_classification=classification,
            deviation_distance=distance,
        )

    async def _build_cycle_evaluation(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        active_baselines: list[BaselineProfile],
        window_start: datetime,
        window_end: datetime,
    ) -> CycleSignalEvaluation | None:
        pressure_rows = await self._telemetry_repo.get_by_machine_time_range(
            tenant_id,
            machine_id,
            start=window_start,
            end=window_end,
            measurement_type=SensorType.PRESSURE,
            limit=_TELEMETRY_QUERY_LIMIT,
        )
        if not pressure_rows:
            return None
        completion_rows = await self._telemetry_repo.get_by_machine_time_range(
            tenant_id,
            machine_id,
            start=window_start,
            end=window_end,
            measurement_type=SensorType.CYCLE_COMPLETION,
            limit=_TELEMETRY_QUERY_LIMIT,
        )
        good_pressure = await self._quality_gate_rows(
            tenant_id, [r for r in pressure_rows if r.quality == TelemetryQuality.GOOD]
        )
        good_completion = await self._quality_gate_rows(
            tenant_id, [r for r in completion_rows if r.quality == TelemetryQuality.GOOD]
        )
        if not good_pressure:
            return None

        idle_threshold = self.baseline_policy.cycle_phase_idle_threshold_for("PRESSURE")
        if idle_threshold is None:
            return None

        pressure_samples = [
            PressureSample(event_id=r.event_id, source_timestamp=r.source_timestamp, value=r.value)
            for r in good_pressure
            if r.value is not None
        ]
        completion_samples = [
            CompletionSample(source_timestamp=r.source_timestamp, value=r.value)
            for r in good_completion
            if r.value is not None
        ]
        recent_stats = compute_cycle_baseline(
            pressure_samples, completion_samples, idle_threshold=idle_threshold
        )

        component_type, component_id = _component_for_row(
            max(good_pressure, key=lambda r: r.source_timestamp)
        )

        baseline = next(
            (p for p in active_baselines if p.metric_kind == BaselineMetricKind.CYCLE_METRIC), None
        )
        baseline_duration = baseline_rise_time = None
        duration_classification = duration_distance = None
        if baseline is not None and baseline.statistics is not None:
            baseline_duration = baseline.statistics.get("median_duration_seconds")
            baseline_rise_time = baseline.statistics.get("median_rise_time_seconds")
            if recent_stats is not None and baseline.statistics.get("duration_mad") is not None:
                distance = mad_distance(
                    recent_stats.to_dict(), baseline.statistics, BaselineMetricKind.CYCLE_METRIC
                )
                # `mad_distance` returns `float("inf")` for its degenerate (zero-spread,
                # unequal-value) case — not valid JSON, and this value is persisted
                # directly into `RuleFinding.evidence` (JSONB), unlike Phase 8's own use
                # of this same function, which only ever compares it numerically and never
                # serializes it. Same finite-sentinel fix as
                # `app.rules_engine.rules.single_signal.classify_reservoir_trend_deviation`.
                if distance == float("inf"):
                    distance = 1e9
                duration_classification = classify_distance(
                    distance,
                    mild_multiplier=self.rules_policy.deviation.mild_multiplier,
                    strong_multiplier=self.rules_policy.deviation.strong_multiplier,
                )
                duration_distance = distance

        rise_time_ratio = None
        if (
            recent_stats is not None
            and recent_stats.median_rise_time_seconds is not None
            and baseline_rise_time is not None
            and baseline_rise_time > 0
        ):
            rise_time_ratio = recent_stats.median_rise_time_seconds / baseline_rise_time

        return CycleSignalEvaluation(
            component_type=component_type,
            component_id=component_id,
            eligible=recent_stats is not None,
            recent_cycle_count=recent_stats.cycle_count if recent_stats else 0,
            recent_median_duration_seconds=(
                recent_stats.median_duration_seconds if recent_stats else None
            ),
            recent_median_rise_time_seconds=(
                recent_stats.median_rise_time_seconds if recent_stats else None
            ),
            recent_completion_success_rate=(
                recent_stats.completion_success_rate if recent_stats else None
            ),
            source_event_ids=[str(p.event_id) for p in pressure_samples],
            baseline_profile_id=baseline.id if baseline else None,
            baseline_version=baseline.version if baseline else None,
            baseline_median_duration_seconds=baseline_duration,
            baseline_median_rise_time_seconds=baseline_rise_time,
            duration_deviation_classification=duration_classification,
            duration_deviation_distance=duration_distance,
            rise_time_ratio=rise_time_ratio,
        )

    # -- rule evaluation --------------------------------------------------------------------

    async def _evaluate_all_rules(self, context: MachineRuleContext) -> list[RuleFindingCandidate]:
        insufficient = check_insufficient_trusted_data(
            context.machine_id,
            tracked_sensor_count=context.tracked_sensor_count,
            eligible_sensor_fraction=context.eligible_sensor_fraction,
            policy=self.rules_policy,
        )
        if insufficient is not None:
            # Mandatory (brief §40/§41): no equipment-condition finding may fire this
            # cycle for this machine — quality gating suppresses evaluation entirely,
            # never merely annotates it.
            return [insufficient]

        all_candidates: list[RuleFindingCandidate] = []
        bearing_temp: dict[uuid.UUID, RuleFindingCandidate] = {}
        bearing_vibration_rms: dict[uuid.UUID, RuleFindingCandidate] = {}

        for signal in context.signals:
            check_fn = _SINGLE_SIGNAL_CHECKS.get(signal.measurement_type)
            if check_fn is None:
                continue
            candidate = check_fn(signal, self.rules_policy)
            if candidate is None:
                continue
            all_candidates.append(candidate)
            if signal.measurement_type == "BEARING_TEMPERATURE" and signal.component_id:
                bearing_temp[signal.component_id] = candidate
            elif signal.measurement_type == "VIBRATION_RMS" and signal.component_id:
                bearing_vibration_rms[signal.component_id] = candidate

        if context.reservoir is not None:
            for reservoir_check in (check_reservoir_level_low, check_reservoir_depletion_abnormal):
                candidate = reservoir_check(context.reservoir, self.rules_policy)
                if candidate is not None:
                    all_candidates.append(candidate)

        if context.cycle is not None:
            for cycle_check in (
                check_pressure_build_slow,
                check_cycle_duration_above_baseline,
                check_cycle_completion_failure,
            ):
                candidate = cycle_check(context.cycle, self.rules_policy)
                if candidate is not None:
                    all_candidates.append(candidate)

        # Cross-signal patterns look up "did finding_type X fire anywhere on this machine
        # this cycle" — first-occurrence-per-type is a deliberate, documented
        # simplification at this reference implementation's scale (docs/RULES_ENGINE.md).
        firing_types: FindingMap = {}
        for candidate in all_candidates:
            firing_types.setdefault(candidate.finding_type, candidate)

        restriction = check_restriction_pattern(firing_types, self.rules_policy)
        leakage = check_leakage_pattern(firing_types, self.rules_policy)
        pump_degradation = check_pump_degradation_pattern(firing_types, self.rules_policy)
        specific_matched = any(f is not None for f in (restriction, leakage, pump_degradation))
        lubrication_path = check_lubrication_path_degradation_pattern(
            firing_types, specific_matched, self.rules_policy
        )
        for pattern_candidate in (restriction, leakage, pump_degradation, lubrication_path):
            if pattern_candidate is not None:
                all_candidates.append(pattern_candidate)
                firing_types.setdefault(pattern_candidate.finding_type, pattern_candidate)

        lubrication_types = {
            RuleFindingType(t) for t in self.rules_policy.bearing.lubrication_signal_types
        }
        lubrication_signals_normal = not any(t in firing_types for t in lubrication_types)
        for bearing_id in set(bearing_temp) | set(bearing_vibration_rms):
            candidate = check_independent_bearing_pattern(
                bearing_id,
                bearing_temp.get(bearing_id),
                bearing_vibration_rms.get(bearing_id),
                lubrication_signals_normal=lubrication_signals_normal,
                policy=self.rules_policy,
            )
            if candidate is not None:
                all_candidates.append(candidate)

        return all_candidates

    # -- lifecycle application ---------------------------------------------------------------

    async def _apply_lifecycle(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        context: MachineRuleContext,
        candidates: list[RuleFindingCandidate],
        now: datetime,
    ) -> EvaluationResult:
        criticality = context.machine_criticality
        created = updated = resolved = errors = 0
        touched_keys: set[tuple[uuid.UUID | None, str, str]] = set()

        for candidate in candidates:
            key = (candidate.component_id, candidate.rule_id, candidate.rule_version)
            touched_keys.add(key)
            try:
                # Per-candidate SAVEPOINT isolation (Phase 7/8 precedent): one bad finding
                # (e.g. a pathological evidence value) must never roll back every other
                # valid finding this cycle computed for the same machine — a real failure
                # mode caught live via scripts/verify_rules.sh (see TECHNICAL_DECISIONS.md).
                async with self.session.begin_nested():
                    component_criticality = (
                        context.bearing_criticality.get(str(candidate.component_id), criticality)
                        if candidate.component_type == "BEARING"
                        else criticality
                    )
                    severity = _severity_for(candidate, component_criticality, self.rules_policy)

                    current = await self._finding_repo.get_current(
                        tenant_id,
                        machine_id,
                        candidate.component_id,
                        candidate.rule_id,
                        candidate.rule_version,
                    )
                    decision = decide(
                        row_exists=current is not None,
                        row_state=current.state if current else None,
                        row_candidate_stable_cycles=(
                            current.candidate_stable_cycles if current else 0
                        ),
                        fired=True,
                        required_stable_cycles=self.rules_policy.required_stable_cycles_for(
                            candidate.finding_type.value
                        ),
                    )
                    if decision.action == LifecycleAction.CREATE_CANDIDATE:
                        await self._finding_repo.create_candidate(
                            tenant_id=tenant_id,
                            machine_id=machine_id,
                            candidate=candidate,
                            config_version=self.rules_policy.policy_version,
                            severity=severity,
                            criticality_at_detection=component_criticality,
                            now=now,
                        )
                        created += 1
                    elif (
                        current is not None and decision.action == LifecycleAction.ADVANCE_CANDIDATE
                    ):
                        await self._finding_repo.advance_candidate(
                            current.id,
                            candidate=candidate,
                            severity=severity,
                            candidate_stable_cycles=decision.candidate_stable_cycles,
                            now=now,
                        )
                        updated += 1
                    elif current is not None and decision.action == LifecycleAction.ACTIVATE:
                        await self._finding_repo.activate(
                            current.id, candidate=candidate, severity=severity, now=now
                        )
                        updated += 1
                    elif current is not None and decision.action == LifecycleAction.REFRESH_ACTIVE:
                        await self._finding_repo.refresh_active(
                            current.id, candidate=candidate, severity=severity, now=now
                        )
                        updated += 1
                    elif (
                        current is not None
                        and decision.action == LifecycleAction.REACTIVATE_FROM_RECOVERING
                    ):
                        await self._finding_repo.reactivate_from_recovering(
                            current.id, candidate=candidate, severity=severity, now=now
                        )
                        updated += 1
            except Exception as exc:  # noqa: BLE001 - per-candidate isolation, see comment above
                errors += 1
                logger.warning(
                    "rule finding persistence failed for one candidate, skipping",
                    extra={
                        "machine_id": str(machine_id),
                        "finding_type": candidate.finding_type.value,
                        "error": str(exc),
                    },
                )

        # Rules that fired last cycle but not this one: advance toward recovery/resolution.
        previously_current = await self._finding_repo.list_current_for_machine(
            tenant_id, machine_id
        )
        for row in previously_current:
            key = (row.component_id, row.rule_id, row.rule_version)
            if key in touched_keys:
                continue
            try:
                async with self.session.begin_nested():
                    decision = decide(
                        row_exists=True,
                        row_state=row.state,
                        row_candidate_stable_cycles=row.candidate_stable_cycles,
                        fired=False,
                        required_stable_cycles=self.rules_policy.required_stable_cycles_for(
                            row.finding_type.value
                        ),
                    )
                    if decision.action == LifecycleAction.MARK_RECOVERING:
                        await self._finding_repo.mark_recovering(row.id, now=now)
                    elif decision.action == LifecycleAction.RESOLVE:
                        await self._finding_repo.resolve(row.id, now=now)
                        resolved += 1
            except Exception as exc:  # noqa: BLE001 - per-row isolation, see comment above
                errors += 1
                logger.warning(
                    "rule finding recovery/resolution failed for one row, skipping",
                    extra={
                        "machine_id": str(machine_id),
                        "finding_id": str(row.id),
                        "error": str(exc),
                    },
                )

        return EvaluationResult(
            machine_id=machine_id,
            signals_evaluated=len(context.signals),
            findings_created=created,
            findings_updated=updated,
            findings_resolved=resolved,
            findings_errors=errors,
        )


def _severity_for(
    candidate: RuleFindingCandidate, criticality: str, policy: RulesPolicy
) -> RuleFindingSeverity:
    """Severity from evidence strength, then criticality may escalate by one level (brief
    §23/§24) — criticality never creates evidence, only reweights the severity of evidence
    that already exists; see docs/RULES_ENGINE.md "Criticality awareness" / ADR."""
    base = RuleFindingSeverity[
        policy.severity.base_by_evidence_strength[candidate.evidence_strength.value]
    ]
    if (
        criticality in policy.severity.escalate_when_criticality_in
        and candidate.evidence_strength.value in policy.severity.escalate_when_evidence_strength_in
    ):
        order = [
            RuleFindingSeverity.INFO,
            RuleFindingSeverity.WARNING,
            RuleFindingSeverity.HIGH,
            RuleFindingSeverity.CRITICAL,
        ]
        index = min(order.index(base) + 1, len(order) - 1)
        return order[index]
    return base
