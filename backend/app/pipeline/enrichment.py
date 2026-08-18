"""Tenant/entity validation and asset-context enrichment (Phase 6 brief §14/§15).

Given a structurally valid event (`validation.ValidatedTelemetry`), resolves the sensor's
full asset-hierarchy path from the authoritative Phase 2 domain tables, and validates that
the event's `tenant_id`/`sensor_id`/`gateway_id` reference real, same-tenant rows. Any
hierarchy field the edge already supplied (currently only `machine_id`, and optionally
`component_id`) is checked against the resolved value rather than overwritten — a mismatch
is a `CONTEXT_CONFLICT`, never silently corrected (TECHNICAL_DECISIONS.md ADR-058).

This is the one place in the pipeline that talks to the domain/asset-hierarchy tables —
everything upstream (`SchemaValidator`, the MQTT bridge) is asset-hierarchy-agnostic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import QuarantineReason
from app.domain.models import (
    Bearing,
    Circuit,
    Gateway,
    LubricationSystem,
    Machine,
    Plant,
    ProductionLine,
    Pump,
    Reservoir,
    Sensor,
    Tenant,
)
from app.pipeline.validation import ValidatedTelemetry


@dataclass(frozen=True)
class EnrichedContext:
    site_id: uuid.UUID | None
    plant_id: uuid.UUID | None
    production_line_id: uuid.UUID | None
    machine_id: uuid.UUID
    bearing_id: uuid.UUID | None
    lubrication_system_id: uuid.UUID | None
    circuit_id: uuid.UUID | None
    lubrication_point_id: uuid.UUID | None


@dataclass(frozen=True)
class EnrichmentFailure:
    reason: QuarantineReason
    detail: str


EnrichmentResult = EnrichedContext | EnrichmentFailure


class ContextEnrichmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enrich(self, event: ValidatedTelemetry) -> EnrichmentResult:
        tenant = await self.session.get(Tenant, event.tenant_id)
        if tenant is None:
            return EnrichmentFailure(
                QuarantineReason.UNKNOWN_TENANT, f"tenant {event.tenant_id} does not exist"
            )

        sensor = await self.session.scalar(
            select(Sensor).where(Sensor.tenant_id == event.tenant_id, Sensor.id == event.sensor_id)
        )
        if sensor is None:
            return EnrichmentFailure(
                QuarantineReason.UNKNOWN_SENSOR,
                f"sensor {event.sensor_id} not found for tenant {event.tenant_id}",
            )

        gateway = await self._resolve_gateway(event.tenant_id, event.gateway_id)
        if gateway is None:
            return EnrichmentFailure(
                QuarantineReason.UNKNOWN_GATEWAY,
                f"gateway {event.gateway_id!r} not found for tenant {event.tenant_id}",
            )

        resolved = await self._resolve_hierarchy(event.tenant_id, sensor)
        if isinstance(resolved, EnrichmentFailure):
            return resolved

        conflict = self._check_conflicts(event, sensor, resolved)
        if conflict is not None:
            return conflict

        return resolved

    async def _resolve_hierarchy(
        self, tenant_id: uuid.UUID, sensor: Sensor
    ) -> EnrichedContext | EnrichmentFailure:
        attachment_type = sensor.attached_entity_type
        attachment_id = sensor.attached_entity_id

        bearing_id: uuid.UUID | None = None
        lubrication_system_id: uuid.UUID | None = None
        circuit_id: uuid.UUID | None = None
        machine_id: uuid.UUID

        if attachment_type == "machine":
            machine_id = attachment_id
        elif attachment_type == "bearing":
            bearing = await self.session.scalar(
                select(Bearing).where(Bearing.tenant_id == tenant_id, Bearing.id == attachment_id)
            )
            if bearing is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"sensor attached to bearing {attachment_id} which no longer exists",
                )
            bearing_id = attachment_id
            machine_id = bearing.machine_id
        elif attachment_type == "lubrication_system":
            ls = await self._get_lubrication_system(tenant_id, attachment_id)
            if ls is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"sensor attached to lubrication_system {attachment_id} which no longer exists",
                )
            lubrication_system_id = attachment_id
            machine_id = ls.machine_id
        elif attachment_type == "reservoir":
            reservoir = await self.session.scalar(
                select(Reservoir).where(
                    Reservoir.tenant_id == tenant_id, Reservoir.id == attachment_id
                )
            )
            if reservoir is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"sensor attached to reservoir {attachment_id} which no longer exists",
                )
            ls = await self._get_lubrication_system(tenant_id, reservoir.lubrication_system_id)
            if ls is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"reservoir {attachment_id}'s lubrication_system no longer exists",
                )
            lubrication_system_id = reservoir.lubrication_system_id
            machine_id = ls.machine_id
        elif attachment_type == "pump":
            pump = await self.session.scalar(
                select(Pump).where(Pump.tenant_id == tenant_id, Pump.id == attachment_id)
            )
            if pump is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"sensor attached to pump {attachment_id} which no longer exists",
                )
            ls = await self._get_lubrication_system(tenant_id, pump.lubrication_system_id)
            if ls is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"pump {attachment_id}'s lubrication_system no longer exists",
                )
            lubrication_system_id = pump.lubrication_system_id
            machine_id = ls.machine_id
        elif attachment_type == "circuit":
            circuit = await self.session.scalar(
                select(Circuit).where(Circuit.tenant_id == tenant_id, Circuit.id == attachment_id)
            )
            if circuit is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"sensor attached to circuit {attachment_id} which no longer exists",
                )
            ls = await self._get_lubrication_system(tenant_id, circuit.lubrication_system_id)
            if ls is None:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"circuit {attachment_id}'s lubrication_system no longer exists",
                )
            circuit_id = attachment_id
            lubrication_system_id = circuit.lubrication_system_id
            machine_id = ls.machine_id
        else:  # pragma: no cover - exhaustive per Sensor's own CHECK constraint
            return EnrichmentFailure(
                QuarantineReason.CONTEXT_CONFLICT,
                f"sensor has unrecognized attachment type {attachment_type!r}",
            )

        machine = await self.session.scalar(
            select(Machine).where(Machine.tenant_id == tenant_id, Machine.id == machine_id)
        )
        if machine is None:
            return EnrichmentFailure(
                QuarantineReason.CONTEXT_CONFLICT,
                f"resolved machine {machine_id} no longer exists",
            )

        production_line = await self.session.scalar(
            select(ProductionLine).where(
                ProductionLine.tenant_id == tenant_id,
                ProductionLine.id == machine.production_line_id,
            )
        )
        plant_id = production_line.plant_id if production_line is not None else None

        plant = (
            await self.session.scalar(
                select(Plant).where(Plant.tenant_id == tenant_id, Plant.id == plant_id)
            )
            if plant_id is not None
            else None
        )
        site_id = plant.site_id if plant is not None else None

        return EnrichedContext(
            site_id=site_id,
            plant_id=plant_id,
            production_line_id=machine.production_line_id,
            machine_id=machine_id,
            bearing_id=bearing_id,
            lubrication_system_id=lubrication_system_id,
            circuit_id=circuit_id,
            lubrication_point_id=None,
        )

    async def _resolve_gateway(self, tenant_id: uuid.UUID, wire_gateway_id: str) -> Gateway | None:
        """The edge's `EnvelopeBuilder` populates the wire `gateway_id` field with
        `EdgeConfig.gateway_id` — the real `Gateway.id` (UUID) of the seeded gateway row it
        is bound to, not `Gateway.gateway_code` (see `edge/edge/acquisition/builder.py` and
        the demo config's `gateway_id`/`gateway_code` pair). Match on `Gateway.id` first;
        fall back to `gateway_code` for a producer that reasonably sends the human-readable
        code instead — the wire contract does not strictly type this field as a UUID."""
        try:
            gateway_uuid = uuid.UUID(wire_gateway_id)
        except ValueError:
            gateway_uuid = None

        if gateway_uuid is not None:
            by_id: Gateway | None = await self.session.scalar(
                select(Gateway).where(Gateway.tenant_id == tenant_id, Gateway.id == gateway_uuid)
            )
            if by_id is not None:
                return by_id

        by_code: Gateway | None = await self.session.scalar(
            select(Gateway).where(
                Gateway.tenant_id == tenant_id, Gateway.gateway_code == wire_gateway_id
            )
        )
        return by_code

    async def _get_lubrication_system(
        self, tenant_id: uuid.UUID, lubrication_system_id: uuid.UUID
    ) -> LubricationSystem | None:
        result: LubricationSystem | None = await self.session.scalar(
            select(LubricationSystem).where(
                LubricationSystem.tenant_id == tenant_id,
                LubricationSystem.id == lubrication_system_id,
            )
        )
        return result

    @staticmethod
    def _check_conflicts(
        event: ValidatedTelemetry, sensor: Sensor, resolved: EnrichedContext
    ) -> EnrichmentFailure | None:
        if event.machine_id != resolved.machine_id:
            return EnrichmentFailure(
                QuarantineReason.CONTEXT_CONFLICT,
                f"edge-supplied machine_id {event.machine_id} != resolved {resolved.machine_id}",
            )
        if event.component_id is not None and event.component_id != sensor.attached_entity_id:
            return EnrichmentFailure(
                QuarantineReason.CONTEXT_CONFLICT,
                f"edge-supplied component_id {event.component_id} != sensor attachment "
                f"{sensor.attached_entity_id}",
            )
        for field, resolved_value in (
            ("site_id", resolved.site_id),
            ("plant_id", resolved.plant_id),
            ("line_id", resolved.production_line_id),
            ("bearing_id", resolved.bearing_id),
            ("lubrication_system_id", resolved.lubrication_system_id),
            ("circuit_id", resolved.circuit_id),
            ("lubrication_point_id", resolved.lubrication_point_id),
        ):
            supplied_value = getattr(event, field)
            if supplied_value is not None and supplied_value != resolved_value:
                return EnrichmentFailure(
                    QuarantineReason.CONTEXT_CONFLICT,
                    f"edge-supplied {field} {supplied_value} != resolved {resolved_value}",
                )
        return None
