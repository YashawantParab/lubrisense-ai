from __future__ import annotations

from datetime import UTC, datetime, timedelta

from edge.config.models import RangeThreshold, RuleThresholds
from edge.domain.envelope import ReadingEnvelope, make_event_id
from edge.rules.engine import LocalRuleEngine
from tests.fakes import (
    BEARING_TEMP_SENSOR_ID,
    MACHINE_ID,
    PRESSURE_SENSOR_ID,
    PUMP_CURRENT_SENSOR_ID,
    RESERVOIR_SENSOR_ID,
    TENANT_ID,
)


def _envelope(
    measurement_type: str,
    value: float | None,
    sensor_id: object,
    quality: str = "GOOD",
    seq: int = 1,
    source_timestamp: datetime | None = None,
) -> ReadingEnvelope:
    ts = source_timestamp or datetime(2026, 1, 1, tzinfo=UTC)
    return ReadingEnvelope.model_validate(
        {
            "event_id": make_event_id("gw-1", str(sensor_id), seq),
            "correlation_id": "corr",
            "tenant_id": TENANT_ID,
            "machine_id": MACHINE_ID,
            "sensor_id": sensor_id,
            "measurement_type": measurement_type,
            "value": value,
            "unit": "u",
            "quality": quality,
            "operating_state": "RUNNING_NORMAL_LOAD",
            "source_timestamp": ts,
            "edge_received_timestamp": ts,
            "sequence_number": seq,
            "gateway_id": "gw-1",
            "device_id": "gw-1",
        }
    )


def _thresholds(**overrides: object) -> RuleThresholds:
    base = {
        "range_thresholds": [
            RangeThreshold(measurement_type="PRESSURE", min_value=0.0, max_value=20.0)
        ],
        "reservoir_critical_percent": 10.0,
        "pump_running_current_a": 1.0,
        "pressure_near_zero_bar": 0.2,
        "lubrication_cycle_failure_seconds": 60.0,
        "critical_measurement_types": ["RESERVOIR_LEVEL"],
        "sensor_fault_debounce_ticks": 3,
    }
    base.update(overrides)
    return RuleThresholds.model_validate(base)


def test_range_violation_triggers_alert() -> None:
    engine = LocalRuleEngine(_thresholds())
    alerts = engine.evaluate(_envelope("PRESSURE", 25.0, PRESSURE_SENSOR_ID))
    assert len(alerts) == 1
    assert alerts[0].rule_id == "LOCAL_RANGE_VIOLATION"


def test_in_range_does_not_trigger() -> None:
    engine = LocalRuleEngine(_thresholds())
    alerts = engine.evaluate(_envelope("PRESSURE", 5.0, PRESSURE_SENSOR_ID))
    assert alerts == []


def test_range_violation_only_fires_once_while_open() -> None:
    engine = LocalRuleEngine(_thresholds())
    first = engine.evaluate(_envelope("PRESSURE", 25.0, PRESSURE_SENSOR_ID, seq=1))
    second = engine.evaluate(_envelope("PRESSURE", 26.0, PRESSURE_SENSOR_ID, seq=2))
    assert len(first) == 1
    assert second == []  # already open, not re-emitted every tick


def test_range_violation_clears_when_back_in_range() -> None:
    engine = LocalRuleEngine(_thresholds())
    engine.evaluate(_envelope("PRESSURE", 25.0, PRESSURE_SENSOR_ID, seq=1))
    cleared = engine.evaluate(_envelope("PRESSURE", 5.0, PRESSURE_SENSOR_ID, seq=2))
    assert len(cleared) == 1
    assert cleared[0].status.value == "CLEARED"


def test_reservoir_critical_triggers_warning() -> None:
    engine = LocalRuleEngine(_thresholds())
    alerts = engine.evaluate(_envelope("RESERVOIR_LEVEL", 5.0, RESERVOIR_SENSOR_ID))
    assert len(alerts) == 1
    assert alerts[0].rule_id == "LOCAL_WARNING"
    assert alerts[0].severity.value == "CRITICAL"


def test_lubrication_cycle_failure_requires_sustained_condition() -> None:
    engine = LocalRuleEngine(_thresholds(lubrication_cycle_failure_seconds=60.0))
    base = datetime(2026, 1, 1, tzinfo=UTC)
    engine.evaluate(
        _envelope("PUMP_CURRENT", 5.0, PUMP_CURRENT_SENSOR_ID, seq=1, source_timestamp=base)
    )
    early = engine.evaluate(
        _envelope("PRESSURE", 0.0, PRESSURE_SENSOR_ID, seq=2, source_timestamp=base)
    )
    assert early == []  # not sustained long enough yet

    late = engine.evaluate(
        _envelope(
            "PRESSURE",
            0.0,
            PRESSURE_SENSOR_ID,
            seq=3,
            source_timestamp=base + timedelta(seconds=120),
        )
    )
    assert len(late) == 1
    assert late[0].rule_id == "LOCAL_LUBRICATION_CYCLE_FAILURE"


def test_lubrication_cycle_failure_inactive_when_pump_not_running() -> None:
    engine = LocalRuleEngine(_thresholds(lubrication_cycle_failure_seconds=1.0))
    base = datetime(2026, 1, 1, tzinfo=UTC)
    engine.evaluate(
        _envelope("PUMP_CURRENT", 0.0, PUMP_CURRENT_SENSOR_ID, seq=1, source_timestamp=base)
    )
    result = engine.evaluate(
        _envelope(
            "PRESSURE",
            0.0,
            PRESSURE_SENSOR_ID,
            seq=2,
            source_timestamp=base + timedelta(seconds=10),
        )
    )
    assert result == []


def test_sensor_fault_requires_debounce() -> None:
    engine = LocalRuleEngine(_thresholds(sensor_fault_debounce_ticks=3))
    for seq in (1, 2):
        alerts = engine.evaluate(
            _envelope("RESERVOIR_LEVEL", None, RESERVOIR_SENSOR_ID, quality="MISSING", seq=seq)
        )
        assert alerts == []
    triggered = engine.evaluate(
        _envelope("RESERVOIR_LEVEL", None, RESERVOIR_SENSOR_ID, quality="MISSING", seq=3)
    )
    assert len(triggered) == 1
    assert triggered[0].rule_id == "LOCAL_SENSOR_FAULT"


def test_sensor_fault_debounce_resets_on_good_reading() -> None:
    engine = LocalRuleEngine(_thresholds(sensor_fault_debounce_ticks=3))
    engine.evaluate(
        _envelope("RESERVOIR_LEVEL", None, RESERVOIR_SENSOR_ID, quality="MISSING", seq=1)
    )
    engine.evaluate(
        _envelope("RESERVOIR_LEVEL", None, RESERVOIR_SENSOR_ID, quality="MISSING", seq=2)
    )
    engine.evaluate(_envelope("RESERVOIR_LEVEL", 50.0, RESERVOIR_SENSOR_ID, quality="GOOD", seq=3))
    result = engine.evaluate(
        _envelope("RESERVOIR_LEVEL", None, RESERVOIR_SENSOR_ID, quality="MISSING", seq=4)
    )
    assert result == []  # counter reset, only 1 consecutive bad tick so far


def test_non_critical_sensor_fault_never_alerts() -> None:
    engine = LocalRuleEngine(_thresholds(critical_measurement_types=[]))
    for seq in range(1, 6):
        alerts = engine.evaluate(
            _envelope(
                "BEARING_TEMPERATURE", None, BEARING_TEMP_SENSOR_ID, quality="MISSING", seq=seq
            )
        )
        assert alerts == []
