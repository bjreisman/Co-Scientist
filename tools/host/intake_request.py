"""Guided intake and start summary helpers for natural-language run bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from packages.agent_contracts import RunPolicySettingsContract, StartRequestContract

from .create_run import DEFAULT_INPUT_FILENAME, build_run_policy_from_controls, generate_run_id


InteractionModeName = Literal["guided", "direct", "brief_import"]
GUIDED_INTAKE_QUESTIONS = (
    "What is the research goal for this run?",
    "Should this run favor exploration or grounded progress?",
    "Should this run keep exploring until semantic stop signals appear, "
    "or should it use a capped low-cost iteration budget?",
    "Do you want to import an existing brief, paper notes, or other written context?",
)


@dataclass(frozen=True)
class StartRequestPreview:
    """Stable preview for a not-yet-created natural-language start request."""

    run_id: str
    run_dir: Path
    interaction_mode: InteractionModeName
    request_text: str
    goal: str
    brief_path: Path | None
    notes_path: Path | None
    explicit_controls: dict[str, str]
    effective_controls: dict[str, str]
    artifacts_to_create: tuple[str, ...]


def build_start_request_preview(
    *,
    goal: str | None = None,
    brief_path: Path | None = None,
    notes_path: Path | None = None,
    run_id: str | None = None,
    runs_dir: Path,
    interaction_mode: InteractionModeName | None = None,
    exploration: str | None = None,
    generation_bias: str | None = None,
    review: str | None = None,
    budget: str | None = None,
    evolution: str | None = None,
    stop_policy: str | None = None,
    iteration_policy: str | None = None,
    iteration_band: str | None = None,
    human_checkpoint: str | None = None,
) -> StartRequestPreview:
    """Build a deterministic preview before any run-local files are written."""
    if goal is None and brief_path is None and notes_path is None:
        raise ValueError("A start preview requires at least one of goal, brief_path, or notes_path.")

    resolved_runs_dir = runs_dir.resolve()
    resolved_brief_path = brief_path.resolve() if brief_path is not None else None
    resolved_notes_path = notes_path.resolve() if notes_path is not None else None
    resolved_run_id = run_id or generate_run_id(
        resolved_runs_dir,
        goal=goal,
        brief_path=resolved_brief_path,
        notes_path=resolved_notes_path,
    )
    resolved_mode = interaction_mode or infer_interaction_mode(goal=goal, brief_path=resolved_brief_path)

    explicit_controls = {
        key: value
        for key, value in {
            "exploration": exploration,
            "generation_bias": generation_bias,
            "review": review,
            "budget": budget,
            "evolution": evolution,
            "stop_policy": stop_policy,
            "iteration_policy": iteration_policy,
            "iteration_band": iteration_band,
            "human_checkpoint": human_checkpoint,
        }.items()
        if value is not None
    }

    policy = build_run_policy_from_controls(
        input_file=DEFAULT_INPUT_FILENAME,
        exploration=exploration,
        generation_bias=generation_bias,
        review=review,
        budget=budget,
        evolution=evolution,
        stop_policy=stop_policy,
        iteration_policy=iteration_policy,
        iteration_band=iteration_band,
        human_checkpoint=human_checkpoint,
    )
    effective_policy = policy.policy if policy is not None else RunPolicySettingsContract()

    goal_summary = (goal or "").strip()
    if not goal_summary and resolved_brief_path is not None:
        goal_summary = f"Imported from `{resolved_brief_path.name}`"
    elif not goal_summary and resolved_notes_path is not None:
        goal_summary = f"Imported from `{resolved_notes_path.name}`"
    request_text = (goal or "").strip()
    if not request_text and resolved_brief_path is not None:
        request_text = f"Imported brief: {resolved_brief_path}"
    elif not request_text and resolved_notes_path is not None:
        request_text = f"Imported notes: {resolved_notes_path}"

    return StartRequestPreview(
        run_id=resolved_run_id,
        run_dir=(resolved_runs_dir / resolved_run_id).resolve(),
        interaction_mode=resolved_mode,
        request_text=request_text,
        goal=goal_summary,
        brief_path=resolved_brief_path,
        notes_path=resolved_notes_path,
        explicit_controls=explicit_controls,
        effective_controls={
            "exploration": effective_policy.exploration_mode,
            "generation_bias": effective_policy.generation_bias,
            "review": effective_policy.review_rigor,
            "budget": effective_policy.budget_profile,
            "evolution": effective_policy.evolution_style,
            "stop_policy": effective_policy.stop_policy,
            "iteration_policy": effective_policy.iteration_policy,
            "iteration_band": effective_policy.iteration_band or "",
            "human_checkpoint": effective_policy.human_checkpoint,
        },
        artifacts_to_create=(
            DEFAULT_INPUT_FILENAME,
            "RUN_POLICY.yaml",
            "state/START_REQUEST.json",
            "state/POLICY_DECISION.json",
            "state/RESOLVED_RUN_CONFIG.json",
            "state/STRATEGY_PLAN.json",
        ),
    )


def infer_interaction_mode(*, goal: str | None, brief_path: Path | None) -> InteractionModeName:
    """Infer the most natural interaction mode from the supplied request context."""
    if brief_path is not None and not (goal or "").strip():
        return "brief_import"
    return "direct"


def render_start_summary(preview: StartRequestPreview) -> str:
    """Render a short confirmation summary for one planned natural-language start."""
    lines = [
        "Planned Co-Scientist run:",
        f"- run id: {preview.run_id}",
        f"- interaction mode: {preview.interaction_mode}",
        f"- goal: {preview.goal or '(pending research goal)'}",
        f"- exploration: {preview.effective_controls['exploration']}",
        f"- generation bias: {preview.effective_controls['generation_bias']}",
        f"- review rigor: {preview.effective_controls['review']}",
        f"- budget: {preview.effective_controls['budget']}",
        f"- iteration policy: {preview.effective_controls['iteration_policy']}",
        "",
        "Artifacts to create:",
    ]
    iteration_band = preview.effective_controls["iteration_band"]
    if iteration_band:
        lines.insert(8, f"- iteration band: {iteration_band}")
    lines.extend(f"- {artifact}" for artifact in preview.artifacts_to_create)
    if preview.brief_path is not None:
        lines.extend(["", f"Imported brief: {preview.brief_path}"])
    if preview.notes_path is not None:
        lines.extend(["", f"Imported notes: {preview.notes_path}"])
    return "\n".join(lines)


def build_start_request_contract(preview: StartRequestPreview) -> StartRequestContract:
    """Materialize one canonical start-request artifact from a confirmed preview."""
    inferred_controls = {
        key: value for key, value in preview.effective_controls.items() if key not in preview.explicit_controls
    }
    return StartRequestContract(
        status="completed",
        runId=preview.run_id,
        requestText=preview.request_text,
        interactionMode=preview.interaction_mode,
        explicitControls=dict(preview.explicit_controls),
        inferredControls=inferred_controls,
        briefSource=str(preview.brief_path) if preview.brief_path is not None else "",
        notesSource=str(preview.notes_path) if preview.notes_path is not None else "",
    )


__all__ = [
    "GUIDED_INTAKE_QUESTIONS",
    "InteractionModeName",
    "StartRequestPreview",
    "build_start_request_contract",
    "build_start_request_preview",
    "infer_interaction_mode",
    "render_start_summary",
]
