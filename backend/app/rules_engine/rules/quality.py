"""`INSUFFICIENT_TRUSTED_DATA` (Phase 9 brief §10 item 17, §40/§41) — machine-level quality
gate: when too few of a machine's currently-tracked sensors are `ELIGIBLE`/
`ELIGIBLE_WITH_CAUTION` this cycle, no equipment-condition finding may fire for that machine
at all (`app.rules_engine.services.rule_engine` enforces the "instead of" — this module only
produces the candidate itself). Converts a data-quality problem into an explicit, visible
finding rather than either silently emitting nothing or, worse, silently evaluating rules
against untrustworthy data. Pure function, no database.
"""

from __future__ import annotations

import uuid

from app.domain.enums import EvidenceStrength, RuleCategory, RuleFindingType
from app.rules_engine.config.policy import RulesPolicy
from app.rules_engine.domain.results import RuleFindingCandidate


def check_insufficient_trusted_data(
    machine_id: uuid.UUID,
    *,
    tracked_sensor_count: int,
    eligible_sensor_fraction: float,
    policy: RulesPolicy,
) -> RuleFindingCandidate | None:
    if tracked_sensor_count == 0:
        return None
    if eligible_sensor_fraction >= policy.quality.minimum_eligible_sensor_fraction:
        return None
    return RuleFindingCandidate(
        finding_type=RuleFindingType.INSUFFICIENT_TRUSTED_DATA,
        rule_id="insufficient_trusted_data",
        rule_version="1",
        category=RuleCategory.SENSOR_QUALITY_DEPENDENT,
        component_type="MACHINE",
        component_id=machine_id,
        evidence_strength=EvidenceStrength.MODERATE,
        message=(
            f"Only {eligible_sensor_fraction:.0%} of this machine's tracked sensors are "
            "currently eligible for evaluation (configured minimum "
            f"{policy.quality.minimum_eligible_sensor_fraction:.0%}) — no equipment-"
            "condition finding is evaluated for this machine this cycle."
        ),
        evidence={
            "quality": {
                "tracked_sensor_count": tracked_sensor_count,
                "eligible_sensor_fraction": eligible_sensor_fraction,
                "minimum_required_fraction": policy.quality.minimum_eligible_sensor_fraction,
            }
        },
        limitations=[
            "This is a data-quality gate, not an equipment-condition finding.",
            "Does not indicate anything about the machine's physical condition.",
        ],
        quality_context={"reason": "insufficient_eligible_sensor_fraction"},
    )
