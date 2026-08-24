"""Pure tests for `app.energy.domain.comparability` — window selection and comparability
classification (Lubrication Efficiency Intelligence, Pass 3, ADR-176). No database, no
fixtures beyond plain dataclasses — mirrors `test_attribution_policy.py`'s own convention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.enums import (
    BaselineSourceKind,
    ComparabilityStatus,
    ComparisonConfidence,
    QualityState,
)
from app.energy.domain.comparability import (
    MIN_DURATION_MINUTES,
    MIN_SAMPLES,
    POST_LOOKAHEAD_MINUTES,
    PRE_LOOKBACK_MINUTES,
    SETTLE_GAP_MINUTES,
    ComparabilityInput,
    WindowSample,
    assess_comparability,
    compute_window_bounds,
    summarize_window,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _samples(
    count: int,
    *,
    start: datetime,
    step_minutes: float = 1.0,
    value: float = 30.0,
    state: str = "RUNNING_NORMAL_LOAD",
) -> list[WindowSample]:
    return [
        WindowSample(
            timestamp=start + timedelta(minutes=step_minutes * i),
            value=value,
            operating_state=state,
        )
        for i in range(count)
    ]


def _full_input(**overrides: object) -> ComparabilityInput:
    pre = summarize_window(_samples(10, start=_T0))
    post = summarize_window(_samples(10, start=_T0 + timedelta(hours=1)))
    base: dict[str, object] = {
        "pre_summary": pre,
        "post_summary": post,
        "pre_quality_state": QualityState.TRUSTED,
        "post_quality_state": QualityState.TRUSTED,
        "pre_baseline_source": BaselineSourceKind.EXACT_CONTEXT,
        "pre_baseline_profile_id": "profile-a",
        "post_baseline_source": BaselineSourceKind.EXACT_CONTEXT,
        "post_baseline_profile_id": "profile-a",
    }
    base.update(overrides)
    return ComparabilityInput(**base)  # type: ignore[arg-type]


class TestWindowBounds:
    def test_settle_gap_excludes_transient_buffer_around_intervention(self) -> None:
        intervention = _T0
        pre, post = compute_window_bounds(intervention)
        assert pre.end == intervention - timedelta(minutes=SETTLE_GAP_MINUTES)
        assert post.start == intervention + timedelta(minutes=SETTLE_GAP_MINUTES)

    def test_pre_window_bounded_lookback_not_since_baseline(self) -> None:
        intervention = _T0
        pre, _post = compute_window_bounds(intervention)
        expected_start = (
            intervention
            - timedelta(minutes=PRE_LOOKBACK_MINUTES)
            - timedelta(minutes=SETTLE_GAP_MINUTES)
        )
        assert pre.start == expected_start

    def test_post_window_bounded_by_max_search_horizon(self) -> None:
        intervention = _T0
        _pre, post = compute_window_bounds(intervention)
        assert post.end == intervention + timedelta(minutes=POST_LOOKAHEAD_MINUTES)


class TestSummarizeWindow:
    def test_empty_samples_returns_none(self) -> None:
        assert summarize_window([]) is None

    def test_dominant_operating_state_and_purity(self) -> None:
        samples = _samples(8, start=_T0, state="RUNNING_NORMAL_LOAD") + _samples(
            2, start=_T0 + timedelta(minutes=100), state="RUNNING_HIGH_LOAD"
        )
        summary = summarize_window(samples)
        assert summary is not None
        assert summary.dominant_operating_state == "RUNNING_NORMAL_LOAD"
        assert summary.operating_state_purity == 0.8

    def test_mean_value_is_plain_arithmetic_mean(self) -> None:
        samples = [
            WindowSample(timestamp=_T0, value=10.0, operating_state="RUNNING_NORMAL_LOAD"),
            WindowSample(
                timestamp=_T0 + timedelta(minutes=1),
                value=20.0,
                operating_state="RUNNING_NORMAL_LOAD",
            ),
        ]
        summary = summarize_window(samples)
        assert summary is not None
        assert summary.mean_value == 15.0


class TestComparability:
    def test_fully_clean_windows_are_comparable_high_confidence(self) -> None:
        result = assess_comparability(_full_input())
        assert result.status == ComparabilityStatus.COMPARABLE
        assert result.confidence == ComparisonConfidence.HIGH
        assert result.limiting_factors == ()

    def test_insufficient_pre_samples_is_insufficient_data(self) -> None:
        pre = summarize_window(_samples(MIN_SAMPLES - 1, start=_T0))
        result = assess_comparability(_full_input(pre_summary=pre))
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA
        assert result.confidence == ComparisonConfidence.LOW

    def test_insufficient_post_samples_is_insufficient_data(self) -> None:
        post = summarize_window(_samples(MIN_SAMPLES - 1, start=_T0))
        result = assess_comparability(_full_input(post_summary=post))
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA

    def test_no_samples_at_all_is_insufficient_data(self) -> None:
        result = assess_comparability(_full_input(pre_summary=None))
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA

    def test_short_duration_window_is_insufficient_data(self) -> None:
        # MIN_SAMPLES samples but spanning under MIN_DURATION_MINUTES.
        short_step = (MIN_DURATION_MINUTES / MIN_SAMPLES) / 10
        pre = summarize_window(_samples(MIN_SAMPLES, start=_T0, step_minutes=short_step))
        result = assess_comparability(_full_input(pre_summary=pre))
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA

    def test_unusable_pre_quality_is_insufficient_data(self) -> None:
        result = assess_comparability(_full_input(pre_quality_state=QualityState.UNUSABLE))
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA

    def test_unusable_post_quality_is_insufficient_data(self) -> None:
        result = assess_comparability(_full_input(post_quality_state=QualityState.UNUSABLE))
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA

    def test_no_baseline_resolved_pre_is_insufficient_data(self) -> None:
        result = assess_comparability(
            _full_input(pre_baseline_source=None, pre_baseline_profile_id=None)
        )
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA

    def test_no_baseline_resolved_post_is_insufficient_data(self) -> None:
        result = assess_comparability(
            _full_input(post_baseline_source=BaselineSourceKind.NONE, post_baseline_profile_id=None)
        )
        assert result.status == ComparabilityStatus.INSUFFICIENT_DATA

    def test_mixed_operating_state_within_window_is_not_comparable(self) -> None:
        # No single state reaches the 0.5 purity bar: 4/10, 3/10, 3/10.
        mixed = summarize_window(
            _samples(4, start=_T0, state="RUNNING_NORMAL_LOAD")
            + _samples(3, start=_T0 + timedelta(minutes=20), state="RUNNING_HIGH_LOAD")
            + _samples(3, start=_T0 + timedelta(minutes=40), state="STARTUP")
        )
        result = assess_comparability(_full_input(pre_summary=mixed))
        assert result.status == ComparabilityStatus.NOT_COMPARABLE

    def test_different_dominant_operating_state_is_partially_comparable(self) -> None:
        post = summarize_window(
            _samples(10, start=_T0 + timedelta(hours=1), state="RUNNING_HIGH_LOAD")
        )
        result = assess_comparability(_full_input(post_summary=post))
        assert result.status == ComparabilityStatus.PARTIALLY_COMPARABLE
        assert result.limiting_factors

    def test_differing_baseline_profile_caps_partially_comparable(self) -> None:
        result = assess_comparability(_full_input(post_baseline_profile_id="profile-b"))
        assert result.status == ComparabilityStatus.PARTIALLY_COMPARABLE

    def test_caution_quality_degrades_to_partially_comparable(self) -> None:
        result = assess_comparability(
            _full_input(pre_quality_state=QualityState.USABLE_WITH_CAUTION)
        )
        assert result.status == ComparabilityStatus.PARTIALLY_COMPARABLE

    def test_fallback_baseline_tier_lowers_confidence_but_stays_comparable(self) -> None:
        result = assess_comparability(
            _full_input(
                pre_baseline_source=BaselineSourceKind.OPERATING_STATE,
                post_baseline_source=BaselineSourceKind.OPERATING_STATE,
            )
        )
        assert result.status == ComparabilityStatus.COMPARABLE
        assert result.confidence == ComparisonConfidence.MODERATE

    def test_low_sample_count_within_bar_lowers_confidence(self) -> None:
        # MIN_SAMPLES samples spanning well over MIN_DURATION_MINUTES, but under
        # HIGH_CONFIDENCE_SAMPLES — enough to be COMPARABLE, not enough for HIGH.
        pre = summarize_window(_samples(MIN_SAMPLES, start=_T0, step_minutes=2.0))
        post = summarize_window(
            _samples(MIN_SAMPLES, start=_T0 + timedelta(hours=1), step_minutes=2.0)
        )
        result = assess_comparability(_full_input(pre_summary=pre, post_summary=post))
        assert result.status == ComparabilityStatus.COMPARABLE
        assert result.confidence == ComparisonConfidence.MODERATE
