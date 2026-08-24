"""API-level tests for `/api/v1/energy/*carbon*`/`emission-factor` — real HTTP requests
via `TestClient` against real Postgres (Lubrication Efficiency Intelligence, Pass 4,
ADR-176)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

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
    Plant,
    ProductionLine,
    Sensor,
    Site,
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
class SeededCarbonMachine:
    tenant: Tenant
    machine: Machine
    site: Site
    sensor: Sensor


async def _resolve_site(session, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> uuid.UUID:
    from sqlalchemy import select

    stmt = (
        select(Plant.site_id)
        .join(ProductionLine, ProductionLine.plant_id == Plant.id)
        .join(Machine, Machine.production_line_id == ProductionLine.id)
        .where(Plant.tenant_id == tenant_id, Machine.id == machine_id)
    )
    site_id = await session.scalar(stmt)
    assert site_id is not None
    return site_id


@pytest_asyncio.fixture
async def seeded_carbon_machine() -> AsyncIterator[SeededCarbonMachine]:
    """Elevated pre-window, fully recovered post-window, a completed relevant
    maintenance case — enough for a real `QUALIFIED_RECOVERY` energy outcome, computed
    live through the actual API route (never seeded directly)."""
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
                for t in (baseline_start + timedelta(minutes=i) for i in range(100))
            ]
            await insert_rows(session, baseline_rows)
            from app.baselines.config.policy import load_baseline_policy
            from app.baselines.services.baseline_engine import BaselineEngine

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
                correlation_key=f"carbon-api-test-{uuid.uuid4()}",
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

            yield SeededCarbonMachine(tenant=tenant, machine=machine, site=site, sensor=sensor)
    finally:
        await database.dispose()


def test_emission_factor_get_returns_null_when_unconfigured(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/sites/{seeded_carbon_machine.site.id}/emission-factor",
        headers={TENANT_HEADER: str(seeded_carbon_machine.tenant.id)},
    )
    assert response.status_code == 200
    assert response.json() is None


def test_emission_factor_configure_and_read_back(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    """No `Authorization` header is sent — the permissive-mode demo fallback principal
    is `UserRole.ADMIN` (`app.api.deps.get_current_principal`'s own documented
    pre-Phase-24-compatibility behavior), which holds every `Permission` including
    `ADMIN_CONFIG`, so this write succeeds; a real deployment (`AUTH_ENFORCEMENT_MODE
    =strict`) would instead require a genuine bearer token here."""
    response = client.post(
        f"/api/v1/energy/sites/{seeded_carbon_machine.site.id}/emission-factor",
        headers={TENANT_HEADER: str(seeded_carbon_machine.tenant.id)},
        json={
            "factor_value": 0.4,
            "source_name": "test factor",
            "jurisdiction": "Demo region",
            "provenance": "DEMO_ESTIMATE",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["factor_value"] == 0.4
    assert body["is_active"] is True
    assert body["provenance"] == "DEMO_ESTIMATE"

    read_back = client.get(
        f"/api/v1/energy/sites/{seeded_carbon_machine.site.id}/emission-factor",
        headers={TENANT_HEADER: str(seeded_carbon_machine.tenant.id)},
    )
    assert read_back.status_code == 200
    assert read_back.json()["id"] == body["id"]


def test_emission_factor_configure_rejects_non_positive_value(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    response = client.post(
        f"/api/v1/energy/sites/{seeded_carbon_machine.site.id}/emission-factor",
        headers={TENANT_HEADER: str(seeded_carbon_machine.tenant.id)},
        json={"factor_value": 0, "source_name": "test"},
    )
    assert response.status_code == 422


def test_carbon_estimate_flow_end_to_end(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    machine_id = seeded_carbon_machine.machine.id
    tenant_id = seeded_carbon_machine.tenant.id

    outcome_response = client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert outcome_response.status_code == 200
    outcome_body = outcome_response.json()
    assert outcome_body["energy_outcome_status"] == "QUALIFIED_RECOVERY"

    carbon_without_factor = client.get(
        f"/api/v1/energy/outcomes/{outcome_body['id']}/carbon",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert carbon_without_factor.status_code == 200
    assert carbon_without_factor.json()["estimate_status"] == "FACTOR_NOT_CONFIGURED"
    assert carbon_without_factor.json()["estimated_co2e_kg"] is None


def test_carbon_estimate_available_once_factor_configured(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    machine_id = seeded_carbon_machine.machine.id
    tenant_id = seeded_carbon_machine.tenant.id

    client.post(
        f"/api/v1/energy/sites/{seeded_carbon_machine.site.id}/emission-factor",
        headers={TENANT_HEADER: str(tenant_id)},
        json={"factor_value": 0.4, "source_name": "test factor"},
    )
    outcome_body = client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    ).json()
    assert outcome_body["energy_outcome_status"] == "QUALIFIED_RECOVERY"
    avoided_kwh = outcome_body["estimated_avoided_energy_kwh"]
    assert avoided_kwh is not None

    carbon = client.get(
        f"/api/v1/energy/outcomes/{outcome_body['id']}/carbon",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert carbon.status_code == 200
    body = carbon.json()
    assert body["estimate_status"] == "ESTIMATE_AVAILABLE"
    assert body["estimated_co2e_kg"] == pytest.approx(avoided_kwh * 0.4)
    assert body["provenance"]["source_name"] == "test factor"


def test_carbon_fleet_latest_and_get_by_id(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    machine_id = seeded_carbon_machine.machine.id
    tenant_id = seeded_carbon_machine.tenant.id

    outcome = client.get(
        f"/api/v1/energy/machines/{machine_id}/outcomes/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    ).json()
    carbon = client.get(
        f"/api/v1/energy/outcomes/{outcome['id']}/carbon",
        headers={TENANT_HEADER: str(tenant_id)},
    ).json()

    fleet = client.get(
        "/api/v1/energy/carbon/fleet-latest", headers={TENANT_HEADER: str(tenant_id)}
    )
    assert fleet.status_code == 200
    assert str(machine_id) in {row["machine_id"] for row in fleet.json()}

    by_id = client.get(
        f"/api/v1/energy/carbon/{carbon['id']}", headers={TENANT_HEADER: str(tenant_id)}
    )
    assert by_id.status_code == 200
    assert by_id.json()["id"] == carbon["id"]

    latest_for_machine = client.get(
        f"/api/v1/energy/machines/{machine_id}/carbon/latest",
        headers={TENANT_HEADER: str(tenant_id)},
    )
    assert latest_for_machine.status_code == 200
    assert latest_for_machine.json()["id"] == carbon["id"]


def test_carbon_get_by_id_404_when_missing(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/carbon/{uuid.uuid4()}",
        headers={TENANT_HEADER: str(seeded_carbon_machine.tenant.id)},
    )
    assert response.status_code == 404


def test_carbon_for_unknown_outcome_404(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/outcomes/{uuid.uuid4()}/carbon",
        headers={TENANT_HEADER: str(seeded_carbon_machine.tenant.id)},
    )
    assert response.status_code == 404


def test_tenant_isolation_on_emission_factor(
    client: TestClient, seeded_carbon_machine: SeededCarbonMachine
) -> None:
    response = client.get(
        f"/api/v1/energy/sites/{seeded_carbon_machine.site.id}/emission-factor",
        headers={TENANT_HEADER: str(uuid.uuid4())},
    )
    assert response.status_code in (400, 404)
