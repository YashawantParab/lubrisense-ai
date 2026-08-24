"""Lubrication-energy attribution orchestration (Lubrication Efficiency Intelligence,
Pass 2 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §5-§10, ADR-176). Gathers real,
already-persisted evidence for one machine — the latest `EnergyAssessment` (Pass 1),
current `RuleFinding`s, latest `StateEstimate`s, the latest `ConditionAssessment`, and
the same two `MLInferenceResult`s `ConditionEngine` itself reads — and hands it to the
pure policy in `app.energy.domain.attribution`. Never computes evidence itself; only
assembles what other phases already computed and persisted.

**Non-circularity boundary (design doc §8, ADR-176)**: this service is read-only with
respect to Condition/Decision Intelligence. It calls `ConditionAssessmentRepository
.get_latest` and `MLInferenceResultRepository.latest_for_machine` — the same read paths
`ConditionEngine`/API routes already use — but never calls `ConditionEngine.assess()`,
never writes to `condition_assessment`/`decision_assessment`, and its own output
(`LubricationEnergyAttribution`) is never read by `ConditionEngine`/`DecisionEngine` in
this pass. Evidence flows condition → attribution, never attribution → condition — the
exact direction the design doc requires to avoid a circular-reasoning loop (a condition
that says "bearing deterioration" must never be allowed to receive attribution as new
"lubrication friction" input that then makes the condition itself more confident).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ml_service.domain.model_metadata import ModelLifecycleState
from ml_service.registry.registry import ModelNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.condition_intelligence.config.policy import load_condition_intelligence_policy
from app.condition_intelligence.repositories.condition_assessment_repository import (
    ConditionAssessmentRepository,
)
from app.domain.models import ConditionAssessment, LubricationEnergyAttribution
from app.energy.domain.attribution import (
    POLICY_VERSION,
    AttributionContext,
    MLSignal,
    RuleFindingSignal,
    StateEstimateSignal,
    derive_attribution,
)
from app.energy.repositories.attribution_repository import AttributionRepository
from app.energy.repositories.energy_assessment_repository import EnergyAssessmentRepository
from app.ml.registry import get_model_registry
from app.ml.repositories.ml_repository import MLInferenceResultRepository
from app.repositories.machine import MachineRepository
from app.rules_engine.repositories.rule_finding_repository import RuleFindingRepository
from app.state_estimation.config.policy import load_state_estimation_config
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository

#: Deliberately the exact same two models `ConditionEngine._ML_MODEL_IDS` reads for
#: condition fusion — never `FAILURE_CLASSIFICATION_BASELINE_V1`, the governed STAGING
#: classifier `ConditionEngine` itself excludes from fusion (real, evidenced domain-shift
#: regression risk — see the ML decision-integration pass). Attribution must not silently
#: reintroduce a model the platform already decided not to trust operationally.
_ML_MODEL_IDS = ("LUBRICATION_ANOMALY_V1", "FAILURE_CLASSIFICATION_V1")
_SERVABLE_STATUSES = (
    ModelLifecycleState.VALIDATED,
    ModelLifecycleState.STAGING,
    ModelLifecycleState.PRODUCTION,
)


class AttributionMachineNotFoundError(LookupError):
    pass


class AttributionEnergyAssessmentNotFoundError(LookupError):
    """No `EnergyAssessment` exists yet for this machine — Pass 1's
    `EnergyAssessmentService.assess_machine` must run first (mirrors how attribution is
    always downstream of, never a substitute for, the energy foundation)."""


class AttributionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._machines = MachineRepository(session)
        self._energy_assessments = EnergyAssessmentRepository(session)
        self._rule_findings = RuleFindingRepository(session)
        self._state_estimates = StateEstimateRepository(session)
        self._conditions = ConditionAssessmentRepository(session)
        self._ml_results = MLInferenceResultRepository(session)
        self._attributions = AttributionRepository(session)
        self._condition_policy = load_condition_intelligence_policy()
        self._state_config = load_state_estimation_config()

    async def assess_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> LubricationEnergyAttribution:
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise AttributionMachineNotFoundError(str(machine_id))

        energy_assessment = await self._energy_assessments.latest_for_machine(tenant_id, machine_id)
        if energy_assessment is None:
            raise AttributionEnergyAssessmentNotFoundError(str(machine_id))

        rule_findings = await self._rule_findings.list_current_for_machine(tenant_id, machine_id)
        rule_signals = tuple(
            RuleFindingSignal(finding_type=f.finding_type.value, state=f.state.value)
            for f in rule_findings
        )

        state_signals: list[StateEstimateSignal] = []
        for state_type in self._state_config.states:
            row = await self._state_estimates.get_latest(
                tenant_id, machine_id, state_type, self._state_config.estimator_version
            )
            if row is None:
                continue
            meaningfully_elevated = (
                abs(row.state_value)
                >= self._condition_policy.state_estimate.minimum_meaningful_level
            )
            state_signals.append(
                StateEstimateSignal(
                    state_type=row.state_type.value,
                    trend=row.trend.value,
                    uncertainty=row.uncertainty.value,
                    meaningfully_elevated=meaningfully_elevated,
                )
            )

        condition: ConditionAssessment | None = await self._conditions.get_latest(
            tenant_id, machine_id
        )
        condition_type = condition.condition_type.value if condition is not None else None
        condition_trust = (
            condition.evidence_summary.get("data_trustworthiness")
            if condition is not None
            else None
        )

        ml_signals: list[MLSignal] = []
        for model_id in _ML_MODEL_IDS:
            ml_result = await self._ml_results.latest_for_machine(tenant_id, machine_id, model_id)
            if ml_result is None or ml_result.status.value != "OK":
                continue
            try:
                metadata = get_model_registry().get_metadata(model_id, ml_result.model_version)
                is_experimental = metadata.status not in _SERVABLE_STATUSES
            except (ModelNotFoundError, FileNotFoundError):
                is_experimental = True
            condition_hint = (
                self._condition_policy.ml_classification_map.get(ml_result.predicted_class)
                if ml_result.predicted_class
                else None
            )
            ml_signals.append(
                MLSignal(
                    model_id=model_id,
                    predicted_class=ml_result.predicted_class,
                    anomalous=ml_result.anomalous,
                    is_experimental=is_experimental,
                    condition_hint=condition_hint,
                )
            )

        ctx = AttributionContext(
            energy_status=energy_assessment.status,
            energy_data_quality=energy_assessment.data_quality_state.value,
            residual_kw=energy_assessment.residual_kw,
            residual_pct=energy_assessment.residual_pct,
            baseline_source=energy_assessment.baseline_source,
            rule_findings=rule_signals,
            state_estimates=tuple(state_signals),
            condition_type=condition_type,
            condition_data_trustworthiness=condition_trust,
            ml_signals=tuple(ml_signals),
        )
        result = derive_attribution(ctx)

        attribution = LubricationEnergyAttribution(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            machine_id=machine_id,
            energy_assessment_id=energy_assessment.id,
            as_of_timestamp=datetime.now(UTC),
            attribution_level=result.level,
            energy_residual_kw=energy_assessment.residual_kw,
            energy_residual_pct=energy_assessment.residual_pct,
            supporting_evidence=list(result.supporting_evidence),
            contradicting_evidence=list(result.contradicting_evidence),
            limiting_factors=list(result.limiting_factors),
            alternative_explanations=list(result.alternative_explanations),
            data_quality_state=result.data_quality_state,
            condition_assessment_id=condition.id if condition is not None else None,
            policy_version=POLICY_VERSION,
        )
        await self._attributions.insert(attribution)
        await self._session.commit()
        return attribution
