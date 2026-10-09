"""Claude Code-facing project CLI for Co-Scientist entry skills."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..install.environment_doctor import collect_environment_doctor_payload, render_environment_doctor_text
from ..token_usage import attach_run, collect_usage
from ..validation.contract_validation import validate_run_artifacts
from .create_run import (
    CreatedRunArtifacts,
    build_run_policy_from_controls,
    create_run_artifacts,
    default_runs_dir,
)
from .host_agent import TOP_LEVEL_SKILLS
from .host_agent_surface import bootstrap_host_agent_run, ensure_dashboard_for_run
from .host_config import HostSettings
from .intake_request import build_start_request_contract, build_start_request_preview, render_start_summary
from .start_parameters import build_start_parameters_payload, render_start_parameters_text


EXPLORATION_CHOICES = ("conservative", "balanced", "aggressive")
GENERATION_BIAS_CHOICES = ("literature_heavy", "debate_heavy", "assumptions_heavy", "mixed")
REVIEW_CHOICES = ("light", "standard", "strict")
BUDGET_CHOICES = ("low", "medium", "high")
EVOLUTION_CHOICES = ("exploit", "balanced", "diversify")
STOP_POLICY_CHOICES = ("exploratory", "standard", "strict")
ITERATION_POLICY_CHOICES = ("completion_driven", "capped")
ITERATION_BAND_CHOICES = ("6_10", "10_14", "15_20", "20_30")
HUMAN_CHECKPOINT_CHOICES = ("auto", "before_overview", "before_completion", "every_major_stage")
INTERACTION_MODE_CHOICES = ("guided", "direct", "brief_import")
_START_CONTROL_ALIASES = {
    "exploration": "--exploration",
    "generation bias": "--generation-bias",
    "review": "--review",
    "budget": "--budget",
    "evolution": "--evolution",
    "stop policy": "--stop-policy",
    "iteration policy": "--iteration-policy",
    "iteration band": "--iteration-band",
    "human checkpoint": "--human-checkpoint",
}
_START_FLAGS_WITH_VALUES = {
    "--goal",
    "--brief",
    "--notes",
    "--run-id",
    "--runs-dir",
    "--exploration",
    "--generation-bias",
    "--review",
    "--budget",
    "--evolution",
    "--stop-policy",
    "--iteration-policy",
    "--iteration-band",
    "--human-checkpoint",
    "--interaction-mode",
    "--skill",
    "--format",
}
_START_BOOLEAN_FLAGS = {"--summary-only", "--no-dashboard", "--resume"}


def _resolve_run_dir(path: Path) -> Path:
    resolved_path = path.resolve()
    if resolved_path.is_dir():
        return resolved_path
    if resolved_path.is_file() and resolved_path.name == "config.yaml":
        return resolved_path.parent
    raise FileNotFoundError(f"Run directory or config.yaml not found: {resolved_path}")


def _normalize_start_control_value(value: str) -> str:
    return re.sub(r"[\s-]+", "_", value.strip().strip(",").strip().lower())


def _extract_start_controls(tokens: list[str]) -> tuple[list[str], list[str], bool]:
    preserved: list[str] = []
    freeform: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _START_FLAGS_WITH_VALUES:
            preserved.append(token)
            if index + 1 < len(tokens):
                preserved.append(tokens[index + 1])
                index += 2
                continue
            index += 1
            continue
        if token in _START_BOOLEAN_FLAGS:
            preserved.append(token)
            index += 1
            continue
        if token == "--":  # noqa: S105 - CLI freeform separator, not a credential.
            freeform.extend(tokens[index + 1 :])
            break
        freeform.append(token)
        index += 1

    parsed_controls: list[str] = []
    freeform_text = " ".join(fragment.strip() for fragment in freeform if fragment.strip())
    if freeform_text:
        pattern = re.compile(
            r"(?P<key>exploration|generation[\s_-]?bias|review|budget|evolution|stop[\s_-]?policy|human[\s_-]?checkpoint|iteration[\s_-]?policy|iteration[\s_-]?band)\s*:\s*(?P<value>[^,]+)",
            flags=re.IGNORECASE,
        )
        for match in pattern.finditer(freeform_text):
            raw_key = match.group("key")
            raw_value = match.group("value")
            key = re.sub(r"[\s_-]+", " ", raw_key.strip().lower())
            value = _normalize_start_control_value(raw_value)
            flag = _START_CONTROL_ALIASES.get(key)
            if flag and value:
                parsed_controls.extend([flag, value])
    return preserved, parsed_controls, bool(freeform_text)


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    tokens = list(argv or [])
    if not tokens:
        return tokens
    if tokens[0] not in {"start", "init"}:
        return tokens
    preserved, parsed_controls, saw_freeform = _extract_start_controls(tokens[1:])
    if saw_freeform and not parsed_controls:
        return tokens
    return [tokens[0], *preserved, *parsed_controls]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    argv = _normalize_argv(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Claude Code project CLI for Co-Scientist.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create a new run directory from a natural-language goal or imported brief.",
    )
    _add_start_arguments(init_parser)

    start_parser = subparsers.add_parser(
        "start",
        help="Create a new run directory and bootstrap it into the canonical host-agent pipeline.",
    )
    _add_start_arguments(start_parser)
    start_parser.add_argument("--skill", default="co-scientist-pipeline", choices=TOP_LEVEL_SKILLS)
    start_parser.add_argument("--no-dashboard", action="store_true", help="Skip dashboard runtime bootstrap.")

    run_parser = subparsers.add_parser("run", help="Bootstrap a fresh host-agent run.")
    run_parser.add_argument("run_target", type=Path, help="Run directory or compatibility config.yaml path.")
    run_parser.add_argument("--skill", default="co-scientist-pipeline", choices=TOP_LEVEL_SKILLS)
    run_parser.add_argument("--no-dashboard", action="store_true", help="Skip dashboard runtime bootstrap.")

    resume_parser = subparsers.add_parser("resume", help="Bootstrap a resumed host-agent run.")
    resume_parser.add_argument("run_dir", type=Path, help="Run directory to resume.")
    resume_parser.add_argument("--skill", default="co-scientist-pipeline", choices=TOP_LEVEL_SKILLS)
    resume_parser.add_argument("--no-dashboard", action="store_true", help="Skip dashboard runtime bootstrap.")

    validate_parser = subparsers.add_parser("validate", help="Validate one run directory.")
    validate_parser.add_argument("run_dir", type=Path, help="Run directory that contains the artifacts.")
    validate_parser.add_argument("--skill", default="co-scientist-pipeline", choices=TOP_LEVEL_SKILLS)
    validate_parser.add_argument("--resume", action="store_true", help="Use resume-mode validation.")

    dashboard_parser = subparsers.add_parser("dashboard", help="Ensure dashboard links for one run.")
    dashboard_parser.add_argument("run_dir", type=Path, help="Run directory to open in the dashboard.")

    doctor_parser = subparsers.add_parser("doctor", help="Run environment diagnostics for the current project.")
    doctor_parser.add_argument("--format", choices=("text", "json"), default="text")

    params_parser = subparsers.add_parser("params", help="Show the natural-language start parameters and examples.")
    params_parser.add_argument("--format", choices=("text", "json"), default="text")

    return parser.parse_args(argv)


def _add_start_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--goal", help="Natural-language research goal used to seed input.md.")
    parser.add_argument("--brief", type=Path, help="Optional Markdown or text brief to import into input.md.")
    parser.add_argument("--notes", type=Path, help="Optional notes file to append to the generated input.md.")
    parser.add_argument("--run-id", help="Optional explicit run directory name.")
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=default_runs_dir(),
        help="Parent directory where new run directories should be created.",
    )
    parser.add_argument("--exploration", choices=EXPLORATION_CHOICES)
    parser.add_argument("--generation-bias", choices=GENERATION_BIAS_CHOICES)
    parser.add_argument("--review", choices=REVIEW_CHOICES)
    parser.add_argument("--budget", choices=BUDGET_CHOICES)
    parser.add_argument("--evolution", choices=EVOLUTION_CHOICES)
    parser.add_argument("--stop-policy", choices=STOP_POLICY_CHOICES)
    parser.add_argument("--iteration-policy", choices=ITERATION_POLICY_CHOICES)
    parser.add_argument("--iteration-band", choices=ITERATION_BAND_CHOICES)
    parser.add_argument("--human-checkpoint", choices=HUMAN_CHECKPOINT_CHOICES)
    parser.add_argument("--interaction-mode", choices=INTERACTION_MODE_CHOICES)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Render the planned run summary without creating files or bootstrapping the pipeline.",
    )


def _created_run_payload(created_run: CreatedRunArtifacts) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "runDir": str(created_run.run_dir),
        "inputPath": str(created_run.input_path),
    }
    if created_run.config_path is not None:
        payload["configPath"] = str(created_run.config_path)
    if created_run.run_policy_path is not None:
        payload["runPolicyPath"] = str(created_run.run_policy_path)
    return payload


def _validate_iteration_controls(args: argparse.Namespace) -> None:
    iteration_policy = getattr(args, "iteration_policy", None)
    iteration_band = getattr(args, "iteration_band", None)
    if iteration_policy == "capped" and iteration_band is None:
        raise ValueError("`--iteration-band` is required when `--iteration-policy capped` is selected.")
    if iteration_policy == "completion_driven" and iteration_band is not None:
        raise ValueError("`--iteration-band` can be used only with `--iteration-policy capped`.")
    if iteration_policy is None and iteration_band is not None:
        args.iteration_policy = "capped"


def _run_init_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.goal is None and args.brief is None and args.notes is None:
        raise ValueError("`init` requires at least one of --goal, --brief, or --notes.")
    _validate_iteration_controls(args)

    preview = build_start_request_preview(
        goal=args.goal,
        brief_path=args.brief,
        notes_path=args.notes,
        run_id=args.run_id,
        runs_dir=args.runs_dir,
        interaction_mode=args.interaction_mode,
        exploration=args.exploration,
        generation_bias=args.generation_bias,
        review=args.review,
        budget=args.budget,
        evolution=args.evolution,
        stop_policy=args.stop_policy,
        iteration_policy=args.iteration_policy,
        iteration_band=args.iteration_band,
        human_checkpoint=args.human_checkpoint,
    )

    if args.summary_only:
        return {
            "command": "init",
            "summaryOnly": True,
            "runId": preview.run_id,
            "runDir": str(preview.run_dir),
            "interactionMode": preview.interaction_mode,
            "goal": preview.goal,
            "explicitControls": preview.explicit_controls,
            "effectiveControls": preview.effective_controls,
            "artifactsToCreate": list(preview.artifacts_to_create),
            "summary": render_start_summary(preview),
            "briefPath": str(preview.brief_path) if preview.brief_path is not None else "",
            "notesPath": str(preview.notes_path) if preview.notes_path is not None else "",
        }

    run_policy = build_run_policy_from_controls(
        input_file="input.md",
        exploration=args.exploration,
        generation_bias=args.generation_bias,
        review=args.review,
        budget=args.budget,
        evolution=args.evolution,
        stop_policy=args.stop_policy,
        iteration_policy=args.iteration_policy,
        iteration_band=args.iteration_band,
        human_checkpoint=args.human_checkpoint,
    )
    created_run = create_run_artifacts(
        goal=args.goal,
        brief_path=args.brief,
        notes_path=args.notes,
        runs_dir=args.runs_dir,
        run_id=preview.run_id,
        run_policy=run_policy,
        start_request=build_start_request_contract(preview),
    )
    payload = {"command": "init"}
    payload.update(_created_run_payload(created_run))
    return payload


def _run_bootstrap_command(
    run_target: Path,
    *,
    requested_skill: str,
    resume: bool,
    ensure_dashboard: bool,
) -> dict[str, Any]:
    result = bootstrap_host_agent_run(
        run_target,
        requested_skill=requested_skill,
        resume=resume,
        ensure_dashboard=ensure_dashboard,
    )
    token_usage = None
    thread_id = os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
    if thread_id:
        try:
            attach_run(result.run_dir, thread_id)
            token_usage = collect_usage(result.run_dir)
        except (OSError, ValueError):
            # Usage telemetry must not prevent scientific state bootstrap.
            token_usage = {"status": "unavailable"}
    return {
        "mode": "host-agent",
        "runDir": str(result.run_dir),
        "requestedSkill": requested_skill,
        "resume": resume,
        "handoffJson": str(result.handoff_json_path),
        "handoffMarkdown": str(result.handoff_markdown_path),
        "dashboard": result.dashboard_runtime,
        "dashboardLinks": result.dashboard_links,
        "validation": result.handoff.validation.model_dump(mode="json"),
        "tokenUsage": token_usage,
    }


def _run_start_command(args: argparse.Namespace) -> dict[str, Any]:
    init_payload = _run_init_command(args)
    if bool(init_payload.get("summaryOnly", False)):
        payload = dict(init_payload)
        payload["command"] = "start"
        return payload

    bootstrap_payload = _run_bootstrap_command(
        Path(init_payload["runDir"]),
        requested_skill=args.skill,
        resume=False,
        ensure_dashboard=not args.no_dashboard,
    )
    payload = dict(init_payload)
    payload["command"] = "start"
    payload.update(bootstrap_payload)
    return payload


def _run_validate_command(run_dir: Path, *, requested_skill: str, resume: bool) -> tuple[dict[str, Any], int]:
    summary = validate_run_artifacts(run_dir.resolve(), resume=resume, requested_skill=requested_skill)
    payload = summary.model_dump(mode="json")
    return payload, 0 if summary.status == "valid" else 1


def _run_dashboard_command(run_dir: Path) -> dict[str, Any]:
    resolved_run_dir = _resolve_run_dir(run_dir)
    settings = HostSettings.from_run_dir(resolved_run_dir)
    dashboard = ensure_dashboard_for_run(
        resolved_run_dir,
        top_k_limit=settings.ranking.tournament_top_k,
        wait_for_health=True,
    )
    return {"runDir": str(resolved_run_dir), "runtime": dashboard.runtime, "links": dashboard.links}


def _run_params_command(output_format: str) -> str:
    if output_format == "json":
        return json.dumps(build_start_parameters_payload(), indent=2)
    return render_start_parameters_text()


def _run_doctor_command(output_format: str) -> str:
    payload = collect_environment_doctor_payload(Path.cwd(), repo_root=Path(__file__).resolve().parents[2])
    if output_format == "json":
        return json.dumps(payload, indent=2)
    return render_environment_doctor_text(payload)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.host.claude_project_cli`."""
    args = _parse_args(argv)

    if args.command == "init":
        payload = _run_init_command(args)
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "start":
        payload = _run_start_command(args)
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "run":
        payload = _run_bootstrap_command(
            args.run_target,
            requested_skill=args.skill,
            resume=False,
            ensure_dashboard=not args.no_dashboard,
        )
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "resume":
        run_dir = _resolve_run_dir(args.run_dir)
        payload = _run_bootstrap_command(
            run_dir,
            requested_skill=args.skill,
            resume=True,
            ensure_dashboard=not args.no_dashboard,
        )
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "validate":
        payload, exit_code = _run_validate_command(
            _resolve_run_dir(args.run_dir), requested_skill=args.skill, resume=args.resume
        )
        print(json.dumps(payload, indent=2))
        return exit_code

    if args.command == "dashboard":
        payload = _run_dashboard_command(args.run_dir)
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "doctor":
        print(_run_doctor_command(args.format))
        return 0

    if args.command == "params":
        print(_run_params_command(args.format))
        return 0

    raise ValueError(f"Unsupported command: {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
