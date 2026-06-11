"""Pipeline state payload builders shared across artifact writers and validators."""

from __future__ import annotations

from typing import Any

from packages.agent_support.pipeline_semantics import (
    PIPELINE_STAGE_BOOTSTRAP,
    PIPELINE_STAGE_IDLE,
    current_phase_from_stage_trail,
    load_completed_skills_from_pipeline_state_payload,
    normalize_pipeline_stage,
    normalize_stage_trail,
    skill_for_stage,
)


ACTIVE_RUNTIME_PHASES = frozenset(
    {
        "Generation",
        "Evolution",
        "Reflection",
        "Insights from Reviews",
        "Proximity",
        "Ranking",
        "Research Overview",
    }
)


def _normalize_pipeline_mode(value: Any) -> str:
    """Normalize persisted pipeline modes to the host-agent execution surface."""
    return "host-agent"


def normalize_pipeline_status(status: str, current_phase: str) -> str:
    """Normalize runtime status so active phases are never persisted as not started."""
    if status == "not_started" and current_phase in ACTIVE_RUNTIME_PHASES:
        return "running"
    return status


def build_current_stage_payload(
    run_id: str,
    stage: str,
    stage_trail: Any,
    updated_at: str,
) -> dict[str, Any]:
    """Build the canonical CURRENT_STAGE payload."""
    return {
        "runId": run_id,
        "stage": normalize_pipeline_stage(stage, default=PIPELINE_STAGE_BOOTSTRAP),
        "stageTrail": normalize_stage_trail(stage_trail),
        "updatedAt": updated_at,
    }


def build_pipeline_state_payload(
    run_id: str,
    updated_at: str,
    state: Any,
    *,
    top_k_limit: int,
    existing: dict[str, Any] | None = None,
    mode: str | None = None,
    status: str | None = None,
    current_phase: str | None = None,
    current_skill: str | None = None,
    completed_skills: list[str] | None = None,
    failed_skill: str | None = None,
    resume_inputs: dict[str, Any] | None = None,
    stage_trail: list[str] | None = None,
) -> dict[str, Any]:
    """Build the canonical PIPELINE_STATE payload from the current state and execution metadata."""
    existing = existing or {}
    normalized_stage_trail = normalize_stage_trail(
        stage_trail if stage_trail is not None else existing.get("stageTrail", [])
    )
    effective_phase = normalize_pipeline_stage(
        current_phase if current_phase is not None else existing.get("currentPhase", ""),
        default=current_phase_from_stage_trail(normalized_stage_trail, default=PIPELINE_STAGE_IDLE),
    )
    effective_skill = (
        current_skill
        if isinstance(current_skill, str)
        else str(existing.get("currentSkill", "") or skill_for_stage(effective_phase))
    )
    effective_completed_skills = (
        record_completed_skills(completed_skills)
        if completed_skills is not None
        else record_completed_skills(existing.get("completedSkills", []))
    )

    top_hypotheses = sorted(
        (hypothesis for hypothesis in state.hypotheses.values() if hypothesis.is_viable),
        key=lambda item: item.elo_rating,
        reverse=True,
    )[:top_k_limit]
    raw_status = status if status is not None else existing.get("status", "running")
    effective_status = normalize_pipeline_status(
        raw_status if isinstance(raw_status, str) else "running",
        effective_phase,
    )

    return {
        "runId": run_id,
        "updatedAt": updated_at,
        "iterationCount": state.iteration_count,
        "convergenceCount": state.convergence_count,
        "researchGoal": state.research_plan.research_goal,
        "hypothesisCount": len(state.hypotheses),
        "viableHypothesisCount": sum(1 for hypothesis in state.hypotheses.values() if hypothesis.is_viable),
        "tournamentMatchCount": len(state.tournament_matches),
        "islandCount": len(state.islands),
        "topHypothesisIds": [hypothesis.id for hypothesis in top_hypotheses],
        "mode": _normalize_pipeline_mode(mode if mode is not None else existing.get("mode", "host-agent")),
        "status": effective_status,
        "currentPhase": effective_phase,
        "currentSkill": effective_skill,
        "currentIteration": state.iteration_count,
        "completedSkills": effective_completed_skills,
        "lastFailedSkill": failed_skill if failed_skill is not None else existing.get("lastFailedSkill"),
        "resumeInputs": resume_inputs if resume_inputs is not None else existing.get("resumeInputs", {}),
        "stageTrail": normalized_stage_trail,
    }


def record_completed_skills(values: Any) -> list[str]:
    """Return the normalized completed skill list for payload emission."""
    return load_completed_skills_from_pipeline_state_payload({"completedSkills": values})


__all__ = [
    "ACTIVE_RUNTIME_PHASES",
    "build_current_stage_payload",
    "build_pipeline_state_payload",
    "normalize_pipeline_status",
    "record_completed_skills",
]
