"""Data-quality read API (Phase 7 brief §32-§34) — tenant-scoped via `get_current_tenant`,
same convention as `app/api/v1/telemetry.py`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.data_quality import (
    MachineQualitySummaryResponse,
    QualityIssueResponse,
    SensorQualityDetailResponse,
    SensorQualityRecordResponse,
    SensorQualityStateResponse,
    TenantQualitySummaryResponse,
)
from app.data_quality.services.quality_query_service import QualityQueryService
from app.domain.enums import Eligibility, IssueSeverity, IssueStatus, QualityState
from app.domain.models import Tenant

router = APIRouter(prefix="/data-quality", tags=["data-quality"])


@router.get("/sensors", response_model=list[SensorQualityRecordResponse])
async def list_fleet_sensor_quality(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    machine_id: uuid.UUID | None = None,
    quality_state: QualityState | None = None,
    eligibility: Eligibility | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[SensorQualityRecordResponse]:
    """Every sensor this tenant has evaluated at least once — including sensors with no
    active issue at all — so the Data Quality page can show trusted sensors, not only
    active problems. `GET /issues` alone cannot answer this: a fully trusted sensor never
    has an issue row."""
    service = QualityQueryService(session)
    records = await service.list_fleet_sensor_records(
        tenant.id,
        machine_id=machine_id,
        quality_state=quality_state,
        eligibility=eligibility,
        limit=limit,
    )
    return [
        SensorQualityRecordResponse(
            sensor_id=record.sensor.id,
            sensor_code=record.sensor.sensor_code,
            sensor_name=record.sensor.name,
            sensor_type=record.sensor.sensor_type.value,
            machine_id=record.state.machine_id,
            state=SensorQualityStateResponse.model_validate(record.state),
            active_issues=[QualityIssueResponse.model_validate(i) for i in record.active_issues],
            expected_reporting_interval_seconds=record.expected_reporting_interval_seconds,
        )
        for record in records
    ]


@router.get("/sensors/{sensor_id}", response_model=SensorQualityDetailResponse)
async def get_sensor_quality(
    sensor_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SensorQualityDetailResponse:
    service = QualityQueryService(session)
    state, issues = await service.get_sensor_state(tenant.id, sensor_id)
    return SensorQualityDetailResponse(
        sensor_id=sensor_id,
        state=SensorQualityStateResponse.model_validate(state) if state is not None else None,
        active_issues=[QualityIssueResponse.model_validate(i) for i in issues],
    )


@router.get("/machines/{machine_id}", response_model=MachineQualitySummaryResponse)
async def get_machine_quality(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MachineQualitySummaryResponse:
    service = QualityQueryService(session)
    states, issues = await service.get_machine_summary(tenant.id, machine_id)
    return MachineQualitySummaryResponse(
        machine_id=machine_id,
        sensors=[SensorQualityStateResponse.model_validate(s) for s in states],
        active_issues=[QualityIssueResponse.model_validate(i) for i in issues],
    )


@router.get("/issues", response_model=list[QualityIssueResponse])
async def list_quality_issues(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    sensor_id: uuid.UUID | None = None,
    machine_id: uuid.UUID | None = None,
    severity: IssueSeverity | None = None,
    status: IssueStatus | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> list[QualityIssueResponse]:
    service = QualityQueryService(session)
    issues = await service.list_issues(
        tenant.id,
        sensor_id=sensor_id,
        machine_id=machine_id,
        severity=severity,
        status=status,
        start=start,
        end=end,
        limit=limit,
    )
    return [QualityIssueResponse.model_validate(i) for i in issues]


@router.get("/summary", response_model=TenantQualitySummaryResponse)
async def get_quality_summary(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantQualitySummaryResponse:
    service = QualityQueryService(session)
    summary = await service.get_tenant_summary(tenant.id)
    return TenantQualitySummaryResponse.model_validate(summary)
