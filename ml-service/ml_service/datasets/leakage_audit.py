"""Leakage and proxy-leakage audits (Phase 11 brief §48-§49).

Two independent checks:

1. `audit_feature_names` — a pure string scan over the feature list for scenario/ground-truth
   vocabulary. This should always pass by construction (`DatasetBuilder` never copies
   simulator fields into `feature_values`), but is run and recorded on every dataset build
   as a structural proof, not an assumption.
2. `audit_proxy_leakage` — a statistical purity check: does any single feature value (almost)
   uniquely determine the label with enough support to be a shortcut, rather than genuine
   physical evidence? Run-identity artifacts (e.g. a context field that happens to be
   constant per run) are the concrete risk this catches.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ml_service.domain.dataset import DatasetSample, LeakageAuditResult

_FORBIDDEN_TOKENS = (
    "scenario",
    "severity",
    "ground_truth",
    "fault_start",
    "run_id",
    "future_duration",
    "failure_phase",
    "true_value",
)


def audit_feature_names(feature_names: tuple[str, ...]) -> tuple[str, ...]:
    found = []
    for name in feature_names:
        lowered = name.lower()
        for token in _FORBIDDEN_TOKENS:
            if token in lowered:
                found.append(name)
                break
    return tuple(found)


def audit_proxy_leakage(
    samples: list[DatasetSample],
    feature_names: tuple[str, ...],
    *,
    purity_threshold: float = 0.98,
    min_support: int = 5,
) -> tuple[str, ...]:
    """Flags a feature as a proxy-leakage suspect if one of its observed values predicts a
    single label class at or above `purity_threshold`, with at least `min_support` samples
    carrying that value — e.g. a context field that happens to be constant within one
    simulator run and therefore perfectly encodes that run's scenario type by accident.
    Continuous FLOAT features are excluded (their raw values are exact evidence, not a
    small discrete vocabulary an attacker/shortcut could memorize) and are covered instead by
    `docs/ML_ARCHITECTURE.md`'s feature-importance review.
    """
    suspects: list[str] = []
    for name in feature_names:
        value_to_labels: dict[object, Counter[str]] = defaultdict(Counter)
        numeric_like = 0
        total = 0
        for sample in samples:
            value = sample.feature_values.get(name)
            if value is None:
                continue
            total += 1
            if isinstance(value, float):
                numeric_like += 1
                continue
            value_to_labels[value][sample.label.value] += 1
        if total == 0 or numeric_like / total > 0.5:
            continue
        for label_counts in value_to_labels.values():
            support = sum(label_counts.values())
            if support < min_support:
                continue
            purity = label_counts.most_common(1)[0][1] / support
            if purity >= purity_threshold and len(label_counts) < len(
                {s.label.value for s in samples}
            ):
                suspects.append(name)
                break
    return tuple(suspects)


def run_leakage_audit(
    samples: list[DatasetSample], feature_names: tuple[str, ...]
) -> LeakageAuditResult:
    forbidden = audit_feature_names(feature_names)
    proxies = audit_proxy_leakage(samples, feature_names)
    return LeakageAuditResult(
        forbidden_features_found=forbidden,
        proxy_suspects=proxies,
        passed=len(forbidden) == 0,
    )
