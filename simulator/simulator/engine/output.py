"""Structured output contract (Phase 3 brief §17, §29; extended Phase 4 §22, §30).

Two channels, always kept separate (§18 — never leak hidden state into observable
telemetry):

- `SimulationReading`: one row per sensor per tick. Carries both `true_value` and
  `observed_value` because Phase 3 itself needs the pair for relationship/invariant testing
  and future model evaluation — but a future telemetry adapter (Phase 6) maps only
  `observed_value` onto `TelemetryReading.value` (docs/EVENT_CATALOG.md §2.1);
  `true_value` is dropped at that boundary. See docs/SYNTHETIC_DATA_MODEL.md.
  `observed_value` is `None` when Sensor Dropout/Network Failure make the observation
  genuinely unavailable this tick (Phase 4 brief §13-§14) — `true_value` keeps being
  computed and stored regardless, because the physical world does not stop just because the
  reading didn't arrive (docs/SCENARIO_ENGINE.md §7).
- `GroundTruthRecord`: one row per machine per tick, carrying the deeper hidden-state
  variables (`restriction_factor`, `pump_efficiency`, `bearing_health`, ...) that must
  never reach a downstream ML feature pipeline. Written to a separate stream/file. Phase 4
  adds `scenarios` (every active fault's type/phase/severity/target) and
  `reservoir_level_state`/`network_state`.

`RunMetadata` records simulator/config/seed provenance once per run (§28); Phase 4 adds
`scenario_engine_version`/`scenario_config_version` and the active scenario plan (§21).
"""

from __future__ import annotations

import csv
import dataclasses
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any, cast


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


@dataclass(frozen=True, slots=True)
class SimulationReading:
    simulation_timestamp: datetime
    tenant_id: uuid.UUID
    asset_id: uuid.UUID  # machine id
    component_id: uuid.UUID  # the specific entity the sensor is attached to
    sensor_id: uuid.UUID
    measurement_type: str
    true_value: float
    observed_value: float | None
    unit: str
    quality: str
    operating_state: str
    cycle_id: str | None
    simulation_state: str  # phase of the owning lubrication cycle, IDLE if not applicable

    def to_dict(self) -> dict[str, Any]:
        return cast("dict[str, Any]", _jsonable(dataclasses.asdict(self)))


@dataclass(frozen=True, slots=True)
class BearingGroundTruth:
    bearing_id: uuid.UUID
    lubrication_effectiveness: float
    health: float


@dataclass(frozen=True, slots=True)
class CircuitGroundTruth:
    circuit_id: uuid.UUID
    restriction_factor: float
    leakage_factor: float


@dataclass(frozen=True, slots=True)
class ScenarioGroundTruth:
    """One active (or recently-active) scenario instance's state this tick (Phase 4 brief
    §22). Never mirrored into `SimulationReading` — see docs/SYNTHETIC_DATA_MODEL.md."""

    instance_id: str
    scenario_type: str
    lifecycle_state: str
    severity: float
    target_type: str
    target_id: uuid.UUID
    started_at_sim_seconds: float | None
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class GroundTruthRecord:
    """SIMULATOR INTERNAL STATE — never a feature source for ML (Phase 3 brief §18, §29).

    `scenario`/`severity`/`affected_component` remain a single-value summary (the
    highest-severity active scenario, or `"NORMAL"`/`"NONE"`/`None` when nothing is active)
    for backward-compatible readability; `scenarios` (Phase 4) is the authoritative,
    multi-fault-capable record — see docs/SCENARIO_ENGINE.md §7.
    """

    simulation_timestamp: datetime
    tenant_id: uuid.UUID
    asset_id: uuid.UUID
    scenario: str
    severity: str
    affected_component: str | None
    operating_state: str
    load_percent: float
    ambient_temperature_c: float
    pump_efficiency: float | None
    reservoir_quantity_l: float | None
    reservoir_capacity_l: float | None
    reservoir_level_state: str | None
    network_state: str
    refill_event: bool
    bearings: tuple[BearingGroundTruth, ...]
    circuits: tuple[CircuitGroundTruth, ...]
    scenarios: tuple[ScenarioGroundTruth, ...]

    def to_dict(self) -> dict[str, Any]:
        return cast("dict[str, Any]", _jsonable(dataclasses.asdict(self)))


@dataclass(frozen=True, slots=True)
class RunMetadata:
    """Recorded once per run for reproducibility (Phase 3 brief §28; extended Phase 4
    §21)."""

    run_id: str
    simulator_version: str
    scenario_engine_version: str
    engineering_config_version: str
    scenario_config_version: str
    seed: int
    tenant_id: uuid.UUID
    asset_id: uuid.UUID
    asset_code: str
    start_timestamp: datetime
    duration_seconds: float
    step_seconds: float
    speed_multiplier: float
    mode: str
    scenarios: tuple[str, ...]
    readings_path: str
    ground_truth_path: str

    def to_dict(self) -> dict[str, Any]:
        return cast("dict[str, Any]", _jsonable(dataclasses.asdict(self)))


class JsonlWriter:
    """Append-only JSON-Lines sink — one record per line, never mutated in place, matching
    the append-only telemetry design principle in docs/EVENT_CATALOG.md §1."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file: IO[str] = path.open("w", encoding="utf-8")
        self.count = 0

    def write(self, record: SimulationReading | GroundTruthRecord | RunMetadata) -> None:
        self._file.write(json.dumps(record.to_dict(), default=str))
        self._file.write("\n")
        self.count += 1

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> JsonlWriter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


_READING_CSV_FIELDS = [f.name for f in dataclasses.fields(SimulationReading)]


@dataclass(slots=True)
class CsvReadingWriter:
    """Optional CSV sink for `SimulationReading` rows only, for quick spreadsheet/plot
    inspection (Phase 3 brief §19-§20). Not the architecture boundary — JSONL is."""

    path: Path
    _writer: csv.DictWriter[str] = field(init=False)
    _file: IO[str] = field(init=False)
    count: int = 0

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=_READING_CSV_FIELDS)
        self._writer.writeheader()

    def write(self, reading: SimulationReading) -> None:
        self._writer.writerow(reading.to_dict())
        self.count += 1

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> CsvReadingWriter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
