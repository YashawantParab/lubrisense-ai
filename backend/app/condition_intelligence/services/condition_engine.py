"""`ConditionEngine` — gathers real, already-persisted Phase 7/9/11/12 evidence for one
machine, synthesizes it (`services/synthesis.py`, pure), classifies lifecycle
(`services/lifecycle.py`, pure), and persists a `ConditionAssessment` (Phase 13 brief).

Never reads `simulator` or any ground-truth field; never consumes Phase 4 scenario labels.
The only inputs are Phase 7 `SensorQualityState`, Phase 9 `RuleFinding`, Phase 11
`MLInferenceResult` (cross-checked against the `ml-service` registry's lifecycle status),
and Phase 12 `StateEstimate` — all real, persisted evidence.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

from ml_service.domain.model_metadata import ModelLifecycleState
from ml_service.registry.registry import ModelNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.condition_intelligence.config.policy import (
    ConditionIntelligencePolicy,
    load_condition_intelligence_policy,
)
from app.condition_intelligence.domain.models import ConditionEvidence, EvidenceItem
from app.condition_intelligence.observability import METRICS
from app.condition_intelligence.repositories.condition_assessment_repository import (
    ConditionAssessmentRepository,
)
from app.condition_intelligence.services.lifecycle import RecentAssessment, classify_lifecycle
from app.condition_intelligence.services.synthesis import synthesize
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import QualityState, RuleFindingState
from app.domain.models import (
    ConditionAssessment,
    MLInferenceResult,
    RuleFinding,
    SensorQualityState,
    StateEstimate,
)
from app.features.repositories.source_repository import FeatureSourceRepository
from app.ml.registry import get_model_registry
from app.ml.repositories.ml_repository import MLInferenceResultRepository
from app.repositories.machine import MachineRepository
from app.rules_engine.repositories.rule_finding_repository import RuleFindingRepository
from app.state_estimation.config.policy import load_state_estimation_config
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository

_ML_MODEL_IDS = ("LUBRICATION_ANOMALY_V1", "FAILURE_CLASSIFICATION_V1")
_SERVABLE_ML_STATUSES = (
    ModelLifecycleState.VALIDATED,
    ModelLifecycleState.STAGING,
    ModelLifecycleState.PRODUCTION,
)


class ConditionEngineMachineNotFoundError(LookupError):
    pass


class ConditionEngine:
    def __init__(
        self, session: AsyncSession, policy: ConditionIntelligencePolicy | None = None
    ) -> None:
        self._session = session
        self._policy = policy or load_condition_intelligence_policy()
        self._machines = MachineRepository(session)
        self._rule_findings = RuleFindingRepository(session)
        self._ml_results = MLInferenceResultRepository(session)
        self._state_estimates = StateEstimateRepository(session)
        self._assessments = ConditionAssessmentRepository(session)
        self._state_config = load_state_estimation_config()

    async def assess(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> ConditionAssessment:
        started = time.perf_counter()
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise ConditionEngineMachineNotFoundError(str(machine_id))

        now = datetime.now(UTC)
        rule_findings = await self._rule_findings.list_current_for_machine(tenant_id, machine_id)
        # `registered_sensor_count` must reflect the asset hierarchy (any `Sensor` row
        # attached anywhere under this machine), NOT how many of them Phase 7 has already
        # produced a `SensorQualityState` row for — a sensor that is commissioned but has
        # never reported yet is still a real registered sensor, not "instrumentation
        # coverage zero". Conflating the two was a real bug caught by this phase's own
        # integration tests: a machine with one freshly-registered PRESSURE sensor and a
        # real ACTIVE rule finding was misreported as INSUFFICIENT_EVIDENCE purely because
        # no `SensorQualityState` row existed for that sensor yet.
        registered_sensors = await FeatureSourceRepository(self._session).registered_sensors(
            tenant_id, machine_id
        )
        quality_rows = await SensorQualityStateRepository(self._session).list_for_machine(
            tenant_id, machine_id
        )

        items: list[EvidenceItem] = []
        rule_finding_ids: list[str] = []
        for finding in rule_findings:
            rule_item, fid = self._evidence_from_rule_finding(finding)
            items.append(rule_item)
            rule_finding_ids.append(fid)

        ml_result_ids: list[str] = []
        for model_id in _ML_MODEL_IDS:
            ml_result = await self._ml_results.latest_for_machine(tenant_id, machine_id, model_id)
            if ml_result is None:
                continue
            ml_item = await self._evidence_from_ml_result(ml_result)
            if ml_item is not None:
                items.append(ml_item)
            ml_result_ids.append(str(ml_result.id))

        state_estimate_ids: list[str] = []
        state_rows: dict[str, StateEstimate] = {}
        for state_type in self._state_config.states:
            row = await self._state_estimates.get_latest(
                tenant_id, machine_id, state_type, self._state_config.estimator_version
            )
            if row is None:
                continue
            state_rows[state_type] = row
            state_estimate_ids.append(str(row.id))
            items.append(self._evidence_from_state_estimate(row))

        instrumentation_coverage: dict[str, object] = {
            "registered_sensor_count": len(registered_sensors),
            "unusable_sensor_count": sum(
                1 for row in quality_rows if row.quality_state == QualityState.UNUSABLE
            ),
            "caution_sensor_count": sum(
                1 for row in quality_rows if row.quality_state == QualityState.USABLE_WITH_CAUTION
            ),
            "sensors_never_reported": max(0, len(registered_sensors) - len(quality_rows)),
        }
        quality_context = {
            "state": _overall_quality_state(quality_rows),
            "registered_sensor_count": len(registered_sensors),
        }
        limitations = _collect_limitations(state_rows, ml_result_ids)

        evidence = ConditionEvidence(
            tenant_id=tenant_id,
            machine_id=machine_id,
            as_of_timestamp=now,
            criticality=machine.criticality.value,
            items=tuple(items),
            quality_context=quality_context,
            instrumentation_coverage=instrumentation_coverage,
            baseline_versions={
                fid: finding.baseline_version_ids
                for fid, finding in zip(rule_finding_ids, rule_findings, strict=True)
            },
            rule_finding_ids=tuple(rule_finding_ids),
            ml_result_ids=tuple(ml_result_ids),
            state_estimate_ids=tuple(state_estimate_ids),
            limitations=tuple(limitations),
        )

        synthesis_result = synthesize(evidence, self._policy)

        recent_rows = await self._assessments.list_recent(tenant_id, machine_id, limit=10)
        recent = [
            RecentAssessment(condition_type=row.condition_type.value, severity=row.severity.value)
            for row in recent_rows
        ]
        lifecycle = classify_lifecycle(
            recent, synthesis_result.condition_type, synthesis_result.severity, self._policy
        )
        first_detected_at = (
            recent_rows[0].first_detected_at
            if lifecycle.inherit_first_detected_at and recent_rows
            else now
        )

        assessment = ConditionAssessment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            machine_id=machine_id,
            component_id=None,
            condition_type=synthesis_result.condition_type,
            lifecycle_state=lifecycle.lifecycle_state,
            severity=synthesis_result.severity,
            confidence=synthesis_result.confidence,
            as_of_timestamp=now,
            first_detected_at=first_detected_at,
            evidence_summary={
                "what_is_happening": synthesis_result.what_is_happening,
                "why": list(synthesis_result.why),
                "supporting_evidence": list(synthesis_result.supporting_evidence),
                "contradicting_evidence": list(synthesis_result.contradicting_evidence),
                "data_trustworthiness": synthesis_result.data_trustworthiness,
                "unknowns": list(synthesis_result.unknowns),
            },
            rule_finding_ids=rule_finding_ids,
            ml_result_ids=ml_result_ids,
            state_estimate_ids=state_estimate_ids,
            quality_context=quality_context,
            baseline_versions=dict(evidence.baseline_versions),
            instrumentation_coverage=instrumentation_coverage,
            limitations=limitations,
            recommended_next_evidence=synthesis_result.recommended_next_evidence,
            policy_version=self._policy.policy_version,
            engine_version=self._policy.engine_version,
        )
        persisted = await self._assessments.insert(assessment)

        METRICS.increment("condition_assessments_created")
        if synthesis_result.condition_type == "AMBIGUOUS_CONDITION":
            METRICS.increment("condition_ambiguous")
        if synthesis_result.condition_type == "INSUFFICIENT_EVIDENCE":
            METRICS.increment("condition_insufficient_evidence")
        METRICS.set_gauge("intelligence_processing_duration", time.perf_counter() - started)
        return persisted

    def _evidence_from_rule_finding(self, finding: RuleFinding) -> tuple[EvidenceItem, str]:
        mapping = self._policy.rule_finding_map.get(finding.finding_type.value)
        condition_hint = mapping.condition if mapping else None
        strength = mapping.strength if mapping else "WEAK"

        override = self._policy.severity_override
        if (
            finding.finding_type.value == override.finding_type
            and finding.severity.value == override.when_severity
        ):
            condition_hint = override.condition

        # A still-debouncing CANDIDATE finding is real evidence but not yet confirmed
        # stable — recorded, never allowed to independently establish a condition.
        if finding.state == RuleFindingState.CANDIDATE:
            strength = "WEAK"

        description = (
            f"Rule finding {finding.finding_type.value} ({finding.state.value}, "
            f"{finding.severity.value}): {finding.message}"
        )
        return (
            EvidenceItem(
                source_type="RULE_FINDING",
                source_id=str(finding.id),
                strength=strength,
                condition_hint=condition_hint,
                description=description,
                severity=finding.severity.value,
            ),
            str(finding.id),
        )

    async def _evidence_from_ml_result(self, result: MLInferenceResult) -> EvidenceItem | None:
        if result.status.value != "OK":
            return None

        try:
            metadata = get_model_registry().get_metadata(result.model_id, result.model_version)
            model_status = metadata.status
        except (ModelNotFoundError, FileNotFoundError):
            model_status = None

        is_validated = model_status in _SERVABLE_ML_STATUSES

        if result.result_kind.value == "ANOMALY":
            description = (
                f"ML anomaly model {result.model_id}@{result.model_version} "
                f"({'VALIDATED' if is_validated else 'EXPERIMENT'}): "
                f"anomaly_score={result.anomaly_score}, anomalous={result.anomalous}"
            )
            # Isolation Forest is not fault-specific (ADR-093) — it can corroborate that
            # something is abnormal, but never itself hints which ConditionType.
            return EvidenceItem(
                source_type="ML_RESULT",
                source_id=str(result.id),
                strength="EXPERIMENTAL" if not is_validated else "WEAK",
                condition_hint=None,
                description=description,
            )

        predicted_class = result.predicted_class
        condition_hint = (
            self._policy.ml_classification_map.get(predicted_class) if predicted_class else None
        )
        confidence_ok = (
            result.confidence_category is not None
            and result.confidence_category.value
            in (
                "MODERATE",
                "HIGH",
            )
        )
        if not is_validated:
            strength = "EXPERIMENTAL"
        elif confidence_ok:
            strength = "SUPPORTING"
        else:
            strength = "WEAK"

        description = (
            f"ML classifier {result.model_id}@{result.model_version} "
            f"({'VALIDATED' if is_validated else 'EXPERIMENT'}): predicted_class="
            f"{predicted_class}, confidence={result.confidence_category}"
        )
        return EvidenceItem(
            source_type="ML_RESULT",
            source_id=str(result.id),
            strength=strength,
            condition_hint=condition_hint,
            description=description,
        )

    def _evidence_from_state_estimate(self, row: StateEstimate) -> EvidenceItem:
        """Always returns a real item — even a STABLE/untrustworthy estimate is evidence
        that was actually checked, distinct from no evidence existing at all (a real bug
        found live: collapsing "checked, found nothing abnormal" into "nothing was
        checked" misreported a genuinely healthy, fully-instrumented machine as
        `INSUFFICIENT_EVIDENCE`). Only a meaningfully deteriorating, trustworthy estimate
        gets a fault-hinting `condition_hint`; a genuinely low, near-baseline level
        corroborates `NORMAL_OPERATION` (`SUPPORTING`) — `WEAK` items are never tallied
        either way (`synthesis._TALLIED_STRENGTHS`).

        A STABLE trend at an ALREADY meaningfully elevated level abstains (`WEAK`) rather
        than either of those: STABLE only means "not currently changing", not "healthy",
        so casting it as `NORMAL_OPERATION` support is wrong the moment the level itself
        is meaningfully elevated (a real bug — a state estimate that had climbed to a
        sustained elevated plateau was voting `NORMAL_OPERATION` purely because its trend
        had gone STABLE, contradicting co-active fault evidence from the same window and
        forcing a spurious `AMBIGUOUS_CONDITION` read instead of the single fault
        hypothesis the rest of the evidence actually supported). But a single fresh
        estimate reaching a modestly elevated level straight from a cold, uninformative
        prior is not yet trustworthy fault evidence either (this filter's own
        `minimum_observations: 1` policy lets uncertainty read LOW after just one
        real observation, well before the level has had time to settle) — so this case
        abstains rather than voting a specific fault, landing on the same
        "checked, nothing definitively voted" `NORMAL_OPERATION`-at-`MODERATE`-confidence
        path `synthesize()` already uses when sources were checked but nothing voted
        either way."""
        base = f"State estimate {row.state_type.value}: level={row.state_value:.3f}"

        if row.prediction_only or row.uncertainty.value == "HIGH":
            return EvidenceItem(
                source_type="STATE_ESTIMATE",
                source_id=str(row.id),
                strength="WEAK",
                condition_hint=None,
                description=(
                    f"{base}, trend={row.trend.value}, uncertainty={row.uncertainty.value} "
                    "(not trustworthy enough to vote)."
                ),
            )

        is_meaningfully_elevated = (
            abs(row.state_value) >= self._policy.state_estimate.minimum_meaningful_level
        )
        if row.trend.value == "DETERIORATING" and is_meaningfully_elevated:
            condition_hint = (
                "LUBRICATION_DELIVERY_DEGRADATION"
                if row.state_type.value == "LUBRICATION_DELIVERY_STATE"
                else "BEARING_CONDITION_DEGRADATION"
            )
            return EvidenceItem(
                source_type="STATE_ESTIMATE",
                source_id=str(row.id),
                strength="SUPPORTING",
                condition_hint=condition_hint,
                description=f"{base}, trend=DETERIORATING, uncertainty={row.uncertainty.value}",
            )

        if row.trend.value == "STABLE" and is_meaningfully_elevated:
            return EvidenceItem(
                source_type="STATE_ESTIMATE",
                source_id=str(row.id),
                strength="WEAK",
                condition_hint=None,
                description=(
                    f"{base}, trend=STABLE, uncertainty={row.uncertainty.value} "
                    "(elevated but no longer actively worsening — not confidently normal "
                    "or confidently a distinct active fault)."
                ),
            )

        return EvidenceItem(
            source_type="STATE_ESTIMATE",
            source_id=str(row.id),
            strength="SUPPORTING",
            condition_hint="NORMAL_OPERATION",
            description=f"{base}, trend={row.trend.value}, uncertainty={row.uncertainty.value}",
        )


def _overall_quality_state(quality_rows: list[SensorQualityState]) -> str:
    if not quality_rows:
        return "NO_TRUSTED_DATA"
    if any(row.quality_state == QualityState.USABLE_WITH_CAUTION for row in quality_rows):
        return "CAUTION"
    if all(row.quality_state == QualityState.UNUSABLE for row in quality_rows):
        return "NO_TRUSTED_DATA"
    return "TRUSTED"


def _collect_limitations(
    state_rows: dict[str, StateEstimate], ml_result_ids: list[str]
) -> list[str]:
    limitations: list[str] = []
    for state_type, row in state_rows.items():
        if row.prediction_only:
            limitations.append(
                f"{state_type} state estimate has no recent observations (prediction-only)."
            )
        if row.uncertainty.value == "HIGH":
            limitations.append(f"{state_type} state estimate uncertainty is HIGH.")
    if not ml_result_ids:
        limitations.append("No ML inference results are available for this machine.")
    return limitations
