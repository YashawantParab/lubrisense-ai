from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import OperationalStatus
from app.domain.models import Plant
from app.repositories.pagination import Page, PageParams
from app.repositories.plant import PlantRepository
from app.repositories.site import SiteRepository
from app.services.errors import ConflictError, InvalidHierarchyError, NotFoundError


@dataclass(frozen=True)
class PlantCreate:
    site_id: uuid.UUID
    name: str
    code: str
    plant_type: str | None = None
    status: OperationalStatus = OperationalStatus.ACTIVE
    metadata_: dict[str, Any] | None = None


class PlantService:
    def __init__(self, session: AsyncSession) -> None:
        self._plants = PlantRepository(session)
        self._sites = SiteRepository(session)

    async def create(self, tenant_id: uuid.UUID, data: PlantCreate) -> Plant:
        site = await self._sites.get(tenant_id, data.site_id)
        if site is None:
            raise InvalidHierarchyError(
                "SITE_NOT_FOUND_FOR_PLANT", "site_id does not reference a site in this tenant."
            )
        if site.status == OperationalStatus.DECOMMISSIONED:
            raise InvalidHierarchyError(
                "SITE_DECOMMISSIONED", "Cannot add a plant to a decommissioned site."
            )
        existing = await self._plants.get_by_code(tenant_id, data.code)
        if existing is not None:
            raise ConflictError(
                "PLANT_CODE_TAKEN",
                f"A plant with code '{data.code}' already exists for this tenant.",
            )
        plant = Plant(
            tenant_id=tenant_id,
            site_id=data.site_id,
            name=data.name,
            code=data.code,
            plant_type=data.plant_type,
            status=data.status,
            metadata_=data.metadata_ or {},
        )
        return await self._plants.add(plant)

    async def get(self, tenant_id: uuid.UUID, plant_id: uuid.UUID) -> Plant:
        plant = await self._plants.get(tenant_id, plant_id)
        if plant is None:
            raise NotFoundError("PLANT_NOT_FOUND", "Plant not found.")
        return plant

    async def list(self, tenant_id: uuid.UUID, *, params: PageParams | None = None) -> Page[Plant]:
        return await self._plants.list(tenant_id, params=params)
