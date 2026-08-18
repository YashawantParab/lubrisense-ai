from __future__ import annotations

from edge.buffering.store import LocalBuffer
from edge.domain.enums import BufferStatus
from edge.domain.envelope import ReadingEnvelope, make_event_id
from tests.fakes import MACHINE_ID, PRESSURE_SENSOR_ID, TENANT_ID


def _envelope(sequence: int, gateway_id: str = "gw-1") -> ReadingEnvelope:
    return ReadingEnvelope.model_validate(
        {
            "event_id": make_event_id(gateway_id, str(PRESSURE_SENSOR_ID), sequence),
            "correlation_id": "corr",
            "tenant_id": TENANT_ID,
            "machine_id": MACHINE_ID,
            "sensor_id": PRESSURE_SENSOR_ID,
            "measurement_type": "PRESSURE",
            "value": 5.0,
            "unit": "bar",
            "quality": "GOOD",
            "operating_state": "RUNNING_NORMAL_LOAD",
            "source_timestamp": "2026-01-01T00:00:00+00:00",
            "edge_received_timestamp": "2026-01-01T00:00:01+00:00",
            "sequence_number": sequence,
            "gateway_id": gateway_id,
            "device_id": gateway_id,
        }
    )


def test_sequence_numbers_increment_per_sensor(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    assert buf.next_sequence("gw-1", "sensor-a") == 1
    assert buf.next_sequence("gw-1", "sensor-a") == 2
    assert buf.next_sequence("gw-1", "sensor-b") == 1
    buf.close()


def test_sequence_numbers_persist_across_restart(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    buf.next_sequence("gw-1", "sensor-a")
    buf.next_sequence("gw-1", "sensor-a")
    buf.close()

    restarted = LocalBuffer(tmp_db_path)
    assert restarted.next_sequence("gw-1", "sensor-a") == 3
    restarted.close()


def test_insert_pending_then_replayable(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    envelope = _envelope(1)
    assert buf.insert_pending(envelope) is True
    assert buf.pending_count() == 1
    replayable = buf.get_replayable()
    assert len(replayable) == 1
    assert replayable[0].event_id == envelope.event_id
    buf.close()


def test_duplicate_event_id_insert_is_rejected_not_duplicated(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    envelope = _envelope(1)
    assert buf.insert_pending(envelope) is True
    assert buf.insert_pending(envelope) is False  # no-op, not an error, not a duplicate row
    assert buf.pending_count() == 1
    buf.close()


def test_replay_order_is_by_sequence_number(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    for seq in [3, 1, 2]:
        buf.insert_pending(_envelope(seq))
    ordered = [e.sequence_number for e in buf.get_replayable()]
    assert ordered == [1, 2, 3]
    buf.close()


def test_lifecycle_transitions(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    envelope = _envelope(1)
    buf.insert_pending(envelope)
    buf.mark_sent(envelope.event_id)
    assert buf.counts_by_status().get("SENT") == 1
    buf.mark_acknowledged(envelope.event_id)
    assert buf.counts_by_status().get("ACKNOWLEDGED") == 1
    buf.close()


def test_failed_events_remain_replayable(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    envelope = _envelope(1)
    buf.insert_pending(envelope)
    buf.mark_failed(envelope.event_id, "transport down")
    assert len(buf.get_replayable()) == 1
    buf.close()


def test_retention_moves_oldest_pending_to_dead_letter_not_delete(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    for seq in range(1, 6):
        buf.insert_pending(_envelope(seq))
    moved = buf.enforce_retention(max_buffered_events=3, max_buffer_age_seconds=999999)
    assert moved == 2
    counts = buf.counts_by_status()
    assert counts.get("DEAD_LETTER") == 2
    assert counts.get("PENDING") == 3
    # never deleted — still visible via list_events
    dead = buf.list_events(status=BufferStatus.DEAD_LETTER)
    assert len(dead) == 2
    buf.close()


def test_retention_age_breach_dead_letters_stale_events(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    buf.insert_pending(_envelope(1))
    moved = buf.enforce_retention(max_buffered_events=1000, max_buffer_age_seconds=-1)
    assert moved == 1
    assert buf.counts_by_status().get("DEAD_LETTER") == 1
    buf.close()


def test_config_version_tracking(tmp_db_path: str) -> None:
    buf = LocalBuffer(tmp_db_path)
    assert buf.get_config_version("gw-1") is None
    buf.set_config_version("gw-1", "1")
    assert buf.get_config_version("gw-1") == "1"
    buf.set_config_version("gw-1", "2")
    assert buf.get_config_version("gw-1") == "2"
    buf.close()
