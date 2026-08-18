"""`EnvelopeBuilder` — turns one `RawObservation` into a fully-formed, sequenced
`ReadingEnvelope` (Phase 5 brief §3-§6). This is the one place sequence numbers are minted
and event ids derived, so it is the natural seam to unit-test both in isolation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from edge.acquisition.source import RawObservation
from edge.buffering.store import LocalBuffer
from edge.config.models import EdgeConfig
from edge.domain.enums import EdgeMeasurementType, EdgeQuality
from edge.domain.envelope import ReadingEnvelope, make_event_id


class EnvelopeBuilder:
    def __init__(self, config: EdgeConfig, buffer: LocalBuffer) -> None:
        self._config = config
        self._buffer = buffer

    def build(self, observation: RawObservation) -> ReadingEnvelope:
        gateway_id = self._config.gateway_id
        sensor_id = str(observation.sensor_id)
        sequence_number = self._buffer.next_sequence(gateway_id, sensor_id)
        event_id = make_event_id(gateway_id, sensor_id, sequence_number)

        received = datetime.now(UTC) + timedelta(seconds=self._config.clock_offset_seconds)

        return ReadingEnvelope(
            event_id=event_id,
            correlation_id=str(uuid.uuid4()),
            tenant_id=observation.tenant_id,
            machine_id=observation.machine_id,
            component_id=observation.component_id,
            sensor_id=observation.sensor_id,
            measurement_type=EdgeMeasurementType(observation.measurement_type),
            value=observation.value,
            unit=observation.unit,
            quality=EdgeQuality(observation.quality),
            operating_state=observation.operating_state,
            source_timestamp=observation.source_timestamp,
            edge_received_timestamp=received,
            sequence_number=sequence_number,
            gateway_id=gateway_id,
            device_id=gateway_id,
            firmware_version=self._config.firmware_version,
            controller_version=self._config.controller_version,
        )
