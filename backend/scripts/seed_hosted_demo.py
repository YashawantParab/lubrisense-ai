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
from app.domain.models import Gateway, Incident, Machine, MaintenanceCase, Tenant
from app.features.config.policy import load_feature_policy
from app.infrastructure.database import Database
from app.ml.services.ml_inference_service import (
    MLInferenceOrchestrationService,
    MLMachineNotFoundError,
    MLModelNotAvailableError,
)

#: Every curated demo machine (Phase 37+ "10 representative scenarios") EXCEPT Secondary
#: Crusher CR-202, keyed by the same `asset_code` each individual scenario script already
#: resolves its machine by. Secondary Crusher CR-202 (`L1-7F84-M017`) is deliberately
#: excluded: it is the one intentional INSUFFICIENT_EVIDENCE story
#: (`seed_insufficient_evidence.py` — 3 telemetry samples/sensor, below
#: `min_sample_count`), and scoring it anyway produces real but meaningless ML output (the
#: minimum-required-features check only cares whether a value is present, not whether 3
#: samples is a statistically reasonable basis for a classification). Worse, an
#: `MLInferenceResult` existing at all — even at EXPERIMENTAL, non-voting strength — is
#: enough to make `synthesize()`'s "was anything checked" gate treat the machine as
#: evaluated, flipping it from INSUFFICIENT_EVIDENCE to NORMAL_OPERATION and silently
#: destroying the one curated example of "no reliable ML inference" this fleet is supposed
#: to demonstrate (verified empirically). Adding an eleventh curated machine later means
#: adding its asset_code here too, nothing else.
_CURATED_ASSET_CODES = (
    "L1-7B43-M000",  # Ore Transfer Conveyor CV-101 — flagship, resolved restriction
    "L1-7B43-M001",  # Rotary Kiln Drive KILN-01 — healthy
    "L2-07A8-M012",  # Stacker-Reclaimer SR-201 — active restriction
    "L1-07A8-M009",  # Ball Mill BM-301 — leakage
    "L1-E915-M005",  # Primary Gyratory Crusher CR-101 — low reservoir
    "L2-7B43-M004",  # Rolling Mill Stand RM-401 — pump degradation
    "L2-E915-M008",  # Kiln ID Fan IDF-01 — bearing condition
    "L1-95FA-M013",  # Apron Feeder AF-101 — data-quality limited
    "L1-7F84-M016",  # Bucket Elevator BE-201 — recovering
)

_ML_MODEL_IDS = (
    "LUBRICATION_ANOMALY_V1",
    "FAILURE_CLASSIFICATION_V1",
    "FAILURE_CLASSIFICATION_BASELINE_V1",
)


async def _seed_ml_evidence() -> None:
    """Real inference, run through the same `MLInferenceOrchestrationService` the live
    `/ml/machines/{id}/latest` API endpoint uses — never a handwritten prediction. Every
    curated machine gets scored against every registered model; a genuinely-insufficient
    feature vector (e.g. Apron Feeder AF-101's data-quality-blocked bearing sensors, or
    Secondary Crusher CR-202's handful of samples) legitimately produces an
    `INSUFFICIENT_FEATURES` result rather than
    a forced one — that is the honest outcome for those machines, not a failure to seed.
    `MLModelNotAvailableError` is only possible here if a model_id is unregistered
    entirely, which would be a real configuration problem worth surfacing, not swallowing.

    Deliberately does NOT re-run `ConditionEngine.assess()` after scoring — tried that
    empirically and it actively breaks the curated portfolio: `FAILURE_CLASSIFICATION_V1`
    generalizes poorly to this demo's synthetic telemetry (it predicts SENSOR_FAULT for
    nearly every curated machine, contradicting each scenario's real rule-based diagnosis),
    and feeding that conflicting evidence back into synthesis flips most machines to
    AMBIGUOUS_CONDITION. Every earlier step's `ConditionAssessment` therefore predates the
    `MLInferenceResult` rows this step persists — the Machine ML Analysis page's "Evidence
    fusion" section already states this honestly ("the assessment ran before this
    inference") rather than silently claiming ML influenced a decision it didn't."""
    settings = get_settings()
    database = Database(settings)
    policy = load_feature_policy()
    scored = 0
    insufficient = 0
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()
        service = MLInferenceOrchestrationService(session, policy)
        for asset_code in _CURATED_ASSET_CODES:
            machine = (
                await session.execute(
                    select(Machine).where(
                        Machine.tenant_id == tenant.id, Machine.asset_code == asset_code
                    )
                )
            ).scalar_one_or_none()
            if machine is None:
                print(f"  {asset_code}: machine not found — skipping")
                continue
            for model_id in _ML_MODEL_IDS:
                try:
                    result = await service.compute_and_persist_latest(
                        tenant.id, machine.id, model_id
                    )
                except MLMachineNotFoundError:
                    print(f"  {asset_code} / {model_id}: machine not found — skipping")
                    continue
                except MLModelNotAvailableError as exc:
                    print(f"  {asset_code} / {model_id}: unavailable ({exc})")
                    continue
                if result.status.value == "INSUFFICIENT_FEATURES":
                    insufficient += 1
                    print(f"  {machine.name} / {model_id}: insufficient features")
                else:
                    scored += 1
                    headline = (
                        f"anomaly_score={result.anomaly_score:.3f}"
                        if result.result_kind.value == "ANOMALY"
                        else f"predicted_class={result.predicted_class}"
                    )
                    print(f"  {machine.name} / {model_id}: {result.status.value} ({headline})")
    await database.dispose()
    print(f"ML evidence: {scored} scored, {insufficient} insufficient-features")


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
    print("=== 1/14 Base asset hierarchy ===")
    await seed_demo_data.main()

    print("\n=== 2/14 Approved knowledge corpus ===")
    await seed_knowledge_corpus.main()

    print("\n=== 3/14 Flagship machine story (resolved) ===")
    await seed_flagship_story.main()

    print("\n=== 4/14 Healthy comparison machine ===")
    await seed_healthy_machine.main()

    print("\n=== 5/14 Active developing-restriction incident ===")
    await seed_active_restriction.main()

    print("\n=== 6/14 Leakage incident ===")
    await seed_leakage.main()

    print("\n=== 7/14 Low-reservoir supply-risk incident ===")
    await seed_low_reservoir.main()

    print("\n=== 8/14 Pump-degradation incident ===")
    await seed_pump_degradation.main()

    print("\n=== 9/14 Bearing-condition incident ===")
    await seed_bearing_degradation.main()

    print("\n=== 10/14 Data-quality-limited machine ===")
    await seed_data_quality_issue.main()

    print("\n=== 11/14 Recently maintained / recovering machine ===")
    await seed_recovering_asset.main()

    print("\n=== 12/14 Insufficient-evidence machine ===")
    await seed_insufficient_evidence.main()

    print("\n=== 13/14 CMMS draft + device/configuration context ===")
    await _seed_flagship_extras()

    print("\n=== 14/14 ML evidence for the curated fleet ===")
    await _seed_ml_evidence()

    print("\nHosted demo seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
