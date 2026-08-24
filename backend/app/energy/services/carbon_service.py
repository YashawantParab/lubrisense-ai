"""Carbon-impact-estimate orchestration (Lubrication Efficiency Intelligence, Pass 4 —
docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §10-§11, ADR-176). Consumes only a *qualified*
`EnergyOutcomeVerification` (Pass 3) and an explicit, provenance-carrying
`SiteEmissionFactor` — never manufactures an energy benefit, never substitutes a default
factor.

**Non-circularity / no-side-effects boundary**: read-only with respect to
`EnergyOutcomeVerification`, `LubricationEnergyAttribution`, Condition Intelligence, and
Decision Intelligence. This service never writes to any of those tables; carbon failure
(`NOT_ELIGIBLE`/`FACTOR_NOT_CONFIGURED`/`FACTOR_NOT_APPLICABLE`) never mutates or
invalidates the energy outcome it read.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import CarbonImpactEstimate, Machine, Plant, ProductionLine
from app.energy.domain.carbon import (
    POLICY_VERSION,
    CarbonEligibilityInput,
    EmissionFactorSnapshot,
    evaluate_carbon,
)
from app.energy.repositories.carbon_estimate_repository import CarbonEstimateRepository
from app.energy.repositories.emission_factor_repository import SiteEmissionFactorRepository
from app.energy.repositories.energy_outcome_repository import EnergyOutcomeRepository


class CarbonOutcomeNotFoundError(LookupError):
    """No `EnergyOutcomeVerification` exists with this id (for this tenant) — Pass 3's
    `EnergyOutcomeService.assess_machine` must run first and produce a real row."""


class CarbonSiteNotResolvedError(LookupError):
    """The machine's `production_line -> plant -> site` chain did not resolve — every
    `Machine` NOT NULL-requires this chain by construction (asset-hierarchy invariant,
    CLAUDE.md "Prevent: orphaned assets"), so this indicates a genuine data-integrity
    problem elsewhere, never a normal "not configured yet" case."""


class CarbonService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._outcomes = EnergyOutcomeRepository(session)
        self._factors = SiteEmissionFactorRepository(session)
        self._estimates = CarbonEstimateRepository(session)

    async def _resolve_site_id(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = (
            select(Plant.site_id)
            .join(ProductionLine, ProductionLine.plant_id == Plant.id)
            .join(Machine, Machine.production_line_id == ProductionLine.id)
            .where(Plant.tenant_id == tenant_id, Machine.id == machine_id)
        )
        result: uuid.UUID | None = await self._session.scalar(stmt)
        return result

    async def assess_for_outcome(
        self, tenant_id: uuid.UUID, energy_outcome_verification_id: uuid.UUID
    ) -> CarbonImpactEstimate:
        outcome = await self._outcomes.get(tenant_id, energy_outcome_verification_id)
        if outcome is None:
            raise CarbonOutcomeNotFoundError(str(energy_outcome_verification_id))
        machine_id = outcome.machine_id

        site_id = await self._resolve_site_id(tenant_id, machine_id)
        if site_id is None:
            raise CarbonSiteNotResolvedError(str(machine_id))

        factor_row = None
        if site_id is not None:
            factor_row = await self._factors.active_for_site(tenant_id, site_id)

        factor_snapshot = (
            EmissionFactorSnapshot(
                id=str(factor_row.id),
                factor_value=factor_row.factor_value,
                factor_unit=factor_row.factor_unit,
                method=factor_row.method,
                source_name=factor_row.source_name,
                source_reference=factor_row.source_reference,
                jurisdiction=factor_row.jurisdiction,
                effective_from=factor_row.effective_from,
                effective_to=factor_row.effective_to,
                is_active=factor_row.is_active,
            )
            if factor_row is not None
            else None
        )

        result = evaluate_carbon(
            CarbonEligibilityInput(
                qualified_avoided_energy_kwh=outcome.estimated_avoided_energy_kwh,
                observed_period_start=outcome.post_window_start,
                observed_period_end=outcome.post_window_end,
                factor=factor_snapshot,
                comparison_confidence_is_high=outcome.comparison_confidence.value == "HIGH",
            )
        )

        provenance: dict[str, object] = {}
        if factor_row is not None:
            provenance = {
                "source_name": factor_row.source_name,
                "source_reference": factor_row.source_reference,
                "jurisdiction": factor_row.jurisdiction,
                "effective_from": factor_row.effective_from.isoformat(),
                "effective_to": (
                    factor_row.effective_to.isoformat() if factor_row.effective_to else None
                ),
                "provenance": factor_row.provenance.value,
            }

        estimate = CarbonImpactEstimate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            site_id=site_id,
            machine_id=machine_id,
            energy_outcome_verification_id=outcome.id,
            emission_factor_id=factor_row.id if factor_row is not None else None,
            observed_period_start=outcome.post_window_start,
            observed_period_end=outcome.post_window_end,
            qualified_avoided_energy_kwh=outcome.estimated_avoided_energy_kwh,
            emission_factor_value=factor_row.factor_value if factor_row is not None else None,
            emission_factor_unit=factor_row.factor_unit if factor_row is not None else None,
            method=factor_row.method if factor_row is not None else None,
            estimated_co2e_kg=result.estimated_co2e_kg,
            estimate_status=result.status,
            limitations=list(result.limitations),
            provenance=provenance,
            policy_version=POLICY_VERSION,
        )
        await self._estimates.insert(estimate)
        await self._session.commit()
        return estimate
