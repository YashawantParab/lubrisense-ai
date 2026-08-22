"""Filesystem-based model registry (Phase 11 brief §23-§25, §40).

Every artifact is looked up through an explicit registry index
(`artifacts/models/registry_index.json`), never by listing a directory and taking whatever
file happens to be newest — "load explicit validated model versions... do not silently use
'latest file in folder'" (§40).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from ml_service.domain.model_metadata import ModelLifecycleState, ModelMetadata

DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "models"


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModelNotFoundError(LookupError):
    pass


class ArtifactIntegrityError(RuntimeError):
    """Raised when a loaded artifact's on-disk sha256 no longer matches the checksum
    recorded at registration time — evidence of accidental corruption or an
    out-of-band file swap, not something `load()` should silently ignore."""


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    model_id: str
    model_version: str
    status: ModelLifecycleState
    training_time: str


class ModelRegistry:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DEFAULT_ARTIFACTS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.base_dir / "registry_index.json"

    def _read_index(self) -> dict[str, Any]:
        if not self._index_path.exists():
            return {}
        return json.loads(self._index_path.read_text())  # type: ignore[no-any-return]

    def _write_index(self, index: dict[str, Any]) -> None:
        self._index_path.write_text(json.dumps(index, indent=2, sort_keys=True))

    def _model_dir(self, model_id: str, version: str) -> Path:
        return self.base_dir / model_id / version

    def register(self, artifact_obj: object, metadata: ModelMetadata) -> ModelMetadata:
        model_dir = self._model_dir(metadata.model_id, metadata.model_version)
        model_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = model_dir / "model.joblib"
        joblib.dump(artifact_obj, artifact_path)

        metadata_with_path = dataclasses.replace(
            metadata,
            artifact_path=str(artifact_path),
            artifact_checksum=_sha256_of(artifact_path),
        )
        (model_dir / "metadata.json").write_text(json.dumps(metadata_with_path.to_dict(), indent=2))

        index = self._read_index()
        model_entry = index.setdefault(metadata.model_id, {"versions": {}})
        model_entry["versions"][metadata.model_version] = {
            "status": metadata.status.value,
            "training_time": metadata.training_time.isoformat(),
        }
        self._write_index(index)
        return metadata_with_path

    def set_status(self, model_id: str, version: str, status: ModelLifecycleState) -> None:
        metadata = self.get_metadata(model_id, version)
        updated = dataclasses.replace(metadata, status=status)
        model_dir = self._model_dir(model_id, version)
        (model_dir / "metadata.json").write_text(json.dumps(updated.to_dict(), indent=2))
        index = self._read_index()
        index[model_id]["versions"][version]["status"] = status.value
        self._write_index(index)

    def get_metadata(self, model_id: str, version: str) -> ModelMetadata:
        path = self._model_dir(model_id, version) / "metadata.json"
        if not path.exists():
            raise ModelNotFoundError(f"{model_id}@{version}")
        return ModelMetadata.from_dict(json.loads(path.read_text()))

    def load(
        self, model_id: str, version: str, *, verify_checksum: bool = True
    ) -> tuple[object, ModelMetadata]:
        metadata = self.get_metadata(model_id, version)
        artifact_path = self._model_dir(model_id, version) / "model.joblib"
        if not artifact_path.exists():
            raise ModelNotFoundError(f"{model_id}@{version} (artifact file missing)")
        if verify_checksum and metadata.artifact_checksum:
            actual = _sha256_of(artifact_path)
            if actual != metadata.artifact_checksum:
                raise ArtifactIntegrityError(
                    f"{model_id}@{version}: artifact checksum mismatch "
                    f"(expected {metadata.artifact_checksum}, got {actual})"
                )
        return joblib.load(artifact_path), metadata

    def list_versions(self, model_id: str) -> list[RegistryEntry]:
        index = self._read_index()
        model_entry = index.get(model_id, {"versions": {}})
        return [
            RegistryEntry(
                model_id=model_id,
                model_version=version,
                status=ModelLifecycleState(info["status"]),
                training_time=info["training_time"],
            )
            for version, info in model_entry["versions"].items()
        ]

    def latest_by_status(
        self, model_id: str, statuses: tuple[ModelLifecycleState, ...]
    ) -> RegistryEntry | None:
        """Explicit index-based lookup of the most-recently-trained version whose status is
        one of `statuses` — the only "latest" concept this registry has, and it is derived
        from the index's recorded `training_time`, never filesystem mtimes."""
        candidates = [e for e in self.list_versions(model_id) if e.status in statuses]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.training_time)

    def list_model_ids(self) -> list[str]:
        return sorted(self._read_index().keys())

    def list_promotions(self, model_id: str | None = None) -> list[dict[str, Any]]:
        """Read-only view of `promotion_log.jsonl` (written only by
        `scripts/promote_model.py`, never by this class) — every lifecycle-change decision
        this registry has ever recorded, each carrying its own reason and a metrics
        snapshot from the moment of the decision. `model_id=None` returns every model's
        history; a missing log file (no promotion has ever happened) returns `[]`, not an
        error."""
        log_path = self.base_dir / "promotion_log.jsonl"
        if not log_path.exists():
            return []
        records = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        if model_id is not None:
            records = [r for r in records if r.get("model_id") == model_id]
        return records
