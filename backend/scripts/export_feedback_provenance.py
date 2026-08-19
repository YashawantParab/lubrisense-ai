"""Feedback-provenance export for a future, explicitly human-triggered retraining
dataset (Phase 32 brief §32.7).

This script never retrains or queues retraining — it only produces a read-only report
tying each `FeedbackRecord` (Phase 17) to the `ConditionAssessment` it was recorded
against, and from there to the specific `ml_result_ids` (Phase 11 `MLInferenceResult`
rows) that assessment cited as evidence at the time. That is the provenance chain a
future ml-service training run would need to decide which feedback-confirmed examples
are worth reviewing for a labeled retraining batch — this script only surfaces the chain,
it does not act on it.

    uv run python scripts/export_feedback_provenance.py --tenant-id <uuid> \
        --out docs/results/feedback_provenance.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import ConditionAssessment, FeedbackRecord
from app.infrastructure.database import Database


async def _export(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    result = await session.execute(
        select(FeedbackRecord)
        .where(FeedbackRecord.tenant_id == tenant_id)
        .order_by(FeedbackRecord.recorded_at)
    )
    feedback_records = result.scalars().all()

    report: list[dict[str, Any]] = []
    for feedback in feedback_records:
        condition = await session.get(ConditionAssessment, feedback.condition_assessment_id)
        report.append(
            {
                "feedback_id": str(feedback.id),
                "maintenance_case_id": str(feedback.maintenance_case_id),
                "incident_id": str(feedback.incident_id),
                "classification": feedback.classification.value,
                "recorded_at": feedback.recorded_at.isoformat(),
                "recorded_by": feedback.recorded_by,
                "condition_assessment_id": str(feedback.condition_assessment_id),
                "ml_result_ids": condition.ml_result_ids if condition else [],
                "rule_finding_ids": condition.rule_finding_ids if condition else [],
                "state_estimate_ids": condition.state_estimate_ids if condition else [],
                "condition_type": condition.condition_type.value if condition else None,
                "note": (
                    "Provenance only — no retraining dataset was built or modified by "
                    "producing this report."
                ),
            }
        )
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings)
    try:
        async with database.session() as session:
            report = await _export(session, args.tenant_id)
    finally:
        await database.dispose()

    payload = {
        "tenant_id": str(args.tenant_id),
        "feedback_count": len(report),
        "ml_linked_feedback_count": sum(1 for r in report if r["ml_result_ids"]),
        "records": report,
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        print(f"Wrote {args.out} ({len(report)} feedback record(s))")
    else:
        print(text)


if __name__ == "__main__":
    asyncio.run(main())
