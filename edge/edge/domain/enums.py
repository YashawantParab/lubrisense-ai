"""Edge-local enumerations.

`EdgeQuality` and `EdgeMeasurementType` intentionally mirror the string values of
`simulator.domain.enums.SensorQuality`/`MeasurementType` rather than importing them. The
edge package does depend on `simulator` at runtime to drive `SimulationEngine` (Phase 5
brief §2 — "do not duplicate simulator logic"), but the edge's own *config/envelope schema*
is a separate contract the edge owns end to end (matching the mirror-not-import convention
`simulator.domain.enums.MeasurementType` itself already uses for the backend's `SensorType`)
so that edge config validation does not silently break if a future simulator refactor
renames an internal enum with no edge-facing intent.
"""

from __future__ import annotations

from enum import StrEnum


class EdgeQuality(StrEnum):
    """Coarse quality tag carried on a `ReadingEnvelope`. `GOOD`..`BAD` mirror
    `simulator.domain.enums.SensorQuality`; `UNAVAILABLE` is edge-local, used only when the
    acquisition adapter itself cannot reach the source (distinct from the source reporting a
    quality-tagged-but-present observation) — see docs/EDGE_ARCHITECTURE.md."""

    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"
    INVALID = "INVALID"
    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    BAD = "BAD"
    UNAVAILABLE = "UNAVAILABLE"


class EdgeMeasurementType(StrEnum):
    """Mirrors `simulator.domain.enums.MeasurementType` 1:1 — see module docstring."""

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


class BufferStatus(StrEnum):
    """Lifecycle of one buffered event row (Phase 5 brief §8) — never silently deleted."""

    PENDING = "PENDING"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class ConnectivityState(StrEnum):
    """`ConnectivityManager` state (Phase 5 brief §12) — see docs/EDGE_ARCHITECTURE.md."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    RECOVERING = "RECOVERING"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    CLEARED = "CLEARED"
