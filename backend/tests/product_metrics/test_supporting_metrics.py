"""Supporting product metrics (Phase 22 brief §22.2/§22.3) — smoke coverage: runs clean
on an empty tenant (every ratio metric undefined, not a fabricated zero) and reflects
real data once present."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import MetricProvenance, SensorType
from app.product_metrics.supporting_metrics import compute_supporting_metrics
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_sensor,
    make_site,
    make_tenant,
)


@pytest.mark.asyncio
async def test_supporting_metrics_on_empty_tenant_are_undefined_not_zero(
    db_session: AsyncSession,
) -> None:
    tenant = await make_tenant(db_session)
    metrics = await compute_supporting_metrics(db_session, tenant.id)

    ids = {m.metric_id for m in metrics}
    assert "coverage.instrumented_asset_coverage" in ids
    assert "feedback.true_positive_confirmation_rate" in ids
    assert "knowledge.approved_knowledge_coverage" in ids

    for metric in metrics:
        assert metric.provenance == MetricProvenance.MEASURED_PLATFORM_METRIC
        if metric.denominator == 0:
            assert metric.value is None
            assert metric.data_completeness_note is not None


@pytest.mark.asyncio
async def test_instrumented_asset_coverage_reflects_real_sensor(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    customer = await make_customer(db_session, tenant)
    site = await make_site(db_session, tenant, customer)
    plant = await make_plant(db_session, tenant, site)
    line = await make_production_line(db_session, tenant, plant)
    machine = await make_machine(db_session, tenant, line)
    await make_sensor(db_session, tenant, SensorType.PRESSURE, machine_id=machine.id)

    metrics = await compute_supporting_metrics(db_session, tenant.id)
    coverage = next(m for m in metrics if m.metric_id == "coverage.instrumented_asset_coverage")

    assert coverage.numerator == 1.0
    assert coverage.denominator == 1.0
    assert coverage.value == 1.0
