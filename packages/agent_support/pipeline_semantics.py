"""Shared pipeline stage semantics for host-agent tools, validators, and dashboard contracts."""

from __future__ import annotations

from typing import Any, Final, Literal, get_args


PipelineStage = Literal[
    "Bootstrap",
    "Idle",
    "Configuration",
    "Generation",
    "Evolution",
    "Reflection",
    "Insights from Reviews",
    "Proximity",
    "Ranking",
    "Research Overview",
    "Completed",
    "Failed",
]

PIPELINE_STAGE_BOOTSTRAP: Final[PipelineStage] = "Bootstrap"
PIPELINE_STAGE_IDLE: Final[PipelineStage] = "Idle"
PIPELINE_STAGE_CONFIGURATION: Final[PipelineStage] = "Configuration"
PIPELINE_STAGE_GENERATION: Final[PipelineStage] = "Generation"
PIPELINE_STAGE_EVOLUTION: Final[PipelineStage] = "Evolution"
PIPELINE_STAGE_REFLECTION: Final[PipelineStage] = "Reflection"
PIPELINE_STAGE_INSIGHTS: Final[PipelineStage] = "Insights from Reviews"
PIPELINE_STAGE_PROXIMITY: Final[PipelineStage] = "Proximity"
PIPELINE_STAGE_RANKING: Final[PipelineStage] = "Ranking"
PIPELINE_STAGE_RESEARCH_OVERVIEW: Final[PipelineStage] = "Research Overview"
PIPELINE_STAGE_COMPLETED: Final[PipelineStage] = "Completed"
PIPELINE_STAGE_FAILED: Final[PipelineStage] = "Failed"
PIPELINE_STAGE_ALIASES: Final[dict[str, PipelineStage]] = {
    "ResearchOverview": PIPELINE_STAGE_RESEARCH_OVERVIEW,
}

PIPELINE_STAGES: tuple[PipelineStage, ...] = get_args(PipelineStage)
TRACKED_PIPELINE_STAGES: frozenset[PipelineStage] = frozenset(
    {
        PIPELINE_STAGE_GENERATION,
        PIPELINE_STAGE_EVOLUTION,
        PIPELINE_STAGE_REFLECTION,
        PIPELINE_STAGE_INSIGHTS,
        PIPELINE_STAGE_PROXIMITY,
        PIPELINE_STAGE_RANKING,
        PIPELINE_STAGE_RESEARCH_OVERVIEW,
    }
)
PIPELINE_STAGE_TO_SKILL: dict[PipelineStage, str] = {
    PIPELINE_STAGE_CONFIGURATION: "research-config",
    PIPELINE_STAGE_GENERATION: "hypothesis-generation-pipeline",
    PIPELINE_STAGE_EVOLUTION: "hypothesis-evolution-loop",
    PIPELINE_STAGE_REFLECTION: "hypothesis-review-pipeline",
    PIPELINE_STAGE_INSIGHTS: "insights-from-reviews",
    PIPELINE_STAGE_PROXIMITY: "hypothesis-proximity-update",
    PIPELINE_STAGE_RANKING: "hypothesis-ranking-pipeline",
    PIPELINE_STAGE_RESEARCH_OVERVIEW: "research-overview-pipeline",
}
PIPELINE_SKILLS: frozenset[str] = frozenset(PIPELINE_STAGE_TO_SKILL.values())


def is_valid_pipeline_stage(value: Any) -> bool:
    """Return whether *value* is one of the shared pipeline stage labels."""
    return isinstance(canonicalize_pipeline_stage(value), str)


def canonicalize_pipeline_stage(value: Any) -> PipelineStage | None:
    """Return the canonical pipeline stage label for one raw value."""
    if not isinstance(value, str):
        return None
    if value in PIPELINE_STAGES:
        return value
    return PIPELINE_STAGE_ALIASES.get(value)


def is_known_pipeline_skill(value: Any) -> bool:
    """Return whether *value* is one of the shared pipeline skill identifiers."""
    return isinstance(value, str) and value in PIPELINE_SKILLS


def normalize_pipeline_stage(
    value: Any,
    *,
    default: PipelineStage = PIPELINE_STAGE_IDLE,
) -> PipelineStage:
    """Return a valid pipeline stage, falling back to *default* for unknown values."""
    canonical = canonicalize_pipeline_stage(value)
    if canonical is not None:
        return canonical
    return default


def normalize_stage_trail(values: Any) -> list[str]:
    """Return the canonical tracked stage trail from an untyped payload."""
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        canonical = canonicalize_pipeline_stage(item)
        if canonical in TRACKED_PIPELINE_STAGES and canonical not in normalized:
            normalized.append(canonical)
    return normalized


def load_stage_trail_from_current_stage_payload(payload: Any) -> list[str]:
    """Extract a normalized stage trail from CURRENT_STAGE-like payloads."""
    if not isinstance(payload, dict):
        return []
    return normalize_stage_trail(payload.get("stageTrail", []))


def load_completed_skills_from_pipeline_state_payload(payload: Any) -> list[str]:
    """Extract the completed skill list from PIPELINE_STATE-like payloads."""
    if not isinstance(payload, dict):
        return []
    completed_skills = payload.get("completedSkills", [])
    if not isinstance(completed_skills, list):
        return []
    normalized: list[str] = []
    for skill in completed_skills:
        if isinstance(skill, str) and skill not in normalized:
            normalized.append(skill)
    return normalized


def update_stage_trail(stage_trail: Any, stage: Any, *, reset_trail: bool = False) -> list[str]:
    """Apply one stage transition to the tracked flowchart trail."""
    normalized_trail = normalize_stage_trail(stage_trail)
    normalized_stage = normalize_pipeline_stage(stage)
    if reset_trail:
        return [normalized_stage] if normalized_stage in TRACKED_PIPELINE_STAGES else []
    if normalized_stage in TRACKED_PIPELINE_STAGES and normalized_stage not in normalized_trail:
        return [*normalized_trail, normalized_stage]
    return normalized_trail


def record_completed_skill(completed_skills: Any, skill_name: Any) -> list[str]:
    """Return a de-duplicated completed skill list with *skill_name* appended if needed."""
    skills = load_completed_skills_from_pipeline_state_payload({"completedSkills": completed_skills})
    if isinstance(skill_name, str) and skill_name and skill_name not in skills:
        skills.append(skill_name)
    return skills


def skill_for_stage(stage: Any) -> str:
    """Return the canonical skill name for one stage, or an empty string if none is mapped."""
    normalized_stage = canonicalize_pipeline_stage(stage)
    if normalized_stage is None:
        return ""
    return PIPELINE_STAGE_TO_SKILL.get(normalized_stage, "")


def current_phase_from_stage_trail(stage_trail: Any, *, default: PipelineStage = PIPELINE_STAGE_IDLE) -> PipelineStage:
    """Return the current logical phase from a tracked stage trail."""
    normalized_trail = normalize_stage_trail(stage_trail)
    if normalized_trail:
        return normalize_pipeline_stage(normalized_trail[-1], default=default)
    return default


__all__ = [
    "PIPELINE_SKILLS",
    "PIPELINE_STAGES",
    "PIPELINE_STAGE_ALIASES",
    "PIPELINE_STAGE_BOOTSTRAP",
    "PIPELINE_STAGE_COMPLETED",
    "PIPELINE_STAGE_CONFIGURATION",
    "PIPELINE_STAGE_EVOLUTION",
    "PIPELINE_STAGE_FAILED",
    "PIPELINE_STAGE_GENERATION",
    "PIPELINE_STAGE_IDLE",
    "PIPELINE_STAGE_INSIGHTS",
    "PIPELINE_STAGE_PROXIMITY",
    "PIPELINE_STAGE_RANKING",
    "PIPELINE_STAGE_REFLECTION",
    "PIPELINE_STAGE_RESEARCH_OVERVIEW",
    "PIPELINE_STAGE_TO_SKILL",
    "TRACKED_PIPELINE_STAGES",
    "PipelineStage",
    "canonicalize_pipeline_stage",
    "current_phase_from_stage_trail",
    "is_known_pipeline_skill",
    "is_valid_pipeline_stage",
    "load_completed_skills_from_pipeline_state_payload",
    "load_stage_trail_from_current_stage_payload",
    "normalize_pipeline_stage",
    "normalize_stage_trail",
    "record_completed_skill",
    "skill_for_stage",
    "update_stage_trail",
]
