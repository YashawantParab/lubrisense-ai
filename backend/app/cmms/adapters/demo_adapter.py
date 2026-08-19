"""`DemoCMMSAdapter` — persists demo work orders locally (Phase 20 brief §20.2). This is
the only adapter this reference implementation actually calls in tests/demos; the
external stubs in `app.cmms.adapters.external_stubs` exist purely to show the boundary."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.cmms.domain.adapter import WorkOrderDraftRequest, WorkOrderRecord
from app.cmms.repositories.demo_work_order_repository import DemoCMMSWorkOrderRepository
from app.domain.enums import CMMSWorkOrderStatus
from app.domain.models import DemoCMMSWorkOrder


def _to_record(row: DemoCMMSWorkOrder) -> WorkOrderRecord:
    return WorkOrderRecord(
        external_reference=row.external_reference,
        title=row.title,
        description=row.description,
        asset_reference=row.asset_reference,
        priority=row.priority.value,
        status=row.status.value,
        recommended_window=row.recommended_window.value,
        checklist=[item["text"] for item in row.checklist],
    )


class DemoCMMSAdapter:
    """One instance per `(session, tenant_id)` — mirrors every other repository/service
    in this codebase being constructed per-request, never a process-wide singleton."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._repo = DemoCMMSWorkOrderRepository(session)

    async def create_work_order_draft(self, request: WorkOrderDraftRequest) -> WorkOrderRecord:
        maintenance_case_id = uuid.UUID(request.maintenance_case_id)
        existing = await self._repo.get_for_case(self._tenant_id, maintenance_case_id)
        if existing is not None:
            return _to_record(existing)

        reference = f"DEMO-WO-{uuid.uuid4().hex[:10].upper()}"
        row = DemoCMMSWorkOrder(
            id=uuid.uuid4(),
            tenant_id=self._tenant_id,
            maintenance_case_id=maintenance_case_id,
            external_reference=reference,
            title=request.title,
            description=request.description,
            asset_reference=request.asset_reference,
            priority=request.priority,
            status=CMMSWorkOrderStatus.DRAFT,
            recommended_window=request.recommended_window,
            checklist=[{"text": item, "completed": False} for item in request.checklist],
        )
        row = await self._repo.insert(row)
        return _to_record(row)

    async def get_work_order(self, external_reference: str) -> WorkOrderRecord | None:
        row = await self._repo.get_by_external_reference(self._tenant_id, external_reference)
        return _to_record(row) if row is not None else None

    async def update_work_order_status(
        self, external_reference: str, status: str
    ) -> WorkOrderRecord:
        row = await self._repo.get_by_external_reference(self._tenant_id, external_reference)
        if row is None:
            raise LookupError(external_reference)
        row.status = CMMSWorkOrderStatus(status)
        row = await self._repo.save(row)
        return _to_record(row)

    async def add_note(self, external_reference: str, note: str) -> None:
        # Demo adapter has no separate notes table yet — a real adapter would post this
        # to the external system's own notes/comments API. Documented as a known
        # limitation (docs/CMMS_INTEGRATION.md), not silently swallowed.
        del note
        row = await self._repo.get_by_external_reference(self._tenant_id, external_reference)
        if row is None:
            raise LookupError(external_reference)
