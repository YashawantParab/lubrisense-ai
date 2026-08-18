from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.models import CustomerAccount, Plant, ProductionLine, Site
from app.repositories.base import TenantScopedRepository


class CustomerAccountRepository(TenantScopedRepository[CustomerAccount]):
    model = CustomerAccount

    async def get_by_code(self, tenant_id: uuid.UUID, code: str) -> CustomerAccount | None:
        stmt = select(CustomerAccount).where(
            CustomerAccount.tenant_id == tenant_id, CustomerAccount.code == code
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_with_full_hierarchy(self, tenant_id: uuid.UUID) -> list[CustomerAccount]:
        """Customer -> Site -> Plant -> ProductionLine -> Machine, eager-loaded in a fixed
        number of queries (selectinload issues one extra query per level, not one per
        row) — see TECHNICAL_DECISIONS.md (hierarchy query/loading strategy ADR) and
        docs/ASSET_HIERARCHY.md §"Performance" for why this shape scales to the demo
        dataset size and how it would need to change at fleet scale.
        """
        stmt = (
            select(CustomerAccount)
            .where(CustomerAccount.tenant_id == tenant_id)
            .order_by(CustomerAccount.created_at)
            .options(
                selectinload(CustomerAccount.sites)
                .selectinload(Site.plants)
                .selectinload(Plant.production_lines)
                .selectinload(ProductionLine.machines)
            )
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
