"""STATIC_ENGINEERING_REFERENCE (Phase 8 brief §3/§4) — uses only synthetic demo config,
never learned telemetry. Always available (no minimum-sample wait, never `BUILDING`/
`INSUFFICIENT_DATA`), and is the last rung of the fallback hierarchy
(`app.baselines.services.fallback`) precisely because it never reflects this specific
asset's actual behavior — it is a physically-possible range, not a learned normal.

Deliberately coarse: `mean` is the range midpoint and `stddev`/`mad` are a fixed fraction of
the range span, not derived from any real distribution — this is intentionally NOT presented
as "this asset's normal", only as "physically plausible" (brief §4's explicit separation of
engineering limits from learned baselines).
"""

from __future__ import annotations

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.statistics import RobustStatistics

# The range midpoint +/- this fraction of the span approximates a p05/p95 band for a
# uniform-ish "physically plausible" distribution — deliberately wide, since this is a
# fallback of last resort, not a claim about the asset's actual behavior.
_RANGE_FRACTION_P05_P95 = 0.45
_RANGE_FRACTION_P25_P75 = 0.20
_RANGE_FRACTION_MAD = 0.15


def build_engineering_reference(
    measurement_type: str, policy: BaselinePolicy
) -> RobustStatistics | None:
    value_range = policy.value_range_for(measurement_type)
    if value_range is None:
        return None
    low, high = value_range
    span = high - low
    mid = (low + high) / 2
    return RobustStatistics(
        count=0,
        caution_count=0,
        mean=mid,
        stddev=span * _RANGE_FRACTION_P05_P95 / 2,
        median=mid,
        mad=span * _RANGE_FRACTION_MAD,
        p05=mid - span * _RANGE_FRACTION_P05_P95,
        p25=mid - span * _RANGE_FRACTION_P25_P75,
        p75=mid + span * _RANGE_FRACTION_P25_P75,
        p95=mid + span * _RANGE_FRACTION_P05_P95,
        min=low,
        max=high,
    )
