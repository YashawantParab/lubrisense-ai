"""Tenant-scoped Phase 11 ML API (Phase 11 brief §43). Kept visibly separate from
`app.api.v1.features` (raw features) and any future Condition Intelligence API — ML output
here is evidence, never a diagnosis or maintenance decision."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from ml_service.registry.registry import ModelNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db_session
from app.api.schemas.ml import MLInferenceResultResponse, ModelDetailResponse, ModelSummaryResponse
from app.domain.models import Tenant
from app.features.config.policy import load_feature_policy
from app.ml.registry import get_model_registry
from app.ml.services.ml_inference_service import (
    MLInferenceOrchestrationService,
    MLMachineNotFoundError,
    MLModelNotAvailableError,
)
from app.ml.services.ml_query_service import MLQueryMachineNotFoundError, MLQueryService

router = APIRouter(prefix="/ml", tags=["ml"])
_POLICY = load_feature_policy()
_KNOWN_MODEL_IDS = ("LUBRICATION_ANOMALY_V1", "FAILURE_CLASSIFICATION_V1")


@router.get("/models", response_model=list[ModelSummaryResponse])
async def list_models(
    _tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> list[ModelSummaryResponse]:
    registry = get_model_registry()
    summaries: list[ModelSummaryResponse] = []
    for model_id in registry.list_model_ids():
        entries = registry.list_versions(model_id)
        if not entries:
            continue
        latest = max(entries, key=lambda e: e.training_time)
        metadata = registry.get_metadata(model_id, latest.model_version)
        summaries.append(
            ModelSummaryResponse(
                model_id=metadata.model_id,
                model_version=metadata.model_version,
                model_type=metadata.model_type.value,
                status=metadata.status.value,
                training_time=metadata.training_time,
                dataset_id=metadata.dataset_id,
                dataset_version=metadata.dataset_version,
                feature_set=metadata.feature_set,
                feature_set_version=metadata.feature_set_version,
            )
        )
    return summaries


@router.get("/models/{model_id}", response_model=ModelDetailResponse)
async def get_model(
    model_id: str,
    _tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> ModelDetailResponse:
    registry = get_model_registry()
    entries = registry.list_versions(model_id)
    if not entries:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found.")
    latest = max(entries, key=lambda e: e.training_time)
    try:
        metadata = registry.get_metadata(model_id, latest.model_version)
    except ModelNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found.") from exc
    return ModelDetailResponse(
        model_id=metadata.model_id,
        model_version=metadata.model_version,
        model_type=metadata.model_type.value,
        status=metadata.status.value,
        training_time=metadata.training_time,
        dataset_id=metadata.dataset_id,
        dataset_version=metadata.dataset_version,
        feature_set=metadata.feature_set,
        feature_set_version=metadata.feature_set_version,
        features=list(metadata.features),
        hyperparameters=metadata.hyperparameters,
        metrics=metadata.metrics,
        thresholds=metadata.thresholds,
        seed=metadata.seed,
        code_version=metadata.code_version,
        limitations=list(metadata.limitations),
        minimum_required_features=list(metadata.minimum_required_features),
    )


@router.get("/machines/{machine_id}/latest", response_model=MLInferenceResultResponse)
async def get_latest_inference(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    model_id: Annotated[str, Query()] = "LUBRICATION_ANOMALY_V1",
) -> MLInferenceResultResponse:
    if model_id not in _KNOWN_MODEL_IDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown model_id.")
    service = MLInferenceOrchestrationService(session, _POLICY)
    try:
        result = await service.compute_and_persist_latest(tenant.id, machine_id, model_id)
    except MLMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    except MLModelNotAvailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return MLInferenceResultResponse.model_validate(result)


@router.get("/machines/{machine_id}/history", response_model=list[MLInferenceResultResponse])
async def get_inference_history(
    machine_id: uuid.UUID,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    model_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[MLInferenceResultResponse]:
    if model_id is not None and model_id not in _KNOWN_MODEL_IDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown model_id.")
    service = MLQueryService(session)
    try:
        results = await service.history(
            tenant.id, machine_id, model_id=model_id, start=start, end=end, limit=limit
        )
    except MLQueryMachineNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine not found.") from exc
    return [MLInferenceResultResponse.model_validate(r) for r in results]
