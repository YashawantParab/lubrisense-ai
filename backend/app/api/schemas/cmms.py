"""Phase 20 CMMS-adapter API contracts. Every response is a local draft (§20.4) — never
an already-submitted external work order."""

from __future__ import annotations

from pydantic import BaseModel


class WorkOrderResponse(BaseModel):
    external_reference: str
    title: str
    description: str
    asset_reference: str
    priority: str
    status: str
    recommended_window: str
    checklist: list[str]
