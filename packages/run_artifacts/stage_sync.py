"""Canonical paired write helpers for pipeline-stage runtime artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from packages.agent_contracts import CurrentStageContract, PipelineStateContract
from packages.agent_support.pipeline_semantics import (
    canonicalize_pipeline_stage,
    skill_for_stage,
    update_stage_trail,
)
from packages.run_artifacts.pipeline_state import build_current_stage_payload, normalize_pipeline_status


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def sync_pipeline_stage_artifacts(
    run_dir: str | Path,
    *,
    current_phase: str,
    current_skill: str | None = None,
    stage_trail: list[str] | None = None,
    status: str | None = None,
) -> tuple[PipelineStateContract, CurrentStageContract]:
    """Synchronize PIPELINE_STATE and CURRENT_STAGE for one active substage.

    The helper preserves all non-stage pipeline summary fields from the existing
    `state/PIPELINE_STATE.json` artifact while updating `currentPhase`,
    `currentSkill`, `stageTrail`, and both timestamps in one paired write.
    """
    run_dir_path = Path(run_dir).resolve()
    pipeline_state_path = run_dir_path / "state" / "PIPELINE_STATE.json"
    current_stage_path = run_dir_path / "state" / "CURRENT_STAGE.json"

    if not pipeline_state_path.exists():
        raise FileNotFoundError(
            f"Cannot synchronize active stage artifacts because {pipeline_state_path} does not exist."
        )

    effective_phase = canonicalize_pipeline_stage(current_phase)
    if effective_phase is None:
        raise ValueError(f"Unknown pipeline stage: {current_phase!r}")

    canonical_skill = skill_for_stage(effective_phase)
    effective_skill = current_skill or canonical_skill
    if canonical_skill and effective_skill != canonical_skill:
        raise ValueError(
            "Active stage synchronization requires the canonical skill for the requested phase: "
            f"{effective_phase!r} expects {canonical_skill!r}, got {effective_skill!r}."
        )

    existing_pipeline_state = PipelineStateContract.from_json_file(pipeline_state_path).model_dump(mode="json")
    effective_stage_trail = update_stage_trail(
        stage_trail if stage_trail is not None else existing_pipeline_state.get("stageTrail", []),
        effective_phase,
    )
    updated_at = _now_iso()

    existing_pipeline_state["updatedAt"] = updated_at
    existing_pipeline_state["currentPhase"] = effective_phase
    existing_pipeline_state["currentSkill"] = effective_skill
    existing_pipeline_state["stageTrail"] = effective_stage_trail
    if status is not None:
        existing_pipeline_state["status"] = status
    existing_pipeline_state["status"] = normalize_pipeline_status(
        str(existing_pipeline_state.get("status", "running")),
        effective_phase,
    )

    pipeline_state_contract = PipelineStateContract.from_payload(existing_pipeline_state)
    current_stage_payload = build_current_stage_payload(
        run_dir_path.name,
        effective_phase,
        effective_stage_trail,
        updated_at,
    )
    current_stage_contract = CurrentStageContract.from_payload(current_stage_payload)

    _write_json_atomic(pipeline_state_path, pipeline_state_contract.model_dump(mode="json"))
    _write_json_atomic(current_stage_path, current_stage_contract.model_dump(mode="json"))

    return pipeline_state_contract, current_stage_contract


__all__ = ["sync_pipeline_stage_artifacts"]
