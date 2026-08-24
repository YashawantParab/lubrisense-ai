"""Pure window-selection and comparability logic — no I/O, no database, mirroring
`app.baselines.domain.deviation`/`app.energy.domain.attribution`'s own "pure logic
separate from orchestration" split (Lubrication Efficiency Intelligence, Pass 3 —
docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §9, ADR-176).

Judges only factors genuinely observable in this architecture: sample count, observed
duration, `operating_state` consistency (the same field `app.baselines.domain.context
.BaselineContext` already uses as the sole operating-context key everywhere else in this
platform — RPM/load are not independently re-checked here, since `operating_state` is
this platform's one existing operating-context signal, not a new one invented for this
pass), per-sensor data-quality trust, and whether the same contextual baseline reference
resolved for both windows. Nothing here invents a process variable this platform does not
already track.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import (
    BaselineSourceKind,
    ComparabilityStatus,
    ComparisonConfidence,
    QualityState,
)

#: Window-selection policy (Pass 3) — deterministic, documented, generic across assets.
#: Not tuned per-machine; the same values apply whichever machine is being verified.
POLICY_VERSION = "1"

#: Buffer excluded on each side of `intervention_timestamp` — a simple, generic proxy for
#: excluding startup/shutdown/downtime transients immediately around the intervention.
#: This reference implementation has no separate downtime-interval record to exclude
#: against instead; a settle-gap buffer is the defensible minimum, documented as a known
#: simplification (see docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §9).
SETTLE_GAP_MINUTES = 2.0

#: How far back before the settled pre-window boundary to look for pre-intervention
#: samples — deliberately bounded (not "since baseline was built") so the pre-window
#: reflects the state *immediately preceding* the intervention, not diluted by an earlier
#: healthy period the same machine may also have telemetry for.
PRE_LOOKBACK_MINUTES = 45.0

#: Maximum forward search horizon for post-intervention samples.
POST_LOOKAHEAD_MINUTES = 180.0

MIN_SAMPLES = 5
MIN_DURATION_MINUTES = 5.0
#: Sample count at/above which a fully-comparable window may earn HIGH confidence rather
#: than MODERATE.
HIGH_CONFIDENCE_SAMPLES = 10

#: Fraction of a window's samples that must share the single most common `operating_state`
#: for that window to be considered internally coherent at all.
MIN_OPERATING_STATE_PURITY = 0.5
#: Fraction at/above which a window's operating-state purity no longer degrades
#: confidence — i.e. is treated as "clean".
HIGH_OPERATING_STATE_PURITY = 0.9


@dataclass(frozen=True)
class WindowBounds:
    start: datetime
    end: datetime


def compute_window_bounds(intervention_timestamp: datetime) -> tuple[WindowBounds, WindowBounds]:
    """Deterministic pre/post window bounds around one intervention timestamp — the same
    policy for every machine, never hand-tuned per asset."""
    from datetime import timedelta

    settle = timedelta(minutes=SETTLE_GAP_MINUTES)
    pre = WindowBounds(
        start=intervention_timestamp - timedelta(minutes=PRE_LOOKBACK_MINUTES) - settle,
        end=intervention_timestamp - settle,
    )
    post = WindowBounds(
        start=intervention_timestamp + settle,
        end=intervention_timestamp + timedelta(minutes=POST_LOOKAHEAD_MINUTES),
    )
    return pre, post


@dataclass(frozen=True)
class WindowSample:
    timestamp: datetime
    value: float
    operating_state: str | None


@dataclass(frozen=True)
class WindowSummary:
    sample_count: int
    duration_minutes: float
    mean_value: float
    values: tuple[float, ...]
    timestamps: tuple[datetime, ...]
    dominant_operating_state: str | None
    operating_state_purity: float
    first_timestamp: datetime
    last_timestamp: datetime


def summarize_window(samples: list[WindowSample]) -> WindowSummary | None:
    """`None` when there are no samples at all — callers must treat that as "no data",
    never as a zero-filled summary (mirrors `compute_robust_statistics`'s own
    convention)."""
    if not samples:
        return None
    ordered = sorted(samples, key=lambda s: s.timestamp)
    values = tuple(s.value for s in ordered)
    timestamps = tuple(s.timestamp for s in ordered)
    duration_minutes = (timestamps[-1] - timestamps[0]).total_seconds() / 60.0

    state_counts = Counter(s.operating_state for s in ordered if s.operating_state is not None)
    if state_counts:
        dominant_state, dominant_count = state_counts.most_common(1)[0]
        purity = dominant_count / len(ordered)
    else:
        dominant_state, purity = None, 0.0

    return WindowSummary(
        sample_count=len(ordered),
        duration_minutes=duration_minutes,
        mean_value=sum(values) / len(values),
        values=values,
        timestamps=timestamps,
        dominant_operating_state=dominant_state,
        operating_state_purity=purity,
        first_timestamp=timestamps[0],
        last_timestamp=timestamps[-1],
    )


@dataclass(frozen=True)
class ComparabilityInput:
    pre_summary: WindowSummary | None
    post_summary: WindowSummary | None
    pre_quality_state: QualityState
    post_quality_state: QualityState
    pre_baseline_source: BaselineSourceKind | None
    pre_baseline_profile_id: str | None
    post_baseline_source: BaselineSourceKind | None
    post_baseline_profile_id: str | None


@dataclass(frozen=True)
class ComparabilityResult:
    status: ComparabilityStatus
    confidence: ComparisonConfidence
    limiting_factors: tuple[str, ...]


def assess_comparability(inp: ComparabilityInput) -> ComparabilityResult:
    """Deterministic, generic across assets — the worst-of-all-checks status wins; no
    single passing check can outweigh a genuine limitation elsewhere."""
    reasons: list[str] = []

    if inp.pre_summary is None or inp.pre_summary.sample_count < MIN_SAMPLES:
        reasons.append(
            f"Fewer than {MIN_SAMPLES} qualifying power samples in the pre-intervention " "window."
        )
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )
    if inp.post_summary is None or inp.post_summary.sample_count < MIN_SAMPLES:
        reasons.append(
            f"Fewer than {MIN_SAMPLES} qualifying power samples in the post-intervention " "window."
        )
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )
    if inp.pre_summary.duration_minutes < MIN_DURATION_MINUTES:
        reasons.append(
            f"Pre-intervention window spans under {MIN_DURATION_MINUTES:.0f} minutes of "
            "observed operation."
        )
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )
    if inp.post_summary.duration_minutes < MIN_DURATION_MINUTES:
        reasons.append(
            f"Post-intervention window spans under {MIN_DURATION_MINUTES:.0f} minutes of "
            "observed operation."
        )
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )
    if inp.pre_quality_state == QualityState.UNUSABLE:
        reasons.append("Pre-intervention power readings are not currently trusted (data quality).")
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )
    if inp.post_quality_state == QualityState.UNUSABLE:
        reasons.append("Post-intervention power readings are not currently trusted (data quality).")
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )
    if inp.pre_baseline_source is None or inp.pre_baseline_source == BaselineSourceKind.NONE:
        reasons.append("No contextual baseline could be resolved for the pre-intervention window.")
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )
    if inp.post_baseline_source is None or inp.post_baseline_source == BaselineSourceKind.NONE:
        reasons.append("No contextual baseline could be resolved for the post-intervention window.")
        return ComparabilityResult(
            ComparabilityStatus.INSUFFICIENT_DATA, ComparisonConfidence.LOW, tuple(reasons)
        )

    # Below this point, both windows have enough trusted samples and a resolvable
    # baseline — degrade status/confidence for softer limitations, never block entirely.
    status = ComparabilityStatus.COMPARABLE
    confidence = ComparisonConfidence.HIGH

    if inp.pre_summary.operating_state_purity < MIN_OPERATING_STATE_PURITY:
        reasons.append("Pre-intervention window mixes multiple operating states.")
        status = ComparabilityStatus.NOT_COMPARABLE
    if inp.post_summary.operating_state_purity < MIN_OPERATING_STATE_PURITY:
        reasons.append("Post-intervention window mixes multiple operating states.")
        status = ComparabilityStatus.NOT_COMPARABLE

    if status != ComparabilityStatus.NOT_COMPARABLE and (
        inp.pre_summary.dominant_operating_state != inp.post_summary.dominant_operating_state
    ):
        reasons.append(
            "Pre- and post-intervention windows have different dominant operating states "
            f"({inp.pre_summary.dominant_operating_state!r} vs. "
            f"{inp.post_summary.dominant_operating_state!r})."
        )
        status = ComparabilityStatus.PARTIALLY_COMPARABLE

    if (
        status != ComparabilityStatus.NOT_COMPARABLE
        and inp.pre_baseline_profile_id is not None
        and inp.post_baseline_profile_id is not None
        and inp.pre_baseline_profile_id != inp.post_baseline_profile_id
    ):
        reasons.append(
            "The contextual baseline reference resolved differently for the pre- and "
            "post-intervention windows."
        )
        if status == ComparabilityStatus.COMPARABLE:
            status = ComparabilityStatus.PARTIALLY_COMPARABLE

    if inp.pre_quality_state == QualityState.USABLE_WITH_CAUTION:
        reasons.append("Pre-intervention power readings are trusted only with caution.")
        if status == ComparabilityStatus.COMPARABLE:
            status = ComparabilityStatus.PARTIALLY_COMPARABLE
    if inp.post_quality_state == QualityState.USABLE_WITH_CAUTION:
        reasons.append("Post-intervention power readings are trusted only with caution.")
        if status == ComparabilityStatus.COMPARABLE:
            status = ComparabilityStatus.PARTIALLY_COMPARABLE

    if (
        inp.pre_baseline_source != BaselineSourceKind.EXACT_CONTEXT
        or inp.post_baseline_source != BaselineSourceKind.EXACT_CONTEXT
    ):
        reasons.append("At least one window's expected power used a fallback baseline tier.")

    if status == ComparabilityStatus.NOT_COMPARABLE:
        confidence = ComparisonConfidence.LOW
    elif status == ComparabilityStatus.PARTIALLY_COMPARABLE:
        confidence = ComparisonConfidence.LOW if reasons else ComparisonConfidence.MODERATE
    else:
        low_purity = (
            inp.pre_summary.operating_state_purity < HIGH_OPERATING_STATE_PURITY
            or inp.post_summary.operating_state_purity < HIGH_OPERATING_STATE_PURITY
        )
        low_samples = (
            inp.pre_summary.sample_count < HIGH_CONFIDENCE_SAMPLES
            or inp.post_summary.sample_count < HIGH_CONFIDENCE_SAMPLES
        )
        if reasons or low_purity or low_samples:
            confidence = ComparisonConfidence.MODERATE

    return ComparabilityResult(status, confidence, tuple(reasons))
