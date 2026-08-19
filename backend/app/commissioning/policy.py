"""Capability-level and instrumentation-validation policy (Phase 30 brief §30.5/§30.6).

Deliberately does not require `SensorType.FLOW` for delivery-intelligence capability —
the flagship reference topology itself has no flow sensor (brief §30.5 explicitly warns
against this), so `DELIVERY_SECONDARY_OPTIONS` accepts any one of several plausible
secondary channels instead of one fixed required sensor.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import CapabilityLevel, SensorType

DELIVERY_PRIMARY = SensorType.PRESSURE
DELIVERY_SECONDARY_OPTIONS: frozenset[SensorType] = frozenset(
    {SensorType.RESERVOIR_LEVEL, SensorType.PUMP_CURRENT, SensorType.FLOW}
)
BEARING_INDICATOR_TYPES: frozenset[SensorType] = frozenset(
    {SensorType.VIBRATION_RMS, SensorType.VIBRATION_PEAK, SensorType.BEARING_TEMPERATURE}
)

#: Case-insensitive expected units per sensor type — used only to WARN, never to block
#: commissioning (brief §30.4 lists "unsupported units" as something to *detect*, not an
#: automatic hard failure).
EXPECTED_UNITS: dict[SensorType, frozenset[str]] = {
    SensorType.PRESSURE: frozenset({"bar", "psi"}),
    SensorType.FLOW: frozenset({"l/min", "lpm"}),
    SensorType.RESERVOIR_LEVEL: frozenset({"%", "percent", "mm"}),
    SensorType.PUMP_CURRENT: frozenset({"a", "amp", "amps"}),
    SensorType.LUBRICANT_TEMPERATURE: frozenset({"degc", "c", "°c"}),
    SensorType.VIBRATION_RMS: frozenset({"mm/s"}),
    SensorType.VIBRATION_PEAK: frozenset({"mm/s", "g"}),
    SensorType.BEARING_TEMPERATURE: frozenset({"degc", "c", "°c"}),
    SensorType.RPM: frozenset({"rpm"}),
    SensorType.LOAD: frozenset({"%", "percent"}),
}


def compute_capability_level(sensor_types: set[SensorType]) -> CapabilityLevel:
    has_delivery = DELIVERY_PRIMARY in sensor_types and bool(
        sensor_types & DELIVERY_SECONDARY_OPTIONS
    )
    has_bearing = bool(sensor_types & BEARING_INDICATOR_TYPES)
    if has_delivery and has_bearing:
        return CapabilityLevel.FULL_INTELLIGENCE
    if has_delivery:
        return CapabilityLevel.DELIVERY_INTELLIGENCE
    if has_bearing:
        return CapabilityLevel.BEARING_INTELLIGENCE
    if sensor_types:
        return CapabilityLevel.BASIC_MONITORING
    return CapabilityLevel.NONE


def is_unit_expected(sensor_type: SensorType, unit: str | None) -> bool:
    expected = EXPECTED_UNITS.get(sensor_type)
    if expected is None or unit is None:
        return True
    return unit.strip().lower() in expected


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    blocking: bool
