"""One deterministic, idempotent seed path for the public hosted demo
(docs/HOSTED_DEPLOYMENT.md).

Runs the existing base-hierarchy, knowledge-corpus, flagship-story, and
healthy-comparison-machine seed scripts in sequence, then the eight release-pass scenario
scripts (each a real telemetry -> baseline -> rule-finding -> condition -> [decision ->
incident -> maintenance] chain through the actual backend services, never fabricated
frontend data — see each script's own module docstring for its specific evidence story),
then adds the two pieces of hosted-demo context none of those already cover — a CMMS draft
and a device/configuration snapshot on the flagship's completed maintenance case — through
the real `CMMSService`/`DeviceConfigurationService`, never a hardcoded API response.

    uv run python scripts/seed_hosted_demo.py

Every step here is independently idempotent; running the whole thing again fully resets
and rebuilds each scenario machine's own data and is safe to repeat. This script seeds; it
does not expose an HTTP endpoint — there is no public reset route (see
docs/HOSTED_DEPLOYMENT.md "No public reset endpoint").
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

import scripts.seed_active_restriction as seed_active_restriction
import scripts.seed_bearing_degradation as seed_bearing_degradation
import scripts.seed_data_quality_issue as seed_data_quality_issue
import scripts.seed_demo_data as seed_demo_data
import scripts.seed_flagship_story as seed_flagship_story
import scripts.seed_healthy_machine as seed_healthy_machine
import scripts.seed_insufficient_evidence as seed_insufficient_evidence
import scripts.seed_knowledge_corpus as seed_knowledge_corpus
import scripts.seed_leakage as seed_leakage
import scripts.seed_low_reservoir as seed_low_reservoir
import scripts.seed_pump_degradation as seed_pump_degradation
import scripts.seed_recovering_asset as seed_recovering_asset
from app.audit.service import AuditActor
from app.cmms.services.cmms_service import CMMSService, CMMSUnavailableError
from app.core.config import get_settings
from app.device_management.service import DeviceConfigurationService
from app.domain.enums import DeviceType, IncidentState
from app.domain.models import Gateway, Incident, MaintenanceCase, Tenant
from app.infrastructure.database import Database


async def _seed_flagship_extras() -> None:
    """CMMS draft + device/configuration snapshot for the flagship's most recently
    completed maintenance case — real service calls, draft-only/visibility-only exactly
    like the interactive "Create CMMS draft" button and Phase 31 commissioning flow."""
    settings = get_settings()
    database = Database(settings)
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()

        incident = (
            (
                await session.execute(
                    select(Incident)
                    .where(
                        Incident.tenant_id == tenant.id,
                        Incident.state == IncidentState.RESOLVED,
                    )
                    .order_by(Incident.first_detected_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if incident is None:
            print("No resolved incident found yet — run seed_flagship_story.py first.")
            return

        case = (
            (
                await session.execute(
                    select(MaintenanceCase)
                    .where(
                        MaintenanceCase.tenant_id == tenant.id,
                        MaintenanceCase.incident_id == incident.id,
                    )
                    .order_by(MaintenanceCase.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if case is None:
            print("No maintenance case found for the latest resolved incident.")
            return

        cmms = CMMSService(session)
        try:
            record = await cmms.create_draft(tenant.id, case.id)
            print(f"CMMS draft: {record.external_reference} ({record.status})")
        except CMMSUnavailableError as exc:
            print(f"CMMS draft skipped ({exc})")
        await session.commit()

        gateway = (
            (
                await session.execute(
                    select(Gateway).where(
                        Gateway.tenant_id == tenant.id,
                        Gateway.gateway_code == seed_flagship_story.GATEWAY_CODE,
                    )
                )
            )
            .scalars()
            .first()
        )
        if gateway is not None:
            devices = DeviceConfigurationService(session)
            await devices.capture_snapshot(
                tenant.id,
                machine_id=incident.machine_id,
                device_type=DeviceType.GATEWAY,
                device_id=gateway.id,
                config={
                    "sampling_interval_seconds": 5,
                    "unit": "bar",
                    "reporting_mode": "periodic",
                },
                firmware_version=gateway.firmware_version,
                actor=AuditActor.system("hosted-demo-seed"),
                reason="Gateway sampling configuration captured during commissioning.",
                source="hosted-demo-seed",
            )
            await session.commit()
            print(f"Device/configuration snapshot captured for gateway {gateway.gateway_code}")
        else:
            print(
                f"Gateway {seed_flagship_story.GATEWAY_CODE} not found — "
                "skipping device context."
            )

    await database.dispose()


async def main() -> None:
    print("=== 1/13 Base asset hierarchy ===")
    await seed_demo_data.main()

    print("\n=== 2/13 Approved knowledge corpus ===")
    await seed_knowledge_corpus.main()

    print("\n=== 3/13 Flagship machine story (resolved) ===")
    await seed_flagship_story.main()

    print("\n=== 4/13 Healthy comparison machine ===")
    await seed_healthy_machine.main()

    print("\n=== 5/13 Active developing-restriction incident ===")
    await seed_active_restriction.main()

    print("\n=== 6/13 Leakage incident ===")
    await seed_leakage.main()

    print("\n=== 7/13 Low-reservoir supply-risk incident ===")
    await seed_low_reservoir.main()

    print("\n=== 8/13 Pump-degradation incident ===")
    await seed_pump_degradation.main()

    print("\n=== 9/13 Bearing-condition incident ===")
    await seed_bearing_degradation.main()

    print("\n=== 10/13 Data-quality-limited machine ===")
    await seed_data_quality_issue.main()

    print("\n=== 11/13 Recently maintained / recovering machine ===")
    await seed_recovering_asset.main()

    print("\n=== 12/13 Insufficient-evidence machine ===")
    await seed_insufficient_evidence.main()

    print("\n=== 13/13 CMMS draft + device/configuration context ===")
    await _seed_flagship_extras()

    print("\nHosted demo seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
