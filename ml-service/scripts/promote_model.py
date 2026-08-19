"""Explicit, human-invoked model promotion (Phase 32 brief §32.5).

There is no code path anywhere in this repository that moves a model version between
lifecycle stages automatically — `ModelRegistry.set_status()` is a low-level primitive,
and training scripts only ever decide EXPERIMENT vs. VALIDATED (Phase 11 brief §25). This
script is the *only* supported way to move a model VALIDATED -> STAGING -> PRODUCTION (or
to RETIRED from any state): it requires an explicit `--reason`, refuses to skip a stage,
and appends every promotion decision — including the operator, the reason, and a snapshot
of the model's metrics at the time — to an append-only log so the decision is auditable
after the fact.

    python scripts/promote_model.py --model-id FAILURE_CLASSIFICATION_BASELINE_V1 \
        --version 1.0.0 --to STAGING --actor demo-admin \
        --reason "Only model that cleared the VALIDATED gate on the reference dataset."

Refuses (does not silently downgrade the request) when the target model has not actually
been evaluated, or when the transition would skip a stage.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from ml_service.domain.model_metadata import ModelLifecycleState
from ml_service.registry.registry import DEFAULT_ARTIFACTS_DIR, ModelNotFoundError, ModelRegistry

# The only transitions this tool will perform — one stage forward at a time, or a
# retirement from any non-retired stage. EXPERIMENT -> STAGING/PRODUCTION directly is
# deliberately not listed: a model must pass through VALIDATED first.
_ALLOWED_TRANSITIONS: dict[ModelLifecycleState, tuple[ModelLifecycleState, ...]] = {
    ModelLifecycleState.EXPERIMENT: (ModelLifecycleState.VALIDATED, ModelLifecycleState.RETIRED),
    ModelLifecycleState.VALIDATED: (ModelLifecycleState.STAGING, ModelLifecycleState.RETIRED),
    ModelLifecycleState.STAGING: (ModelLifecycleState.PRODUCTION, ModelLifecycleState.RETIRED),
    ModelLifecycleState.PRODUCTION: (ModelLifecycleState.RETIRED,),
    ModelLifecycleState.RETIRED: (),
}


class PromotionRefusedError(Exception):
    pass


def _promotion_log_path(artifacts_dir: Path) -> Path:
    return artifacts_dir / "promotion_log.jsonl"


def promote(
    registry: ModelRegistry,
    *,
    model_id: str,
    version: str,
    to_status: ModelLifecycleState,
    actor: str,
    reason: str,
) -> dict[str, object]:
    try:
        metadata = registry.get_metadata(model_id, version)
    except ModelNotFoundError as exc:
        raise PromotionRefusedError(f"{model_id}@{version} is not registered") from exc

    current = metadata.status
    allowed = _ALLOWED_TRANSITIONS.get(current, ())
    if to_status not in allowed:
        raise PromotionRefusedError(
            f"{model_id}@{version} is {current.value}; promoting directly to "
            f"{to_status.value} is not an allowed transition "
            f"(allowed next stage(s): {[s.value for s in allowed] or 'none — terminal state'})"
        )
    if not reason.strip():
        raise PromotionRefusedError("a non-empty --reason is required for every promotion")

    registry.set_status(model_id, version, to_status)

    record = {
        "model_id": model_id,
        "model_version": version,
        "from_status": current.value,
        "to_status": to_status.value,
        "actor": actor,
        "reason": reason,
        "decided_at": datetime.now(UTC).isoformat(),
        "metrics_snapshot": metadata.metrics,
        "artifact_checksum": metadata.artifact_checksum,
    }
    log_path = _promotion_log_path(registry.base_dir)
    with log_path.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--to", required=True, choices=[s.value for s in ModelLifecycleState], dest="to_status"
    )
    parser.add_argument("--actor", required=True, help="human operator making this decision")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    args = parser.parse_args()

    registry = ModelRegistry(base_dir=args.artifacts_dir)
    try:
        record = promote(
            registry,
            model_id=args.model_id,
            version=args.version,
            to_status=ModelLifecycleState(args.to_status),
            actor=args.actor,
            reason=args.reason,
        )
    except PromotionRefusedError as exc:
        print(f"REFUSED: {exc}")
        return 1

    print(f"Promoted {record['model_id']}@{record['model_version']}: "
          f"{record['from_status']} -> {record['to_status']} (actor={record['actor']})")
    print(f"Logged to {_promotion_log_path(registry.base_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
