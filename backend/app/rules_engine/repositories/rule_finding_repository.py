"""Persistence for `RuleFinding` (Phase 9 brief §27/§28/§29).

"Current" row = whichever row in one `(tenant_id, machine_id, component_id, rule_id,
rule_version)` lineage is not yet `RESOLVED` — at most one such row should exist at a time,
an invariant this repository maintains by only ever writing through the explicit
lifecycle-action methods below (never a raw insert after the first version), mirroring
`BaselineProfileRepository`'s own "upsert via the service layer, never bypass it"
discipline (Phase 8). Enforced at the database level by the partial unique index
`uq_rule_finding_active_scope` (`state IN ('CANDIDATE', 'ACTIVE', 'RECOVERING')`).

`app.rules_engine.services.lifecycle.decide` is the pure state machine; this repository
only executes whichever `LifecycleAction` it returns.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RuleFindingSeverity, RuleFindingState, RuleFindingType
from app.domain.models import RuleFinding
from app.rules_engine.domain.results import RuleFindingCandidate

_NON_TERMINAL = (RuleFindingState.CANDIDATE, RuleFindingState.ACTIVE, RuleFindingState.RECOVERING)


class RuleFindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_current(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        component_id: uuid.UUID | None,
        rule_id: str,
        rule_version: str,
    ) -> RuleFinding | None:
        component_clause = (
            RuleFinding.component_id.is_(None)
            if component_id is None
            else RuleFinding.component_id == component_id
        )
        stmt = select(RuleFinding).where(
            RuleFinding.tenant_id == tenant_id,
            RuleFinding.machine_id == machine_id,
            component_clause,
            RuleFinding.rule_id == rule_id,
            RuleFinding.rule_version == rule_version,
            RuleFinding.state.in_(_NON_TERMINAL),
        )
        result: RuleFinding | None = await self.session.scalar(stmt)
        return result

    async def create_candidate(
        self,
        *,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        candidate: RuleFindingCandidate,
        config_version: str,
        severity: RuleFindingSeverity,
        criticality_at_detection: str | None,
        now: datetime,
    ) -> RuleFinding:
        finding = RuleFinding(
            tenant_id=tenant_id,
            machine_id=machine_id,
            component_id=candidate.component_id,
            component_type=candidate.component_type,
            finding_type=candidate.finding_type,
            rule_id=candidate.rule_id,
            rule_version=candidate.rule_version,
            config_version=config_version,
            category=candidate.category,
            severity=severity,
            state=RuleFindingState.CANDIDATE,
            evidence_strength=candidate.evidence_strength,
            criticality_at_detection=criticality_at_detection,
            message=candidate.message,
            evidence=candidate.evidence,
            limitations=candidate.limitations,
            quality_context=candidate.quality_context,
            baseline_version_ids=candidate.baseline_version_ids,
            source_event_ids=candidate.source_event_ids,
            window_start=None,
            window_end=None,
            candidate_stable_cycles=1,
            first_detected_at=now,
            last_detected_at=now,
        )
        self.session.add(finding)
        await self.session.flush()
        return finding

    async def _refresh_fields(self, candidate: RuleFindingCandidate) -> dict[str, Any]:
        """Fields every lifecycle-action method refreshes from the freshly-evaluated
        candidate. `severity` is deliberately not included — it is computed by
        `app.rules_engine.services.rule_engine` (evidence strength + criticality, brief
        §23/§24), not carried on the candidate itself; every caller adds it explicitly."""
        return {
            "evidence_strength": candidate.evidence_strength,
            "message": candidate.message,
            "evidence": candidate.evidence,
            "limitations": candidate.limitations,
            "quality_context": candidate.quality_context,
            "baseline_version_ids": candidate.baseline_version_ids,
            "source_event_ids": candidate.source_event_ids,
        }

    async def advance_candidate(
        self,
        finding_id: uuid.UUID,
        *,
        candidate: RuleFindingCandidate,
        severity: RuleFindingSeverity,
        candidate_stable_cycles: int,
        now: datetime,
    ) -> None:
        fields = await self._refresh_fields(candidate)
        fields.update(
            severity=severity,
            candidate_stable_cycles=candidate_stable_cycles,
            last_detected_at=now,
        )
        await self.session.execute(
            update(RuleFinding).where(RuleFinding.id == finding_id).values(**fields)
        )

    async def activate(
        self,
        finding_id: uuid.UUID,
        *,
        candidate: RuleFindingCandidate,
        severity: RuleFindingSeverity,
        now: datetime,
    ) -> None:
        fields = await self._refresh_fields(candidate)
        fields.update(
            severity=severity,
            state=RuleFindingState.ACTIVE,
            activated_at=now,
            last_detected_at=now,
            # Reset once the row leaves CANDIDATE — the counter has no meaning for a
            # non-CANDIDATE row, and a stale non-zero value here would otherwise be
            # confusing to a human inspecting the finding (brief §44 explainability).
            candidate_stable_cycles=0,
        )
        await self.session.execute(
            update(RuleFinding).where(RuleFinding.id == finding_id).values(**fields)
        )

    async def refresh_active(
        self,
        finding_id: uuid.UUID,
        *,
        candidate: RuleFindingCandidate,
        severity: RuleFindingSeverity,
        now: datetime,
    ) -> None:
        fields = await self._refresh_fields(candidate)
        fields.update(severity=severity, last_detected_at=now, candidate_stable_cycles=0)
        await self.session.execute(
            update(RuleFinding).where(RuleFinding.id == finding_id).values(**fields)
        )

    async def reactivate_from_recovering(
        self,
        finding_id: uuid.UUID,
        *,
        candidate: RuleFindingCandidate,
        severity: RuleFindingSeverity,
        now: datetime,
    ) -> None:
        """The condition fired again before `RECOVERING` reached `RESOLVED` — it never
        actually recovered (Phase 7's identical precedent for `QualityIssue`)."""
        fields = await self._refresh_fields(candidate)
        fields.update(
            severity=severity,
            state=RuleFindingState.ACTIVE,
            last_detected_at=now,
            candidate_stable_cycles=0,
        )
        await self.session.execute(
            update(RuleFinding).where(RuleFinding.id == finding_id).values(**fields)
        )

    async def mark_recovering(self, finding_id: uuid.UUID, *, now: datetime) -> None:
        await self.session.execute(
            update(RuleFinding)
            .where(RuleFinding.id == finding_id)
            .values(state=RuleFindingState.RECOVERING, last_detected_at=now)
        )

    async def resolve(self, finding_id: uuid.UUID, *, now: datetime) -> None:
        await self.session.execute(
            update(RuleFinding)
            .where(RuleFinding.id == finding_id)
            .values(state=RuleFindingState.RESOLVED, resolved_at=now, last_detected_at=now)
        )

    async def list_current_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[RuleFinding]:
        stmt = select(RuleFinding).where(
            RuleFinding.tenant_id == tenant_id,
            RuleFinding.machine_id == machine_id,
            RuleFinding.state.in_(_NON_TERMINAL),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_current_machine_ids(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """`(tenant_id, machine_id)` pairs with at least one non-terminal finding —
        cross-tenant, only for the worker's own housekeeping (e.g. staleness sweeps over
        findings whose machine no longer has *any* tracked sensor). The worker's primary
        machine-discovery loop instead comes from `SensorQualityStateRepository.
        list_all_tracked` (mirrors `app.baselines.workers.worker`'s own precedent of
        discovering machines from Phase 7 state, not from its own table)."""
        stmt = (
            select(RuleFinding.tenant_id, RuleFinding.machine_id)
            .where(RuleFinding.state.in_(_NON_TERMINAL))
            .distinct()
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_by_id(self, tenant_id: uuid.UUID, finding_id: uuid.UUID) -> RuleFinding | None:
        stmt = select(RuleFinding).where(
            RuleFinding.tenant_id == tenant_id, RuleFinding.id == finding_id
        )
        result: RuleFinding | None = await self.session.scalar(stmt)
        return result

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
        clauses: list[Any] = [RuleFinding.tenant_id == tenant_id]
        if machine_id is not None:
            clauses.append(RuleFinding.machine_id == machine_id)
        if finding_type is not None:
            clauses.append(RuleFinding.finding_type == finding_type)
        if severity is not None:
            clauses.append(RuleFinding.severity == severity)
        if state is not None:
            clauses.append(RuleFinding.state == state)
        if rule_id is not None:
            clauses.append(RuleFinding.rule_id == rule_id)
        if start is not None:
            clauses.append(RuleFinding.last_detected_at >= start)
        if end is not None:
            clauses.append(RuleFinding.last_detected_at <= end)
        stmt = (
            select(RuleFinding)
            .where(*clauses)
            .order_by(RuleFinding.last_detected_at.desc())
            .limit(min(limit, 2000))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_state(self, tenant_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(RuleFinding.state, func.count())
            .where(RuleFinding.tenant_id == tenant_id, RuleFinding.state.in_(_NON_TERMINAL))
            .group_by(RuleFinding.state)
        )
        result = await self.session.execute(stmt)
        return {state.value: count for state, count in result.all()}

    async def count_by_severity(self, tenant_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(RuleFinding.severity, func.count())
            .where(RuleFinding.tenant_id == tenant_id, RuleFinding.state.in_(_NON_TERMINAL))
            .group_by(RuleFinding.severity)
        )
        result = await self.session.execute(stmt)
        return {severity.value: count for severity, count in result.all()}
