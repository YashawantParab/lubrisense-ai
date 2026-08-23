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
from datetime import datetime, timedelta

from sqlalchemy import Select, delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import Eligibility, IncidentState, QualityState, TelemetryQuality
from app.domain.models import (
    BaselineProfile,
    Bearing,
    Circuit,
    CommissioningSession,
    ConditionAssessment,
    ConfigurationChange,
    ConfigurationSnapshot,
    Controller,
    DecisionAssessment,
    DemoCMMSWorkOrder,
    Distributor,
    FeatureVector,
    FeedbackRecord,
    Incident,
    IncidentEvent,
    LubricationPoint,
    LubricationSystem,
    Machine,
    MaintenanceAction,
    MaintenanceCase,
    MLInferenceResult,
    PrognosticAssessment,
    Pump,
    QualityAssessment,
    QualityIssue,
    Reservoir,
    RuleFinding,
    Sensor,
    StateEstimate,
    TechnicianFinding,
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
    """Mostly identical shape to `seed_flagship_story.py`'s own `_envelope()` — the one
    deliberate difference is that the pipeline-receipt timestamps below track `t` with a
    small constant realistic latency rather than being pinned to the single seed-time
    `now` for every row. Pinning them all to `now` makes `mqtt_received_timestamp -
    source_timestamp` shrink linearly across a backfilled multi-hour series (from hours
    at the start of the window down to ~0 at the end), which
    `app.data_quality.rules.timeliness.check_clock_status` correctly reads as a
    *progressive* clock drift (its whole point is telling that apart from a flat offset)
    and flags `CLOCK_DRIFT_SUSPECTED` on nearly every sensor on every machine — pure
    backfill-artifact noise, not a real timeliness problem, and not the deliberate single
    data-quality story that belongs only to `seed_data_quality_issue.py` (found
    empirically: every one of this module's callers was raising this warning). A small
    *constant* latency keeps the offset flat, which the same rule explicitly treats as
    fine."""
    received_at = t + timedelta(seconds=1.5)
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
        "mqtt_received_timestamp": received_at,
        "kafka_published_timestamp": received_at,
        "consumer_received_timestamp": received_at,
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
    """Deterministic reset (ADR-173): delete *all* prior telemetry/state-estimates/
    quality-issue history for this one machine — this one machine_id only, never
    touching another machine or tenant — before reseeding, so every re-run starts from
    the same clean slate. Quality issues/assessments are included alongside telemetry
    (not just left for the live data-quality-worker to eventually re-evaluate): without
    this, a `CLOCK_DRIFT_SUSPECTED`/`STALE_STREAM` issue raised hours ago against
    telemetry this reset is about to delete stays `ACTIVE` forever — the worker only
    opens new issues, it never retroactively closes one whose underlying data no longer
    exists — which would leave the Data Quality page showing stale noise unrelated to
    the machine's just-reseeded, genuinely fresh state (found empirically re-running the
    hosted orchestrator after several hours).

    Also clears prior incident/maintenance workflow history for this machine (Incident,
    IncidentEvent, MaintenanceCase and its children, and any CMMS draft) — without this,
    `IncidentService`'s correlation-key dedup (which only ever looks at currently-OPEN
    incidents) lets every re-run of a scenario script that reaches RESOLVED create a
    brand-new incident/case rather than reusing the old one, so a handful of re-runs over
    a demo's development life silently pile up dozens of duplicate "resolved" incidents
    for the same one or two machines — found live on the Incidents page (54 total
    incidents, the large majority duplicate rows for exactly the two machines whose
    scripts reach RESOLVED). A machine reseeded by this helper always ends up with at
    most the one incident/case its own scenario script goes on to (re)create this run.

    Also clears prior `RuleFinding` and `ConditionAssessment` history for this machine.
    Without this, a non-terminal (`CANDIDATE`/`ACTIVE`/`RECOVERING`) `RuleFinding` row from
    a previous run survives a reseed untouched — `RuleFindingRepository
    .list_current_for_machine` has no age/run-window filter, so `ConditionEngine.assess()`
    (triggered on-demand by any `GET /machines/{id}` view, not just by this script) can mix
    that stale finding with the fresh evidence this run just wrote, landing on a genuine
    rule/state conflict (`AMBIGUOUS_CONDITION`) instead of the scenario's intended final
    state — found live on the flagship restriction machine, whose condition history
    flip-flopped between `NORMAL_OPERATION` and `DEVELOPING_RESTRICTION_PATTERN` across
    122 assessments spanning several days of repeated reseeds. Old `ConditionAssessment`
    rows are cleared for the same reason: a prior run's stale rows must not influence this
    run's fresh lifecycle classification (`services/lifecycle.py` reads recent history).

    Retries on deadlock (same convention as `mark_sensor_quality` below): the live
    `data-quality-worker` container is concurrently upserting rows in the quality tables
    on its own schedule, and this multi-row delete can lock-order-deadlock against its
    own multi-row transaction (`psycopg.errors.DeadlockDetected`, observed adding the
    quality-table deletes)."""
    for attempt in range(3):
        try:
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
            await session.execute(
                delete(QualityIssue).where(
                    QualityIssue.tenant_id == tenant_id, QualityIssue.machine_id == machine_id
                )
            )
            await session.execute(
                delete(QualityAssessment).where(
                    QualityAssessment.tenant_id == tenant_id,
                    QualityAssessment.machine_id == machine_id,
                )
            )
            # An `MLInferenceResult` row existing at all (regardless of confidence/status)
            # is enough to change `ConditionEngine`/`synthesize()`'s "was any evidence
            # source ever checked" gate — a stale row from an earlier run must not silently
            # outlive the telemetry it was actually computed from.
            await session.execute(
                delete(MLInferenceResult).where(
                    MLInferenceResult.tenant_id == tenant_id,
                    MLInferenceResult.machine_id == machine_id,
                )
            )
            # See this function's own docstring above: a stale non-terminal `RuleFinding`
            # or an old `ConditionAssessment` row must not survive into this run's fresh
            # evidence set.
            await session.execute(
                delete(RuleFinding).where(
                    RuleFinding.tenant_id == tenant_id, RuleFinding.machine_id == machine_id
                )
            )
            await session.execute(
                delete(ConditionAssessment).where(
                    ConditionAssessment.tenant_id == tenant_id,
                    ConditionAssessment.machine_id == machine_id,
                )
            )
            await reset_machine_workflow_history(session, tenant_id, machine_id)
            await session.commit()
            return
        except OperationalError:
            await session.rollback()
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))


async def reset_machine_workflow_history(
    session: AsyncSession, tenant_id: uuid.UUID, machine_id: uuid.UUID
) -> None:
    """Deletes, in FK-safe child-before-parent order, every Incident/MaintenanceCase
    (and their own children) for this one machine — see `reset_machine_data`'s docstring
    for why. Runs inside the caller's existing transaction/retry loop, not its own."""
    case_ids = (
        (
            await session.execute(
                select(MaintenanceCase.id).where(
                    MaintenanceCase.tenant_id == tenant_id,
                    MaintenanceCase.machine_id == machine_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if case_ids:
        await session.execute(
            delete(FeedbackRecord).where(
                FeedbackRecord.tenant_id == tenant_id,
                FeedbackRecord.maintenance_case_id.in_(case_ids),
            )
        )
        await session.execute(
            delete(MaintenanceAction).where(
                MaintenanceAction.tenant_id == tenant_id,
                MaintenanceAction.maintenance_case_id.in_(case_ids),
            )
        )
        await session.execute(
            delete(TechnicianFinding).where(
                TechnicianFinding.tenant_id == tenant_id,
                TechnicianFinding.maintenance_case_id.in_(case_ids),
            )
        )
        await session.execute(
            delete(DemoCMMSWorkOrder).where(
                DemoCMMSWorkOrder.tenant_id == tenant_id,
                DemoCMMSWorkOrder.maintenance_case_id.in_(case_ids),
            )
        )
        await session.execute(
            delete(MaintenanceCase).where(
                MaintenanceCase.tenant_id == tenant_id, MaintenanceCase.id.in_(case_ids)
            )
        )

    incident_ids = (
        (
            await session.execute(
                select(Incident.id).where(
                    Incident.tenant_id == tenant_id, Incident.machine_id == machine_id
                )
            )
        )
        .scalars()
        .all()
    )
    if incident_ids:
        await session.execute(
            delete(IncidentEvent).where(
                IncidentEvent.tenant_id == tenant_id, IncidentEvent.incident_id.in_(incident_ids)
            )
        )
        await session.execute(
            delete(Incident).where(Incident.tenant_id == tenant_id, Incident.id.in_(incident_ids))
        )


async def mark_sensor_quality(
    database: Database,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    sensor_id: uuid.UUID,
    *,
    quality_state: QualityState = QualityState.TRUSTED,
    eligibility: Eligibility = Eligibility.ELIGIBLE,
    last_observed_at: datetime | None = None,
) -> None:
    """One sensor, one commit, with retry-on-deadlock — same convention
    `seed_flagship_story.py`'s `_mark_eligible()` uses, generalized to accept any quality
    state/eligibility pair (not just TRUSTED/ELIGIBLE) so the data-quality scenario can
    reuse it for UNUSABLE/INELIGIBLE too.

    `last_observed_at` is a merge-patch field (`SensorQualityStateRepository.upsert` only
    sets keys it's given): omitting it leaves whatever `last_observed_at` a *previous* seed
    run already wrote untouched. Since sensor UUIDs are deterministic and `reset_machine_data`
    never deletes `SensorQualityState` rows, an old run's real (now days-stale) timestamp
    otherwise survives a fresh reseed unchanged — `check_stale_stream` then compares "now"
    against that stale value and raises a phantom `STALE_STREAM` issue for a sensor whose
    telemetry the reseed just wrote seconds ago. Callers that just backfilled telemetry
    ending at a known synthetic "now" should pass that same timestamp here."""
    for attempt in range(3):
        try:
            async with database.session() as session:
                fields: dict[str, object] = {
                    "machine_id": machine_id,
                    "quality_state": quality_state,
                    "eligibility": eligibility,
                    "policy_version": "1",
                }
                if last_observed_at is not None:
                    fields["last_observed_at"] = last_observed_at
                    fields["last_source_timestamp_seen"] = last_observed_at
                await SensorQualityStateRepository(session).upsert(tenant_id, sensor_id, **fields)
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


async def delete_machine_fully(
    session: AsyncSession, tenant_id: uuid.UUID, machine_id: uuid.UUID
) -> None:
    """Permanently removes one machine and every row anywhere in the schema that
    references it — used only by the hosted-demo debris cleanup
    (`seed_hosted_demo.py`'s `_delete_debris_machines`) to remove machines created outside
    any seed script (manual commissioning-wizard testing, stray pytest runs against a
    shared dev database — see that function's docstring for how they're identified).
    Never called by any scenario script — those call `reset_machine_data` instead, which
    resets a machine's data but keeps the machine itself.

    This schema has no `ON DELETE CASCADE` anywhere for machine-scoped children (verified:
    every machine-scoped child table has a real composite `(tenant_id, machine_id)` (or
    equivalent chained) foreign key, and all are `NO ACTION`) — an out-of-order delete
    therefore fails loudly with a real constraint violation rather than silently orphaning
    data, so the order below matters and is deliberate: evidence/workflow rows, then the
    Phase 30/31 commissioning and configuration rows, then sensors (which can attach to
    *any* of bearing/lubrication_system/reservoir/pump/circuit, so must go before all of
    them), then the physical lubrication chain leaf-to-root (breaking
    `LubricationSystem`'s cyclic `reservoir_id`/`pump_id`/`controller_id` "primary
    equipment" pointers first — see its `composite_tenant_fk(..., use_alter=True)`
    comment), then bearings, then the machine itself."""
    await reset_machine_data(session, tenant_id, machine_id)

    lubrication_system_ids = (
        (
            await session.execute(
                select(LubricationSystem.id).where(
                    LubricationSystem.tenant_id == tenant_id,
                    LubricationSystem.machine_id == machine_id,
                )
            )
        )
        .scalars()
        .all()
    )
    circuit_ids = (
        (
            await session.execute(
                select(Circuit.id).where(
                    Circuit.tenant_id == tenant_id,
                    Circuit.lubrication_system_id.in_(lubrication_system_ids),
                )
            )
        )
        .scalars()
        .all()
        if lubrication_system_ids
        else []
    )
    sensor_ids = (
        (
            await session.execute(
                select(Sensor.id).where(
                    Sensor.tenant_id == tenant_id,
                    (Sensor.machine_id == machine_id)
                    | Sensor.lubrication_system_id.in_(lubrication_system_ids)
                    | Sensor.circuit_id.in_(circuit_ids),
                )
            )
        )
        .scalars()
        .all()
    )

    await session.execute(
        delete(DecisionAssessment).where(
            DecisionAssessment.tenant_id == tenant_id, DecisionAssessment.machine_id == machine_id
        )
    )
    await session.execute(
        delete(PrognosticAssessment).where(
            PrognosticAssessment.tenant_id == tenant_id,
            PrognosticAssessment.machine_id == machine_id,
        )
    )
    await session.execute(
        delete(FeatureVector).where(
            FeatureVector.tenant_id == tenant_id, FeatureVector.machine_id == machine_id
        )
    )
    if sensor_ids:
        await session.execute(
            delete(BaselineProfile).where(
                BaselineProfile.tenant_id == tenant_id,
                (BaselineProfile.machine_id == machine_id)
                | BaselineProfile.sensor_id.in_(sensor_ids),
            )
        )
    else:
        await session.execute(
            delete(BaselineProfile).where(
                BaselineProfile.tenant_id == tenant_id, BaselineProfile.machine_id == machine_id
            )
        )
    snapshot_ids = (
        (
            await session.execute(
                select(ConfigurationSnapshot.id).where(
                    ConfigurationSnapshot.tenant_id == tenant_id,
                    ConfigurationSnapshot.machine_id == machine_id,
                )
            )
        )
        .scalars()
        .all()
    )
    # `ConfigurationChange.machine_id` alone isn't a reliable filter here: a device history
    # chains snapshots by id (`previous_snapshot_id`/`new_snapshot_id`), and a device
    # re-commissioned under a second `Machine` row (e.g. a "retest" of the same mock
    # gateway) can leave a change row whose own `machine_id` differs from the machine that
    # captured the snapshot it references — found live deleting demo commissioning-wizard
    # debris. Delete by reference to this machine's own snapshot ids as well as by
    # `machine_id`, so no dangling reference can survive.
    change_condition = ConfigurationChange.machine_id == machine_id
    if snapshot_ids:
        change_condition = (
            change_condition
            | ConfigurationChange.new_snapshot_id.in_(snapshot_ids)
            | ConfigurationChange.previous_snapshot_id.in_(snapshot_ids)
        )
    await session.execute(
        delete(ConfigurationChange).where(
            ConfigurationChange.tenant_id == tenant_id, change_condition
        )
    )
    await session.execute(
        delete(ConfigurationSnapshot).where(
            ConfigurationSnapshot.tenant_id == tenant_id,
            ConfigurationSnapshot.machine_id == machine_id,
        )
    )
    await session.execute(
        delete(CommissioningSession).where(
            CommissioningSession.tenant_id == tenant_id,
            CommissioningSession.machine_id == machine_id,
        )
    )

    if sensor_ids:
        await session.execute(
            delete(Sensor).where(Sensor.tenant_id == tenant_id, Sensor.id.in_(sensor_ids))
        )

    if lubrication_system_ids:
        # Break the cyclic "primary equipment" pointers before deleting the rows they
        # point at.
        await session.execute(
            update(LubricationSystem)
            .where(
                LubricationSystem.tenant_id == tenant_id,
                LubricationSystem.id.in_(lubrication_system_ids),
            )
            .values(reservoir_id=None, pump_id=None, controller_id=None)
        )
        if circuit_ids:
            await session.execute(
                delete(LubricationPoint).where(
                    LubricationPoint.tenant_id == tenant_id,
                    LubricationPoint.circuit_id.in_(circuit_ids),
                )
            )
        await session.execute(
            delete(Circuit).where(
                Circuit.tenant_id == tenant_id,
                Circuit.lubrication_system_id.in_(lubrication_system_ids),
            )
        )
        await session.execute(
            delete(Distributor).where(
                Distributor.tenant_id == tenant_id,
                Distributor.lubrication_system_id.in_(lubrication_system_ids),
            )
        )
        await session.execute(
            delete(Reservoir).where(
                Reservoir.tenant_id == tenant_id,
                Reservoir.lubrication_system_id.in_(lubrication_system_ids),
            )
        )
        await session.execute(
            delete(Pump).where(
                Pump.tenant_id == tenant_id, Pump.lubrication_system_id.in_(lubrication_system_ids)
            )
        )
        await session.execute(
            delete(Controller).where(
                Controller.tenant_id == tenant_id,
                Controller.lubrication_system_id.in_(lubrication_system_ids),
            )
        )
        await session.execute(
            delete(LubricationSystem).where(
                LubricationSystem.tenant_id == tenant_id,
                LubricationSystem.id.in_(lubrication_system_ids),
            )
        )

    await session.execute(
        delete(Bearing).where(Bearing.tenant_id == tenant_id, Bearing.machine_id == machine_id)
    )
    await session.execute(
        delete(Machine).where(Machine.tenant_id == tenant_id, Machine.id == machine_id)
    )
    await session.commit()
