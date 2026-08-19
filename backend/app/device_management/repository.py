from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.enums import DeviceType
from app.domain.models import ConfigurationChange, ConfigurationSnapshot
from app.repositories.base import TenantScopedRepository


class ConfigurationSnapshotRepository(TenantScopedRepository[ConfigurationSnapshot]):
    model = ConfigurationSnapshot

    async def get_current(
        self, tenant_id: uuid.UUID, device_type: DeviceType, device_id: uuid.UUID
    ) -> ConfigurationSnapshot | None:
        stmt = select(ConfigurationSnapshot).where(
            ConfigurationSnapshot.tenant_id == tenant_id,
            ConfigurationSnapshot.device_type == device_type,
            ConfigurationSnapshot.device_id == device_id,
            ConfigurationSnapshot.is_current.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_current_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[ConfigurationSnapshot]:
        stmt = select(ConfigurationSnapshot).where(
            ConfigurationSnapshot.tenant_id == tenant_id,
            ConfigurationSnapshot.machine_id == machine_id,
            ConfigurationSnapshot.is_current.is_(True),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ConfigurationChangeRepository(TenantScopedRepository[ConfigurationChange]):
    model = ConfigurationChange

    async def list_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[ConfigurationChange]:
        stmt = (
            select(ConfigurationChange)
            .where(
                ConfigurationChange.tenant_id == tenant_id,
                ConfigurationChange.machine_id == machine_id,
            )
            .order_by(ConfigurationChange.occurred_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
