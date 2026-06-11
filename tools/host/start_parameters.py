"""Shared parameter metadata for the natural-language Co-Scientist start surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


ParameterLevel = Literal["core", "advanced", "utility"]


@dataclass(frozen=True)
class StartParameter:
    """One user-facing parameter on the natural-language start surface."""

    name: str
    flag: str
    level: ParameterLevel
    default: str
    description: str
    options: tuple[str, ...]


START_PARAMETERS: tuple[StartParameter, ...] = (
    StartParameter(
        name="exploration",
        flag="--exploration",
        level="core",
        default="balanced",
        description="Controls how strongly the run favors novelty, diversity, and broad search.",
        options=("conservative", "balanced", "aggressive"),
    ),
    StartParameter(
        name="review",
        flag="--review",
        level="core",
        default="standard",
        description="Controls review depth and critique strictness while keeping the full review stack enabled.",
        options=("light", "standard", "strict"),
    ),
    StartParameter(
        name="budget",
        flag="--budget",
        level="core",
        default="medium",
        description=(
            "Controls per-round run intensity and how expensive each generation, review, and ranking pass may become."
        ),
        options=("low", "medium", "high"),
    ),
    StartParameter(
        name="iteration-policy",
        flag="--iteration-policy",
        level="core",
        default="completion_driven",
        description=(
            "Controls whether the run stops through semantic completion signals or through a user-chosen "
            "iteration cap."
        ),
        options=("completion_driven", "capped"),
    ),
    StartParameter(
        name="human-checkpoint",
        flag="--human-checkpoint",
        level="core",
        default="auto",
        description="Controls where the run should pause for explicit human confirmation.",
        options=("auto", "before_overview", "before_completion", "every_major_stage"),
    ),
    StartParameter(
        name="generation-bias",
        flag="--generation-bias",
        level="advanced",
        default="mixed",
        description="Biases generation toward one family of idea creation strategies.",
        options=("literature_heavy", "debate_heavy", "assumptions_heavy", "mixed"),
    ),
    StartParameter(
        name="evolution",
        flag="--evolution",
        level="advanced",
        default="balanced",
        description="Controls whether later iterations exploit current winners or diversify the search.",
        options=("exploit", "balanced", "diversify"),
    ),
    StartParameter(
        name="stop-policy",
        flag="--stop-policy",
        level="advanced",
        default="standard",
        description=(
            "Controls how readily the run accepts that semantic stop conditions are sufficient to move toward "
            "the overview or final synthesis."
        ),
        options=("exploratory", "standard", "strict"),
    ),
    StartParameter(
        name="iteration-band",
        flag="--iteration-band",
        level="advanced",
        default="",
        description="Optional capped-run iteration range. Use only with `--iteration-policy capped`.",
        options=("6_10", "10_14", "15_20", "20_30"),
    ),
    StartParameter(
        name="goal",
        flag="--goal",
        level="utility",
        default="",
        description="Primary natural-language research goal for the run.",
        options=(),
    ),
    StartParameter(
        name="brief",
        flag="--brief",
        level="utility",
        default="",
        description="Imports an existing Markdown or text brief into input.md.",
        options=(),
    ),
    StartParameter(
        name="notes",
        flag="--notes",
        level="utility",
        default="",
        description="Appends one notes file to the generated research brief.",
        options=(),
    ),
    StartParameter(
        name="run-id",
        flag="--run-id",
        level="utility",
        default="auto-generated",
        description="Sets the run directory name explicitly instead of using the generated slug.",
        options=(),
    ),
    StartParameter(
        name="runs-dir",
        flag="--runs-dir",
        level="utility",
        default="runs/",
        description="Sets the parent directory where new runs should be created.",
        options=(),
    ),
    StartParameter(
        name="summary-only",
        flag="--summary-only",
        level="utility",
        default="false",
        description="Renders the start summary without creating files or bootstrapping the pipeline.",
        options=("false", "true"),
    ),
)


def build_start_parameters_payload() -> dict[str, object]:
    """Return a stable machine-readable description of the start surface."""
    core_axes = [asdict(parameter) for parameter in START_PARAMETERS if parameter.level == "core"]
    advanced_axes = [asdict(parameter) for parameter in START_PARAMETERS if parameter.level == "advanced"]
    utility_flags = [asdict(parameter) for parameter in START_PARAMETERS if parameter.level == "utility"]
    return {
        "entrySkill": "/co-scientist-start",
        "cliCommand": "python -m tools.host.project_cli start",
        "guidedIntake": {
            "available": True,
            "maxQuestions": 4,
            "defaultFocus": ["goal", "exploration", "iteration-policy", "brief-import"],
        },
        "coreAxes": core_axes,
        "advancedAxes": advanced_axes,
        "utilityFlags": utility_flags,
        "examples": [
            '/co-scientist-start "Investigate a plausible resistance mechanism."',
            '/co-scientist-start "Investigate a plausible resistance mechanism." -- exploration: aggressive, '
            "iteration policy: completion_driven",
            'python -m tools.host.project_cli start --goal "Investigate a plausible resistance mechanism." '
            "--budget low --iteration-policy capped --iteration-band 6_10",
        ],
    }


def render_start_parameters_text() -> str:
    """Render a concise human-readable parameter reference."""
    payload = build_start_parameters_payload()
    lines = [
        "Co-Scientist start parameters",
        "",
        "Primary entrypoints:",
        f"- {payload['entrySkill']}",
        f"- {payload['cliCommand']}",
        "",
        "Default guided intake:",
        "- asks for the goal, exploration preference, iteration strategy, and optional brief import",
        "- does not ask for low-level mechanics knobs",
        "",
        "Core axes:",
    ]
    for parameter in payload["coreAxes"]:
        options = ", ".join(parameter["options"])
        lines.append(
            f"- {parameter['name']} ({parameter['flag']}) | default: {parameter['default']} | options: {options}"
        )
        lines.append(f"  {parameter['description']}")

    lines.extend(["", "Advanced axes:"])
    for parameter in payload["advancedAxes"]:
        options = ", ".join(parameter["options"])
        lines.append(
            f"- {parameter['name']} ({parameter['flag']}) | default: {parameter['default']} | options: {options}"
        )
        lines.append(f"  {parameter['description']}")

    lines.extend(["", "Utility flags:"])
    for parameter in payload["utilityFlags"]:
        default = parameter["default"] or "(none)"
        lines.append(f"- {parameter['name']} ({parameter['flag']}) | default: {default}")
        lines.append(f"  {parameter['description']}")

    lines.extend(["", "Examples:"])
    lines.extend(f"- {example}" for example in payload["examples"])
    return "\n".join(lines)


__all__ = [
    "START_PARAMETERS",
    "StartParameter",
    "build_start_parameters_payload",
    "render_start_parameters_text",
]
