"""Persistence for `QualityAssessment` (Phase 7 brief §5/§29 — storage strategy #4 in the
plan: window-scoped assessments always persisted; event-scoped assessments only when at
least one issue was found)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AssessmentScope, QualityState
from app.domain.models import QualityAssessment


class QualityAssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_event_assessment(
        self,
        *,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        machine_id: uuid.UUID | None,
        event_id: uuid.UUID,
        quality_state: QualityState,
        policy_version: str,
        rule_versions: dict[str, str],
        metadata: dict[str, Any] | None = None,
    ) -> QualityAssessment:
        assessment = QualityAssessment(
            tenant_id=tenant_id,
            scope=AssessmentScope.EVENT,
            sensor_id=sensor_id,
            machine_id=machine_id,
            event_id=event_id,
            window_start=None,
            window_end=None,
            quality_state=quality_state,
            quality_score=None,
            policy_version=policy_version,
            rule_versions=rule_versions,
            metadata_=metadata or {},
        )
        self.session.add(assessment)
        await self.session.flush()
        return assessment

    async def create_window_assessment(
        self,
        *,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        machine_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
        quality_state: QualityState,
        policy_version: str,
        rule_versions: dict[str, str],
        metadata: dict[str, Any] | None = None,
    ) -> QualityAssessment:
        assessment = QualityAssessment(
            tenant_id=tenant_id,
            scope=AssessmentScope.WINDOW,
            sensor_id=sensor_id,
            machine_id=machine_id,
            event_id=None,
            window_start=window_start,
            window_end=window_end,
            quality_state=quality_state,
            quality_score=None,
            policy_version=policy_version,
            rule_versions=rule_versions,
            metadata_=metadata or {},
        )
        self.session.add(assessment)
        await self.session.flush()
        return assessment
