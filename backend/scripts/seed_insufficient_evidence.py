"""Demo scenario — a freshly commissioned, not-yet-enough-evidence asset
(docs/HOSTED_DEPLOYMENT.md "10 meaningful synthetic scenarios" pass). Seeds Secondary
Crusher CR-202 (`L1-7F84-M017`, the `lubrisense-demo` tenant) with only a handful of
telemetry readings per
sensor — deliberately fewer than `demo_rules_policy.yaml`'s `min_sample_count: 5` — so no
rule can fire and no baseline can be built. This is the ONE deliberate example in this demo
fleet of a real `INSUFFICIENT_EVIDENCE` condition (`app.condition_intelligence.services.
condition_engine`), not a data-quality/trust problem (that story belongs to
`seed_data_quality_issue.py`): every sensor here is marked TRUSTED/ELIGIBLE, there just
isn't enough history yet to say anything.

No incident is expected (`IncidentService.evaluate_machine` never opens one for
`INSUFFICIENT_EVIDENCE` — Phase 16 brief §16.11) — this script only drives a single real
`DecisionEngine.decide_for_machine()` call (via `evaluate_machine`) so a real
`ConditionAssessment`/`DecisionAssessment` pair is persisted for the fleet-wide views to
pick up.

    uv run python scripts/seed_insufficient_evidence.py

Safe to re-run: deletes and rebuilds only this one machine's own telemetry/state estimates
first (ADR-173) before reseeding the same small sample.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.domain.enums import Eligibility, QualityState
from app.domain.models import Sensor
from app.incidents.services.incident_service import IncidentService
from app.infrastructure.database import Database
from app.repositories.telemetry import TelemetryRepository
from scripts._scenario_seed_common import (
    envelope,
    mark_sensor_quality,
    reset_machine_data,
    resolve_machine,
)

ASSET_CODE = "L1-7F84-M017"
DEVICE_ID = "insufficient-evidence-seed"

# Below `min_sample_count: 5` (demo_rules_policy.yaml) — the whole point of this scenario.
SAMPLE_COUNT = 3


async def main() -> None:
    settings = get_settings()
    database = Database(settings)
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=12)

    async with database.session() as session:
        base = await resolve_machine(session, ASSET_CODE)
        tenant_id, machine_id, circuit_id = base.tenant_id, base.machine_id, base.circuit_id
        by_type = base.by_type

        pressure = by_type["PRESSURE"][0]
        pump_current = by_type["PUMP_CURRENT"][0]
        reservoir = by_type["RESERVOIR_LEVEL"][0]
        rpm = by_type["RPM"][0]
        bearing_temps = by_type["BEARING_TEMPERATURE"]
        vibrations = by_type["VIBRATION_RMS"]
        # Lubrication Efficiency Intelligence, Pass 1
        # (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176) — CR-202 is this
        # capability's representative commissioning/insufficient-history case: real power
        # telemetry exists (and is trusted), but — like every other sensor here — no
        # `backfill()` is ever called for it, so no baseline can be resolved and its
        # energy assessment reads `INSUFFICIENT_BASELINE`, the same honest "not enough
        # history yet" story this whole scenario already tells for every other signal.
        power = by_type["MACHINE_POWER"][0]

        await reset_machine_data(session, tenant_id, machine_id)

        rng = random.Random(20260821109)

        def jitter(value: float, magnitude: float) -> float:
            return value + rng.uniform(-magnitude, magnitude)

        rows: list[dict[str, object]] = []

        def add(
            sensor: Sensor, value: float, t: datetime, *, circuit: uuid.UUID | None = None
        ) -> None:
            rows.append(
                envelope(
                    tenant_id=tenant_id,
                    machine_id=machine_id,
                    sensor=sensor,
                    value=value,
                    t=t,
                    now=now,
                    circuit_id=circuit,
                    device_id=DEVICE_ID,
                )
            )

        # Just a handful of plausible-looking readings — commissioning has only just
        # started, no history to judge anything against yet.
        for i in range(SAMPLE_COUNT):
            t = window_start + (now - window_start) * (i / max(SAMPLE_COUNT - 1, 1))
            add(pressure, jitter(9.0, 0.15), t, circuit=circuit_id)
            add(pump_current, jitter(3.0, 0.05), t)
            add(reservoir, jitter(55.0, 0.1), t)
            add(rpm, jitter(1450.0, 3.0), t)
            add(power, jitter(15.0, 0.4), t)
            for b in bearing_temps:
                add(b, jitter(41.0, 0.15), t)
            for v in vibrations:
                add(v, jitter(2.0, 0.03), t)

        repo = TelemetryRepository(session)
        await repo.batch_insert_idempotent(rows)
        await session.commit()
        print(
            f"Seeded {len(rows)} telemetry rows ({SAMPLE_COUNT} samples/sensor) "
            f"for machine={machine_id}"
        )

        all_sensor_ids = [pressure.id, pump_current.id, reservoir.id, rpm.id, power.id]
        all_sensor_ids += [b.id for b in bearing_temps]
        all_sensor_ids += [v.id for v in vibrations]

    # Trusted/eligible sensors — the limiting factor here is sample count, not sensor
    # trust (that's the separate data-quality scenario).
    for sid in all_sensor_ids:
        await mark_sensor_quality(
            database,
            tenant_id,
            machine_id,
            sid,
            quality_state=QualityState.TRUSTED,
            eligibility=Eligibility.ELIGIBLE,
            last_observed_at=now,
        )
    print(f"Marked {len(all_sensor_ids)} sensors ELIGIBLE (no baseline built — too few samples)")

    async with database.session() as session:
        incidents = IncidentService(session)
        incident = await incidents.evaluate_machine(tenant_id, machine_id)
        await session.commit()
        if incident is not None:
            print(
                f"Unexpected incident created ({incident.incident_type.value}) — "
                "evidence was not as sparse as intended."
            )
        else:
            print("No incident created, as expected — insufficient evidence to warrant one.")

    await database.dispose()
    print("")
    print(f"Insufficient-evidence story complete: machine_id={machine_id}")
    print(f"View at: http://localhost:3000/machines/{machine_id}")


if __name__ == "__main__":
    asyncio.run(main())
