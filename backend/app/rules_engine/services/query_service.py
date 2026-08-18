"""Read-only query service backing `app/api/v1/rules.py` (Phase 9 brief §32-§33). Same
not-found-vs-empty-result convention as `TelemetryQueryService`/`QualityQueryService`:
querying a machine that doesn't exist for this tenant is a 404, not an empty response.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RuleFindingSeverity, RuleFindingState, RuleFindingType
from app.domain.models import RuleFinding
from app.repositories.machine import MachineRepository
from app.rules_engine.repositories.rule_finding_repository import RuleFindingRepository
from app.services.errors import NotFoundError


class RuleFindingQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._finding_repo = RuleFindingRepository(session)
        self._machine_repo = MachineRepository(session)

    async def list_findings(
        self,
        tenant_id: uuid.UUID,
        *,
        machine_id: uuid.UUID | None = None,
        finding_type: RuleFindingType | None = None,
        severity: RuleFindingSeverity | None = None,
        state: RuleFindingState | None = None,
        rule_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[RuleFinding]:
        return await self._finding_repo.list_findings(
            tenant_id,
            machine_id=machine_id,
            finding_type=finding_type,
            severity=severity,
            state=state,
            rule_id=rule_id,
            start=start,
            end=end,
            limit=limit,
        )

    async def get_machine_findings(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[RuleFinding]:
        machine = await self._machine_repo.get(tenant_id, machine_id)
        if machine is None:
            raise NotFoundError("MACHINE_NOT_FOUND", "Machine not found.")
        return await self._finding_repo.list_current_for_machine(tenant_id, machine_id)

    async def get_finding(self, tenant_id: uuid.UUID, finding_id: uuid.UUID) -> RuleFinding:
        finding = await self._finding_repo.get_by_id(tenant_id, finding_id)
        if finding is None:
            raise NotFoundError("FINDING_NOT_FOUND", "Rule finding not found.")
        return finding

    async def get_tenant_summary(self, tenant_id: uuid.UUID) -> dict[str, object]:
        by_state = await self._finding_repo.count_by_state(tenant_id)
        by_severity = await self._finding_repo.count_by_severity(tenant_id)
        return {
            "findings_by_state": by_state,
            "findings_by_severity": by_severity,
            "total_active_findings": sum(by_state.values()),
        }
