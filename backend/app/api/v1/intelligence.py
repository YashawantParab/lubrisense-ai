"""Combined tenant-scoped read view over condition/prognostic/decision assessments
(Phase 13-15 brief "Integration across 13/14/15" — optional combined endpoint, persistence
boundaries kept separate). Runs the full chain once via `DecisionEngine` (which itself
triggers a fresh `ConditionEngine`/`PrognosticEngine` run) rather than three independent
computations, so the three pieces returned are always mutually consistent."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.condition_intelligence import ConditionAssessmentResponse
from app.api.schemas.decision_intelligence import DecisionAssessmentResponse
from app.api.schemas.intelligence import IntelligenceViewResponse
from app.api.schemas.prognostics import PrognosticAssessmentResponse
from app.decision_intelligence.services.decision_engine import (
    DecisionEngine,
    DecisionEngineMachineNotFoundError,
)
from app.domain.models import Tenant

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/machines/{machine_id}", response_model=IntelligenceViewResponse)
async def get_intelligence_view(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> IntelligenceViewResponse:
    engine = DecisionEngine(session)
    try:
        bundle = await engine.decide_for_machine(tenant.id, machine_id)
    except DecisionEngineMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return IntelligenceViewResponse(
        condition=ConditionAssessmentResponse.model_validate(bundle.condition),
        prognostics=[PrognosticAssessmentResponse.model_validate(p) for p in bundle.prognostics],
        decision=DecisionAssessmentResponse.model_validate(bundle.decision),
    )
