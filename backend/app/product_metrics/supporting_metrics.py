"""Supporting product metrics (Phase 22 brief §22.2) — computed only where the platform's
persisted data genuinely supports the definition; nothing here is forced or fabricated.
See docs/PRODUCT_METRICS.md for each metric's exact numerator/denominator.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_services.policy import DEFAULT_POLICY
from app.customer_services.service import instrumented_machine_ids_subquery
from app.domain.enums import (
    AgentMessageRole,
    DocumentStatus,
    FeedbackClassification,
    IncidentState,
    MaintenanceState,
    MetricProvenance,
    RecommendedWindow,
)
from app.domain.models import (
    AgentMessage,
    AgentSession,
    DemoCMMSWorkOrder,
    FeedbackRecord,
    Incident,
    KnowledgeDocument,
    Machine,
    MaintenanceCase,
    Telemetry,
)
from app.knowledge.services.rag_service import INSUFFICIENT_DOCUMENTATION_TEXT
from app.product_metrics.models import Metric

_TERMINAL_INCIDENT_STATES = (IncidentState.RESOLVED, IncidentState.CLOSED)


def _metric(
    *,
    metric_id: str,
    name: str,
    definition: str,
    window_description: str,
    value: float | None,
    unit: str,
    numerator: float | None,
    denominator: float | None,
    provenance: MetricProvenance,
    tenant_id: uuid.UUID,
    source: str,
    note: str | None = None,
) -> Metric:
    return Metric(
        metric_id=metric_id,
        name=name,
        definition=definition,
        window_description=window_description,
        value=value,
        unit=unit,
        numerator=numerator,
        denominator=denominator,
        provenance=provenance,
        source=source,
        scope=f"tenant:{tenant_id}",
        calculated_at=datetime.now(UTC),
        data_completeness_note=note,
    )


async def _ratio_metric(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    metric_id: str,
    name: str,
    definition: str,
    window_description: str,
    numerator: int,
    denominator: int,
    provenance: MetricProvenance,
    source: str,
) -> Metric:
    value = (numerator / denominator) if denominator > 0 else None
    return _metric(
        metric_id=metric_id,
        name=name,
        definition=definition,
        window_description=window_description,
        value=value,
        unit="ratio",
        numerator=float(numerator),
        denominator=float(denominator),
        provenance=provenance,
        tenant_id=tenant_id,
        source=source,
        note=None if denominator > 0 else "Denominator is zero — value is undefined.",
    )


async def compute_supporting_metrics(session: AsyncSession, tenant_id: uuid.UUID) -> list[Metric]:
    metrics: list[Metric] = []

    # --- connected / instrumented asset coverage --------------------------------
    tenant_machine_ids = list(
        (await session.scalars(select(Machine.id).where(Machine.tenant_id == tenant_id))).all()
    )
    total_machines = len(tenant_machine_ids)
    instrumented = (
        len((await session.scalars(instrumented_machine_ids_subquery(tenant_machine_ids))).all())
        if total_machines
        else 0
    )
    connected = await session.scalar(
        select(func.count(func.distinct(Telemetry.machine_id))).where(
            Telemetry.tenant_id == tenant_id
        )
    ) or 0

    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="coverage.instrumented_asset_coverage",
            name="Instrumented asset coverage",
            definition="Machines with >=1 attached sensor / total machines.",
            window_description="Current state",
            numerator=instrumented,
            denominator=total_machines,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="coverage.connected_asset_coverage",
            name="Connected asset coverage",
            definition="Machines that have ever produced a telemetry event / total machines.",
            window_description="All time",
            numerator=connected,
            denominator=total_machines,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    freshness_cutoff = datetime.now(UTC) - timedelta(
        minutes=DEFAULT_POLICY.telemetry_freshness_window_minutes
    )
    recent = await session.scalar(
        select(func.count(func.distinct(Telemetry.machine_id))).where(
            Telemetry.tenant_id == tenant_id, Telemetry.source_timestamp >= freshness_cutoff
        )
    ) or 0
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="coverage.telemetry_availability",
            name="Telemetry availability",
            definition=(
                f"Machines with telemetry in the last "
                f"{DEFAULT_POLICY.telemetry_freshness_window_minutes} minutes / total machines."
            ),
            window_description=(
                f"Trailing {DEFAULT_POLICY.telemetry_freshness_window_minutes} minutes"
            ),
            numerator=recent,
            denominator=total_machines,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    # --- feedback-derived rates ---------------------------------------------------
    feedback_counts_stmt = select(FeedbackRecord.classification, func.count()).where(
        FeedbackRecord.tenant_id == tenant_id
    ).group_by(FeedbackRecord.classification)
    counts: dict[FeedbackClassification, int] = {
        row[0]: row[1] for row in (await session.execute(feedback_counts_stmt)).all()
    }
    total_feedback = sum(counts.values())
    true_positive = counts.get(FeedbackClassification.TRUE_POSITIVE, 0)
    false_positive = counts.get(FeedbackClassification.FALSE_POSITIVE, 0)
    missed_failure = counts.get(FeedbackClassification.MISSED_FAILURE, 0)

    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="feedback.true_positive_confirmation_rate",
            name="True-positive confirmation rate",
            definition="TRUE_POSITIVE feedback / all recorded feedback.",
            window_description="All time",
            numerator=true_positive,
            denominator=total_feedback,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="feedback.false_positive_rate",
            name="False-positive feedback rate",
            definition="FALSE_POSITIVE feedback / all recorded feedback.",
            window_description="All time",
            numerator=false_positive,
            denominator=total_feedback,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="feedback.useful_incident_rate",
            name="Useful incident rate",
            definition=(
                "(TRUE_POSITIVE + MISSED_FAILURE) feedback / all recorded feedback — the "
                "share of investigated incidents a technician judged worth having raised."
            ),
            window_description="All time",
            numerator=true_positive + missed_failure,
            denominator=total_feedback,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    # --- incident burden / timing --------------------------------------------------
    unresolved = await session.scalar(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id, Incident.state.notin_(_TERMINAL_INCIDENT_STATES)
        )
    ) or 0
    metrics.append(
        _metric(
            metric_id="incidents.unresolved_burden",
            name="Unresolved incident burden",
            definition="Count of incidents not in RESOLVED/CLOSED state.",
            window_description="Current state",
            value=float(unresolved),
            unit="incidents",
            numerator=None,
            denominator=None,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            tenant_id=tenant_id,
            source="app.product_metrics.supporting_metrics",
        )
    )

    ack_seconds = await session.scalar(
        select(
            func.avg(
                func.extract("epoch", Incident.acknowledged_at)
                - func.extract("epoch", Incident.first_detected_at)
            )
        ).where(Incident.tenant_id == tenant_id, Incident.acknowledged_at.is_not(None))
    )
    metrics.append(
        _metric(
            metric_id="incidents.mean_acknowledge_time_minutes",
            name="Mean acknowledgement time",
            definition="Mean minutes from incident first_detected_at to acknowledged_at.",
            window_description="All time",
            value=(ack_seconds / 60) if ack_seconds is not None else None,
            unit="minutes",
            numerator=None,
            denominator=None,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            tenant_id=tenant_id,
            source="app.product_metrics.supporting_metrics",
            note=None if ack_seconds is not None else "No acknowledged incidents yet.",
        )
    )

    resolution_seconds = await session.scalar(
        select(
            func.avg(
                func.extract("epoch", MaintenanceCase.completed_at)
                - func.extract("epoch", MaintenanceCase.created_at)
            )
        ).where(
            MaintenanceCase.tenant_id == tenant_id,
            MaintenanceCase.state == MaintenanceState.COMPLETED,
        )
    )
    metrics.append(
        _metric(
            metric_id="maintenance.mean_resolution_time_minutes",
            name="Mean maintenance resolution time",
            definition="Mean minutes from case creation to case completion, COMPLETED cases only.",
            window_description="All time",
            value=(resolution_seconds / 60) if resolution_seconds is not None else None,
            unit="minutes",
            numerator=None,
            denominator=None,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            tenant_id=tenant_id,
            source="app.product_metrics.supporting_metrics",
            note=None if resolution_seconds is not None else "No completed cases yet.",
        )
    )

    actionable_lead_numerator = await session.scalar(
        select(func.count())
        .select_from(FeedbackRecord)
        .join(MaintenanceCase, MaintenanceCase.id == FeedbackRecord.maintenance_case_id)
        .where(
            FeedbackRecord.tenant_id == tenant_id,
            FeedbackRecord.classification == FeedbackClassification.TRUE_POSITIVE,
            MaintenanceCase.recommended_window != RecommendedWindow.NOW,
        )
    ) or 0
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="decisions.actionable_warning_lead_time_rate",
            name="Actionable-warning lead-time rate",
            definition=(
                "TRUE_POSITIVE feedback whose case had a non-NOW recommended window / "
                "all TRUE_POSITIVE feedback."
            ),
            window_description="All time",
            numerator=actionable_lead_numerator,
            denominator=true_positive,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    # --- conversion / workflow adoption ---------------------------------------------
    total_incidents = await session.scalar(
        select(func.count()).select_from(Incident).where(Incident.tenant_id == tenant_id)
    ) or 0
    total_cases = await session.scalar(
        select(func.count()).select_from(MaintenanceCase).where(
            MaintenanceCase.tenant_id == tenant_id
        )
    ) or 0
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="workflow.decision_to_maintenance_conversion",
            name="Decision-to-maintenance conversion",
            definition="Maintenance cases created / incidents created.",
            window_description="All time",
            numerator=total_cases,
            denominator=total_incidents,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    total_work_orders = await session.scalar(
        select(func.count()).select_from(DemoCMMSWorkOrder).where(
            DemoCMMSWorkOrder.tenant_id == tenant_id
        )
    ) or 0
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="workflow.cmms_draft_creation_rate",
            name="CMMS draft creation rate",
            definition="Demo CMMS work-order drafts created / maintenance cases created.",
            window_description="All time",
            numerator=total_work_orders,
            denominator=total_cases,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    # --- assistant / knowledge adoption ---------------------------------------------
    assistant_sessions = await session.scalar(
        select(func.count()).select_from(AgentSession).where(AgentSession.tenant_id == tenant_id)
    ) or 0
    assistant_messages = await session.scalar(
        select(func.count()).select_from(AgentMessage).where(AgentMessage.tenant_id == tenant_id)
    ) or 0
    metrics.append(
        _metric(
            metric_id="assistant.usage_sessions",
            name="Assistant usage (sessions)",
            definition="Count of AgentSession rows.",
            window_description="All time",
            value=float(assistant_sessions),
            unit="sessions",
            numerator=None,
            denominator=None,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            tenant_id=tenant_id,
            source="app.product_metrics.supporting_metrics",
        )
    )
    metrics.append(
        _metric(
            metric_id="assistant.usage_messages",
            name="Assistant usage (messages)",
            definition="Count of AgentMessage rows (both user and assistant turns).",
            window_description="All time",
            value=float(assistant_messages),
            unit="messages",
            numerator=None,
            denominator=None,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            tenant_id=tenant_id,
            source="app.product_metrics.supporting_metrics",
        )
    )

    assistant_answers = await session.scalar(
        select(func.count()).select_from(AgentMessage).where(
            AgentMessage.tenant_id == tenant_id, AgentMessage.role == AgentMessageRole.ASSISTANT
        )
    ) or 0
    insufficient_answers = await session.scalar(
        select(func.count()).select_from(AgentMessage).where(
            AgentMessage.tenant_id == tenant_id,
            AgentMessage.role == AgentMessageRole.ASSISTANT,
            AgentMessage.content.contains(INSUFFICIENT_DOCUMENTATION_TEXT),
        )
    ) or 0
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="knowledge.insufficient_documentation_rate",
            name="Insufficient-documentation rate",
            definition=(
                "Assistant answers containing the exact insufficient-documentation "
                "fallback / all assistant answers."
            ),
            window_description="All time",
            numerator=insufficient_answers,
            denominator=assistant_answers,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    approved_docs = await session.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(
            or_(KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.tenant_id.is_(None)),
            KnowledgeDocument.status == DocumentStatus.APPROVED,
        )
    ) or 0
    total_docs = await session.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(
            or_(KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.tenant_id.is_(None))
        )
    ) or 0
    metrics.append(
        await _ratio_metric(
            session,
            tenant_id,
            metric_id="knowledge.approved_knowledge_coverage",
            name="Approved knowledge coverage",
            definition="APPROVED documents visible to this tenant / all documents visible to it.",
            window_description="Current state",
            numerator=approved_docs,
            denominator=total_docs,
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC,
            source="app.product_metrics.supporting_metrics",
        )
    )

    return metrics
