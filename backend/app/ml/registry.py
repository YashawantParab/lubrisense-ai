"""Builds the one `ModelRegistry` handle the backend uses, pointed at
`settings.ml_artifacts_dir` (a read-only bind mount of the host's `ml-service/artifacts/models`
in Docker Compose, see docker-compose.yml) rather than `ml_service`'s own package-relative
default — the registry a training run populates lives on the host, not inside the backend
image (TECHNICAL_DECISIONS.md ADR-096)."""

from __future__ import annotations

from pathlib import Path

from ml_service.registry.registry import ModelRegistry

from app.core.config import get_settings


def get_model_registry() -> ModelRegistry:
    return ModelRegistry(Path(get_settings().ml_artifacts_dir))
