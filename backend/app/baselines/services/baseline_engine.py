"""`BaselineEngine` — the per-sensor (and, for cycle-level baselines, per-machine)
refresh orchestrator (Phase 8 brief §2/§28). Consumes only persisted Phase 6 telemetry plus
Phase 7 quality output — never re-runs the simulator (brief §6) and never imports it.

Called by both the live worker (`app.baselines.workers.worker`, recent-window refresh) and
the historical backfill CLI (`app.baselines.workers.backfill`, an explicit start/end range)
— the same method serves both (brief §28's "simple architecture that supports both live and
historical operation").
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import BaselineContext, TelemetrySample
from app.baselines.domain.context import context_key as _context_key
from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.baselines.services.promotion import UpdateAction, decide
from app.baselines.strategies.contextual import compute_contextual_baselines
from app.baselines.strategies.cycle import compute_machine_cycle_baseline
from app.baselines.strategies.reservoir import compute_reservoir_baseline
from app.baselines.strategies.rolling import compute_rolling_baseline
from app.baselines.strategies.static_reference import build_engineering_reference
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import (
    BaselineMetricKind,
    BaselineState,
    BaselineStrategyType,
    Eligibility,
    SensorType,
    TelemetryQuality,
)
from app.domain.models import BaselineProfile, Sensor, Telemetry
from app.repositories.telemetry import TelemetryRepository

_TELEMETRY_QUERY_LIMIT = 5000
_NEVER_SECONDS = 1e10


class BaselineEngine:
    def __init__(self, session: AsyncSession, policy: BaselinePolicy) -> None:
        self.session = session
        self.policy = policy
        self._profile_repo = BaselineProfileRepository(session)
        self._telemetry_repo = TelemetryRepository(session)
        self._quality_state_repo = SensorQualityStateRepository(session)

    async def refresh_sensor(
        self,
        tenant_id: uuid.UUID,
        sensor: Sensor,
        now: datetime,
        *,
        window_override: tuple[datetime, datetime] | None = None,
    ) -> None:
        """Refreshes every profile lineage applicable to one sensor: STATIC_ENGINEERING_REFERENCE
        (always ensured), ROLLING_ASSET_BASELINE (always), CONTEXTUAL_ASSET_BASELINE (if
        `BaselinePolicy.is_contextual`), RESERVOIR_LEVEL's RESERVOIR_TREND variant (if
        `BaselinePolicy.is_reservoir_trend`). `window_override` lets the backfill CLI
        (`app.baselines.workers.backfill`) evaluate an explicit historical range instead of
        "now minus the configured rolling window"."""
        measurement_type = sensor.sensor_type.value

        latest = await self._telemetry_repo.get_latest_by_sensor(tenant_id, sensor.id)
        # `Telemetry.machine_id` is resolved once by Phase 6's `ContextEnrichmentService`
        # for every attachment type (a sensor need not attach directly to `machine` —
        # docs/ASSET_HIERARCHY.md's six attachment types), so it is the authoritative
        # source once any telemetry exists; `BaselineProfile.machine_id` is denormalized
        # convenience for querying, not correctness-critical, so `None` before any
        # telemetry has ever arrived is an acceptable, self-correcting starting state.
        machine_id = latest.machine_id if latest else None
        firmware_version = latest.firmware_version if latest else None
        controller_version = latest.controller_version if latest else None

        await self._ensure_static_reference(tenant_id, sensor, machine_id, measurement_type, now)

        quality_state = await self._quality_state_repo.get(tenant_id, sensor.id)
        eligibility = quality_state.eligibility if quality_state else Eligibility.ELIGIBLE
        caution = eligibility == Eligibility.ELIGIBLE_WITH_CAUTION

        if window_override is not None:
            window_start, window_end = window_override
        else:
            window_seconds = self.policy.rolling_window_seconds_for(measurement_type)
            window_start, window_end = now - timedelta(seconds=window_seconds), now

        samples: list[TelemetrySample] = []
        if eligibility != Eligibility.INELIGIBLE:
            rows = await self._telemetry_repo.get_by_sensor_time_range(
                tenant_id,
                sensor.id,
                start=window_start,
                end=window_end,
                measurement_type=sensor.sensor_type,
                limit=_TELEMETRY_QUERY_LIMIT,
            )
            samples = [_to_sample(r, caution) for r in rows if r.quality == TelemetryQuality.GOOD]

        window_seconds_for_profile = (window_end - window_start).total_seconds()

        rolling_stats = compute_rolling_baseline(samples)
        await self._apply_measurement(
            tenant_id=tenant_id,
            sensor_id=sensor.id,
            machine_id=machine_id,
            measurement_type=measurement_type,
            strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
            context_key_value="",
            context_dict={},
            metric_kind=BaselineMetricKind.STANDARD,
            new_stats=rolling_stats.to_dict() if rolling_stats else None,
            new_sample_count=rolling_stats.count if rolling_stats else len(samples),
            window_start=window_start,
            window_end=window_end,
            window_seconds=window_seconds_for_profile,
            firmware_version=firmware_version,
            controller_version=controller_version,
            quality_policy_version=quality_state.policy_version if quality_state else None,
            now=now,
        )

        if self.policy.is_reservoir_trend(measurement_type):
            # Own context_key ("trend"), distinct from the plain rolling distribution
            # above — both are stored (brief §24: "do not use ONLY symmetric bands" does
            # not forbid keeping the raw distribution as supplementary context alongside
            # the trend), distinguished by `metric_kind` as well as `context_key`.
            trend_stats = compute_reservoir_baseline(samples)
            await self._apply_measurement(
                tenant_id=tenant_id,
                sensor_id=sensor.id,
                machine_id=machine_id,
                measurement_type=measurement_type,
                strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
                context_key_value="trend",
                context_dict={"metric": "trend"},
                metric_kind=BaselineMetricKind.RESERVOIR_TREND,
                new_stats=trend_stats.to_dict() if trend_stats else None,
                new_sample_count=trend_stats.sample_count if trend_stats else len(samples),
                window_start=window_start,
                window_end=window_end,
                window_seconds=window_seconds_for_profile,
                firmware_version=firmware_version,
                controller_version=controller_version,
                quality_policy_version=quality_state.policy_version if quality_state else None,
                now=now,
            )

        if self.policy.is_contextual(measurement_type):
            per_context = compute_contextual_baselines(samples, measurement_type, self.policy)
            for context, stats in per_context.items():
                await self._apply_measurement(
                    tenant_id=tenant_id,
                    sensor_id=sensor.id,
                    machine_id=machine_id,
                    measurement_type=measurement_type,
                    strategy=BaselineStrategyType.CONTEXTUAL_ASSET_BASELINE,
                    context_key_value=_context_key(context),
                    context_dict={
                        "operating_state": context.operating_state,
                        "cycle_phase": context.cycle_phase,
                    },
                    metric_kind=BaselineMetricKind.STANDARD,
                    new_stats=stats.to_dict(),
                    new_sample_count=stats.count,
                    window_start=window_start,
                    window_end=window_end,
                    window_seconds=window_seconds_for_profile,
                    firmware_version=firmware_version,
                    controller_version=controller_version,
                    quality_policy_version=quality_state.policy_version if quality_state else None,
                    now=now,
                )

    async def refresh_machine_cycle(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        now: datetime,
        *,
        window_override: tuple[datetime, datetime] | None = None,
    ) -> None:
        """Cycle-level baseline (brief §25) — machine-scoped, not sensor-scoped (a
        lubrication cycle belongs to the pump/circuit as a whole). Recorded against one
        deterministically chosen representative `PRESSURE` sensor on the machine (lowest
        `sensor_id`), mirroring Phase 7's `COMMUNICATION_LOSS` precedent
        (`app.data_quality.services.window_evaluator.evaluate_machine_communication`) for
        the same reason: `BaselineProfile.sensor_id` is NOT NULL, and `machine_id` is the
        real column to query/filter this profile by, not `sensor_id`."""
        if window_override is not None:
            window_start, window_end = window_override
        else:
            window_seconds = self.policy.rolling_window_seconds_for("PRESSURE")
            window_start, window_end = now - timedelta(seconds=window_seconds), now

        pressure_rows = await self._telemetry_repo.get_by_machine_time_range(
            tenant_id,
            machine_id,
            start=window_start,
            end=window_end,
            measurement_type=SensorType.PRESSURE,
            limit=_TELEMETRY_QUERY_LIMIT,
        )
        if not pressure_rows:
            return
        completion_rows = await self._telemetry_repo.get_by_machine_time_range(
            tenant_id,
            machine_id,
            start=window_start,
            end=window_end,
            measurement_type=SensorType.CYCLE_COMPLETION,
            limit=_TELEMETRY_QUERY_LIMIT,
        )

        pressure_samples = await self._gated_samples(tenant_id, pressure_rows)
        completion_samples = await self._gated_samples(tenant_id, completion_rows)

        stats = compute_machine_cycle_baseline(pressure_samples, completion_samples, self.policy)
        representative_sensor_id = min(r.sensor_id for r in pressure_rows)
        latest = max(pressure_rows, key=lambda r: r.source_timestamp)

        await self._apply_measurement(
            tenant_id=tenant_id,
            sensor_id=representative_sensor_id,
            machine_id=machine_id,
            measurement_type="PRESSURE",
            strategy=BaselineStrategyType.ROLLING_ASSET_BASELINE,
            context_key_value="cycle",
            context_dict={"metric": "cycle"},
            metric_kind=BaselineMetricKind.CYCLE_METRIC,
            new_stats=stats.to_dict() if stats else None,
            new_sample_count=stats.cycle_count if stats else 0,
            window_start=window_start,
            window_end=window_end,
            window_seconds=(window_end - window_start).total_seconds(),
            firmware_version=latest.firmware_version,
            controller_version=latest.controller_version,
            quality_policy_version=None,
            now=now,
        )

    async def _gated_samples(
        self, tenant_id: uuid.UUID, rows: list[Telemetry]
    ) -> list[TelemetrySample]:
        """Quality-gates a mixed-sensor row set (used by `refresh_machine_cycle`, where
        `rows` may span more than one physical sensor) — own-reading `GOOD` quality plus
        each row's *own* sensor's current eligibility, batched to one
        `SensorQualityState` lookup per distinct sensor rather than per row."""
        sensor_ids = {r.sensor_id for r in rows}
        eligibility_by_sensor: dict[uuid.UUID, Eligibility] = {}
        caution_by_sensor: dict[uuid.UUID, bool] = {}
        for sensor_id in sensor_ids:
            state = await self._quality_state_repo.get(tenant_id, sensor_id)
            eligibility = state.eligibility if state else Eligibility.ELIGIBLE
            eligibility_by_sensor[sensor_id] = eligibility
            caution_by_sensor[sensor_id] = eligibility == Eligibility.ELIGIBLE_WITH_CAUTION
        return [
            _to_sample(r, caution_by_sensor[r.sensor_id])
            for r in rows
            if r.quality == TelemetryQuality.GOOD
            and eligibility_by_sensor[r.sensor_id] != Eligibility.INELIGIBLE
        ]

    async def _ensure_static_reference(
        self,
        tenant_id: uuid.UUID,
        sensor: Sensor,
        machine_id: uuid.UUID | None,
        measurement_type: str,
        now: datetime,
    ) -> None:
        context_key_value = _context_key(BaselineContext())
        existing = await self._profile_repo.get_current(
            tenant_id,
            sensor.id,
            BaselineStrategyType.STATIC_ENGINEERING_REFERENCE,
            context_key_value,
        )
        if existing is not None:
            return
        stats = build_engineering_reference(measurement_type, self.policy)
        if stats is None:
            return
        await self._profile_repo.create_initial(
            tenant_id=tenant_id,
            sensor_id=sensor.id,
            machine_id=machine_id,
            measurement_type=measurement_type,
            strategy=BaselineStrategyType.STATIC_ENGINEERING_REFERENCE,
            metric_kind=BaselineMetricKind.STANDARD,
            context_key=context_key_value,
            context={},
            state=BaselineState.ACTIVE,
            statistics=stats.to_dict(),
            sample_count=0,
            min_sample_required=0,
            window_start=None,
            window_end=None,
            window_seconds=0.0,
            config_version=self.policy.policy_version,
            activated_at=now,
            last_evaluated_at=now,
            # A large finite sentinel, not `float("inf")` — `inf` is not valid JSON and
            # would break API serialization the moment this row is ever returned. The
            # static reference never needs refreshing/staleness-checking (it is
            # config-derived, not learned), so "practically never" is all this needs to
            # express; ~317 years is simply "never" at any real operational timescale.
            refresh_interval_seconds=_NEVER_SECONDS,
            stale_after_seconds=_NEVER_SECONDS,
        )

    async def _apply_measurement(
        self,
        *,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        machine_id: uuid.UUID | None,
        measurement_type: str,
        strategy: BaselineStrategyType,
        context_key_value: str,
        context_dict: dict[str, Any],
        metric_kind: BaselineMetricKind,
        new_stats: dict[str, Any] | None,
        new_sample_count: int,
        window_start: datetime,
        window_end: datetime,
        window_seconds: float,
        firmware_version: str | None,
        controller_version: str | None,
        quality_policy_version: str | None,
        now: datetime,
    ) -> None:
        min_sample_required = self.policy.min_sample_count_for(measurement_type)
        refresh_interval = self.policy.refresh_interval_seconds_for(measurement_type)
        stale_after = self.policy.stale_after_seconds_for(measurement_type)

        current = await self._profile_repo.get_current(
            tenant_id, sensor_id, strategy, context_key_value
        )

        current = await self._apply_config_change_check(
            current, firmware_version, controller_version, now
        )

        decision = decide(
            row_exists=current is not None,
            row_state=current.state if current else None,
            row_statistics=current.statistics if current else None,
            row_candidate_statistics=current.candidate_statistics if current else None,
            row_candidate_stable_cycles=current.candidate_stable_cycles if current else 0,
            new_stats=new_stats,
            new_sample_count=new_sample_count,
            min_sample_required=min_sample_required,
            metric_kind=metric_kind,
            stability_gate=self.policy.stability_gate,
        )

        base_fields: dict[str, Any] = {
            "tenant_id": tenant_id,
            "sensor_id": sensor_id,
            "machine_id": machine_id,
            "measurement_type": measurement_type,
            "strategy": strategy,
            "metric_kind": metric_kind,
            "context_key": context_key_value,
            "context": context_dict,
            "min_sample_required": min_sample_required,
            "window_seconds": window_seconds,
            "config_version": self.policy.policy_version,
            "quality_policy_version": quality_policy_version,
            "refresh_interval_seconds": refresh_interval,
            "stale_after_seconds": stale_after,
            "firmware_version": firmware_version,
            "controller_version": controller_version,
        }

        if decision.action == UpdateAction.CREATE_INSUFFICIENT:
            await self._profile_repo.create_initial(
                **base_fields,
                state=BaselineState.INSUFFICIENT_DATA,
                statistics=None,
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                last_evaluated_at=now,
            )
            return

        if current is None:
            # `decide()` can return START_CANDIDATE with `row_exists=False` (e.g. right
            # after `_apply_config_change_check` invalidated the prior row this same
            # cycle) — a fresh generation starts directly in BUILDING with the candidate
            # already seeded, rather than a separate INSUFFICIENT_DATA row first.
            assert decision.action == UpdateAction.START_CANDIDATE  # noqa: S101
            await self._profile_repo.create_initial(
                **base_fields,
                state=BaselineState.BUILDING,
                statistics=None,
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                candidate_statistics=new_stats,
                candidate_sample_count=new_sample_count,
                candidate_window_start=window_start,
                candidate_window_end=window_end,
                candidate_first_seen_at=now,
                candidate_stable_cycles=1,
                last_evaluated_at=now,
            )
            return

        if decision.action == UpdateAction.FREEZE:
            await self._profile_repo.update_in_place(
                current.id,
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                last_evaluated_at=now,
            )
        elif decision.action == UpdateAction.START_CANDIDATE:
            await self._profile_repo.update_in_place(
                current.id,
                state=BaselineState.BUILDING
                if current.state == BaselineState.INSUFFICIENT_DATA
                else current.state,
                candidate_statistics=new_stats,
                candidate_sample_count=new_sample_count,
                candidate_window_start=window_start,
                candidate_window_end=window_end,
                candidate_first_seen_at=now,
                candidate_stable_cycles=1,
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                last_evaluated_at=now,
            )
        elif decision.action == UpdateAction.ADVANCE_CANDIDATE:
            await self._profile_repo.update_in_place(
                current.id,
                candidate_statistics=new_stats,
                candidate_sample_count=new_sample_count,
                candidate_window_start=window_start,
                candidate_window_end=window_end,
                candidate_stable_cycles=decision.candidate_stable_cycles,
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                last_evaluated_at=now,
            )
        elif decision.action == UpdateAction.ACTIVATE:
            await self._profile_repo.update_in_place(
                current.id,
                state=BaselineState.ACTIVE,
                statistics=new_stats,
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                candidate_statistics=None,
                candidate_sample_count=None,
                candidate_window_start=None,
                candidate_window_end=None,
                candidate_stable_cycles=0,
                activated_at=now,
                last_evaluated_at=now,
            )
        elif decision.action == UpdateAction.REFINE_ACTIVE:
            await self._profile_repo.update_in_place(
                current.id,
                state=BaselineState.ACTIVE,
                statistics=new_stats,
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                candidate_statistics=None,
                candidate_sample_count=None,
                candidate_stable_cycles=0,
                last_evaluated_at=now,
            )
        elif decision.action == UpdateAction.PROMOTE:
            await self._profile_repo.promote(
                current,
                statistics=new_stats or {},
                sample_count=new_sample_count,
                window_start=window_start,
                window_end=window_end,
                now=now,
            )

    async def _apply_config_change_check(
        self,
        current: BaselineProfile | None,
        firmware_version: str | None,
        controller_version: str | None,
        now: datetime,
    ) -> BaselineProfile | None:
        """Firmware/config-change awareness (brief §17/§18): if either identity marker
        materially changed since this lineage's current row was last stamped, the pre-change
        row is invalidated (if it ever reached ACTIVE/STALE — nothing to invalidate for a
        still-`BUILDING` row) and a fresh generation begins, so pre-/post-change behavior is
        never blended into one baseline."""
        if current is None:
            return None
        changed = (
            current.firmware_version is not None
            and firmware_version is not None
            and current.firmware_version != firmware_version
        ) or (
            current.controller_version is not None
            and controller_version is not None
            and current.controller_version != controller_version
        )
        if not changed:
            return current
        if current.state in (BaselineState.ACTIVE, BaselineState.STALE):
            await self._profile_repo.invalidate(
                current.id,
                reason=(
                    f"firmware/controller version changed "
                    f"({current.firmware_version!r} -> {firmware_version!r}, "
                    f"{current.controller_version!r} -> {controller_version!r})"
                ),
                now=now,
            )
        return None


def _to_sample(row: Telemetry, caution: bool) -> TelemetrySample:
    return TelemetrySample(
        event_id=row.event_id,
        sensor_id=row.sensor_id,
        source_timestamp=row.source_timestamp,
        value=row.value,
        operating_state=row.operating_state,
        quality=row.quality.value,
        eligible=True,
        caution=caution,
    )
