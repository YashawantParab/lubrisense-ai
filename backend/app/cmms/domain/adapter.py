"""`CMMSAdapter` — the integration boundary for enterprise maintenance systems (Phase 20
brief §20.1). Core `app.maintenance`/`app.incidents` domain logic never binds directly to
one vendor; it only ever talks to this `Protocol`. Every operation is draft-first (§20.4) —
none of them represent an already-submitted, externally-visible work order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WorkOrderDraftRequest:
    maintenance_case_id: str
    title: str
    description: str
    asset_reference: str
    priority: str
    recommended_window: str
    checklist: list[str]


@dataclass(frozen=True, slots=True)
class WorkOrderRecord:
    external_reference: str
    title: str
    description: str
    asset_reference: str
    priority: str
    status: str
    recommended_window: str
    checklist: list[str]


class CMMSAdapter(Protocol):
    """Structural interface — any adapter (demo or a real vendor integration) implements
    exactly these four operations. Draft creation must be idempotent per maintenance case
    (§20.5); failures must never be interpreted by callers as "core monitoring is down"
    (§20.6, `CMMSUnavailableError` in `app.cmms.services.cmms_service`)."""

    async def create_work_order_draft(self, request: WorkOrderDraftRequest) -> WorkOrderRecord: ...

    async def get_work_order(self, external_reference: str) -> WorkOrderRecord | None: ...

    async def update_work_order_status(
        self, external_reference: str, status: str
    ) -> WorkOrderRecord: ...

    async def add_note(self, external_reference: str, note: str) -> None: ...
