"""Clearly-labelled external CMMS adapter stubs (Phase 20 brief §20.3). These do NOT
invent real endpoint paths, auth schemes, payload formats, or proprietary vendor
behavior — every method raises `NotImplementedError` naming exactly what a real
integration would need to supply. They exist only to show the adapter boundary is real
(`CMMSAdapter` is genuinely vendor-neutral), never to simulate a vendor's actual API.
"""

from __future__ import annotations

from app.cmms.domain.adapter import WorkOrderDraftRequest, WorkOrderRecord

_REQUIRES_CONFIG = (
    "{vendor} integration requires customer-specific integration configuration "
    "(authentication, endpoint URL, and payload field mapping) that this reference "
    "platform does not define — see docs/CMMS_INTEGRATION.md."
)


class SAPPMAdapterStub:
    """Placeholder for a real SAP Plant Maintenance (PM) integration. Every method is
    unimplemented on purpose — see module docstring."""

    async def create_work_order_draft(self, request: WorkOrderDraftRequest) -> WorkOrderRecord:
        del request
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="SAP PM"))

    async def get_work_order(self, external_reference: str) -> WorkOrderRecord | None:
        del external_reference
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="SAP PM"))

    async def update_work_order_status(
        self, external_reference: str, status: str
    ) -> WorkOrderRecord:
        del external_reference, status
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="SAP PM"))

    async def add_note(self, external_reference: str, note: str) -> None:
        del external_reference, note
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="SAP PM"))


class MaximoAdapterStub:
    """Placeholder for a real IBM Maximo integration. Every method is unimplemented on
    purpose — see module docstring."""

    async def create_work_order_draft(self, request: WorkOrderDraftRequest) -> WorkOrderRecord:
        del request
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="Maximo"))

    async def get_work_order(self, external_reference: str) -> WorkOrderRecord | None:
        del external_reference
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="Maximo"))

    async def update_work_order_status(
        self, external_reference: str, status: str
    ) -> WorkOrderRecord:
        del external_reference, status
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="Maximo"))

    async def add_note(self, external_reference: str, note: str) -> None:
        del external_reference, note
        raise NotImplementedError(_REQUIRES_CONFIG.format(vendor="Maximo"))
