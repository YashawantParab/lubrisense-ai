"""Phase 36 flagship demo story — seeds a real, understandable evidence chain on the
existing flagship machine (Conveyor 000, `L1-7B43-M000`, the Phase 2 demo tenant) and
drives it through the real backend services end to end:

    telemetry -> baseline -> rule finding -> state estimate -> condition -> decision
    -> incident -> maintenance case -> technician finding -> action -> feedback

Every step is a real, persisted write through the actual service classes (`RuleEngine`
via `app.rules_engine.workers.reprocess`, `BaselineEngine` via
`app.baselines.workers.backfill`, `StateEstimationService`, `IncidentService`,
`MaintenanceService`) — nothing here is a hardcoded frontend value. Telemetry itself is
hand-seeded directly into TimescaleDB (the same convention `scripts/verify_rules.sh`/
`verify_baselines.sh` already use — the real MQTT/Kafka pipeline is proven separately by
`scripts/verify_pipeline.sh`; re-routing this story through it would only add latency,
not additional evidence of correctness).

Deliberately tells the correlated-signal story CLAUDE.md/the Phase 36 brief ask for:
hydraulic evidence (PRESSURE) rises first; a modest, later bearing-signal uptick
(BEARING_TEMPERATURE, VIBRATION_RMS) appears only in the most recent window — never strong
enough on its own to imply a separate, independent bearing fault; this is one condition
telling one coherent story, not two conflated ones. PUMP_CURRENT is kept flat — see the
comment above phase 2's telemetry loop for why.

    uv run python scripts/seed_flagship_story.py

Safe to re-run: `IncidentService`'s own correlation-key deduplication means re-running
this against an already-open incident just re-evaluates it in place rather than creating
a duplicate (see `docs/RULES_ENGINE.md`/`docs/INCIDENT_MANAGEMENT.md`).
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.workers.backfill import backfill
from app.core.config import get_settings
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import (
    Eligibility,
    FeedbackClassification,
    MaintenanceActionType,
    QualityState,
    SensorType,
    TechnicianFindingResult,
    TelemetryQuality,
)
from app.domain.models import Circuit, LubricationSystem, Sensor, StateEstimate, Tenant
from app.features.config.policy import load_feature_policy
from app.features.services.feature_engine import FeatureEngine
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.maintenance.services.maintenance_service import MaintenanceService
from app.repositories.telemetry import TelemetryRepository
from app.rules_engine.workers.reprocess import reprocess
from app.state_estimation.config.policy import load_state_estimation_config
from app.state_estimation.domain.models import PriorEstimate
from app.state_estimation.models.estimator import FeatureTick, StateEstimator
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository

FLAGSHIP_ASSET_CODE = "L1-7B43-M000"
DEMO_TENANT_SLUG = "lubrisense-demo"
GATEWAY_CODE = "GW-RIDGE"


@dataclass(frozen=True, slots=True)
class _FlagshipContext:
    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    circuit_id: uuid.UUID
    pressure_sensor: Sensor


async def _resolve_flagship(session: AsyncSession) -> _FlagshipContext:
    from app.domain.models import Machine

    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))
    ).scalar_one()

    machine = (
        await session.execute(
            select(Machine).where(
                Machine.tenant_id == tenant.id, Machine.asset_code == FLAGSHIP_ASSET_CODE
            )
        )
    ).scalar_one()

    # Resolve via the pressure sensor's circuit -> lubrication_system chain, filtered to
    # *this specific machine* — the demo tenant has grown several other machines with
    # their own PRESSURE sensors over the course of this project's commissioning phase
    # (Phase 30), so matching on sensor_type/tenant_id alone is not unique enough.
    pressure_row = (
        await session.execute(
            select(Sensor, Circuit)
            .join(Circuit, Circuit.id == Sensor.circuit_id)
            .join(LubricationSystem, LubricationSystem.id == Circuit.lubrication_system_id)
            .where(
                Sensor.tenant_id == tenant.id,
                Sensor.sensor_type == SensorType.PRESSURE,
                LubricationSystem.machine_id == machine.id,
            )
        )
    ).first()
    if pressure_row is None:
        raise SystemExit(
            f"no PRESSURE sensor found for flagship machine {machine.id} — run 'make seed' first"
        )
    pressure_sensor, circuit = pressure_row

    return _FlagshipContext(
        tenant_id=tenant.id,
        machine_id=machine.id,
        circuit_id=circuit.id,
        pressure_sensor=pressure_sensor,
    )


async def _load_all_sensors(
    session: AsyncSession, tenant_id: uuid.UUID, machine_id: uuid.UUID
) -> dict[str, list[Sensor]]:
    from app.domain.models import Bearing, Pump, Reservoir

    grouped: dict[str, list[Sensor]] = {}

    async def _add(stmt: Select[tuple[Sensor]]) -> None:
        rows = (await session.execute(stmt)).scalars().all()
        for s in rows:
            grouped.setdefault(s.sensor_type.value, []).append(s)

    await _add(
        select(Sensor)
        .join(Circuit, Circuit.id == Sensor.circuit_id)
        .join(LubricationSystem, LubricationSystem.id == Circuit.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine_id, Sensor.tenant_id == tenant_id)
    )
    await _add(
        select(Sensor)
        .join(Pump, Pump.id == Sensor.pump_id)
        .join(LubricationSystem, LubricationSystem.id == Pump.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine_id, Sensor.tenant_id == tenant_id)
    )
    await _add(
        select(Sensor)
        .join(Reservoir, Reservoir.id == Sensor.reservoir_id)
        .join(LubricationSystem, LubricationSystem.id == Reservoir.lubrication_system_id)
        .where(LubricationSystem.machine_id == machine_id, Sensor.tenant_id == tenant_id)
    )
    await _add(
        select(Sensor)
        .join(Bearing, Bearing.id == Sensor.bearing_id)
        .where(Bearing.machine_id == machine_id, Sensor.tenant_id == tenant_id)
    )
    await _add(select(Sensor).where(Sensor.machine_id == machine_id, Sensor.tenant_id == tenant_id))
    return grouped


def _envelope(
    *,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    sensor: Sensor,
    value: float,
    t: datetime,
    now: datetime,
    circuit_id: uuid.UUID | None = None,
) -> dict[str, object]:
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
        "quality": TelemetryQuality.GOOD,
        "operating_state": "RUNNING_NORMAL_LOAD",
        "source_timestamp": t,
        "edge_received_timestamp": t,
        "edge_emitted_timestamp": None,
        "mqtt_received_timestamp": now,
        "kafka_published_timestamp": now,
        "consumer_received_timestamp": now,
        "sequence_number": 1,
        "gateway_id": GATEWAY_CODE,
        "device_id": "flagship-story-seed",
        "firmware_version": None,
        "controller_version": None,
        "source": "synthetic",
        "metadata": {},
        "kafka_partition": 0,
        "kafka_offset": 0,
    }


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    healthy_start = now - timedelta(hours=3)
    restriction_start = now - timedelta(minutes=40)
    bearing_effect_start = now - timedelta(minutes=10)

    async with database.session() as session:
        base = await _resolve_flagship(session)
        tenant_id = base.tenant_id
        machine_id = base.machine_id
        circuit_id = base.circuit_id
        by_type = await _load_all_sensors(session, tenant_id, machine_id)

        pressure = by_type["PRESSURE"][0]
        pump_current = by_type["PUMP_CURRENT"][0]
        reservoir = by_type["RESERVOIR_LEVEL"][0]
        bearing_temps = by_type["BEARING_TEMPERATURE"]
        vibrations = by_type["VIBRATION_RMS"]
        rpm = by_type["RPM"][0]

        # Demo-reset: delete *all* prior telemetry for this one machine — every device_id,
        # every timestamp — not just this script's own window. The flagship machine is a
        # dedicated demo asset that this script fully owns; nothing outside this one
        # machine_id (no other machine, no other tenant) is ever touched.
        #
        # This used to be scoped to just `[healthy_start, now]`, which left an older,
        # separately-seeded historical stream in place (device `eb34fc54-...`, ~67k rows
        # since 2026-08-04 from an earlier phase's commissioning/verification run — not
        # live/ongoing, real test debris). That stream sat entirely *before* this story's
        # own window, so it never affected rule/condition evaluation, but it directly
        # corrupted the machine detail page's telemetry chart: that chart's query has no
        # window filter, just "most recent N rows for this machine," so a chunk of that
        # stale, day-old, disconnected data snuck into the "recent" result and stretched
        # the visible chart axis across ~26 hours with a huge empty gap — found during
        # Phase 36's industrial visualization review (ADR-173 in TECHNICAL_DECISIONS.md).
        from app.domain.models import Telemetry

        await session.execute(
            delete(Telemetry).where(
                Telemetry.tenant_id == tenant_id,
                Telemetry.machine_id == machine_id,
            )
        )
        # `StateEstimate` is sequential (Phase 12 brief §17) — each tick's Kalman posterior
        # depends on the previous tick's, read back via `get_latest()`. Leaving old rows in
        # place would let leftover momentum/uncertainty from a previous run's (possibly
        # different) telemetry bleed into this run's estimate, defeating a deterministic
        # reset — the same class of problem the telemetry-window delete above solves.
        await session.execute(
            delete(StateEstimate).where(
                StateEstimate.tenant_id == tenant_id,
                StateEstimate.machine_id == machine_id,
            )
        )
        await session.commit()

        rows: list[dict[str, object]] = []

        # Reservoir depletion is a slow, separate process from the restriction story.
        # `check_reservoir_depletion_abnormal` only fires when the recent-window rate
        # exceeds the healthy-window baseline rate — and with a perfectly linear
        # (zero-noise) synthetic baseline its MAD is exactly 0, which makes the
        # classifier's standardized distance blow up to a large sentinel for *any*
        # nonzero difference (see `classify_reservoir_trend_deviation`). To stay safely
        # on the "not abnormal" side regardless of floating-point noise, the post-healthy
        # phases deplete at a distinctly *slower* rate than the healthy baseline, not
        # merely an equal one.
        HEALTHY_RESERVOIR_RATE_PERCENT_PER_MIN = 0.028
        POST_HEALTHY_RESERVOIR_RATE_PERCENT_PER_MIN = 0.010
        _restriction_anchor = 60.0 - HEALTHY_RESERVOIR_RATE_PERCENT_PER_MIN * (
            (restriction_start - healthy_start).total_seconds() / 60.0
        )

        def reservoir_value(t: datetime) -> float:
            if t <= restriction_start:
                minutes = (t - healthy_start).total_seconds() / 60.0
                return 60.0 - HEALTHY_RESERVOIR_RATE_PERCENT_PER_MIN * minutes
            minutes_after = (t - restriction_start).total_seconds() / 60.0
            return (
                _restriction_anchor
                - POST_HEALTHY_RESERVOIR_RATE_PERCENT_PER_MIN * minutes_after
            )

        def add(
            sensor: Sensor, value: float, t: datetime, *, circuit: uuid.UUID | None = None
        ) -> None:
            rows.append(
                _envelope(
                    tenant_id=tenant_id, machine_id=machine_id, sensor=sensor,
                    value=value, t=t, now=now, circuit_id=circuit,
                )
            )

        # Fixed seed (not time-based) so every run of this script produces bit-for-bit
        # identical telemetry — required for a deterministic demo reset (Phase 36.6).
        # Real sensor noise, not a perfectly flat line: several downstream baseline/
        # deviation computations (`CONTEXTUAL_ASSET_BASELINE`, `RESERVOIR_TREND`, Phase 10's
        # `pressure.robust_deviation`) divide by a MAD computed from the healthy window — a
        # perfectly noiseless healthy signal makes that MAD exactly 0, which several real
        # bugs this session traced back to (a `distance == 0 or 1e9` sentinel, or the
        # feature simply being omitted as "no baseline" when MAD is at/under an epsilon).
        # Small, believable jitter keeps every baseline's MAD genuinely positive.
        _rng = random.Random(20260819)

        def jitter(value: float, magnitude: float) -> float:
            return value + _rng.uniform(-magnitude, magnitude)

        # --- 1. Healthy period (3h -> 40min ago): calm, stable evidence across every
        # channel — this is the "normal operation" the rest of the story departs from.
        steps = 130
        for i in range(steps):
            t = healthy_start + (restriction_start - healthy_start) * (i / steps)
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, reservoir_value(t), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(42.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.1, 0.03), t)

        # --- 2. Developing restriction (40min -> 10min ago): hydraulic evidence rises
        # first — pressure climbs — while bearing/vibration stay at their healthy baseline
        # (no bearing evidence yet). Deliberately a small number of points relative to the
        # healthy history above: `CONTEXTUAL_ASSET_BASELINE` aggregates *all* matching-
        # context telemetry for a sensor, not a bounded rolling window (ADR-171 in
        # TECHNICAL_DECISIONS.md), so a large anomalous fraction would dilute its own
        # comparison baseline instead of standing out against it — exactly like a real
        # just-developing condition would still be a minority of a machine's history.
        #
        # Pump current is deliberately kept flat (not also rising with pressure): this
        # topology has no FLOW sensor, so `check_restriction_pattern` (which requires
        # FLOW_BELOW_CONTEXTUAL_BASELINE) can never fire here, and a co-active
        # `PUMP_CURRENT_ABOVE_BASELINE` finding would vote a second, distinct
        # `PUMP_PERFORMANCE_DEGRADATION` hypothesis alongside pressure's
        # `DEVELOPING_RESTRICTION_PATTERN` vote — synthesis.py's step 5 currently reports
        # any 2+ *specific* hypotheses as `AMBIGUOUS_CONDITION` even when, as here, they are
        # physically compatible siblings of the same delivery-degradation family (unlike the
        # genuinely-exclusive restriction-vs-leakage case `test_conflicting_hypotheses_
        # produce_ambiguous_condition` correctly guards) — known limitation, ADR-172 in
        # TECHNICAL_DECISIONS.md, deliberately not fixed here.
        steps = 10
        for i in range(steps):
            frac = i / steps
            t = restriction_start + (bearing_effect_start - restriction_start) * frac
            add(pressure, jitter(9.0 + 15.0 * frac, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, reservoir_value(t), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(42.0 + 0.5 * frac, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.1 + 0.1 * frac, 0.03), t)

        # --- 3. Later bearing effect (10min ago -> now): restriction evidence persists
        # (pressure keeps climbing gently rather than plateauing — a still-developing
        # problem, not yet stabilized, so a state estimator sampling this window sees a
        # genuine rising trend right up to "now") AND a modest secondary bearing signal
        # appears — deliberately kept modest (not a dramatic independent spike) so this
        # reads as "possible secondary effect of sustained restriction," never as a
        # fabricated second unrelated fault. Pump current stays flat — see phase 2's
        # comment.
        steps = 6
        for i in range(steps):
            frac = i / steps
            t = bearing_effect_start + (now - bearing_effect_start) * frac
            add(pressure, jitter(22.0 + 2.5 * frac, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, reservoir_value(t), t)
            add(rpm, jitter(1450.0, 3.0), t)
            for b in bearing_temps:
                add(b, jitter(42.5 + 6.0 * frac, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.2 + 1.1 * frac, 0.03), t)

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(f"Seeded {len(rows)} telemetry rows for machine={machine_id}")

        all_sensor_ids = [pressure.id, pump_current.id, reservoir.id, rpm.id]
        all_sensor_ids += [b.id for b in bearing_temps]
        all_sensor_ids += [v.id for v in vibrations]

    # Eligibility is marked one sensor + one commit at a time, each with a small
    # retry-on-deadlock: the live `data-quality-worker` container is concurrently
    # upserting these same `sensor_quality_state` rows on its own schedule, and a single
    # multi-row transaction here can lock-order-deadlock against its own multi-row
    # transaction (`psycopg.errors.DeadlockDetected`, observed running this script twice
    # in quick succession). Committing per row keeps each transaction single-row, which
    # eliminates that whole deadlock class; the retry is defense-in-depth for the rare
    # remaining case where both sides still land on the exact same single row at once.
    async def _mark_eligible(sid: uuid.UUID) -> None:
        for attempt in range(3):
            try:
                async with database.session() as session:
                    await SensorQualityStateRepository(session).upsert(
                        tenant_id, sid, machine_id=machine_id,
                        quality_state=QualityState.TRUSTED, eligibility=Eligibility.ELIGIBLE,
                        policy_version="1",
                    )
                    await session.commit()
                return
            except OperationalError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

    for sid in all_sensor_ids:
        await _mark_eligible(sid)
    print(f"Marked {len(all_sensor_ids)} sensors ELIGIBLE")

    # --- Baselines from the healthy window (each call opens its own session/engine).
    for sid in all_sensor_ids:
        await backfill(tenant_id, sid, healthy_start, restriction_start)
        await backfill(tenant_id, sid, healthy_start, restriction_start)
    print("Built baselines from the healthy window")

    # Re-assert eligibility immediately before reprocessing (same race-avoidance
    # convention as verify_rules.sh — the live data-quality-worker keeps re-evaluating
    # these same sensors independently).
    for sid in all_sensor_ids:
        await _mark_eligible(sid)

    # `debounce.default: 3` in demo_rules_policy.yaml — a finding needs 3 *consecutive*
    # reprocess cycles before CANDIDATE is promoted to ACTIVE.
    for _ in range(3):
        await reprocess(tenant_id, machine_id, restriction_start, now)
    print("Reprocessed rules over the restriction window")

    # State estimation is inherently sequential (Phase 12 brief §17) — each tick's Kalman
    # posterior is built from the *previous* tick's posterior plus one new observation.
    # `StateEstimationService.compute_and_persist_latest()` only ever computes a single
    # "as of now" tick, which starting from a freshly-reset (empty) prior barely moves the
    # filter and never gives `state_rate` real information about a *trend* (an
    # `IMPROVING`/`DETERIORATING` classification needs the level to visibly change across
    # ticks with real elapsed time between them). To get a state estimate that actually
    # reflects this story's progression, replay several ticks across the restriction
    # window directly through the same building blocks that service uses internally
    # (`FeatureEngine.compute(as_of=...)` + `StateEstimator.step()` +
    # `StateEstimateRepository.persist()`), each one further into the developing
    # restriction than the last.
    try:
        state_config = load_state_estimation_config()
        feature_policy = load_feature_policy()

        async def _replay(state_type: str, as_of_times: tuple[datetime, ...]) -> int:
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
                    computed = await engine.compute(
                        tenant_id, machine_id, state_config.feature_set, as_of
                    )
                    tick = FeatureTick(
                        tenant_id=computed.tenant_id,
                        machine_id=computed.machine_id,
                        feature_vector_id=computed.feature_vector_id,
                        feature_set=computed.feature_set,
                        feature_set_version=computed.feature_set_version,
                        as_of_timestamp=computed.as_of_timestamp,
                        feature_values=computed.feature_values,
                        missing_features=computed.missing_features,
                        quality_state=str(
                            computed.quality_summary.get("state", "NO_TRUSTED_DATA")
                        ),
                    )
                    state_repo = StateEstimateRepository(session)
                    prior_row = await state_repo.get_latest(
                        tenant_id,
                        machine_id,
                        state_type,
                        state_config.estimator_version,
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

        # Each state type is replayed with its *own* tick schedule, not a shared one:
        # `LUBRICATION_DELIVERY_STATE`'s only rising channel (`pressure.robust_deviation`)
        # saturates almost immediately once pressure clears the healthy baseline's MAD
        # (`mad_scale: 6.0` in state_estimation_v1.yaml), then holds flat — replaying all
        # the way to "now" lets the filter settle back to a confident `STABLE` at that
        # plateau, which `condition_intelligence`'s synthesis correctly treats as
        # corroborating NORMAL_OPERATION (Phase 13 brief §13.8's tested "rules fault, one
        # source normal -> ambiguous" rule — a real, intentional design choice, not a bug;
        # ADR-172 in TECHNICAL_DECISIONS.md).
        # Stopping the replay while the filter is still *mid-rise* captures a genuine
        # `DETERIORATING` read instead. `BEARING_CONDITION_STATE`'s channels rise smoothly
        # across all of phase 3 without saturating early, so it replays all the way through.
        def _times(fracs: tuple[float, ...]) -> tuple[datetime, ...]:
            return tuple(healthy_start + (now - healthy_start) * frac for frac in fracs)

        lubrication_ticks = await _replay(
            "LUBRICATION_DELIVERY_STATE", _times((0.0, 0.6, 0.82, 0.84, 0.86))
        )
        bearing_ticks = await _replay(
            "BEARING_CONDITION_STATE", _times((0.0, 0.6, 0.9, 0.95, 1.0))
        )
        total_ticks = lubrication_ticks + bearing_ticks
        print(f"Computed {total_ticks} state estimate ticks across the story window")
    except Exception as exc:  # noqa: BLE001 - best-effort for this demo story
        print(
            f"State estimation skipped ({exc}) — "
            "condition/decision still work from rule evidence alone"
        )

    async with database.session() as session:
        incidents = IncidentService(session)
        incident = await incidents.evaluate_machine(tenant_id, machine_id)
        await session.commit()
        if incident is None:
            print("No incident created — condition evidence did not warrant one this run")
            return
        print(
            f"Incident: {incident.id} "
            f"({incident.incident_type.value}, {incident.severity.value})"
        )

        await incidents.acknowledge(tenant_id, incident.id)
        await incidents.start_investigation(tenant_id, incident.id)
        await session.commit()

        maintenance = MaintenanceService(session)
        case = await maintenance.create_case_for_incident(tenant_id, incident.id)
        await maintenance.plan(tenant_id, case.id, planned_for=None)
        await maintenance.start(tenant_id, case.id)
        await session.commit()
        print(f"Maintenance case: {case.id} ({case.recommended_action.value})")

        await maintenance.record_finding(
            tenant_id,
            case.id,
            result=TechnicianFindingResult.PARTIALLY_CONFIRMED,
            component="distributor",
            observed_issue=(
                "Elevated main-line pressure and pump current consistent with a "
                "developing restriction; distributor outlet showed partial blockage. "
                "Bearing temperature/vibration on the driven bearing were slightly "
                "elevated, consistent with sustained restriction rather than an "
                "independent bearing fault."
            ),
            notes="Confirmed on-site inspection of the distributor outlet.",
            technician_identifier="demo-technician",
        )
        await maintenance.record_action(
            tenant_id,
            case.id,
            action_type=MaintenanceActionType.CLEANED,
            notes=(
                "Cleared partial blockage at the distributor outlet; verified free flow "
                "before closing out."
            ),
            recorded_by="demo-technician",
        )
        await session.commit()

    # --- Recovery (real telemetry, real re-evaluation) ------------------------------
    # `MaintenanceService.complete()` runs a *fresh* post-action condition re-check
    # (Phase 17 brief §17.8) and always resolves the incident on the technician's
    # classification regardless of what that re-check finds — it does not fabricate a
    # "fixed" outcome. Without new evidence, that re-check would still see the same
    # elevated pressure/bearing/vibration readings and report "Developing Restriction
    # Pattern" right next to a RESOLVED incident — technically honest (the automated
    # assessment legitimately lags a human's real-world confirmation until new telemetry
    # arrives) but a confusing, incomplete story for a reviewer. The flagship story is
    # supposed to end in a real OUTCOME, not just an ACTION (CLAUDE.md's
    # DATA -> ... -> ACTION -> OUTCOME -> LEARNING arc) — so seed a short recovery phase
    # showing the cleared distributor's real effect (pressure/bearing/vibration tapering
    # back to their healthy baseline) *before* completing the case, so the fresh
    # post-action re-check genuinely finds NORMAL_OPERATION.
    recovery_end = datetime.now(UTC)
    recovery_rows: list[dict[str, object]] = []

    def add_recovery(
        sensor: Sensor, value: float, t: datetime, *, circuit: uuid.UUID | None = None
    ) -> None:
        recovery_rows.append(
            _envelope(
                tenant_id=tenant_id, machine_id=machine_id, sensor=sensor,
                value=value, t=t, now=recovery_end, circuit_id=circuit,
            )
        )

    recovery_steps = 10
    for i in range(recovery_steps):
        # (i+1)/steps, never 0.0 — the first point must postdate phase 3's own last
        # point (exactly at `now`), not collide with it.
        frac = (i + 1) / recovery_steps
        t = now + (recovery_end - now) * frac
        add_recovery(pressure, jitter(24.5 - 15.5 * frac, 0.15), t, circuit=circuit_id)
        add_recovery(pump_current, jitter(3.0, 0.05), t)
        add_recovery(reservoir, reservoir_value(now), t)
        add_recovery(rpm, jitter(1450.0, 3.0), t)
        for b in bearing_temps:
            add_recovery(b, jitter(48.5 - 6.5 * frac, 0.15), t)
        for v in vibrations:
            add_recovery(v, jitter(3.3 - 1.2 * frac, 0.03), t)

    async with database.session() as session:
        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(recovery_rows)
        await session.commit()
    print(f"Seeded {len(recovery_rows)} recovery telemetry rows (cleared blockage)")

    for _ in range(3):
        await reprocess(tenant_id, machine_id, now, recovery_end)
    print("Reprocessed rules over the recovery window")

    # The main story's own replay leaves each filter confidently (LOW uncertainty)
    # committed to a strong uphill trend — reversing that through observations alone
    # takes many more consecutive "already recovered" ticks than is practical here
    # (empirically: even several back-loaded recovery ticks were not reliably enough to
    # flip `trend` away from `DETERIORATING`). A real technician's confirmed fix is a
    # legitimate recalibration point: reset each filter to a fresh prior (`prior=None`,
    # matching a machine seeing its first-ever observation) before replaying the
    # recovered telemetry, rather than fighting the old filter's entrenched momentum.
    async with database.session() as session:
        await session.execute(
            delete(StateEstimate).where(
                StateEstimate.tenant_id == tenant_id,
                StateEstimate.machine_id == machine_id,
            )
        )
        await session.commit()

    recovery_replay_times = tuple(
        now + (recovery_end - now) * frac for frac in (0.7, 0.8, 0.88, 0.94, 0.98, 1.0)
    )
    try:
        await _replay("LUBRICATION_DELIVERY_STATE", recovery_replay_times)
        await _replay("BEARING_CONDITION_STATE", recovery_replay_times)
    except Exception as exc:  # noqa: BLE001 - best-effort for this demo story
        print(f"Recovery state estimation skipped ({exc})")

    async with database.session() as session:
        maintenance = MaintenanceService(session)
        await maintenance.complete(
            tenant_id,
            case.id,
            classification=FeedbackClassification.TRUE_POSITIVE,
            confirmed_component="distributor",
            confirmed_finding="Partial blockage at the distributor outlet, cleared.",
            notes="Machine returned to normal operating condition after the blockage was cleared.",
            recorded_by="demo-technician",
        )
        await session.commit()
        print(f"Maintenance case {case.id} completed with TRUE_POSITIVE feedback")

    await database.dispose()
    print("")
    print(
        f"Flagship story complete: machine_id={machine_id} "
        f"incident_id={incident.id} case_id={case.id}"
    )
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
