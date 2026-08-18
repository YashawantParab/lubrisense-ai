"""Tenant-scoped, read-only Phase 10 feature API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.features import (
    FeatureDefinitionResponse,
    FeatureSetResponse,
    FeatureVectorResponse,
)
from app.domain.models import Tenant
from app.features.config.policy import load_feature_policy
from app.features.definitions.catalog import FEATURE_DEFINITIONS
from app.features.definitions.sets import FEATURE_SETS
from app.features.domain.models import FeatureComputationResult
from app.features.services.feature_engine import FeatureEngine, FeatureMachineNotFoundError
from app.features.services.query_service import (
    FeatureQueryMachineNotFoundError,
    FeatureQueryService,
    FeatureVectorNotFoundError,
)

router = APIRouter(prefix="/features", tags=["features"])
_POLICY = load_feature_policy()


def _computed_response(result: FeatureComputationResult) -> FeatureVectorResponse:
    return FeatureVectorResponse(
        id=result.feature_vector_id,
        feature_set=result.feature_set,
        feature_set_version=result.feature_set_version,
        tenant_id=result.tenant_id,
        machine_id=result.machine_id,
        component_id=result.component_id,
        as_of_timestamp=result.as_of_timestamp,
        feature_values=result.feature_values,
        missing_features=list(result.missing_features),
        quality_summary=result.quality_summary,
        source_window=result.source_window,
        baseline_versions=result.baseline_versions,
        rule_versions=result.rule_versions,
        feature_definition_versions=result.feature_definition_versions,
        created_at=result.created_at,
    )


@router.get("/registry", response_model=list[FeatureDefinitionResponse])
async def get_registry(
    _tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> list[FeatureDefinitionResponse]:
    return [
        FeatureDefinitionResponse(
            feature_name=definition.name,
            feature_version=definition.version,
            group=definition.group.value,
            data_type=definition.data_type.value,
            unit=definition.unit,
            entity_scope=definition.entity_scope,
            source_measurements=list(definition.source_measurements),
            window_seconds=definition.window_seconds,
            aggregation=definition.aggregation,
            context_requirements=list(definition.context_requirements),
            quality_requirement=definition.quality_requirement,
            null_behavior=definition.null_behavior,
            description=definition.description,
            owner=definition.owner,
            availability=definition.availability,
            status=definition.status.value,
            feature_sets=list(definition.feature_sets),
        )
        for definition in FEATURE_DEFINITIONS
    ]


@router.get("/sets", response_model=list[FeatureSetResponse])
async def get_feature_sets(
    _tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> list[FeatureSetResponse]:
    return [
        FeatureSetResponse(
            name=feature_set.name,
            version=feature_set.version,
            intended_use=feature_set.intended_use,
            feature_count=len(feature_set.feature_names),
            feature_names=list(feature_set.feature_names),
        )
        for feature_set in FEATURE_SETS.values()
    ]


@router.get("/machines/{machine_id}/latest", response_model=FeatureVectorResponse)
async def get_latest_features(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    feature_set: Annotated[str, Query()] = "LUBRICATION_ANOMALY_V1",
) -> FeatureVectorResponse:
    if feature_set not in FEATURE_SETS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown feature set.")
    try:
        result = await FeatureEngine(session, _POLICY).compute_latest(
            tenant.id, machine_id, feature_set
        )
    except FeatureMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return _computed_response(result)


@router.get("/machines/{machine_id}", response_model=list[FeatureVectorResponse])
async def list_machine_features(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    feature_set: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[FeatureVectorResponse]:
    if feature_set is not None and feature_set not in FEATURE_SETS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown feature set.")
    try:
        vectors = await FeatureQueryService(session).list_for_machine(
            tenant.id,
            machine_id,
            feature_set=feature_set,
            start=start,
            end=end,
            limit=limit,
        )
    except FeatureQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [FeatureVectorResponse.model_validate(vector) for vector in vectors]


@router.get("/vectors/{vector_id}", response_model=FeatureVectorResponse)
async def get_feature_vector(
    vector_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FeatureVectorResponse:
    try:
        vector = await FeatureQueryService(session).get_vector(tenant.id, vector_id)
    except FeatureVectorNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feature vector not found.") from exc
    return FeatureVectorResponse.model_validate(vector)
