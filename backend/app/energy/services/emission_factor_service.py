"""Site emission-factor configuration service (Lubrication Efficiency Intelligence, Pass
4 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §10, ADR-176). A small, explicit
tenant/site-scoped configuration surface — deliberately not a generic settings table:
every field here exists because `app.energy.domain.carbon` actually reads it.

Audit logging for configuration writes happens at the API layer (`app.api.v1.energy`),
mirroring `app.api.v1.maintenance`'s own `_audit_case` convention — this service performs
no audit writes itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EmissionFactorMethod, MetricProvenance
from app.domain.models import SiteEmissionFactor
from app.energy.repositories.emission_factor_repository import SiteEmissionFactorRepository
from app.repositories.site import SiteRepository


class EmissionFactorSiteNotFoundError(LookupError):
    pass


class EmissionFactorInvalidError(ValueError):
    pass


class EmissionFactorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sites = SiteRepository(session)
        self._factors = SiteEmissionFactorRepository(session)

    async def get_active(
        self, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> SiteEmissionFactor | None:
        if await self._sites.get(tenant_id, site_id) is None:
            raise EmissionFactorSiteNotFoundError(str(site_id))
        return await self._factors.active_for_site(tenant_id, site_id)

    async def configure(
        self,
        tenant_id: uuid.UUID,
        site_id: uuid.UUID,
        *,
        factor_value: float,
        source_name: str,
        source_reference: str | None,
        jurisdiction: str | None,
        provenance: MetricProvenance,
        method: EmissionFactorMethod = EmissionFactorMethod.LOCATION_BASED,
        effective_from: datetime | None = None,
    ) -> SiteEmissionFactor:
        """Deactivates any currently-active factor for this site and inserts a fresh row
        — never mutates a prior factor's `factor_value` in place (auditability; see
        `SiteEmissionFactor`'s own docstring)."""
        if await self._sites.get(tenant_id, site_id) is None:
            raise EmissionFactorSiteNotFoundError(str(site_id))
        if not (factor_value > 0):
            raise EmissionFactorInvalidError("factor_value must be a positive number.")

        now = datetime.now(UTC)
        await self._factors.deactivate_active_for_site(tenant_id, site_id, as_of=now)

        factor = SiteEmissionFactor(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            site_id=site_id,
            factor_type="ELECTRICITY",
            factor_value=factor_value,
            factor_unit="kg_co2e_per_kwh",
            method=method,
            source_name=source_name,
            source_reference=source_reference,
            jurisdiction=jurisdiction,
            effective_from=effective_from or now,
            effective_to=None,
            published_at=now,
            is_active=True,
            provenance=provenance,
        )
        await self._factors.insert(factor)
        await self._session.commit()
        return factor
