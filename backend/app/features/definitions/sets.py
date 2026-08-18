"""Initial versioned feature-set contracts."""

from __future__ import annotations

from app.features.definitions.catalog import FEATURE_DEFINITIONS
from app.features.domain.models import FeatureSetDefinition

_USES = {
    "LUBRICATION_ANOMALY_V1": (
        "Later unsupervised anomaly detection over lubrication and condition signals."
    ),
    "FAILURE_CLASSIFICATION_V1": (
        "Later supervised failure-pattern classification using observable evidence only."
    ),
    "REFILL_FORECAST_V1": "Later reservoir depletion and refill-demand forecasting.",
    "STATE_ESTIMATION_V1": "Later state-estimation input; Phase 10 performs no state estimation.",
}

_VERSIONS = {
    "LUBRICATION_ANOMALY_V1": "1.0.2",
    "FAILURE_CLASSIFICATION_V1": "1.0.2",
    "REFILL_FORECAST_V1": "1.0.1",
    "STATE_ESTIMATION_V1": "1.0.1",
}

FEATURE_SETS = {
    name: FeatureSetDefinition(
        name=name,
        version=_VERSIONS[name],
        intended_use=intended_use,
        feature_names=tuple(d.name for d in FEATURE_DEFINITIONS if name in d.feature_sets),
    )
    for name, intended_use in _USES.items()
}

if any(not feature_set.feature_names for feature_set in FEATURE_SETS.values()):
    raise RuntimeError("Every feature set must contain at least one feature")
