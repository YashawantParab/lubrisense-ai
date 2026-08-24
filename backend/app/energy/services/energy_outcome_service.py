"""Energy-outcome verification orchestration (Lubrication Efficiency Intelligence, Pass 3
— docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §9, ADR-176). Reuses the real maintenance
workflow entirely: the most recent `COMPLETED` `MaintenanceCase` for a machine anchors the
comparison; no parallel maintenance-outcome workflow is created here.

Gathers real telemetry windows around the intervention, resolves each window's own
contextual baseline via the exact `app.baselines` machinery Pass 1 already uses, and hands
everything to the pure policy in `app.energy.domain.comparability`/
`app.energy.domain.outcome`. Never computes evidence itself; only assembles what other
phases already computed and reads real telemetry directly.

**Temporal-attribution-integrity boundary (design doc §"temporal attribution integrity")**:
the pre-intervention `LubricationEnergyAttribution` snapshot is resolved with an explicit
`end=intervention_timestamp` bound — the most recent attribution *at or before* the
intervention, never the machine's current/latest attribution (which may have been computed
long after, informed by outcomes this service has no business feeding backward into it).

**Non-circularity boundary**: read-only with respect to Condition/Decision Intelligence
and with respect to `LubricationEnergyAttribution` itself — this service never calls
`ConditionEngine.assess()`, never calls `AttributionService.assess_machine()`, and never
writes to `condition_assessment`, `decision_assessment`, or
`lubrication_energy_attribution`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import BaselineContext
from app.baselines.domain.statistics import RobustStatistics
from app.baselines.services.deviation_service import evaluate as evaluate_deviation
from app.condition_intelligence.repositories.condition_assessment_repository import (
    ConditionAssessmentRepository,
)
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import (
    BaselineSourceKind,
    DeviationClassification,
    EnergyEstimateStatus,
    QualityState,
    SensorType,
)
from app.domain.models import EnergyOutcomeVerification
from app.energy.domain.comparability import (
    POLICY_VERSION as COMPARABILITY_POLICY_VERSION,
)
from app.energy.domain.comparability import (
    ComparabilityInput,
    WindowSample,
    assess_comparability,
    compute_window_bounds,
    summarize_window,
)
from app.energy.domain.outcome import (
    classify_energy_outcome,
    derive_lubrication_association,
    determine_energy_estimate_status,
    determine_maintenance_relevance,
    integrate_avoided_energy_kwh,
)
from app.energy.domain.residual import compute_residual
from app.energy.repositories.attribution_repository import AttributionRepository
from app.energy.repositories.energy_outcome_repository import EnergyOutcomeRepository
from app.maintenance.repositories.maintenance_action_repository import MaintenanceActionRepository
from app.maintenance.repositories.maintenance_case_repository import MaintenanceCaseRepository
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository
from app.repositories.telemetry import TelemetryRepository

POLICY_VERSION = "1"


class EnergyOutcomeMachineNotFoundError(LookupError):
    pass


class EnergyOutcomeNoInterventionError(LookupError):
    """No `COMPLETED` `MaintenanceCase` exists for this machine yet — an active energy
    opportunity may still exist (see `LubricationEnergyAttribution`), but outcome
    verification has nothing to compare against until a real intervention completes."""


class EnergyOutcomeNoPowerSensorError(LookupError):
    pass


class EnergyOutcomeService:
    def __init__(self, session: AsyncSession, baseline_policy: BaselinePolicy) -> None:
        self._session = session
        self._policy = baseline_policy
        self._machines = MachineRepository(session)
        self._sensors = SensorRepository(session)
        self._telemetry = TelemetryRepository(session)
        self._quality_states = SensorQualityStateRepository(session)
        self._cases = MaintenanceCaseRepository(session)
        self._actions = MaintenanceActionRepository(session)
        self._attributions = AttributionRepository(session)
        self._conditions = ConditionAssessmentRepository(session)
        self._outcomes = EnergyOutcomeRepository(session)

    async def assess_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> EnergyOutcomeVerification:
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise EnergyOutcomeMachineNotFoundError(str(machine_id))

        cases = await self._cases.list_completed_for_machine(tenant_id, machine_id, limit=1)
        if not cases:
            raise EnergyOutcomeNoInterventionError(str(machine_id))
        case = cases[0]
        if case.completed_at is None:
            raise EnergyOutcomeNoInterventionError(str(machine_id))
        intervention_timestamp = case.completed_at

        sensor = await self._sensors.get_by_machine_and_type(
            tenant_id, machine_id, SensorType.MACHINE_POWER
        )
        if sensor is None:
            raise EnergyOutcomeNoPowerSensorError(str(machine_id))

        pre_bounds, post_bounds = compute_window_bounds(intervention_timestamp)
        pre_rows = await self._telemetry.get_by_sensor_time_range(
            tenant_id,
            sensor.id,
            start=pre_bounds.start,
            end=pre_bounds.end,
            measurement_type=SensorType.MACHINE_POWER,
            limit=2000,
        )
        post_rows = await self._telemetry.get_by_sensor_time_range(
            tenant_id,
            sensor.id,
            start=post_bounds.start,
            end=post_bounds.end,
            measurement_type=SensorType.MACHINE_POWER,
            limit=2000,
        )
        pre_samples = [
            WindowSample(
                timestamp=r.source_timestamp, value=r.value, operating_state=r.operating_state
            )
            for r in pre_rows
            if r.value is not None
        ]
        post_samples = [
            WindowSample(
                timestamp=r.source_timestamp, value=r.value, operating_state=r.operating_state
            )
            for r in post_rows
            if r.value is not None
        ]
        pre_summary = summarize_window(pre_samples)
        post_summary = summarize_window(post_samples)

        quality_row = await self._quality_states.get(tenant_id, sensor.id)
        quality_state = (
            quality_row.quality_state if quality_row is not None else QualityState.TRUSTED
        )

        pre_expected_kw: float | None = None
        pre_deviation_classification = DeviationClassification.NOT_ENOUGH_DATA
        pre_baseline_source: BaselineSourceKind | None = None
        pre_baseline_profile_id: str | None = None
        pre_stats: RobustStatistics | None = None
        if pre_summary is not None:
            lookup = await evaluate_deviation(
                self._session,
                self._policy,
                tenant_id,
                sensor,
                BaselineContext(operating_state=pre_summary.dominant_operating_state),
                pre_summary.mean_value,
            )
            pre_baseline_source = lookup.resolved.source
            if lookup.deviation is not None:
                pre_deviation_classification = lookup.deviation.classification
            profile = lookup.resolved.profile
            if (
                profile is not None
                and profile.statistics is not None
                and pre_deviation_classification != DeviationClassification.NOT_ENOUGH_DATA
            ):
                pre_stats = RobustStatistics(**profile.statistics)
                pre_expected_kw = pre_stats.median
                pre_baseline_profile_id = str(profile.id)
            else:
                pre_baseline_source = None  # no usable statistics — comparability engine
                # treats this identically to "no baseline resolved" (see class docstring).

        post_expected_kw: float | None = None
        post_deviation_classification = DeviationClassification.NOT_ENOUGH_DATA
        post_baseline_source: BaselineSourceKind | None = None
        post_baseline_profile_id: str | None = None
        if post_summary is not None:
            lookup = await evaluate_deviation(
                self._session,
                self._policy,
                tenant_id,
                sensor,
                BaselineContext(operating_state=post_summary.dominant_operating_state),
                post_summary.mean_value,
            )
            post_baseline_source = lookup.resolved.source
            if lookup.deviation is not None:
                post_deviation_classification = lookup.deviation.classification
            profile = lookup.resolved.profile
            if (
                profile is not None
                and profile.statistics is not None
                and post_deviation_classification != DeviationClassification.NOT_ENOUGH_DATA
            ):
                post_stats = RobustStatistics(**profile.statistics)
                post_expected_kw = post_stats.median
                post_baseline_profile_id = str(profile.id)
            else:
                post_baseline_source = None

        pre_residual_kw: float | None = None
        pre_residual_pct: float | None = None
        if pre_summary is not None and pre_expected_kw is not None:
            pre_residual_kw, pre_residual_pct = compute_residual(
                pre_summary.mean_value, pre_expected_kw
            )

        post_residual_kw: float | None = None
        post_residual_pct: float | None = None
        if post_summary is not None and post_expected_kw is not None:
            post_residual_kw, post_residual_pct = compute_residual(
                post_summary.mean_value, post_expected_kw
            )

        residual_change_kw = (
            pre_residual_kw - post_residual_kw
            if pre_residual_kw is not None and post_residual_kw is not None
            else None
        )
        residual_change_pct = (
            pre_residual_pct - post_residual_pct
            if pre_residual_pct is not None and post_residual_pct is not None
            else None
        )

        comparability = assess_comparability(
            ComparabilityInput(
                pre_summary=pre_summary,
                post_summary=post_summary,
                pre_quality_state=quality_state,
                post_quality_state=quality_state,
                pre_baseline_source=pre_baseline_source,
                pre_baseline_profile_id=pre_baseline_profile_id,
                post_baseline_source=post_baseline_source,
                post_baseline_profile_id=post_baseline_profile_id,
            )
        )

        energy_outcome_status = classify_energy_outcome(
            comparability_status=comparability.status,
            pre_classification=pre_deviation_classification,
            pre_residual_kw=pre_residual_kw,
            post_classification=post_deviation_classification,
            post_residual_kw=post_residual_kw,
        )
        energy_estimate_status = determine_energy_estimate_status(energy_outcome_status)

        estimated_avoided_energy_kwh: float | None = None
        if (
            energy_estimate_status == EnergyEstimateStatus.ESTIMATED
            and pre_residual_kw is not None
            and post_expected_kw is not None
            and post_summary is not None
        ):
            post_residual_samples = [
                (t, compute_residual(v, post_expected_kw)[0])
                for t, v in zip(post_summary.timestamps, post_summary.values, strict=True)
            ]
            estimated_avoided_energy_kwh = integrate_avoided_energy_kwh(
                pre_residual_kw, post_residual_samples
            )

        action_rows = await self._actions.list_for_case(tenant_id, case.id)
        action_types = tuple(a.action_type for a in action_rows)
        maintenance_relevant, relevance_reason = determine_maintenance_relevance(
            case.recommended_action, action_types
        )

        pre_attributions = await self._attributions.list_for_machine(
            tenant_id, machine_id, start=None, end=intervention_timestamp, limit=1
        )
        pre_attribution = pre_attributions[0] if pre_attributions else None

        condition = await self._conditions.get_latest(tenant_id, machine_id)

        lubrication_association_status, association_text = derive_lubrication_association(
            energy_outcome_status=energy_outcome_status,
            maintenance_relevant=maintenance_relevant,
            pre_attribution_level=pre_attribution.attribution_level if pre_attribution else None,
        )

        supporting_evidence: list[str] = []
        contradicting_evidence: list[str] = []
        limiting_factors: list[str] = list(comparability.limiting_factors)
        alternative_explanations: list[str] = []

        if pre_residual_kw is not None and post_residual_kw is not None:
            supporting_evidence.append(
                f"Mean contextual power residual moved from {pre_residual_kw:+.1f} kW "
                f"pre-intervention to {post_residual_kw:+.1f} kW post-intervention."
            )
        if energy_outcome_status.value in ("QUALIFIED_RECOVERY", "PROBABLE_RECOVERY"):
            supporting_evidence.append(association_text)
        elif energy_outcome_status.value == "DETERIORATED":
            contradicting_evidence.append(
                "Contextual excess energy demand increased after the intervention rather "
                "than decreasing."
            )
        else:
            alternative_explanations.append(association_text)

        if not maintenance_relevant and relevance_reason is not None:
            limiting_factors.append(relevance_reason)
        if quality_state != QualityState.TRUSTED:
            limiting_factors.append(
                "Power-sensor data quality is not currently TRUSTED; only current, not "
                "historical, per-reading quality could be verified for these windows."
            )

        verification = EnergyOutcomeVerification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            machine_id=machine_id,
            maintenance_case_id=case.id,
            incident_id=case.incident_id,
            intervention_timestamp=intervention_timestamp,
            pre_window_start=pre_bounds.start,
            pre_window_end=pre_bounds.end,
            post_window_start=post_bounds.start,
            post_window_end=post_bounds.end,
            pre_mean_actual_power_kw=pre_summary.mean_value if pre_summary else None,
            pre_mean_expected_power_kw=pre_expected_kw,
            pre_mean_residual_kw=pre_residual_kw,
            pre_mean_residual_pct=pre_residual_pct,
            post_mean_actual_power_kw=post_summary.mean_value if post_summary else None,
            post_mean_expected_power_kw=post_expected_kw,
            post_mean_residual_kw=post_residual_kw,
            post_mean_residual_pct=post_residual_pct,
            residual_change_kw=residual_change_kw,
            residual_change_pct=residual_change_pct,
            comparability_status=comparability.status,
            comparison_confidence=comparability.confidence,
            energy_outcome_status=energy_outcome_status,
            estimated_avoided_energy_kwh=estimated_avoided_energy_kwh,
            energy_estimate_status=energy_estimate_status,
            pre_attribution_id=pre_attribution.id if pre_attribution else None,
            pre_attribution_level=pre_attribution.attribution_level if pre_attribution else None,
            condition_outcome_status=condition.lifecycle_state if condition else None,
            maintenance_relevant=maintenance_relevant,
            lubrication_association_status=lubrication_association_status,
            supporting_evidence=supporting_evidence,
            contradicting_evidence=contradicting_evidence,
            limiting_factors=limiting_factors,
            alternative_explanations=alternative_explanations,
            provenance={
                "pre_sample_count": pre_summary.sample_count if pre_summary else 0,
                "post_sample_count": post_summary.sample_count if post_summary else 0,
                "pre_baseline_profile_id": pre_baseline_profile_id,
                "post_baseline_profile_id": post_baseline_profile_id,
                "pre_dominant_operating_state": (
                    pre_summary.dominant_operating_state if pre_summary else None
                ),
                "post_dominant_operating_state": (
                    post_summary.dominant_operating_state if post_summary else None
                ),
                "computed_at": datetime.now(UTC).isoformat(),
                "comparability_policy_version": COMPARABILITY_POLICY_VERSION,
                "synthetic_demonstration_data": True,
            },
            policy_version=POLICY_VERSION,
        )
        await self._outcomes.insert(verification)
        await self._session.commit()
        return verification
