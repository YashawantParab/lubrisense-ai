"""Pure evidence-synthesis logic — no I/O, no config-file reads, no database. Takes a
`ConditionEvidence` bundle (already gathered by `ConditionEngine`) and a resolved
`ConditionIntelligencePolicy`, returns one `ConditionAssessmentResult`. Kept pure and
separate from `condition_engine.py`'s DB orchestration for the same reason
`app.state_estimation.models.kalman`/`estimator` are split from `services/` — the decision
logic itself is what needs to be exhaustively unit-tested; the DB plumbing around it does
not.

Evidence weighting (Phase 13 brief §13.7): explainable tiers, not an opaque weighted sum.
`STRONG` evidence (a cross-signal rule pattern, already multi-signal corroborated inside
the rules engine itself) can establish a condition on its own; `SUPPORTING` evidence
(single-signal rule findings, VALIDATED-ML classifications, meaningfully-deteriorating
state estimates) needs at least one corroborating source of a *different* type to reach
`HIGH` confidence; `EXPERIMENTAL` evidence (an EXPERIMENT-status ML model's output) is
recorded for transparency but never counted in the tally at all (Phase 13 brief §13.3).
"""

from __future__ import annotations

from collections import defaultdict

from app.condition_intelligence.config.policy import ConditionIntelligencePolicy
from app.condition_intelligence.domain.models import ConditionAssessmentResult, ConditionEvidence

_TALLIED_STRENGTHS = frozenset({"STRONG", "SUPPORTING"})

#: A Phase 12 state estimate can only ever vote a *generic* delivery/bearing hint (ADR-103:
#: the Kalman filter is fault-agnostic, it cannot itself distinguish restriction from
#: leakage from pump degradation). When a more specific rule/ML hypothesis is ALSO present
#: for the same family, the generic vote corroborates it rather than becoming a second,
#: competing hypothesis — without this, a state estimate voting
#: `LUBRICATION_DELIVERY_DEGRADATION` alongside a rule finding voting
#: `DEVELOPING_RESTRICTION_PATTERN` would be misreported as `AMBIGUOUS_CONDITION` (a real
#: bug caught by `test_single_strong_vote_with_corroboration_is_high_confidence`), even
#: though both describe the same underlying delivery problem at different specificity.
_GENERIC_TO_SPECIFIC_FAMILY: dict[str, frozenset[str]] = {
    "LUBRICATION_DELIVERY_DEGRADATION": frozenset(
        {
            "DEVELOPING_RESTRICTION_PATTERN",
            "DELIVERY_BLOCKAGE_PATTERN",
            "POSSIBLE_LEAKAGE_PATTERN",
            "PUMP_PERFORMANCE_DEGRADATION",
            "LOW_LUBRICANT_AVAILABILITY",
        }
    ),
    "BEARING_CONDITION_DEGRADATION": frozenset({"INDEPENDENT_BEARING_CONDITION"}),
}


def _matching_hints(condition_type: str) -> frozenset[str]:
    """`condition_type` itself, plus any generic hint that folds into it (the reverse of
    `_GENERIC_TO_SPECIFIC_FAMILY`) — the set of `EvidenceItem.condition_hint` values that
    should all be treated as evidence *for* `condition_type`."""
    hints = {condition_type}
    for generic, specifics in _GENERIC_TO_SPECIFIC_FAMILY.items():
        if condition_type in specifics:
            hints.add(generic)
    return frozenset(hints)


def synthesize(
    evidence: ConditionEvidence, policy: ConditionIntelligencePolicy
) -> ConditionAssessmentResult:
    unknowns: list[str] = list(evidence.limitations)

    # --- Step 1: quality-first gate (Phase 13 brief §13.9) ---------------------------
    quality_verdict = _quality_gate_verdict(evidence, policy)
    if quality_verdict is not None:
        return quality_verdict

    # --- Step 2: tally non-experimental votes by condition hypothesis ---------------
    votes: dict[str, list[str]] = defaultdict(list)  # condition -> [source_type, ...]
    experimental_notes: list[str] = []
    for item in evidence.items:
        if item.condition_hint is None:
            continue
        if item.strength == "EXPERIMENTAL":
            experimental_notes.append(item.description)
            continue
        if item.strength in _TALLIED_STRENGTHS:
            votes[item.condition_hint].append(item.source_type)

    normal_votes = votes.pop("NORMAL_OPERATION", [])

    # Fold a generic hint into whichever more-specific sibling(s) are also present, rather
    # than letting it stand as its own competing hypothesis (see
    # `_GENERIC_TO_SPECIFIC_FAMILY`'s docstring).
    for generic, specifics in _GENERIC_TO_SPECIFIC_FAMILY.items():
        if generic not in votes:
            continue
        present_specifics = [s for s in specifics if s in votes]
        if present_specifics:
            generic_sources = votes.pop(generic)
            for specific in present_specifics:
                votes[specific].extend(generic_sources)

    non_normal_types = sorted(votes)

    # --- Step 3: no abnormal-condition votes -> NORMAL_OPERATION, unless literally nothing
    # was ever checked (zero rule findings, zero ML results, zero state estimates even
    # fetched), in which case there is nothing to base NORMAL_OPERATION on either. A
    # source that *was* checked and came back stable/inactive (e.g. a STABLE-trend state
    # estimate) never produces a voting `EvidenceItem`, but it is real, positive evidence
    # of normalcy — conflating "nothing was checked" with "everything checked out fine"
    # was a real bug caught live (a healthy flagship machine with genuinely no active
    # findings, no persisted ML results, and two STABLE state estimates was misreported as
    # INSUFFICIENT_EVIDENCE, when two real evidence sources had, in fact, been checked and
    # found nothing abnormal).
    sources_checked = bool(
        evidence.rule_finding_ids or evidence.ml_result_ids or evidence.state_estimate_ids
    )
    if not non_normal_types:
        if not sources_checked and not normal_votes:
            return ConditionAssessmentResult(
                condition_type="INSUFFICIENT_EVIDENCE",
                severity=policy.default_severity["INSUFFICIENT_EVIDENCE"],
                confidence="LOW",
                what_is_happening="Not enough evidence has been gathered to assess this machine.",
                why=("No rule findings, ML results, or state estimates were available.",),
                supporting_evidence=(),
                contradicting_evidence=(),
                data_trustworthiness=_trust_label(evidence),
                unknowns=tuple(unknowns) or ("No evidence sources produced output.",),
                recommended_next_evidence=(
                    "Confirm telemetry is flowing and instrumentation is registered."
                ),
            )
        confidence = "HIGH" if normal_votes else "MODERATE"
        why = tuple(_describe(evidence, s) for s in ("RULE_FINDING", "ML_RESULT", "STATE_ESTIMATE"))
        return ConditionAssessmentResult(
            condition_type="NORMAL_OPERATION",
            severity=policy.default_severity["NORMAL_OPERATION"],
            confidence=confidence,
            what_is_happening="All monitored evidence is consistent with normal operation.",
            why=why,
            supporting_evidence=tuple(
                item.description
                for item in evidence.items
                if item.condition_hint == "NORMAL_OPERATION"
            ),
            contradicting_evidence=(),
            data_trustworthiness=_trust_label(evidence),
            unknowns=tuple(unknowns),
            recommended_next_evidence=None,
        )

    # --- Step 4: exactly one non-normal hypothesis, no contradicting NORMAL vote -----
    if len(non_normal_types) == 1 and not normal_votes:
        condition_type = non_normal_types[0]
        return _single_hypothesis_result(evidence, policy, condition_type, votes[condition_type])

    # --- Step 4b: delivery + bearing coexistence is not automatically ambiguous ------
    # (Phase 13 brief §13.10: independent bearing evidence is expected to coexist with
    # lubrication-delivery evidence without one implicating the other.)
    bearing_only = {"BEARING_CONDITION_DEGRADATION", "INDEPENDENT_BEARING_CONDITION"}
    if len(non_normal_types) == 2 and not normal_votes:
        bearing_types = [t for t in non_normal_types if t in bearing_only]
        delivery_types = [t for t in non_normal_types if t not in bearing_only]
        if len(bearing_types) == 1 and len(delivery_types) == 1:
            primary = delivery_types[0]
            result = _single_hypothesis_result(evidence, policy, primary, votes[primary])
            bearing_label = bearing_types[0].replace("_", " ").title()
            bearing_note = (
                f"Independent bearing evidence also present ({bearing_label}) — recorded "
                "separately from this delivery-focused assessment, since one does not "
                "necessarily explain the other."
            )
            return ConditionAssessmentResult(
                condition_type=result.condition_type,
                severity=result.severity,
                confidence=result.confidence,
                what_is_happening=result.what_is_happening,
                why=(*result.why, bearing_note),
                supporting_evidence=result.supporting_evidence,
                contradicting_evidence=result.contradicting_evidence,
                data_trustworthiness=result.data_trustworthiness,
                unknowns=result.unknowns,
                recommended_next_evidence=result.recommended_next_evidence,
            )

    # --- Step 5: genuine conflict -> AMBIGUOUS_CONDITION (Phase 13 brief §13.8) ------
    all_matching_hints: set[str] = set(non_normal_types)
    for condition_type in non_normal_types:
        all_matching_hints |= _matching_hints(condition_type)
    supporting = [
        item.description
        for item in evidence.items
        if item.condition_hint in all_matching_hints and item.strength in _TALLIED_STRENGTHS
    ]
    contradicting = [
        item.description
        for item in evidence.items
        if item.condition_hint == "NORMAL_OPERATION" and item.strength in _TALLIED_STRENGTHS
    ]
    return ConditionAssessmentResult(
        condition_type="AMBIGUOUS_CONDITION",
        severity=policy.default_severity["AMBIGUOUS_CONDITION"],
        confidence="MODERATE" if (supporting and not contradicting) else "LOW",
        what_is_happening=(
            "Evidence disagrees on what is happening: "
            + ", ".join(t.replace("_", " ").title() for t in non_normal_types)
            + (" vs. normal-operation evidence" if normal_votes else "")
            + "."
        ),
        why=(
            "Multiple evidence sources point to different, non-overlapping explanations; "
            "this assessment reports the disagreement rather than picking one arbitrarily.",
        ),
        supporting_evidence=tuple(supporting),
        contradicting_evidence=tuple(contradicting),
        data_trustworthiness=_trust_label(evidence),
        unknowns=(*unknowns, "Root cause is not resolved by current evidence."),
        recommended_next_evidence=(
            "Additional corroborating evidence or manual inspection is needed to resolve "
            "the disagreement."
        ),
    )


def _single_hypothesis_result(
    evidence: ConditionEvidence,
    policy: ConditionIntelligencePolicy,
    condition_type: str,
    source_types: list[str],
) -> ConditionAssessmentResult:
    hints = _matching_hints(condition_type)
    strong_items = [
        item
        for item in evidence.items
        if item.condition_hint in hints and item.strength == "STRONG"
    ]
    supporting_items = [
        item
        for item in evidence.items
        if item.condition_hint in hints and item.strength == "SUPPORTING"
    ]
    distinct_sources = set(source_types)

    if strong_items and len(distinct_sources) >= 2:
        confidence = "HIGH"
    elif (
        strong_items
        or len(supporting_items) >= policy.confidence.moderate_min_supporting_sources
        and len(distinct_sources) >= 2
    ):
        confidence = "MODERATE"
    else:
        confidence = "LOW"

    severity = _severity_for(evidence, condition_type, policy)
    all_items = strong_items + supporting_items
    return ConditionAssessmentResult(
        condition_type=condition_type,
        severity=severity,
        confidence=confidence,
        what_is_happening=all_items[0].description if all_items else condition_type,
        why=tuple(item.description for item in all_items),
        supporting_evidence=tuple(item.description for item in all_items),
        contradicting_evidence=(),
        data_trustworthiness=_trust_label(evidence),
        unknowns=tuple(evidence.limitations),
        recommended_next_evidence=None
        if confidence == "HIGH"
        else "Additional corroborating evidence would increase confidence in this assessment.",
    )


def _severity_for(
    evidence: ConditionEvidence, condition_type: str, policy: ConditionIntelligencePolicy
) -> str:
    """Borrows the highest `RuleFindingSeverity` among the contributing rule findings when
    one exists; otherwise falls back to the condition type's configured default. Never
    invents a severity a rule finding did not itself already compute."""
    hints = _matching_hints(condition_type)
    finding_severities = [
        item.severity
        for item in evidence.items
        if item.source_type == "RULE_FINDING"
        and item.condition_hint in hints
        and item.severity is not None
    ]
    ranked = [s for s in finding_severities if s in policy.severity_rank]
    if ranked:
        return max(ranked, key=policy.rank)
    return policy.default_severity[condition_type]


def _quality_gate_verdict(
    evidence: ConditionEvidence, policy: ConditionIntelligencePolicy
) -> ConditionAssessmentResult | None:
    raw_total = evidence.instrumentation_coverage.get("registered_sensor_count", 0)
    raw_unusable = evidence.instrumentation_coverage.get("unusable_sensor_count", 0)
    total = raw_total if isinstance(raw_total, int) else 0
    unusable = raw_unusable if isinstance(raw_unusable, int) else 0
    if total == 0:
        return ConditionAssessmentResult(
            condition_type="INSUFFICIENT_EVIDENCE",
            severity=policy.default_severity["INSUFFICIENT_EVIDENCE"],
            confidence="LOW",
            what_is_happening="No sensors are registered for this machine.",
            why=("Instrumentation coverage is zero.",),
            supporting_evidence=(),
            contradicting_evidence=(),
            data_trustworthiness="NO_TRUSTED_DATA",
            unknowns=("No physical evidence is available for any signal.",),
            recommended_next_evidence="Register and commission sensors for this machine.",
        )
    if total > 0 and (unusable / total) >= policy.quality_gate.unusable_fraction_threshold:
        return ConditionAssessmentResult(
            condition_type="SENSOR_OR_DATA_QUALITY_LIMITATION",
            severity=policy.default_severity["SENSOR_OR_DATA_QUALITY_LIMITATION"],
            confidence="MODERATE",
            what_is_happening=(
                f"{unusable} of {total} registered sensors are in an unusable quality "
                "state; evidence for a physical-condition assessment is not currently "
                "trustworthy."
            ),
            why=("Data-quality state, not machine condition, is limiting this assessment.",),
            supporting_evidence=(),
            contradicting_evidence=(),
            data_trustworthiness="UNTRUSTED",
            unknowns=(
                "Underlying machine condition cannot be assessed until data quality recovers.",
            ),
            recommended_next_evidence="Verify affected sensors and confirm data-quality recovery.",
        )
    return None


def _trust_label(evidence: ConditionEvidence) -> str:
    state = str(evidence.quality_context.get("state", "UNKNOWN"))
    return state


def _describe(evidence: ConditionEvidence, source_type: str) -> str:
    matches = [item.description for item in evidence.items if item.source_type == source_type]
    return "; ".join(matches) if matches else f"No {source_type.lower()} evidence available."
