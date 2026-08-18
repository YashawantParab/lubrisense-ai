"""Generic tenant-scoped repository base.

Every repository in this package inherits from `TenantScopedRepository` instead of
hand-rolling the same get/list/create boilerplate twelve times — see
TECHNICAL_DECISIONS.md (domain-vs-ORM-separation / repository-layer ADR). Subclasses add
only the entity-specific lookups (e.g. `get_by_code`) that a generic base cannot express.

Every query is scoped by `tenant_id` in the `WHERE` clause. This is defense in depth on
top of the composite-tenant-foreign-key schema (app.domain.mixins): even if a caller
somehow obtained an `id` belonging to another tenant, no repository method will return or
mutate that row without the matching `tenant_id`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import ColumnExpressionArgument, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.pagination import Page, PageParams

ModelT = TypeVar("ModelT")


class TenantScopedRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.tenant_id == tenant_id,  # type: ignore[attr-defined]
            self.model.id == entity_id,  # type: ignore[attr-defined]
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        params: PageParams | None = None,
        filters: Sequence[ColumnExpressionArgument[bool]] = (),
    ) -> Page[ModelT]:
        params = params or PageParams()
        where_clauses: list[Any] = [self.model.tenant_id == tenant_id, *filters]  # type: ignore[attr-defined]

        total = await self.session.scalar(
            select(func.count()).select_from(self.model).where(*where_clauses)
        )

        stmt = (
            select(self.model)
            .where(*where_clauses)
            .order_by(self.model.created_at)  # type: ignore[attr-defined]
            .limit(params.limit)
            .offset(params.offset)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return Page(items=items, total=total or 0, limit=params.limit, offset=params.offset)

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity
