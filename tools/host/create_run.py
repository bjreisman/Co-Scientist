"""Helpers for creating run-local artifacts from natural-language start requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from packages.agent_contracts import RunPolicyContract, RunPolicySettingsContract, StartRequestContract
from packages.agent_support import (
    DEFAULT_ALLOWED_GENERATION_STRATEGIES,
    DEFAULT_ALLOWED_REVIEW_MODES,
)


DEFAULT_CONFIG_FILENAME = "config.yaml"
DEFAULT_INPUT_FILENAME = "input.md"
DEFAULT_LOG_FILENAME = "co_scientist.log"


@dataclass(frozen=True)
class CreatedRunArtifacts:
    """Stable output bundle for one initialized run directory."""

    run_dir: Path
    config_path: Path | None
    input_path: Path
    run_policy_path: Path | None


def default_runs_dir() -> Path:
    """Return the repository-local default runs directory."""
    return Path(__file__).resolve().parents[2] / "runs"


def create_run_artifacts(
    *,
    goal: str | None = None,
    brief_path: Path | None = None,
    notes_path: Path | None = None,
    runs_dir: Path | None = None,
    run_id: str | None = None,
    run_policy: RunPolicyContract | None = None,
    start_request: StartRequestContract | None = None,
    write_config: bool = False,
) -> CreatedRunArtifacts:
    """Create a new run directory with the minimum bootstrap artifacts."""
    resolved_runs_dir = (runs_dir or default_runs_dir()).resolve()
    resolved_runs_dir.mkdir(parents=True, exist_ok=True)

    if goal is None and brief_path is None and notes_path is None:
        raise ValueError("At least one of goal, brief_path, or notes_path must be provided.")

    resolved_brief_path = brief_path.resolve() if brief_path is not None else None
    resolved_notes_path = notes_path.resolve() if notes_path is not None else None
    resolved_run_id = run_id or generate_run_id(
        resolved_runs_dir,
        goal=goal,
        brief_path=resolved_brief_path,
        notes_path=resolved_notes_path,
    )
    run_dir = (resolved_runs_dir / resolved_run_id).resolve()
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}")

    run_dir.mkdir(parents=True)
    input_path = run_dir / DEFAULT_INPUT_FILENAME
    config_path = (run_dir / DEFAULT_CONFIG_FILENAME) if write_config else None
    run_policy_path = run_dir / "RUN_POLICY.yaml" if run_policy is not None else None
    state_dir = run_dir / "state"

    input_path.write_text(
        render_input_markdown(goal=goal, brief_path=resolved_brief_path, notes_path=resolved_notes_path),
        encoding="utf-8",
    )
    if config_path is not None:
        config_path.write_text(
            yaml.safe_dump(
                {
                    "input_file": DEFAULT_INPUT_FILENAME,
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    if run_policy_path is not None:
        run_policy_path.write_text(run_policy.to_yaml_text(), encoding="utf-8")
    if start_request is not None:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "START_REQUEST.json").write_text(start_request.model_dump_json(indent=2) + "\n", encoding="utf-8")

    return CreatedRunArtifacts(
        run_dir=run_dir,
        config_path=config_path,
        input_path=input_path,
        run_policy_path=run_policy_path,
    )


def build_run_policy_from_controls(
    *,
    input_file: str = DEFAULT_INPUT_FILENAME,
    exploration: str | None = None,
    generation_bias: str | None = None,
    review: str | None = None,
    budget: str | None = None,
    evolution: str | None = None,
    stop_policy: str | None = None,
    iteration_policy: str | None = None,
    iteration_band: str | None = None,
    human_checkpoint: str | None = None,
) -> RunPolicyContract | None:
    """Build a run policy only when the caller explicitly overrides high-level controls."""
    resolved_iteration_policy = iteration_policy or ("capped" if iteration_band is not None else None)
    controls = {
        "exploration_mode": exploration,
        "generation_bias": generation_bias,
        "review_rigor": review,
        "budget_profile": budget,
        "evolution_style": evolution,
        "stop_policy": stop_policy,
        "iteration_policy": resolved_iteration_policy,
        "iteration_band": iteration_band,
        "human_checkpoint": human_checkpoint,
    }
    if not any(value is not None for value in controls.values()):
        return None

    policy_settings = RunPolicySettingsContract(
        allowed_generation_strategies=list(DEFAULT_ALLOWED_GENERATION_STRATEGIES),
        allowed_review_modes=list(DEFAULT_ALLOWED_REVIEW_MODES),
        **{key: value for key, value in controls.items() if value is not None},
    )
    return RunPolicyContract(
        input_file=input_file,
        log_file=DEFAULT_LOG_FILENAME,
        policy=policy_settings,
    )


def generate_run_id(
    runs_dir: Path,
    *,
    goal: str | None = None,
    brief_path: Path | None = None,
    notes_path: Path | None = None,
) -> str:
    """Generate a stable run id from the date and the available task context."""
    base_label = (
        goal
        or (brief_path.stem if brief_path is not None else "")
        or (notes_path.stem if notes_path is not None else "")
    )
    slug = _slugify(base_label) or "co-scientist-run"
    prefix = datetime.now(UTC).strftime("%Y-%m-%d")
    base_name = f"{prefix}-{slug}"
    candidate = base_name
    index = 1
    while (runs_dir / candidate).exists():
        index += 1
        candidate = f"{base_name}-{index:03d}"
    return candidate


def render_input_markdown(
    *,
    goal: str | None = None,
    brief_path: Path | None = None,
    notes_path: Path | None = None,
) -> str:
    """Render the canonical research brief artifact for one initialized run."""
    sections: list[str] = ["# Research Brief", ""]

    normalized_goal = (goal or "").strip()
    if normalized_goal:
        sections.extend(["## Goal", "", normalized_goal, ""])

    if brief_path is not None:
        brief_content = brief_path.read_text(encoding="utf-8").strip()
        if brief_content:
            sections.extend(["## Imported Brief", "", brief_content, ""])
            sections.extend(["## Brief Source", "", f"`{brief_path}`", ""])

    if notes_path is not None:
        notes_content = notes_path.read_text(encoding="utf-8").strip()
        if notes_content:
            sections.extend(["## Imported Notes", "", notes_content, ""])
            sections.extend(["## Notes Source", "", f"`{notes_path}`", ""])

    if len(sections) == 2:
        sections.extend(["## Goal", "", "(pending research goal)", ""])

    return "\n".join(sections).rstrip() + "\n"


def _slugify(value: str) -> str:
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered)
    return normalized.strip("-")[:48]


__all__ = [
    "DEFAULT_CONFIG_FILENAME",
    "DEFAULT_INPUT_FILENAME",
    "DEFAULT_LOG_FILENAME",
    "CreatedRunArtifacts",
    "build_run_policy_from_controls",
    "create_run_artifacts",
    "default_runs_dir",
    "generate_run_id",
    "render_input_markdown",
]
