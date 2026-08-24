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
import re
from datetime import UTC, datetime, timedelta

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
from app.baselines.config.policy import load_baseline_policy
from app.cmms.services.cmms_service import CMMSService, CMMSUnavailableError
from app.core.config import get_settings
from app.device_management.service import DeviceConfigurationService
from app.domain.enums import DeviceType, EmissionFactorMethod, IncidentState, MetricProvenance
from app.domain.models import Gateway, Incident, Machine, MaintenanceCase, Site, Tenant
from app.energy.services.attribution_service import (
    AttributionEnergyAssessmentNotFoundError,
    AttributionMachineNotFoundError,
    AttributionService,
)
from app.energy.services.carbon_service import (
    CarbonOutcomeNotFoundError,
    CarbonService,
    CarbonSiteNotResolvedError,
)
from app.energy.services.emission_factor_service import EmissionFactorService
from app.energy.services.energy_assessment_service import (
    EnergyAssessmentService,
    EnergyMachineNotFoundError,
    EnergyPowerSensorNotFoundError,
)
from app.energy.services.energy_outcome_query_service import EnergyOutcomeQueryService
from app.energy.services.energy_outcome_service import (
    EnergyOutcomeMachineNotFoundError,
    EnergyOutcomeNoInterventionError,
    EnergyOutcomeNoPowerSensorError,
    EnergyOutcomeService,
)
from app.features.config.policy import load_feature_policy
from app.infrastructure.database import Database
from app.ml.services.ml_inference_service import (
    MLInferenceOrchestrationService,
    MLMachineNotFoundError,
    MLModelNotAvailableError,
)
from scripts._scenario_seed_common import delete_machine_fully

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

#: Every asset code `seed_demo_data.seed_machine()` ever mints — curated fleet and
#: background hierarchy alike — follows this exact algorithmic shape:
#: `f"{line_code}-{plant_id.hex[:4].upper()}-M{index:03d}"` where `line_code` is
#: `f"L{line_offset + 1}"` (`seed_demo_data.py`). A machine whose asset_code does NOT match
#: this pattern was never created by any seed script — it came from a human-typed
#: commissioning-wizard session (`app/commissioning/service.py`'s `start_session` takes a
#: caller-supplied `asset_code`) or a stray pytest run against this database
#: (`tests/factories.py`'s `unique("ASSET")` produces `ASSET-<hex>`, never this shape).
#: This is the safe, deterministic way to identify debris asked for in the hosted-scenario
#: integrity pass — it never depends on a human-typed *name* like "Test Machine-..." or
#: "Demo Wizard Motor", which a future stray session could easily not repeat.
_SEED_GENERATED_ASSET_CODE = re.compile(r"^L\d+-[0-9A-F]{4}-M\d{3,}$")


async def _delete_debris_machines() -> None:
    """Removes every machine under the canonical demo tenant that no seed script created
    (see `_SEED_GENERATED_ASSET_CODE` above) — manual commissioning-wizard test machines,
    stray pytest fixtures, anything else. Runs immediately after the base hierarchy step
    (so the canonical tenant and its full legitimate curated+background machine set are
    guaranteed to already exist) and before every scenario script, so a clean reseed
    always converges to exactly the seed-generated hierarchy with no accumulation across
    repeated runs. Deliberately scoped to
    ONE tenant (the canonical demo tenant) and to an asset_code *shape*, never a broad
    delete — this must never touch another tenant's data (e.g. the thousands of isolated
    per-test tenants a misconfigured pytest run can leave behind elsewhere in this
    database are a separate, much larger CI-hygiene issue, out of scope here, and
    untouched by this tenant-scoped query)."""
    settings = get_settings()
    database = Database(settings)
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()
        machines = (
            (await session.execute(select(Machine).where(Machine.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        debris = [m for m in machines if not _SEED_GENERATED_ASSET_CODE.match(m.asset_code)]
        if not debris:
            print("  no debris machines found")
        for machine in debris:
            print(f"  deleting debris machine: {machine.name!r} ({machine.asset_code})")
            await delete_machine_fully(session, tenant.id, machine.id)
    await database.dispose()


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


#: Secondary Crusher CR-202 is deliberately excluded from `_CURATED_ASSET_CODES` (see the
#: comment on that tuple) because ML evidence existing at all changes what
#: `ConditionEngine.assess()`'s own "was anything checked" gate sees for that machine.
#: `EnergyAssessment` carries no equivalent risk — this pass never wires it into
#: `ConditionEngine`/`synthesize()` at all (see `app.energy.domain.evidence`'s own
#: docstring), so CR-202 is included here on its own: it is this capability's
#: representative "commissioning / insufficient baseline history" case
#: (docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md), and skipping it would silently drop the
#: one curated example of `INSUFFICIENT_BASELINE`.
_ENERGY_ASSET_CODES = _CURATED_ASSET_CODES + ("L1-7F84-M017",)  # + Secondary Crusher CR-202


async def _seed_energy_assessments() -> None:
    """Real on-demand assessment, run through the same `EnergyAssessmentService` the live
    `/energy/machines/{id}/latest` API endpoint uses (Lubrication Efficiency
    Intelligence, Pass 1 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Every
    curated machine is assessed; a machine with no power telemetry yet honestly reads
    `INSUFFICIENT_DATA` rather than being skipped — see the design doc's representative
    -machine list for which of these are expected to show a real deviation."""
    settings = get_settings()
    database = Database(settings)
    baseline_policy = load_baseline_policy()
    by_status: dict[str, int] = {}
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()
        service = EnergyAssessmentService(session, baseline_policy)
        for asset_code in _ENERGY_ASSET_CODES:
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
            try:
                result = await service.assess_machine(tenant.id, machine.id)
            except EnergyMachineNotFoundError:
                print(f"  {asset_code}: machine not found — skipping")
                continue
            except EnergyPowerSensorNotFoundError:
                print(f"  {machine.name}: no machine-power sensor commissioned — skipping")
                continue
            by_status[result.status.value] = by_status.get(result.status.value, 0) + 1
            headline = (
                f"actual={result.actual_power_kw:.1f}kW expected={result.expected_power_kw:.1f}kW "
                f"residual={result.residual_pct:+.1f}%"
                if result.actual_power_kw is not None and result.expected_power_kw is not None
                else f"actual={result.actual_power_kw}"
            )
            print(f"  {machine.name}: {result.status.value} ({headline})")
    await database.dispose()
    summary = ", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
    print(f"Energy assessments: {summary}")


async def _seed_attribution_assessments() -> None:
    """Real deterministic-policy assessment, run through the same `AttributionService`
    the live `/energy/machines/{id}/attribution/latest` API endpoint uses (Lubrication
    Efficiency Intelligence, Pass 2 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md,
    ADR-176). Runs after `_seed_energy_assessments` in the same `main()` sequence, since
    every attribution requires a real, already-persisted `EnergyAssessment` to attribute
    against. Every curated machine (same set as energy assessments) is assessed; a
    machine with no energy assessment yet is honestly skipped, not forced."""
    settings = get_settings()
    database = Database(settings)
    by_level: dict[str, int] = {}
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()
        service = AttributionService(session)
        for asset_code in _ENERGY_ASSET_CODES:
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
            try:
                result = await service.assess_machine(tenant.id, machine.id)
            except AttributionMachineNotFoundError:
                print(f"  {asset_code}: machine not found — skipping")
                continue
            except AttributionEnergyAssessmentNotFoundError:
                print(f"  {machine.name}: no energy assessment yet — skipping")
                continue
            by_level[result.attribution_level.value] = (
                by_level.get(result.attribution_level.value, 0) + 1
            )
            print(f"  {machine.name}: {result.attribution_level.value}")
    await database.dispose()
    summary = ", ".join(f"{count} {level}" for level, count in sorted(by_level.items()))
    print(f"Lubrication-energy attribution: {summary}")


async def _seed_energy_outcomes() -> None:
    """Real deterministic-policy verification, run through the same
    `EnergyOutcomeService` the live `/energy/machines/{id}/outcomes/latest` API endpoint
    uses (Lubrication Efficiency Intelligence, Pass 3 —
    docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Every curated machine is
    attempted; a machine with no completed maintenance intervention yet (an active energy
    opportunity, not yet an outcome) or no power sensor is honestly skipped, not forced —
    see the design doc's verification matrix for which curated machines are expected to
    produce which outcome."""
    settings = get_settings()
    database = Database(settings)
    baseline_policy = load_baseline_policy()
    by_status: dict[str, int] = {}
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()
        service = EnergyOutcomeService(session, baseline_policy)
        for asset_code in _ENERGY_ASSET_CODES:
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
            try:
                result = await service.assess_machine(tenant.id, machine.id)
            except EnergyOutcomeMachineNotFoundError:
                print(f"  {asset_code}: machine not found — skipping")
                continue
            except EnergyOutcomeNoInterventionError:
                print(f"  {machine.name}: no completed maintenance intervention yet — skipping")
                continue
            except EnergyOutcomeNoPowerSensorError:
                print(f"  {machine.name}: no machine-power sensor commissioned — skipping")
                continue
            by_status[result.energy_outcome_status.value] = (
                by_status.get(result.energy_outcome_status.value, 0) + 1
            )
            avoided = (
                f", avoided≈{result.estimated_avoided_energy_kwh:.1f}kWh"
                if result.estimated_avoided_energy_kwh is not None
                else ""
            )
            print(
                f"  {machine.name}: {result.energy_outcome_status.value} "
                f"({result.comparability_status.value}{avoided})"
            )
    await database.dispose()
    summary = ", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
    print(f"Energy outcome verification: {summary}")


#: Every site the curated fleet actually spans (Lubrication Efficiency Intelligence, Pass
#: 4 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md, ADR-176). Configuring a demo factor
#: for all four (not just BE-201's own EASTGATE) exercises the config API across the real
#: portfolio, not one hand-picked machine.
_CURATED_SITE_CODES = ("RIDGE", "EASTGATE", "HARBOR", "MILLBROOK")

#: A single plausible, neutral, clearly-labelled illustrative value — not any real
#: jurisdiction's actual published grid-average factor. See `SiteEmissionFactor
#: .provenance` (`MetricProvenance.DEMO_ESTIMATE`) and `source_name` below for the
#: explicit synthetic-data disclosure this number carries end-to-end.
_DEMO_FACTOR_KG_CO2E_PER_KWH = 0.40


async def _seed_emission_factors() -> None:
    """Configures one active `SiteEmissionFactor` per curated site — never a hardcoded
    default inside application logic (`app.energy.domain.carbon` refuses to estimate
    without one). `effective_from` is set far enough in the past that it safely covers
    any curated machine's real `EnergyOutcomeVerification` observed period."""
    settings = get_settings()
    database = Database(settings)
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()
        service = EmissionFactorService(session)
        effective_from = datetime.now(UTC) - timedelta(days=365)
        for site_code in _CURATED_SITE_CODES:
            site = (
                await session.execute(
                    select(Site).where(Site.tenant_id == tenant.id, Site.code == site_code)
                )
            ).scalar_one_or_none()
            if site is None:
                print(f"  {site_code}: site not found — skipping")
                continue
            factor = await service.configure(
                tenant.id,
                site.id,
                factor_value=_DEMO_FACTOR_KG_CO2E_PER_KWH,
                source_name="Illustrative demonstration factor (not an audited grid dataset)",
                source_reference=None,
                jurisdiction="Demo region",
                provenance=MetricProvenance.DEMO_ESTIMATE,
                method=EmissionFactorMethod.LOCATION_BASED,
                effective_from=effective_from,
            )
            print(f"  {site.name}: {factor.factor_value} {factor.factor_unit} (DEMO_ESTIMATE)")
    await database.dispose()


async def _seed_carbon_estimates() -> None:
    """Real deterministic-policy estimation, run through the same `CarbonService` the
    live `/energy/outcomes/{id}/carbon` API endpoint uses. Only machines with an already
    -persisted `EnergyOutcomeVerification` (this run's step 18) are attempted; a machine
    with none yet is honestly skipped — carbon is strictly downstream of a real energy
    outcome, never computed independently of one."""
    settings = get_settings()
    database = Database(settings)
    by_status: dict[str, int] = {}
    async with database.session() as session:
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == seed_flagship_story.DEMO_TENANT_SLUG)
            )
        ).scalar_one()
        outcome_query = EnergyOutcomeQueryService(session)
        service = CarbonService(session)
        for asset_code in _ENERGY_ASSET_CODES:
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
            outcome = await outcome_query.latest(tenant.id, machine.id)
            if outcome is None:
                print(f"  {machine.name}: no energy outcome verification yet — skipping")
                continue
            try:
                result = await service.assess_for_outcome(tenant.id, outcome.id)
            except CarbonOutcomeNotFoundError:
                print(f"  {machine.name}: energy outcome verification not found — skipping")
                continue
            except CarbonSiteNotResolvedError:
                print(f"  {machine.name}: site could not be resolved — skipping")
                continue
            by_status[result.estimate_status.value] = (
                by_status.get(result.estimate_status.value, 0) + 1
            )
            co2e = (
                f", {result.estimated_co2e_kg:.2f}kg CO2e"
                if result.estimated_co2e_kg is not None
                else ""
            )
            print(f"  {machine.name}: {result.estimate_status.value}{co2e}")
    await database.dispose()
    summary = ", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
    print(f"Carbon impact estimation: {summary}")


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
    print("=== 1/20 Base asset hierarchy ===")
    await seed_demo_data.main()

    print("\n=== 2/20 Clean non-canonical debris machines ===")
    await _delete_debris_machines()

    print("\n=== 3/20 Approved knowledge corpus ===")
    await seed_knowledge_corpus.main()

    print("\n=== 4/20 Flagship machine story (resolved) ===")
    await seed_flagship_story.main()

    print("\n=== 5/20 Healthy comparison machine ===")
    await seed_healthy_machine.main()

    print("\n=== 6/20 Active developing-restriction incident ===")
    await seed_active_restriction.main()

    print("\n=== 7/20 Leakage incident ===")
    await seed_leakage.main()

    print("\n=== 8/20 Low-reservoir supply-risk incident ===")
    await seed_low_reservoir.main()

    print("\n=== 9/20 Pump-degradation incident ===")
    await seed_pump_degradation.main()

    print("\n=== 10/20 Bearing-condition incident ===")
    await seed_bearing_degradation.main()

    print("\n=== 11/20 Data-quality-limited machine ===")
    await seed_data_quality_issue.main()

    print("\n=== 12/20 Recently maintained / recovering machine ===")
    await seed_recovering_asset.main()

    print("\n=== 13/20 Insufficient-evidence machine ===")
    await seed_insufficient_evidence.main()

    print("\n=== 14/20 CMMS draft + device/configuration context ===")
    await _seed_flagship_extras()

    print("\n=== 15/20 ML evidence for the curated fleet ===")
    await _seed_ml_evidence()

    print("\n=== 16/20 Energy assessments for the curated fleet ===")
    await _seed_energy_assessments()

    print("\n=== 17/20 Lubrication-energy attribution for the curated fleet ===")
    await _seed_attribution_assessments()

    print("\n=== 18/20 Energy outcome verification for the curated fleet ===")
    await _seed_energy_outcomes()

    print("\n=== 19/20 Site emission factors (carbon intelligence) ===")
    await _seed_emission_factors()

    print("\n=== 20/20 Carbon impact estimation for the curated fleet ===")
    await _seed_carbon_estimates()

    print("\nHosted demo seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
