"""Shared setup for agent tests — a real machine with a real restriction incident,
mirroring `tests/cmms/helpers.py`'s pattern."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType
from app.domain.models import Incident, Machine, Tenant
from app.incidents.services.incident_service import IncidentService
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


async def seed_restriction_incident(
    db_session: AsyncSession,
) -> tuple[Tenant, Machine, Incident]:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.WARNING,
    )
    incident = await IncidentService(db_session).evaluate_machine(tenant.id, machine.id)
    assert incident is not None
    return tenant, machine, incident
