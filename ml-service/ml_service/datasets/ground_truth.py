"""Reads simulator ground-truth JSONL (written by
`edge/scripts/generate_ml_training_data.py`, using the same
`simulator.engine.output.GroundTruthRecord` shape) to resolve point-in-time labels.

This is the ONLY place `ml_service` reads simulator ground truth, and it is used
EXCLUSIVELY to derive labels (Phase 11 brief §4) — nothing here is ever merged into a
feature matrix. `ml_service` does not import the `simulator` package; ground truth is read
as plain JSON so this module has no simulator dependency.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ml_service.domain.labels import FailureLabel, label_for_ground_truth


@dataclass(frozen=True, slots=True)
class GroundTruthTick:
    timestamp: datetime
    scenarios: list[dict[str, Any]]


class GroundTruthTimeline:
    """One run's ground-truth ticks, sorted by timestamp, supporting point-in-time (<=T)
    lookup only — never a future tick (Phase 11 brief §8)."""

    def __init__(self, ticks: list[GroundTruthTick]) -> None:
        self._ticks = sorted(ticks, key=lambda t: t.timestamp)
        self._timestamps = [t.timestamp for t in self._ticks]

    @staticmethod
    def load(path: Path) -> GroundTruthTimeline:
        ticks: list[GroundTruthTick] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                ticks.append(
                    GroundTruthTick(
                        timestamp=datetime.fromisoformat(record["simulation_timestamp"]),
                        scenarios=record.get("scenarios", []),
                    )
                )
        return GroundTruthTimeline(ticks)

    def label_at_or_before(
        self, as_of: datetime, max_staleness_seconds: float
    ) -> tuple[FailureLabel | None, str | None, float]:
        """Returns `(label, source_scenario_type, severity)` for the latest tick at or
        before `as_of`, only if within `max_staleness_seconds` — never looks ahead of `T`
        (point-in-time correctness, mirroring Phase 10's own `source_timestamp <= T` rule).
        `(None, None, 0.0)` means "no usable ground truth for this sample" (drop it), which
        also covers the `NETWORK_FAILURE`-excluded-from-supervised case.
        """
        idx = bisect_right(self._timestamps, as_of) - 1
        if idx < 0:
            return None, None, 0.0
        tick = self._ticks[idx]
        staleness = (as_of - tick.timestamp).total_seconds()
        if staleness < 0 or staleness > max_staleness_seconds:
            return None, None, 0.0
        label, source = label_for_ground_truth(tick.scenarios)
        if label is None:
            return None, None, 0.0
        severity = 0.0
        if source is not None:
            matching = [s for s in tick.scenarios if s.get("scenario_type") == source]
            if matching:
                severity = float(matching[0].get("severity", 0.0))
        return label, source, severity
