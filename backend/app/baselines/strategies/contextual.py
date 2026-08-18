"""CONTEXTUAL_ASSET_BASELINE (Phase 8 brief §3/§8/§9/§11) — conditions on operating state
and/or lubrication-cycle-phase (per `BaselinePolicy.context_dimensions_for`, sensor-type
aware — brief §7). Buckets samples into one `BaselineContext` each, then computes robust
statistics per bucket independently, so e.g. `RUNNING_HIGH_LOAD` bearing temperature never
gets averaged together with `RUNNING_LOW_LOAD` (brief §8's core example).
"""

from __future__ import annotations

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import BaselineContext, TelemetrySample
from app.baselines.domain.statistics import RobustStatistics, compute_robust_statistics


def _cycle_phase(sample: TelemetrySample, idle_threshold: float) -> str:
    if sample.value is None:
        return "IDLE"
    return "ACTIVE" if sample.value > idle_threshold else "IDLE"


def bucket_samples(
    samples: list[TelemetrySample],
    measurement_type: str,
    policy: BaselinePolicy,
    *,
    include_cycle_phase: bool = True,
) -> dict[BaselineContext, list[TelemetrySample]]:
    """Only buckets into `stable_operating_states` (brief §21 — "avoid generating profiles
    for impossible combinations"); samples taken during a transitional state
    (STARTING/SHUTTING_DOWN/MAINTENANCE) are dropped from contextual segmentation entirely
    (they still count toward the unsegmented `ROLLING_ASSET_BASELINE`).

    `include_cycle_phase=False` produces the coarser operating-state-only bucketing used
    as the middle rung of the fallback hierarchy (`app.baselines.services.fallback`) for
    measurement types that also use `cycle_phase` — see `compute_contextual_baselines`.
    """
    uses_state = policy.uses_operating_state(measurement_type)
    uses_phase = include_cycle_phase and policy.uses_cycle_phase(measurement_type)
    idle_threshold = policy.cycle_phase_idle_threshold_for(measurement_type)

    buckets: dict[BaselineContext, list[TelemetrySample]] = {}
    for sample in samples:
        if sample.value is None:
            continue
        operating_state: str | None = None
        if uses_state:
            if sample.operating_state not in policy.stable_operating_states:
                continue
            operating_state = sample.operating_state
        cycle_phase: str | None = None
        if uses_phase and idle_threshold is not None:
            cycle_phase = _cycle_phase(sample, idle_threshold)
        context = BaselineContext(operating_state=operating_state, cycle_phase=cycle_phase)
        buckets.setdefault(context, []).append(sample)
    return buckets


def _stats_per_bucket(
    buckets: dict[BaselineContext, list[TelemetrySample]],
) -> dict[BaselineContext, RobustStatistics]:
    result: dict[BaselineContext, RobustStatistics] = {}
    for context, bucket_samples_list in buckets.items():
        stats = compute_robust_statistics(
            [s.value for s in bucket_samples_list if s.value is not None],
            [s.caution for s in bucket_samples_list],
        )
        if stats is not None:
            result[context] = stats
    return result


def compute_contextual_baselines(
    samples: list[TelemetrySample], measurement_type: str, policy: BaselinePolicy
) -> dict[BaselineContext, RobustStatistics]:
    """Every measurement type that uses `cycle_phase` also gets a coarser
    operating-state-only profile alongside the full (operating_state, cycle_phase) one —
    a real, separately-stored middle rung between an exact-context match and the
    unsegmented `ROLLING_ASSET_BASELINE` (brief §22's fallback hierarchy), not merely a
    conceptual one."""
    result = _stats_per_bucket(bucket_samples(samples, measurement_type, policy))
    if policy.uses_cycle_phase(measurement_type):
        coarse = _stats_per_bucket(
            bucket_samples(samples, measurement_type, policy, include_cycle_phase=False)
        )
        for context, stats in coarse.items():
            result.setdefault(context, stats)
    return result
