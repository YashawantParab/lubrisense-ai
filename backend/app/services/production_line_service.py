from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Criticality, OperationalStatus
from app.domain.models import ProductionLine
from app.repositories.pagination import Page, PageParams
from app.repositories.plant import PlantRepository
from app.repositories.production_line import ProductionLineRepository
from app.services.errors import ConflictError, InvalidHierarchyError, NotFoundError


@dataclass(frozen=True)
class ProductionLineCreate:
    plant_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    status: OperationalStatus = OperationalStatus.ACTIVE
    criticality: Criticality = Criticality.MEDIUM
    metadata_: dict[str, Any] | None = None


class ProductionLineService:
    def __init__(self, session: AsyncSession) -> None:
        self._lines = ProductionLineRepository(session)
        self._plants = PlantRepository(session)

    async def create(self, tenant_id: uuid.UUID, data: ProductionLineCreate) -> ProductionLine:
        plant = await self._plants.get(tenant_id, data.plant_id)
        if plant is None:
            raise InvalidHierarchyError(
                "PLANT_NOT_FOUND_FOR_PRODUCTION_LINE",
                "plant_id does not reference a plant in this tenant.",
            )
        if plant.status == OperationalStatus.DECOMMISSIONED:
            raise InvalidHierarchyError(
                "PLANT_DECOMMISSIONED", "Cannot add a production line to a decommissioned plant."
            )
        existing = await self._lines.get_by_code(tenant_id, data.plant_id, data.code)
        if existing is not None:
            raise ConflictError(
                "PRODUCTION_LINE_CODE_TAKEN",
                f"A production line with code '{data.code}' already exists in this plant.",
            )
        line = ProductionLine(
            tenant_id=tenant_id,
            plant_id=data.plant_id,
            name=data.name,
            code=data.code,
            description=data.description,
            status=data.status,
            criticality=data.criticality,
            metadata_=data.metadata_ or {},
        )
        return await self._lines.add(line)

    async def get(self, tenant_id: uuid.UUID, production_line_id: uuid.UUID) -> ProductionLine:
        line = await self._lines.get(tenant_id, production_line_id)
        if line is None:
            raise NotFoundError("PRODUCTION_LINE_NOT_FOUND", "Production line not found.")
        return line

    async def list(
        self, tenant_id: uuid.UUID, *, params: PageParams | None = None
    ) -> Page[ProductionLine]:
        return await self._lines.list(tenant_id, params=params)
