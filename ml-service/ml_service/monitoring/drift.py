"""Feature-distribution drift, missingness, and coverage checks (Phase 32 brief §32.8).

Population Stability Index (PSI) is the one standard, well-understood statistic used here
— computed directly from real feature values in two `DatasetSample` batches (e.g. a
reference/TRAIN batch vs. a more recent/TEST batch, or two dataset builds taken months
apart), never simulated. Common interpretation thresholds (not invented here): PSI < 0.1
no meaningful shift, 0.1-0.25 moderate shift worth a look, > 0.25 substantial shift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ml_service.domain.dataset import DatasetSample


def _numeric_values(samples: list[DatasetSample], feature: str) -> list[float]:
    values: list[float] = []
    for sample in samples:
        raw = sample.feature_values.get(feature)
        if isinstance(raw, int | float) and not isinstance(raw, bool):
            values.append(float(raw))
    return values


def population_stability_index(
    reference: list[float], current: list[float], buckets: int = 10
) -> float | None:
    """Standard PSI over equal-frequency buckets drawn from `reference`. Returns `None`
    when there isn't enough data in either batch to bucket meaningfully (small demo
    datasets routinely hit this — reported honestly as "insufficient data", not as a
    fabricated zero)."""
    if len(reference) < buckets * 2 or len(current) < buckets:
        return None

    sorted_ref = sorted(reference)
    edges = sorted(
        {sorted_ref[min(int(q * (len(sorted_ref) - 1)), len(sorted_ref) - 1)] for q in
         [i / buckets for i in range(1, buckets)]}
    )
    if not edges:
        return None

    def _bucket_fractions(values: list[float]) -> list[float]:
        counts = [0] * (len(edges) + 1)
        for v in values:
            idx = 0
            while idx < len(edges) and v > edges[idx]:
                idx += 1
            counts[idx] += 1
        total = len(values)
        # Laplace-style floor so no bucket is exactly zero (PSI is undefined at 0).
        return [max(c, 1e-6) / total for c in counts]

    ref_fracs = _bucket_fractions(reference)
    cur_fracs = _bucket_fractions(current)
    return sum(
        (c - r) * math.log(c / r) for r, c in zip(ref_fracs, cur_fracs, strict=True)
    )


def psi_severity(psi: float) -> str:
    if psi < 0.1:
        return "NO_MEANINGFUL_SHIFT"
    if psi < 0.25:
        return "MODERATE_SHIFT"
    return "SUBSTANTIAL_SHIFT"


@dataclass(frozen=True, slots=True)
class FeatureDriftResult:
    feature: str
    reference_count: int
    current_count: int
    psi: float | None
    severity: str | None
    reference_missing_rate: float
    current_missing_rate: float
    missing_rate_delta: float


@dataclass(frozen=True, slots=True)
class DriftReport:
    features: tuple[FeatureDriftResult, ...] = field(default_factory=tuple)
    reference_sample_count: int = 0
    current_sample_count: int = 0
    reference_coverage: float = 0.0
    current_coverage: float = 0.0

    @property
    def substantial_shift_features(self) -> tuple[str, ...]:
        return tuple(
            f.feature for f in self.features if f.severity == "SUBSTANTIAL_SHIFT"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_sample_count": self.reference_sample_count,
            "current_sample_count": self.current_sample_count,
            "reference_coverage": self.reference_coverage,
            "current_coverage": self.current_coverage,
            "substantial_shift_features": list(self.substantial_shift_features),
            "features": [
                {
                    "feature": f.feature,
                    "reference_count": f.reference_count,
                    "current_count": f.current_count,
                    "psi": f.psi,
                    "severity": f.severity,
                    "reference_missing_rate": f.reference_missing_rate,
                    "current_missing_rate": f.current_missing_rate,
                    "missing_rate_delta": f.missing_rate_delta,
                }
                for f in self.features
            ],
        }


def _missing_rate(samples: list[DatasetSample], feature: str) -> float:
    if not samples:
        return 1.0
    missing = sum(1 for s in samples if feature in s.missing_features)
    return missing / len(samples)


def _coverage(samples: list[DatasetSample], feature_names: list[str]) -> float:
    """Average fraction of `feature_names` actually present (non-missing) per sample —
    a coarse instrumentation-coverage signal, distinct from per-feature missingness."""
    if not samples or not feature_names:
        return 0.0
    total = 0.0
    for sample in samples:
        present = sum(1 for f in feature_names if f not in sample.missing_features)
        total += present / len(feature_names)
    return total / len(samples)


def compute_drift_report(
    reference_samples: list[DatasetSample],
    current_samples: list[DatasetSample],
    feature_names: list[str],
    psi_buckets: int = 10,
) -> DriftReport:
    results: list[FeatureDriftResult] = []
    for feature in feature_names:
        ref_values = _numeric_values(reference_samples, feature)
        cur_values = _numeric_values(current_samples, feature)
        psi = population_stability_index(ref_values, cur_values, buckets=psi_buckets)
        ref_missing = _missing_rate(reference_samples, feature)
        cur_missing = _missing_rate(current_samples, feature)
        results.append(
            FeatureDriftResult(
                feature=feature,
                reference_count=len(ref_values),
                current_count=len(cur_values),
                psi=psi,
                severity=psi_severity(psi) if psi is not None else None,
                reference_missing_rate=ref_missing,
                current_missing_rate=cur_missing,
                missing_rate_delta=cur_missing - ref_missing,
            )
        )
    return DriftReport(
        features=tuple(results),
        reference_sample_count=len(reference_samples),
        current_sample_count=len(current_samples),
        reference_coverage=_coverage(reference_samples, feature_names),
        current_coverage=_coverage(current_samples, feature_names),
    )
