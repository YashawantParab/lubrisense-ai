"""Shared plumbing for the Phase-37 synthetic demo-scenario seed scripts
(`backend/scripts/seed_active_restriction.py` and its seven siblings).

This module factors out exactly the boilerplate `seed_flagship_story.py` /
`seed_healthy_machine.py` already duplicate byte-for-byte between each other — tenant/
machine resolution by asset code, sensor grouping by type, the telemetry envelope, the
deadlock-safe `SensorQualityState` upsert, and the state-estimation tick replay. No
business logic lives here: every real write still goes through the actual service classes
(`TelemetryRepository`, `SensorQualityStateRepository`, `app.baselines.workers.backfill`,
`app.rules_engine.workers.reprocess`, `IncidentService`, `MaintenanceService`,
`FeatureEngine`/`StateEstimator`) exactly as flagship/healthy call them — this module only
avoids re-typing the plumbing around those calls in eight more files.

Not itself a seed script (no `main()` / no `__main__` guard) — nothing runs it directly.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import Eligibility, IncidentState, QualityState, TelemetryQuality
from app.domain.models import (
    Bearing,
    Circuit,
    Incident,
    LubricationSystem,
    Machine,
    Pump,
    Reservoir,
    Sensor,
    StateEstimate,
    Telemetry,
    Tenant,
)
from app.features.config.policy import load_feature_policy
from app.features.services.feature_engine import FeatureEngine
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.state_estimation.config.policy import load_state_estimation_config
from app.state_estimation.domain.models import PriorEstimate
from app.state_estimation.models.estimator import FeatureTick, StateEstimator
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository

DEMO_TENANT_SLUG = "lubrisense-demo"
GATEWAY_CODE = "GW-RIDGE"


@dataclass(frozen=True, slots=True)
class MachineContext:
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    circuit_id: uuid.UUID | None
    by_type: dict[str, list[Sensor]]


async def resolve_machine(session: AsyncSession, asset_code: str) -> MachineContext:
    """Same resolution path `seed_flagship_story.py`/`seed_healthy_machine.py` use —
    match on `(tenant.slug, machine.asset_code)`, then collect every sensor reachable
    from this one machine's circuit/pump/reservoir/bearing/machine-direct attachment
    points, grouped by `sensor_type`."""
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))
    ).scalar_one()
    machine = (
        await session.execute(
            select(Machine).where(Machine.tenant_id == tenant.id, Machine.asset_code == asset_code)
        )
    ).scalar_one()

    grouped: dict[str, list[Sensor]] = {}

    async def _add(stmt: Select[tuple[Sensor]]) -> None:
        rows = (await session.execute(stmt)).scalars().all()
        for s in rows:
            grouped.setdefault(s.sensor_type.value, []).append(s)

    await _add(
        select(Sensor)
        .join(Circuit, Circuit.id == Sensor.circuit_id)
        .join(LubricationSystem, LubricationSystem.id == Circuit.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(
        select(Sensor)
        .join(Pump, Pump.id == Sensor.pump_id)
        .join(LubricationSystem, LubricationSystem.id == Pump.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(
        select(Sensor)
        .join(Reservoir, Reservoir.id == Sensor.reservoir_id)
        .join(LubricationSystem, LubricationSystem.id == Reservoir.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(
        select(Sensor)
        .join(Bearing, Bearing.id == Sensor.bearing_id)
        .where(Bearing.machine_id == machine.id, Sensor.tenant_id == tenant.id)
    )
    await _add(select(Sensor).where(Sensor.machine_id == machine.id, Sensor.tenant_id == tenant.id))

    circuit_row = (
        (
            await session.execute(
                select(Circuit)
                .join(LubricationSystem, LubricationSystem.id == Circuit.lubrication_system_id)
                .where(LubricationSystem.machine_id == machine.id)
            )
        )
        .scalars()
        .first()
    )

    return MachineContext(
        tenant_id=tenant.id,
        machine_id=machine.id,
        circuit_id=circuit_row.id if circuit_row else None,
        by_type=grouped,
    )


def envelope(
    *,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    sensor: Sensor,
    value: float,
    t: datetime,
    now: datetime,
    circuit_id: uuid.UUID | None = None,
    device_id: str = "scenario-seed",
    quality: TelemetryQuality = TelemetryQuality.GOOD,
) -> dict[str, object]:
    """Identical shape to `seed_flagship_story.py`'s own `_envelope()`."""
    return {
        "event_id": uuid.uuid4(),
        "schema_version": "1",
        "correlation_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "site_id": None,
        "plant_id": None,
        "production_line_id": None,
        "machine_id": machine_id,
        "bearing_id": None,
        "lubrication_system_id": None,
        "circuit_id": circuit_id,
        "lubrication_point_id": None,
        "sensor_id": sensor.id,
        "measurement_type": sensor.sensor_type,
        "value": value,
        "unit": sensor.unit,
        "quality": quality,
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": t,
        "edge_received_timestamp": t,
        "edge_emitted_timestamp": None,
        "mqtt_received_timestamp": now,
        "kafka_published_timestamp": now,
        "consumer_received_timestamp": now,
        "sequence_number": 1,
        "gateway_id": GATEWAY_CODE,
        "device_id": device_id,
        "firmware_version": None,
        "controller_version": None,
        "source": "synthetic",
        "metadata": {},
        "kafka_partition": 0,
        "kafka_offset": 0,
    }


async def reset_machine_data(
    session: AsyncSession, tenant_id: uuid.UUID, machine_id: uuid.UUID
) -> None:
    """Deterministic reset (ADR-173): delete *all* prior telemetry/state-estimates for
    this one machine — this one machine_id only, never touching another machine or
    tenant — before reseeding, so every re-run starts from the same clean slate."""
    await session.execute(
        delete(Telemetry).where(
            Telemetry.tenant_id == tenant_id, Telemetry.machine_id == machine_id
        )
    )
    await session.execute(
        delete(StateEstimate).where(
            StateEstimate.tenant_id == tenant_id, StateEstimate.machine_id == machine_id
        )
    )
    await session.commit()


async def mark_sensor_quality(
    database: Database,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    sensor_id: uuid.UUID,
    *,
    quality_state: QualityState = QualityState.TRUSTED,
    eligibility: Eligibility = Eligibility.ELIGIBLE,
) -> None:
    """One sensor, one commit, with retry-on-deadlock — same convention
    `seed_flagship_story.py`'s `_mark_eligible()` uses, generalized to accept any quality
    state/eligibility pair (not just TRUSTED/ELIGIBLE) so the data-quality scenario can
    reuse it for UNUSABLE/INELIGIBLE too."""
    for attempt in range(3):
        try:
            async with database.session() as session:
                await SensorQualityStateRepository(session).upsert(
                    tenant_id,
                    sensor_id,
                    machine_id=machine_id,
                    quality_state=quality_state,
                    eligibility=eligibility,
                    policy_version="1",
                )
                await session.commit()
            return
        except OperationalError:
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))


_INCIDENT_ACK_CHAIN = (IncidentState.OPEN, IncidentState.ACKNOWLEDGED, IncidentState.INVESTIGATING)


async def advance_incident_to(
    incidents: IncidentService, tenant_id: uuid.UUID, incident: Incident, target: IncidentState
) -> Incident:
    """Idempotently walk a freshly-created/correlated incident forward to `target`
    (ACKNOWLEDGED or INVESTIGATING) via the real `IncidentService` transition calls,
    skipping any step the incident has already passed — a second run of the same seed
    script against an already-open incident must not re-attempt a transition
    `IncidentService`'s own lifecycle validation (`app.incidents.services.lifecycle`)
    already considers complete (re-calling `acknowledge()` on an already-INVESTIGATING
    incident raises `InvalidIncidentTransitionError`). No-ops (returns `incident`
    unchanged) if the incident is not currently on this chain at all (e.g. already
    RESOLVED by a human/other run)."""
    if target not in _INCIDENT_ACK_CHAIN or incident.state not in _INCIDENT_ACK_CHAIN:
        return incident
    target_index = _INCIDENT_ACK_CHAIN.index(target)
    while _INCIDENT_ACK_CHAIN.index(incident.state) < target_index:
        next_state = _INCIDENT_ACK_CHAIN[_INCIDENT_ACK_CHAIN.index(incident.state) + 1]
        if next_state == IncidentState.ACKNOWLEDGED:
            incident = await incidents.acknowledge(tenant_id, incident.id)
        else:
            incident = await incidents.start_investigation(tenant_id, incident.id)
    return incident


async def replay_state_estimates(
    database: Database,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    state_type: str,
    as_of_times: tuple[datetime, ...],
) -> int:
    """Sequential Kalman-filter replay identical to `seed_flagship_story.py`'s own
    `_replay()` — each tick's posterior is built from the previous tick's posterior plus
    one new `FeatureEngine.compute(as_of=...)` observation, matching what
    `StateEstimationService` does internally, just driven across several historical
    `as_of` points instead of one "latest" point so `state_rate` reflects a real trend."""
    state_config = load_state_estimation_config()
    feature_policy = load_feature_policy()
    estimator = StateEstimator(
        estimator_id=state_type,
        estimator_version=state_config.estimator_version,
        config_version=state_config.config_version,
        state_type=state_type,
        config=state_config.state_config(state_type),
        gap=state_config.gap,
        uncertainty=state_config.uncertainty,
    )
    ticks_done = 0
    for as_of in as_of_times:
        async with database.session() as session:
            engine = FeatureEngine(session, feature_policy)
            computed = await engine.compute(tenant_id, machine_id, state_config.feature_set, as_of)
            tick = FeatureTick(
                tenant_id=computed.tenant_id,
                machine_id=computed.machine_id,
                feature_vector_id=computed.feature_vector_id,
                feature_set=computed.feature_set,
                feature_set_version=computed.feature_set_version,
                as_of_timestamp=computed.as_of_timestamp,
                feature_values=computed.feature_values,
                missing_features=computed.missing_features,
                quality_state=str(computed.quality_summary.get("state", "NO_TRUSTED_DATA")),
            )
            state_repo = StateEstimateRepository(session)
            prior_row = await state_repo.get_latest(
                tenant_id, machine_id, state_type, state_config.estimator_version
            )
            prior = (
                None
                if prior_row is None
                else PriorEstimate(
                    as_of_timestamp=prior_row.as_of_timestamp,
                    level=prior_row.state_value,
                    rate=prior_row.state_rate,
                    p00=float(prior_row.covariance_summary["p00"]),
                    p01=float(prior_row.covariance_summary["p01"]),
                    p11=float(prior_row.covariance_summary["p11"]),
                )
            )
            result = estimator.step(prior, tick)
            await state_repo.persist(result)
            ticks_done += 1
            await session.commit()
    return ticks_done
