"""Bearing-condition rules (Phase 9 brief §16-§17) — `INDEPENDENT_BEARING_CONDITION_PATTERN`
is mandatory (brief §39): a bearing showing temperature/vibration deviation while every
lubrication-system signal on the machine remains within expected range must never be
auto-attributed to lubrication (`docs/FAILURE_MODE_CATALOG.md` §12). Evaluated per bearing
(a machine may have more than one) — `app.rules_engine.services.rule_engine` calls this once
per bearing that has an active temperature and/or vibration finding, passing a
machine-wide "are all lubrication-system signals currently normal" flag.

Pure function, no database.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.enums import RuleCategory, RuleFindingType
from app.rules_engine.config.policy import RulesPolicy
from app.rules_engine.domain.results import RuleFindingCandidate
from app.rules_engine.domain.strength import escalate_one, weakest


def check_independent_bearing_pattern(
    bearing_id: uuid.UUID,
    temperature_finding: RuleFindingCandidate | None,
    vibration_finding: RuleFindingCandidate | None,
    *,
    lubrication_signals_normal: bool,
    policy: RulesPolicy,
) -> RuleFindingCandidate | None:
    del policy  # kept for signature symmetry with every other check_* rule; unused here
    present = [f for f in (temperature_finding, vibration_finding) if f is not None]
    if not present or not lubrication_signals_normal:
        return None

    strength = weakest([f.evidence_strength for f in present])
    if len(present) > 1:
        strength = escalate_one(strength)

    combined_evidence: dict[str, Any] = {}
    for f in present:
        combined_evidence.update(f.evidence)

    signal_names = " and ".join(f.finding_type.value.split("_")[0].lower() for f in present)
    return RuleFindingCandidate(
        finding_type=RuleFindingType.INDEPENDENT_BEARING_CONDITION_PATTERN,
        rule_id="independent_bearing_condition_pattern",
        rule_version="1",
        category=RuleCategory.BEARING_CONDITION,
        component_type="BEARING",
        component_id=bearing_id,
        evidence_strength=strength,
        message=(
            f"Bearing {signal_names} deviates from its expected baseline while monitored "
            "lubrication-system signals (reservoir, pressure, flow, cycle completion) "
            "remain within normal range — evidence does not support a lubrication-related "
            "cause. Further mechanical inspection recommended."
        ),
        evidence=combined_evidence,
        limitations=[
            "Evidence indicates a developing bearing issue; it does not identify the "
            "mechanical cause (misalignment, imbalance, fatigue, contamination, etc.).",
            "Absence of an active lubrication-system finding this cycle does not "
            "retroactively rule out a lubrication contribution earlier in onset.",
        ],
        source_event_ids=sorted({eid for f in present for eid in f.source_event_ids}),
        baseline_version_ids=sorted({bid for f in present for bid in f.baseline_version_ids}),
        quality_context={"signals_combined": [f.finding_type.value for f in present]},
    )
