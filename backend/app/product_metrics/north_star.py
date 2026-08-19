"""The North Star: "percentage of meaningful lubrication issues detected with
actionable lead time" (CLAUDE.md).

Definition (see docs/PRODUCT_METRICS.md for the full rationale):

- **Denominator** ("meaningful lubrication issues"): every `FeedbackRecord` a technician
  has classified as `TRUE_POSITIVE` or `MISSED_FAILURE` — i.e., every case a human
  confirmed was a real issue, whether the platform gave useful lead time or not. This is
  the honest, currently-measurable population: this reference platform has no external
  ground-truth failure feed, so it cannot count a failure that occurred with *no*
  incident ever raised (see `docs/PRODUCT_METRICS.md` "Known limitation").
- **Numerator** ("detected with actionable lead time"): of those, the ones classified
  `TRUE_POSITIVE` whose `MaintenanceCase.recommended_window` was not `NOW` — i.e., the
  platform's own decision output gave the technician a planning window rather than only
  flagging an emergency already underway.

This is computed only over `FeedbackRecord`s that exist — i.e., only over completed
maintenance cases with recorded feedback — so a small/young dataset gives a wide-variance
number. Always presented as `DEMO_ESTIMATE`/`MEASURED_PLATFORM_METRIC` per
`docs/PRODUCT_METRICS.md`, never as validated industrial performance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import FeedbackClassification, MetricProvenance, RecommendedWindow
from app.domain.models import FeedbackRecord, MaintenanceCase
from app.product_metrics.models import Metric, NorthStarResult

NORTH_STAR_METRIC_ID = "north_star.meaningful_issues_detected_with_lead_time"


async def compute_north_star(session: AsyncSession, tenant_id: uuid.UUID) -> NorthStarResult:
    denominator_stmt = select(func.count()).select_from(FeedbackRecord).where(
        FeedbackRecord.tenant_id == tenant_id,
        FeedbackRecord.classification.in_(
            (FeedbackClassification.TRUE_POSITIVE, FeedbackClassification.MISSED_FAILURE)
        ),
    )
    denominator = await session.scalar(denominator_stmt) or 0

    numerator_stmt = (
        select(func.count())
        .select_from(FeedbackRecord)
        .join(MaintenanceCase, MaintenanceCase.id == FeedbackRecord.maintenance_case_id)
        .where(
            FeedbackRecord.tenant_id == tenant_id,
            FeedbackRecord.classification == FeedbackClassification.TRUE_POSITIVE,
            MaintenanceCase.recommended_window != RecommendedWindow.NOW,
        )
    )
    numerator = await session.scalar(numerator_stmt) or 0

    value = (numerator / denominator) if denominator > 0 else None
    completeness_note = (
        None
        if denominator > 0
        else "No technician feedback recorded yet for this tenant — value is undefined, "
        "not zero."
    )

    metric = Metric(
        metric_id=NORTH_STAR_METRIC_ID,
        name="Meaningful lubrication issues detected with actionable lead time",
        definition=(
            "Of technician-confirmed real issues (TRUE_POSITIVE or MISSED_FAILURE "
            "feedback), the share that were TRUE_POSITIVE with a non-emergency "
            "(not NOW) recommended maintenance window at detection."
        ),
        window_description="All time (all recorded feedback for this tenant)",
        value=value,
        unit="ratio",
        numerator=float(numerator),
        denominator=float(denominator),
        provenance=MetricProvenance.DEMO_ESTIMATE,
        source="app.product_metrics.north_star.compute_north_star",
        scope=f"tenant:{tenant_id}",
        calculated_at=datetime.now(UTC),
        data_completeness_note=completeness_note,
    )
    return NorthStarResult(
        metric=metric,
        meaningful_issues_detected_with_lead_time=numerator,
        meaningful_issues_total=denominator,
    )
