"""Simulator domain enumerations.

`MeasurementType` intentionally mirrors the string values of
`backend/app/domain/enums.py::SensorType` (not imported — the simulator and backend are
separate services per TECHNICAL_DECISIONS.md ADR-011) so that a future telemetry adapter
can map a `SimulationReading.measurement_type` onto `TelemetryReading.signal_type`
(docs/EVENT_CATALOG.md §2.1) without a translation table.
"""

from __future__ import annotations

from enum import StrEnum


class OperatingState(StrEnum):
    """Machine operating states — see docs/SIMULATOR.md §4."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING_LOW_LOAD = "RUNNING_LOW_LOAD"
    RUNNING_NORMAL_LOAD = "RUNNING_NORMAL_LOAD"
    RUNNING_HIGH_LOAD = "RUNNING_HIGH_LOAD"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    MAINTENANCE = "MAINTENANCE"

    @property
    def is_running(self) -> bool:
        return self in (
            OperatingState.RUNNING_LOW_LOAD,
            OperatingState.RUNNING_NORMAL_LOAD,
            OperatingState.RUNNING_HIGH_LOAD,
        )


class CycleResult(StrEnum):
    """Lubrication-cycle outcome — see docs/SIMULATOR.md §6."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class CyclePhase(StrEnum):
    IDLE = "IDLE"
    PUMP_START = "PUMP_START"
    PRESSURE_BUILD = "PRESSURE_BUILD"
    FLOW_DELIVERY = "FLOW_DELIVERY"
    COMPLETING = "COMPLETING"


class SensorQuality(StrEnum):
    """Coarse quality label the simulator itself can assert (device-side self-diagnostic
    only). The Phase 7 data-quality engine computes a richer, independent assessment from
    observed telemetry — this is not that engine, see docs/SYNTHETIC_DATA_MODEL.md §4.

    Phase 4 adds `MISSING`/`INVALID`/`COMMUNICATION_LOSS`/`UNCERTAIN` to represent Sensor
    Dropout and Network Failure without ever substituting a fabricated numeric value for a
    genuinely absent observation — see docs/SCENARIO_ENGINE.md §7."""

    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"
    INVALID = "INVALID"
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    BAD = "BAD"


class NetworkState(StrEnum):
    """Connectivity-loss representation for the Network Failure scenario
    (docs/FAILURE_MODE_CATALOG.md §11). Phase 4 only represents this state internally — no
    real edge buffering/MQTT behavior exists yet (that is Phase 5/6); see
    docs/SCENARIO_ENGINE.md §8."""

    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"


class ReservoirLevelState(StrEnum):
    """Ground-truth-only qualitative reservoir band, computed purely from the physical
    `level_percent` — see `simulator.physics.reservoir.level_state` and
    docs/FAILURE_MODE_CATALOG.md §7 (Low Reservoir)."""

    NORMAL = "NORMAL"
    LOW = "LOW"
    CRITICAL = "CRITICAL"
    EMPTY = "EMPTY"


class MeasurementType(StrEnum):
    """Mirrors backend `SensorType` values 1:1 — see module docstring."""

    PRESSURE = "PRESSURE"
    FLOW = "FLOW"
    RESERVOIR_LEVEL = "RESERVOIR_LEVEL"
    PUMP_CURRENT = "PUMP_CURRENT"
    PUMP_RUNTIME = "PUMP_RUNTIME"
    CYCLE_COMPLETION = "CYCLE_COMPLETION"
    PISTON_MOVEMENT = "PISTON_MOVEMENT"
    LUBRICANT_TEMPERATURE = "LUBRICANT_TEMPERATURE"
    VIBRATION_RMS = "VIBRATION_RMS"
    VIBRATION_PEAK = "VIBRATION_PEAK"
    BEARING_TEMPERATURE = "BEARING_TEMPERATURE"
    RPM = "RPM"
    LOAD = "LOAD"
    #: Machine driveline power, kW — Lubrication Efficiency Intelligence
    #: (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Deliberately distinct from
    #: PUMP_CURRENT (the lubrication pump's own small motor current).
    MACHINE_POWER = "MACHINE_POWER"
