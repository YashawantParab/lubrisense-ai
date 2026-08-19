"""Shared setup for CMMS tests — a real `MaintenanceCase` backed by a real `Incident` and
a real `RuleFinding`, since `demo_cmms_work_order.maintenance_case_id` carries a genuine
composite foreign key to `maintenance_case` (tenant-safe pattern, not a test convenience
to bypass)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RuleFindingSeverity, RuleFindingType, SensorType
from app.domain.models import MaintenanceCase, Tenant
from app.incidents.services.incident_service import IncidentService
from app.maintenance.services.maintenance_service import MaintenanceService
from tests.incidents.helpers import active_rule_finding
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


async def seed_case(db_session: AsyncSession) -> tuple[Tenant, MaintenanceCase]:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.WARNING,
    )
    incidents = IncidentService(db_session)
    incident = await incidents.evaluate_machine(tenant.id, machine.id)
    assert incident is not None
    await incidents.acknowledge(tenant.id, incident.id)
    await incidents.start_investigation(tenant.id, incident.id)
    maintenance = MaintenanceService(db_session)
    case = await maintenance.create_case_for_incident(tenant.id, incident.id)
    return tenant, case
