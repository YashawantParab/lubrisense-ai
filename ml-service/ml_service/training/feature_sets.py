"""Model-specific feature subsets (Phase 11 brief §18) — never blindly feed every Phase 10
feature into every model. Each subset is documented here, not inferred at training time.

Excluded from every model subset, with reasons:

- `context.machine_type`, `context.criticality` — with only a small demo fleet (one or two
  machines), these would trivially encode "which machine", making asset generalization
  (Phase 11 brief §31) untestable and inviting shortcut learning rather than genuine
  physical evidence.
- `context.firmware_version`, `context.controller_version` — fine-grained, high-cardinality
  identifiers with real risk of acting as a run/config proxy rather than physical evidence.
- `rules.*` (RULE_EVIDENCE group) — `rules.restriction_pattern_active`,
  `rules.leakage_pattern_active`, `rules.pump_degradation_pattern_active`, and
  `rules.bearing_condition_pattern_active` are named almost 1:1 with the supervised label
  schema (they are Phase 9's own deterministic detectors for the same failure modes). Using
  them as classifier input would make the model largely reproduce the rules engine's own
  output instead of learning independent evidence from raw signals — the opposite of
  CLAUDE.md's "Decision Intelligence combines rules AND ML as independent evidence sources."
  Excluded from training; documented in the leakage audit as a deliberate exclusion, not an
  oversight.

`LUBRICATION_ANOMALY_V1_MODEL` additionally excludes the CYCLE and CROSS_SIGNAL groups from
the raw feature-catalog set is NOT done — cycle/cross-signal features are legitimate,
non-identifier physical evidence and are kept for both models.
"""

from __future__ import annotations

_EXCLUDED_EVERYWHERE = (
    "context.machine_type",
    "context.criticality",
    "context.firmware_version",
    "context.controller_version",
)

_CATEGORICAL_CONTEXT_FEATURES = (
    "context.operating_state",
    "context.load_bucket",
    "context.rpm_bucket",
    "context.cycle_phase",
    "context.sensor_availability_mask",
)

#: Features an Isolation Forest can consume directly — numeric/boolean only. Categorical
#: context is not included (Isolation Forest has no native categorical handling; adding
#: one-hot columns for a model meant to catch multivariate numeric deviation adds noise
#: without evidence of benefit at this dataset scale).
ANOMALY_EXCLUDED_FEATURES = (
    _EXCLUDED_EVERYWHERE
    + _CATEGORICAL_CONTEXT_FEATURES
    + (
        "rules.restriction_pattern_active",
        "rules.leakage_pattern_active",
        "rules.pump_degradation_pattern_active",
        "rules.bearing_condition_pattern_active",
        "rules.evidence_strength",
    )
)

#: Classifier keeps the small-cardinality categorical context features (physically
#: meaningful, not identifiers) alongside numeric/boolean evidence, but still excludes rule
#: evidence for the reason documented above.
CLASSIFIER_EXCLUDED_FEATURES = _EXCLUDED_EVERYWHERE + (
    "rules.restriction_pattern_active",
    "rules.leakage_pattern_active",
    "rules.pump_degradation_pattern_active",
    "rules.bearing_condition_pattern_active",
    "rules.evidence_strength",
)

CLASSIFIER_CATEGORICAL_FEATURES = _CATEGORICAL_CONTEXT_FEATURES

#: Minimum-feature requirement (Phase 11 brief §34): if fewer than this many of the model's
#: selected numeric features are present (not missing) for a sample, inference returns
#: INSUFFICIENT_FEATURES rather than a forced prediction.
ANOMALY_MINIMUM_REQUIRED_FEATURES = (
    "pressure.current",
    "pump_current.current",
    "bearing_temp.current",
    "vibration_rms.current",
)

CLASSIFIER_MINIMUM_REQUIRED_FEATURES = ANOMALY_MINIMUM_REQUIRED_FEATURES


def select_feature_names(
    all_feature_names: tuple[str, ...], excluded: tuple[str, ...]
) -> tuple[str, ...]:
    excluded_set = set(excluded)
    return tuple(name for name in sorted(all_feature_names) if name not in excluded_set)
