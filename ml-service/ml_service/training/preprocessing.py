"""Model-specific preprocessing, fit on TRAIN only (Phase 11 brief §19-§20).

Numeric/boolean features get median imputation (median computed from TRAIN's observed
values only) plus an explicit missingness-indicator column — a legitimate observed zero is
never confused with "missing" (matching Phase 10's own no-zero-fill rule,
`docs/FEATURE_ENGINEERING.md`). Small-cardinality categorical context features are one-hot
encoded against a TRAIN-fit vocabulary, with an explicit bucket for values unseen at
inference time (`__OTHER__`) and one for missing values (`__MISSING__`) — never silently
dropped or crashed on. The fitted `Preprocessor` (medians + vocabularies + final column
order) is persisted alongside the model artifact and reused unchanged at inference
(train/serve parity).
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from ml_service.domain.dataset import FeatureValue

_MISSING_BUCKET = "__MISSING__"
_OTHER_BUCKET = "__OTHER__"


class HasFeatureValues(Protocol):
    """Structural type satisfied by both `ml_service.domain.dataset.DatasetSample`
    (training/evaluation, carries labels) and `ml_service.domain.feature_snapshot.
    FeatureSnapshot` (inference, label-free) — the preprocessor only ever needs
    `feature_values`, so it works unchanged in both places (train/serve parity)."""

    @property
    def feature_values(self) -> dict[str, FeatureValue]: ...


def _is_bool(value: FeatureValue) -> bool:
    return isinstance(value, bool)


def _is_numeric(value: FeatureValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass
class Preprocessor:
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    fitted: bool = False
    medians: dict[str, float] = field(default_factory=dict)
    means: dict[str, float] = field(default_factory=dict)
    stddevs: dict[str, float] = field(default_factory=dict)
    vocabularies: dict[str, list[str]] = field(default_factory=dict)
    output_columns: list[str] = field(default_factory=list)

    def fit(self, train_samples: Sequence[HasFeatureValues]) -> None:
        for name in self.numeric_features:
            observed: list[float] = []
            for sample in train_samples:
                value = sample.feature_values.get(name)
                if value is None:
                    continue
                if _is_bool(value):
                    observed.append(1.0 if value else 0.0)
                elif _is_numeric(value):
                    observed.append(float(value))
            self.medians[name] = statistics.median(observed) if observed else 0.0
            self.means[name] = statistics.mean(observed) if observed else 0.0
            self.stddevs[name] = statistics.pstdev(observed) if len(observed) > 1 else 0.0

        for name in self.categorical_features:
            values = sorted(
                {
                    str(sample.feature_values[name])
                    for sample in train_samples
                    if sample.feature_values.get(name) is not None
                }
            )
            self.vocabularies[name] = values

        columns: list[str] = []
        for name in self.numeric_features:
            columns.append(name)
            columns.append(f"{name}.__missing__")
        for name in self.categorical_features:
            for value in self.vocabularies.get(name, []):
                columns.append(f"{name}={value}")
            columns.append(f"{name}={_OTHER_BUCKET}")
            columns.append(f"{name}={_MISSING_BUCKET}")
        self.output_columns = columns
        self.fitted = True

    def transform(self, samples: Sequence[HasFeatureValues]) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("Preprocessor.transform called before fit()")
        rows = np.zeros((len(samples), len(self.output_columns)), dtype=np.float64)
        column_index = {name: i for i, name in enumerate(self.output_columns)}

        for row_idx, sample in enumerate(samples):
            for name in self.numeric_features:
                value = sample.feature_values.get(name)
                if value is None:
                    rows[row_idx, column_index[f"{name}.__missing__"]] = 1.0
                    rows[row_idx, column_index[name]] = self.medians[name]
                else:
                    numeric = 1.0 if _is_bool(value) else float(value)
                    rows[row_idx, column_index[name]] = numeric
            for name in self.categorical_features:
                value = sample.feature_values.get(name)
                if value is None:
                    rows[row_idx, column_index[f"{name}={_MISSING_BUCKET}"]] = 1.0
                    continue
                str_value = str(value)
                key = f"{name}={str_value}"
                if key in column_index:
                    rows[row_idx, column_index[key]] = 1.0
                else:
                    rows[row_idx, column_index[f"{name}={_OTHER_BUCKET}"]] = 1.0
        return rows

    def missing_feature_count(self, sample: HasFeatureValues, required: tuple[str, ...]) -> int:
        return sum(1 for name in required if sample.feature_values.get(name) is None)
