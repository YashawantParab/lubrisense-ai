"""`LocalRuleEngine` — four deterministic, edge-local checks only (Phase 5 brief §16-§17):
sensor out-of-range, critical/empty reservoir, pump running with no evidence of lubrication
delivery, and invalid/missing critical sensor reading. Generic rule ids only
(`LOCAL_WARNING`/`LOCAL_SENSOR_FAULT`/`LOCAL_RANGE_VIOLATION`/
`LOCAL_LUBRICATION_CYCLE_FAILURE`) — never a domain-specific diagnosis (that is Phase 9's
job). This is explicitly not a general rules engine: four hardcoded checks, no rule
authoring/plugin mechanism, no ML, see ADR-049.

Each rule tracks its own OPEN/CLEARED state per (machine_id, rule_id[, sensor_id]) so a
condition that persists across many ticks produces one alert transition, not one alert per
tick — matching `docs/EVENT_CATALOG.md` §4.1's `LocalAlarmRaised`/`LocalAlarmCleared` model.
`evaluate()` returns only alerts that *changed* state this call.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from edge.config.models import RuleThresholds
from edge.domain.alert import LocalEdgeAlert
from edge.domain.enums import AlertSeverity, AlertStatus, EdgeMeasurementType, EdgeQuality
from edge.domain.envelope import ReadingEnvelope

_BAD_QUALITIES = {EdgeQuality.MISSING, EdgeQuality.COMMUNICATION_LOSS, EdgeQuality.INVALID}


class LocalRuleEngine:
    def __init__(self, thresholds: RuleThresholds) -> None:
        self._thresholds = thresholds
        self._range_by_type = {t.measurement_type: t for t in thresholds.range_thresholds}
        self._open: dict[tuple[str, ...], str] = {}  # key -> alert_id currently open
        self._debounce_counts: dict[str, int] = {}  # sensor_id -> consecutive bad ticks
        self._latest_pump_current: dict[str, tuple[float, datetime]] = {}
        self._latest_pressure: dict[str, tuple[float, datetime]] = {}
        self._low_pressure_since: dict[str, datetime] = {}

    def evaluate(self, envelope: ReadingEnvelope) -> list[LocalEdgeAlert]:
        alerts: list[LocalEdgeAlert] = []
        alerts += self._check_range(envelope)
        alerts += self._check_reservoir_critical(envelope)
        alerts += self._check_lubrication_cycle_failure(envelope)
        alerts += self._check_sensor_fault(envelope)
        return alerts

    # -- rule 1: out-of-range --------------------------------------------------

    def _check_range(self, envelope: ReadingEnvelope) -> list[LocalEdgeAlert]:
        threshold = self._range_by_type.get(envelope.measurement_type)
        if threshold is None or envelope.value is None:
            return self._maybe_clear(("range", str(envelope.sensor_id)), envelope)
        out_of_range = envelope.value < threshold.min_value or envelope.value > threshold.max_value
        key = ("range", str(envelope.sensor_id))
        if out_of_range:
            return self._maybe_open(
                key,
                envelope,
                rule_id="LOCAL_RANGE_VIOLATION",
                severity=AlertSeverity.WARNING,
                message=(
                    f"{envelope.measurement_type} reading {envelope.value} outside configured "
                    f"range [{threshold.min_value}, {threshold.max_value}]"
                ),
                evidence={
                    "value": envelope.value,
                    "min_value": threshold.min_value,
                    "max_value": threshold.max_value,
                },
            )
        return self._maybe_clear(key, envelope)

    # -- rule 2: reservoir critical/empty ---------------------------------------

    def _check_reservoir_critical(self, envelope: ReadingEnvelope) -> list[LocalEdgeAlert]:
        if envelope.measurement_type != EdgeMeasurementType.RESERVOIR_LEVEL:
            return []
        key = ("reservoir_critical", str(envelope.machine_id))
        if (
            envelope.value is not None
            and envelope.value <= self._thresholds.reservoir_critical_percent
        ):
            return self._maybe_open(
                key,
                envelope,
                rule_id="LOCAL_WARNING",
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"Reservoir level {envelope.value}% at/below critical threshold "
                    f"{self._thresholds.reservoir_critical_percent}%"
                ),
                evidence={"value": envelope.value},
            )
        return self._maybe_clear(key, envelope)

    # -- rule 3: pump running with no evidence of lubrication delivery ----------

    def _check_lubrication_cycle_failure(self, envelope: ReadingEnvelope) -> list[LocalEdgeAlert]:
        machine_key = str(envelope.machine_id)
        if (
            envelope.measurement_type == EdgeMeasurementType.PUMP_CURRENT
            and envelope.value is not None
        ):
            self._latest_pump_current[machine_key] = (envelope.value, envelope.source_timestamp)
        elif (
            envelope.measurement_type == EdgeMeasurementType.PRESSURE and envelope.value is not None
        ):
            self._latest_pressure[machine_key] = (envelope.value, envelope.source_timestamp)
        else:
            return []

        pump = self._latest_pump_current.get(machine_key)
        pressure = self._latest_pressure.get(machine_key)
        key = ("lubrication_cycle_failure", machine_key)
        if pump is None or pressure is None:
            return []

        pump_running = pump[0] >= self._thresholds.pump_running_current_a
        pressure_low = pressure[0] <= self._thresholds.pressure_near_zero_bar

        if not (pump_running and pressure_low):
            self._low_pressure_since.pop(machine_key, None)
            return self._maybe_clear(key, envelope)

        since = self._low_pressure_since.setdefault(machine_key, envelope.source_timestamp)
        elapsed = (envelope.source_timestamp - since).total_seconds()
        if elapsed >= self._thresholds.lubrication_cycle_failure_seconds:
            return self._maybe_open(
                key,
                envelope,
                rule_id="LOCAL_LUBRICATION_CYCLE_FAILURE",
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"Pump current {pump[0]}A (running) with pressure {pressure[0]}bar "
                    f"(near zero) sustained for {elapsed:.0f}s — no evidence of lubrication "
                    "delivery"
                ),
                evidence={
                    "pump_current_a": pump[0],
                    "pressure_bar": pressure[0],
                    "elapsed_seconds": elapsed,
                },
            )
        return []

    # -- rule 4: invalid/missing critical sensor (debounced) ---------------------

    def _check_sensor_fault(self, envelope: ReadingEnvelope) -> list[LocalEdgeAlert]:
        if envelope.measurement_type not in self._thresholds.critical_measurement_types:
            return []
        sensor_key = str(envelope.sensor_id)
        key = ("sensor_fault", sensor_key)

        if envelope.quality in _BAD_QUALITIES:
            self._debounce_counts[sensor_key] = self._debounce_counts.get(sensor_key, 0) + 1
        else:
            self._debounce_counts[sensor_key] = 0
            return self._maybe_clear(key, envelope)

        if self._debounce_counts[sensor_key] >= self._thresholds.sensor_fault_debounce_ticks:
            return self._maybe_open(
                key,
                envelope,
                rule_id="LOCAL_SENSOR_FAULT",
                severity=AlertSeverity.WARNING,
                message=(
                    f"{envelope.measurement_type} sensor quality={envelope.quality} for "
                    f"{self._debounce_counts[sensor_key]} consecutive readings"
                ),
                evidence={
                    "quality": envelope.quality.value,
                    "consecutive_ticks": self._debounce_counts[sensor_key],
                },
            )
        return []

    # -- open/clear bookkeeping --------------------------------------------------

    def _maybe_open(
        self,
        key: tuple[str, ...],
        envelope: ReadingEnvelope,
        *,
        rule_id: str,
        severity: AlertSeverity,
        message: str,
        evidence: dict[str, object],
    ) -> list[LocalEdgeAlert]:
        if key in self._open:
            return []
        alert_id = str(uuid.uuid4())
        self._open[key] = alert_id
        alert = LocalEdgeAlert(
            alert_id=alert_id,
            timestamp=datetime.now(UTC),
            tenant_id=envelope.tenant_id,
            gateway_id=envelope.gateway_id,
            machine_id=envelope.machine_id,
            component_id=envelope.component_id,
            sensor_id=envelope.sensor_id,
            rule_id=rule_id,
            severity=severity,
            message=message,
            evidence=evidence,
            source_event_ids=[envelope.event_id],
            status=AlertStatus.OPEN,
        )
        return [alert]

    def _maybe_clear(self, key: tuple[str, ...], envelope: ReadingEnvelope) -> list[LocalEdgeAlert]:
        alert_id = self._open.pop(key, None)
        if alert_id is None:
            return []
        return [
            LocalEdgeAlert(
                alert_id=alert_id,
                timestamp=datetime.now(UTC),
                tenant_id=envelope.tenant_id,
                gateway_id=envelope.gateway_id,
                machine_id=envelope.machine_id,
                sensor_id=envelope.sensor_id,
                rule_id="CLEARED",
                severity=AlertSeverity.INFO,
                message="condition cleared",
                source_event_ids=[envelope.event_id],
                status=AlertStatus.CLEARED,
            )
        ]

    @property
    def open_alert_count(self) -> int:
        return len(self._open)
