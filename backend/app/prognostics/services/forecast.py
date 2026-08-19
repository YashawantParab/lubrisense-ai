"""Pure forecast logic (Phase 15 brief §15.3) — no I/O, no database. Extrapolates directly
from Phase 12's own posterior `[level, rate]`, deliberately NOT re-fitting a separate trend
model over raw history: the Kalman filter already IS a smoothed, uncertainty-aware trend
estimate, so re-deriving one here would duplicate Phase 12's own job with a second,
inconsistent set of assumptions (see docs/PROGNOSTICS.md "Forecast method" / the
corresponding ADR). This keeps Phase 15 genuinely CPU-light and explainable: one
multiplication and a bounds clip.
"""

from __future__ import annotations

from app.prognostics.config.policy import PrognosticsPolicy
from app.prognostics.domain.models import ForecastResult, StateEstimateSnapshot


def data_sufficiency_check(
    current: StateEstimateSnapshot,
    history: list[StateEstimateSnapshot],  # most-recent-first, current excluded
    policy: PrognosticsPolicy,
) -> tuple[bool, list[str]]:
    """Phase 15 brief §15.7: uncertainty must increase (forecast degrade to
    NO_RELIABLE_FORECAST) when state-estimation uncertainty is high, observations are
    missing, trend history is short, or the trend is unstable."""
    reasons: list[str] = []

    if current.prediction_only:
        reasons.append("Current state estimate has no recent observations (prediction-only).")
    if current.uncertainty == "HIGH":
        reasons.append("Current state-estimation uncertainty is HIGH.")

    usable_history = [current, *history]
    if len(usable_history) < policy.data_sufficiency.minimum_history_count:
        reasons.append(
            f"Only {len(usable_history)} state estimate(s) available; "
            f"{policy.data_sufficiency.minimum_history_count} required for a reliable trend."
        )

    if policy.data_sufficiency.rate_sign_flip_makes_unstable and len(usable_history) >= 2:
        signs = {_sign(row.rate) for row in usable_history if row.rate != 0.0}
        if len(signs) > 1:
            reasons.append("Recent state-estimate rate has flipped sign — trend is unstable.")

    return (not reasons, reasons)


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def forecast_one(
    current: StateEstimateSnapshot,
    history: list[StateEstimateSnapshot],
    horizon_seconds: float,
    policy: PrognosticsPolicy,
) -> ForecastResult:
    sufficient, reasons = data_sufficiency_check(current, history, policy)
    if not sufficient:
        return ForecastResult(
            status="NO_RELIABLE_FORECAST",
            predicted_state_at_horizon=None,
            threshold_crossing_seconds=None,
            uncertainty="HIGH",
            data_sufficient=False,
            limitations=tuple(reasons),
        )

    low, high = policy.level_bounds
    predicted = min(max(current.level + current.rate * horizon_seconds, low), high)

    threshold_crossing: float | None = None
    if current.rate > 0.0 and current.level < policy.degradation_threshold:
        seconds_to_cross = (policy.degradation_threshold - current.level) / current.rate
        if 0.0 < seconds_to_cross <= policy.max_crossing_horizon_seconds:
            threshold_crossing = seconds_to_cross

    return ForecastResult(
        status="OK",
        predicted_state_at_horizon=predicted,
        threshold_crossing_seconds=threshold_crossing,
        uncertainty=current.uncertainty,
        data_sufficient=True,
        limitations=(),
    )
