"""Combined Phase 13+14+15 read view (Phase 13-15 brief "Integration"). Purely a response
shape — condition/prognostic/decision persistence boundaries are never merged; each is
still its own table, this just bundles one read of each."""

from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas.condition_intelligence import ConditionAssessmentResponse
from app.api.schemas.decision_intelligence import DecisionAssessmentResponse
from app.api.schemas.prognostics import PrognosticAssessmentResponse


class IntelligenceViewResponse(BaseModel):
    condition: ConditionAssessmentResponse
    prognostics: list[PrognosticAssessmentResponse]
    decision: DecisionAssessmentResponse
