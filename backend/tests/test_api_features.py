"""Feature API tenant scoping, registry, sets, and online latest computation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.models import Tenant
from app.features.config.policy import load_feature_policy
from app.features.materialization.materializer import FeatureMaterializer
from app.infrastructure.database import Database
from tests.factories import make_customer, make_machine, make_plant, make_production_line, make_site


async def _committed_machine(tenant: Tenant):
    database = Database(get_settings())
    try:
        async with database.session() as session:
            customer = await make_customer(session, tenant)
            site = await make_site(session, tenant, customer)
            plant = await make_plant(session, tenant, site)
            line = await make_production_line(session, tenant, plant)
            machine = await make_machine(session, tenant, line)
            await session.commit()
            return machine
    finally:
        await database.dispose()


async def _materialized_vector(tenant: Tenant, machine_id: uuid.UUID) -> uuid.UUID:
    database = Database(get_settings())
    try:
        async with database.session() as session:
            result = await FeatureMaterializer(session, load_feature_policy()).materialize(
                tenant.id,
                machine_id,
                "LUBRICATION_ANOMALY_V1",
                datetime.now(UTC),
            )
            await session.commit()
            return result.vector.id
    finally:
        await database.dispose()


def test_feature_registry_sets_and_latest_api(client: TestClient, api_tenant: Tenant) -> None:
    import asyncio

    machine = asyncio.run(_committed_machine(api_tenant))
    headers = {"X-Tenant-ID": str(api_tenant.id)}

    registry = client.get("/api/v1/features/registry", headers=headers)
    assert registry.status_code == 200
    assert any(item["feature_name"] == "pressure.robust_deviation" for item in registry.json())

    sets = client.get("/api/v1/features/sets", headers=headers)
    assert sets.status_code == 200
    assert {item["name"] for item in sets.json()} == {
        "LUBRICATION_ANOMALY_V1",
        "FAILURE_CLASSIFICATION_V1",
        "REFILL_FORECAST_V1",
        "STATE_ESTIMATION_V1",
    }

    latest = client.get(f"/api/v1/features/machines/{machine.id}/latest", headers=headers)
    assert latest.status_code == 200
    payload = latest.json()
    assert payload["machine_id"] == str(machine.id)
    assert payload["feature_set"] == "LUBRICATION_ANOMALY_V1"
    assert payload["feature_values"]["availability.has_pressure_sensor"] is False
    assert "pressure.current" in payload["missing_features"]

    vector_id = asyncio.run(_materialized_vector(api_tenant, machine.id))
    history = client.get(f"/api/v1/features/machines/{machine.id}", headers=headers)
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [str(vector_id)]

    detail = client.get(f"/api/v1/features/vectors/{vector_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == str(vector_id)
    assert detail.json()["source_window"]["event_time_field"] == "source_timestamp"

    missing_tenant = client.get("/api/v1/features/registry")
    assert missing_tenant.status_code == 400
