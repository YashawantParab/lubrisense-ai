"""`CMMSService` — Phase 20 orchestration between `app.maintenance` and a `CMMSAdapter`.

Draft-first only (§20.4): this service never submits anything externally, it only ever
creates/reads a local draft. If the adapter fails, the failure is isolated here — the
underlying `MaintenanceCase`/`Incident` are never touched by a CMMS failure (§20.6), and
the caller receives a clear `CMMSUnavailableError` it can surface without losing any
workflow state.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.cmms.adapters.demo_adapter import DemoCMMSAdapter
from app.cmms.domain.adapter import CMMSAdapter, WorkOrderDraftRequest, WorkOrderRecord
from app.cmms.observability import METRICS
from app.domain.models import Machine, MaintenanceCase
from app.maintenance.services.maintenance_service import MaintenanceService
from app.repositories.machine import MachineRepository


class CMMSUnavailableError(RuntimeError):
    """Raised when the configured `CMMSAdapter` fails. Never leaks adapter-specific
    exception types to callers — core workflow code only needs to know "the CMMS call
    failed", not why, to satisfy the isolation guarantee (Phase 20 brief §20.6)."""


def _describe(case: MaintenanceCase, machine: Machine) -> WorkOrderDraftRequest:
    checklist_texts = [item["text"] for item in case.checklist]
    return WorkOrderDraftRequest(
        maintenance_case_id=str(case.id),
        title=f"{case.recommended_action.value.replace('_', ' ').title()} — {machine.name}",
        description=(
            f"Draft work order for maintenance case {case.id}, generated from decision "
            f"assessment {case.decision_assessment_id}. Priority: {case.priority.value}."
        ),
        asset_reference=machine.asset_code,
        priority=case.priority.value,
        recommended_window=case.recommended_window.value,
        checklist=checklist_texts,
    )


class CMMSService:
    def __init__(self, session: AsyncSession, adapter: CMMSAdapter | None = None) -> None:
        self._session = session
        self._maintenance = MaintenanceService(session)
        self._machines = MachineRepository(session)
        # `None` means "use the demo adapter, tenant-bound at call time" — a real
        # deployment would inject a configured vendor adapter here instead.
        self._adapter_override = adapter

    def _adapter_for(self, tenant_id: uuid.UUID) -> CMMSAdapter:
        return self._adapter_override or DemoCMMSAdapter(self._session, tenant_id)

    async def create_draft(
        self, tenant_id: uuid.UUID, maintenance_case_id: uuid.UUID
    ) -> WorkOrderRecord:
        case = await self._maintenance.get(tenant_id, maintenance_case_id)
        machine = await self._machines.get(tenant_id, case.machine_id)
        if machine is None:
            raise CMMSUnavailableError(f"Machine {case.machine_id} not found.")

        adapter = self._adapter_for(tenant_id)
        try:
            record = await adapter.create_work_order_draft(_describe(case, machine))
        except Exception as exc:  # noqa: BLE001 — deliberately broad: any adapter
            # failure (network, vendor error, unconfigured stub) must isolate identically
            # from the caller's perspective, per §20.6.
            METRICS.increment("cmms_draft_failures")
            raise CMMSUnavailableError(
                f"CMMS draft creation failed for maintenance case {maintenance_case_id}: {exc}"
            ) from exc

        METRICS.increment("cmms_drafts_created")
        return record

    async def get_work_order(
        self, tenant_id: uuid.UUID, external_reference: str
    ) -> WorkOrderRecord | None:
        adapter = self._adapter_for(tenant_id)
        try:
            return await adapter.get_work_order(external_reference)
        except Exception as exc:  # noqa: BLE001 — see create_draft
            METRICS.increment("cmms_read_failures")
            raise CMMSUnavailableError(
                f"CMMS lookup failed for {external_reference}: {exc}"
            ) from exc
