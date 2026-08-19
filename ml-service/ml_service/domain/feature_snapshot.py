"""A minimal, label-free view of a single Phase 10 feature vector — what actually crosses
the wire at inference time (no dataset/split/label bookkeeping). `DatasetSample` and
`FeatureSnapshot` are structurally interchangeable wherever only feature values matter (see
`HasFeatureValues` in `ml_service.training.preprocessing`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from ml_service.domain.dataset import FeatureValue


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    feature_vector_id: uuid.UUID
    as_of_timestamp: datetime
    feature_set: str
    feature_set_version: str
    feature_values: dict[str, FeatureValue]
    missing_features: tuple[str, ...]
    quality_summary: dict[str, object]
