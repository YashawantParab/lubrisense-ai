"""API-level tests for `/api/v1/energy/*/outcomes*` — real HTTP requests via `TestClient`
against real Postgres, mirroring `tests/test_api_attribution.py`'s own committed-fixture
convention (Lubrication Efficiency Intelligence, Pass 3, ADR-176)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient

from app.baselines.config.policy import load_baseline_policy
from app.baselines.services.baseline_engine import BaselineEngine
from app.core.config import get_settings
from app.domain.enums import (
    ConditionSeverity,
    ConditionType,
    DecisionPriority,
    IncidentState,
    MaintenanceActionType,
    MaintenanceState,
    RecommendedAction,
    RecommendedWindow,
    SensorType,
)
from app.domain.models import (
    Incident,
    Machine,
    MaintenanceAction,
    MaintenanceCase,
    Sensor,
    Tenant,
)
from app.infrastructure.database import Database
from tests.baselines.helpers import insert_rows, telemetry_row
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_sensor,
    make_site,
    make_tenant,
)

TENANT_HEADER = "X-Tenant-ID"


@dataclass(frozen=True)
class SeededOutcomeMachine:
    tenant: Tenant
    machine: Machine
    sensor: Sensor
    maintenance_case_id: uuid.UUID


@pytest_asyncio.fixture
async def seeded_recovery_machine() -> AsyncIterator[SeededOutcomeMachine]:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            tenant = await make_tenant(session)
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            sensor = await make_sensor(
                session, tenant, sensor_type=SensorType.MACHINE_POWER, machine_id=machine.id
            )

            now = datetime.now(UTC)
            baseline_start = now - timedelta(hours=3)
            baseline_rows = [
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    source_timestamp=t,
                    value=30.0,
                    measurement_type=SensorType.MACHINE_POWER,
                )
                for t in (baseline_start + timedelta(minutes=1 * i) for i in range(100))
            ]
            await insert_rows(session, baseline_rows)
            engine = BaselineEngine(session, load_baseline_policy())
            for _ in range(3):
                await engine.refresh_sensor(
                    tenant.id, sensor, now, window_override=(baseline_start, now)
                )

            intervention = now
            pre_rows = [
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    source_timestamp=intervention
                    - timedelta(minutes=40)
                    + timedelta(minutes=2 * i),
                    value=40.0,
                    measurement_type=SensorType.MACHINE_POWER,
                )
                for i in range(10)
            ]
            post_rows = [
                telemetry_row(
                    tenant_id=tenant.id,
                    sensor_id=sensor.id,
                    machine_id=machine.id,
                    source_timestamp=intervention + timedelta(minutes=5) + timedelta(minutes=2 * i),
                    value=30.0,
                    measurement_type=SensorType.MACHINE_POWER,
                )
                for i in range(10)
            ]
            await insert_rows(session, pre_rows + post_rows)

            incident = Incident(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                machine_id=machine.id,
                component_id=None,
                correlation_key=f"api-test-{uuid.uuid4()}",
                incident_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
                title="test incident",
                summary="test",
                severity=ConditionSeverity.HIGH,
                priority=DecisionPriority.HIGH,
                state=IncidentState.RESOLVED,
                first_detected_at=now,
                last_updated_at=now,
                resolved_at=intervention,
                condition_assessment_ids=[],
                decision_assessment_ids=[],
                prognostic_assessment_ids=[],
                rule_finding_ids=[],
                ml_result_ids=[],
                state_estimate_ids=[],
                evidence_refs={},
                policy_version="1",
                engine_version="1",
            )
            session.add(incident)
            await session.flush()

            case = MaintenanceCase(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                incident_id=incident.id,
                machine_id=machine.id,
                component_id=None,
                condition_assessment_id=uuid.uuid4(),
                decision_assessment_id=uuid.uuid4(),
                recommended_action=RecommendedAction.INSPECT_LUBRICATION_PATH,
                recommended_window=RecommendedWindow.WITHIN_HOURS,
                priority=DecisionPriority.HIGH,
                human_review_required=True,
                state=MaintenanceState.COMPLETED,
                checklist=[],
                checklist_template_id="test",
                started_at=intervention - timedelta(minutes=30),
                completed_at=intervention,
                policy_version="1",
            )
            session.add(case)
            await session.flush()

            action = MaintenanceAction(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                maintenance_case_id=case.id,
                action_type=MaintenanceActionType.CLEANED,
                notes="test",
                recorded_by="tester",
                recorded_at=intervention - timedelta(minutes=5),
            )
            session.add(action)
            await session.commit()

            yield SeededOutcomeMachine(
                tenant=tenant, machine=machine, sensor=sensor, maintenance_case_id=case.id
            )
    finally:
        await database.dispose()


def test_outcome_requires_tenant_header(
    client: TestClient, seeded_recovery_machine: SeededOutcomeMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/machines/{seeded_recovery_machine.machine.id}/outcomes/latest"
    )
    assert response.status_code == 400


def test_outcome_404_for_unknown_machine(
    client: TestClient, seeded_recovery_machine: SeededOutcomeMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/machines/{uuid.uuid4()}/outcomes/latest",
        headers={TENANT_HEADER: str(seeded_recovery_machine.tenant.id)},
    )
    assert response.status_code == 404


def test_qualified_recovery_computed_via_api(
    client: TestClient, seeded_recovery_machine: SeededOutcomeMachine
) -> None:
    machine_id = seeded_recovery_machine.machine.id
    tenant_id = seeded_recovery_machine.tenant.id
    response = client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["machine_id"] == str(machine_id)
    assert body["maintenance_case_id"] == str(seeded_recovery_machine.maintenance_case_id)
    assert body["energy_outcome_status"] == "QUALIFIED_RECOVERY"
    assert body["comparability_status"] == "COMPARABLE"
    assert body["estimated_avoided_energy_kwh"] is not None
    assert body["estimated_avoided_energy_kwh"] > 0
    assert body["energy_estimate_status"] == "ESTIMATED"


def test_fleet_latest_includes_seeded_machine(
    client: TestClient, seeded_recovery_machine: SeededOutcomeMachine
) -> None:
    machine_id = seeded_recovery_machine.machine.id
    tenant_id = seeded_recovery_machine.tenant.id
    client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    response = client.get(
        "/api/v1/energy/outcomes/fleet-latest", headers={TENANT_HEADER: str(tenant_id)}
    )
    assert response.status_code == 200
    machine_ids = {row["machine_id"] for row in response.json()}
    assert str(machine_id) in machine_ids


def test_history_returns_persisted_verifications(
    client: TestClient, seeded_recovery_machine: SeededOutcomeMachine
) -> None:
    machine_id = seeded_recovery_machine.machine.id
    tenant_id = seeded_recovery_machine.tenant.id
    client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    response = client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert body[0]["energy_outcome_status"] == "QUALIFIED_RECOVERY"


def test_get_by_id(client: TestClient, seeded_recovery_machine: SeededOutcomeMachine) -> None:
    machine_id = seeded_recovery_machine.machine.id
    tenant_id = seeded_recovery_machine.tenant.id
    latest = client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    ).json()
    response = client.get(
        f"/api/v1/energy/outcomes/{latest['id']}", headers={TENANT_HEADER: str(tenant_id)}
    )
    assert response.status_code == 200
    assert response.json()["id"] == latest["id"]


def test_get_by_id_404_when_missing(
    client: TestClient, seeded_recovery_machine: SeededOutcomeMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/outcomes/{uuid.uuid4()}",
        headers={TENANT_HEADER: str(seeded_recovery_machine.tenant.id)},
    )
    assert response.status_code == 404


def test_tenant_isolation_on_outcome(
    client: TestClient, seeded_recovery_machine: SeededOutcomeMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/machines/{seeded_recovery_machine.machine.id}/outcomes/latest",
        headers={TENANT_HEADER: str(uuid.uuid4())},
    )
    assert response.status_code in (400, 404)
