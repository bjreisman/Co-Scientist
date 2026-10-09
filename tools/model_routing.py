"""Resolve host-agent model policies and audit actual Codex dispatches; no LLM calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tomllib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from packages.agent_contracts.model_policy import ModelPolicyContract, TaskKind
from tools.token_usage import _records


REPO = Path(__file__).resolve().parents[1]
POLICY_NAME = ".co-scientist/model-policy.yaml"
TASK_SKILLS: dict[str, TaskKind] = {
    "research-config": "configuration",
    "evidence-extract": "evidence",
    **dict.fromkeys(
        ("hypothesis-generate-literature", "hypothesis-generate-debate", "hypothesis-generate-assumptions"),
        "generation",
    ),
    **dict.fromkeys(
        (
            "hypothesis-initial-review",
            "hypothesis-full-review",
            "hypothesis-deep-verification",
            "hypothesis-observation-review",
            "hypothesis-simulation-review",
            "hypothesis-review-summary",
            "hypothesis-review-pipeline",
        ),
        "review",
    ),
    **dict.fromkeys(("hypothesis-placement-tournament", "hypothesis-ranked-tournament"), "ranking"),
    **dict.fromkeys(
        (
            "evolution-strategy-supervisor",
            "hypothesis-evolve-grounding",
            "hypothesis-evolve-coherence",
            "hypothesis-evolve-feasibility",
            "hypothesis-evolve-simplification",
            "hypothesis-evolve-inspiration",
            "hypothesis-evolve-combination",
            "hypothesis-evolve-out-of-box",
        ),
        "evolution",
    ),
    **dict.fromkeys(("insights-from-reviews", "research-overview-pipeline"), "meta_review"),
}
AGENT_HEADER = "# Managed by Co-Scientist model routing. Edit model-policy.yaml and reinstall.\n"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_policy(path: Path) -> ModelPolicyContract:
    """Read a strict project policy, rejecting typos and deterministic skill overrides."""
    policy = ModelPolicyContract.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    unknown = set(policy.skill_overrides) - set(TASK_SKILLS)
    if unknown:
        raise ValueError(f"Unsupported scientific skill overrides: {sorted(unknown)}")
    return policy


def freeze_policy(run_dir: Path, *, project: Path | None = None) -> dict[str, Any] | None:
    """Capture policy once; resuming never silently changes model choices."""
    snapshot = run_dir / "state/MODEL_POLICY.json"
    if snapshot.exists():
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        ModelPolicyContract.model_validate(data["policy"])
        return data
    candidates = [project] if project is not None else [run_dir, *run_dir.resolve().parents]
    source = next((p / POLICY_NAME for p in candidates if p and (p / POLICY_NAME).is_file()), None)
    if source is None:
        return None  # Legacy/unconfigured runs keep their host inheritance behavior.
    policy = load_policy(source)
    data = {
        "version": 1,
        "source": str(source.resolve()),
        "capturedAt": _now(),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "policy": policy.model_dump(mode="json"),
    }
    _write(snapshot, data)
    return data


def resolve_task(run_dir: Path, skill: str, *, local: bool = False) -> dict[str, Any]:
    """Return an exact spawn request or a disclosed local fallback, never switch the main model."""
    if skill not in TASK_SKILLS:
        raise ValueError(f"{skill!r} is not a delegated scientific task; mechanics remain local Python tools.")
    snapshot = freeze_policy(run_dir)
    if snapshot is None:
        return {
            "skill": skill,
            "task": TASK_SKILLS[skill],
            "route": "local_main_thread",
            "reason": "No configured model policy; use host inheritance.",
            "requested": None,
        }
    policy = ModelPolicyContract.model_validate(snapshot["policy"])
    role = policy.skill_overrides.get(skill, policy.tasks[TASK_SKILLS[skill]])
    selected = policy.roles[role]
    if local and policy.enabled and policy.fallback == "stop":
        raise ValueError(
            "Model policy requires delegation; fallback=stop. Report unavailable agents without dispatch."
        )
    delegated = policy.enabled and not local
    agent_type = "co_scientist_" + role
    agent_path = Path(snapshot["source"]).parent.parent / ".codex/agents" / (agent_type + ".toml")
    # A role file wins over explicit spawn settings in Codex. Avoid using a
    # newly edited role file to override an older run's frozen request.
    if delegated:
        agent = tomllib.loads(agent_path.read_text(encoding="utf-8")) if agent_path.exists() else {}
        if agent.get("model") != selected.model or agent.get("model_reasoning_effort") != selected.reasoning_effort:
            agent_type = "default"
    return {
        "skill": skill,
        "task": TASK_SKILLS[skill],
        "role": role,
        "route": "codex_subagent" if delegated else "local_main_thread",
        "requested": {"model": selected.model, "reasoningEffort": selected.reasoning_effort},
        "spawn": {
            "agent_type": agent_type,
            "model": selected.model,
            "reasoning_effort": selected.reasoning_effort,
            "fork_turns": "none",
        }
        if delegated
        else None,
        "maxConcurrentSubagents": policy.max_concurrent_subagents,
        "reason": "Configured task role."
        if delegated
        else "Delegation disabled or explicit local fallback; host settings apply.",
    }


def begin_dispatch(run_dir: Path, skill: str, *, local: bool = False, hypothesis_id: str = "") -> dict[str, Any]:
    """Persist requested settings before the host spawns a child."""
    route = resolve_task(run_dir, skill, local=local)
    record = {
        **route,
        "id": str(uuid.uuid4()),
        "hypothesisId": hypothesis_id,
        "status": "planned",
        "createdAt": _now(),
        "observed": [],
        "verification": "unverified",
        "sessionId": None,
        "parentSessionId": os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID"),
    }
    _write(run_dir / "state/model_dispatches" / (record["id"] + ".json"), record)
    refresh_summary(run_dir)
    return record


def observed_settings(session_id: str, *, codex_home: Path | None = None, since: str = "") -> list[dict[str, Any]]:
    """Read only model/effort metadata for an exact session; do not copy conversation text."""
    home = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    observed: list[dict[str, Any]] = []
    for directory in (home / "sessions", home / "archived_sessions"):
        for path in directory.rglob("*.jsonl"):
            try:
                first = next(_records(path), {})
                if first.get("type") != "session_meta" or first.get("payload", {}).get("id") != session_id:
                    continue
                for record in _records(path):
                    if record.get("type") != "turn_context":
                        continue
                    timestamp = record.get("timestamp", "")
                    if since and (
                        not timestamp
                        or datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        < datetime.fromisoformat(since.replace("Z", "+00:00"))
                    ):
                        continue
                    p = record.get("payload", {})
                    effort = p.get("effort") or p.get("reasoning_effort") or p.get("model_reasoning_effort")
                    setting = {"model": p.get("model"), "reasoningEffort": effort}
                    if setting["model"] and setting not in observed:
                        observed.append(setting)
            except (OSError, ValueError, UnicodeError):
                continue
    return observed


def finish_dispatch(
    run_dir: Path,
    dispatch_id: str,
    *,
    session_id: str,
    status: str = "completed",
    findings: str = "",
    codex_home: Path | None = None,
) -> dict[str, Any]:
    """Verify an executed request against rollout metadata, preserving missing evidence as unknown."""
    uuid.UUID(dispatch_id)
    if status not in {"completed", "failed", "unavailable"}:
        raise ValueError("Invalid dispatch status.")
    path = run_dir / "state/model_dispatches" / (dispatch_id + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["status"] != "planned":
        raise ValueError("Dispatch already closed; start a new receipt for a retry.")
    if status == "completed" and not session_id:
        raise ValueError("Completed dispatches require the actual child or local host session ID.")
    # Never verify a child using the parent's matching model settings.
    if record["route"] == "codex_subagent" and session_id and session_id == record.get("parentSessionId"):
        raise ValueError("A delegated dispatch must reference the child session, not the parent.")
    observed = observed_settings(session_id, codex_home=codex_home, since=record["createdAt"]) if session_id else []
    record.update(
        status=status, sessionId=session_id or None, observed=observed, findingsArtifact=findings, finishedAt=_now()
    )
    requested = record.get("requested")
    if record["route"] == "codex_subagent" and requested and observed:
        if any(
            o["model"] != requested["model"]
            or (o["reasoningEffort"] is not None and o["reasoningEffort"] != requested["reasoningEffort"])
            for o in observed
        ):
            record["verification"] = "mismatch"
        elif all(o["reasoningEffort"] is not None for o in observed):
            record["verification"] = "verified"
        else:
            record["verification"] = "model_only"
    else:
        record["verification"] = "local_observed" if observed else "unverified"
    _write(path, record)
    refresh_summary(run_dir)
    return record


def refresh_summary(run_dir: Path) -> dict[str, Any]:
    """Publish dashboard routing metadata without conversation content."""
    policy_path = run_dir / "state/MODEL_POLICY.json"
    snapshot = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else None
    dispatches = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted((run_dir / "state/model_dispatches").glob("*.json"))
    ]
    data = {"version": 1, "updatedAt": _now(), "policy": snapshot, "dispatches": dispatches}
    _write(run_dir / "state/MODEL_ROUTING.json", data)
    return data


def install_policy(project: Path, *, policy_path: Path | None = None) -> dict[str, Any]:
    """Install role files, preserving unrelated config and refusing to overwrite unmanaged agents."""
    project = project.resolve()
    target = project / POLICY_NAME
    source = policy_path or (target if target.exists() else REPO / "templates/codex/model-policy.yaml")
    policy = load_policy(source)
    config_path = project / ".codex/config.toml"
    existing_config = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    if existing_config is not None:
        tomllib.loads(existing_config)  # Fail before any writes on malformed user config.
    files: dict[Path, str] = {}
    for role, settings in policy.roles.items():
        name = "co_scientist_" + role
        path = project / ".codex/agents" / (name + ".toml")
        if path.exists() and not path.read_text(encoding="utf-8").startswith(AGENT_HEADER):
            raise ValueError(f"Refusing to replace unmanaged agent file: {path}")
        description = f"Co-Scientist {role}; execute only the assigned scientific skill contract."
        instructions = (
            "Perform only the assigned task using the supplied canonical skill, research plan and evidence. "
            "You are not alone in this project; do not revert others' work. Do not spawn further agents. "
            "Return contract-shaped advisory findings and traceable citations to the parent. "
            "Do not write canonical artifacts, run mechanics, invent retrievals or select a different task. "
            "Use only the parent's assigned evidence and source-access scope. "
            "Clearly label observations versus conjectures."
        )
        files[path] = (
            AGENT_HEADER
            + "\n".join(
                f"{k} = {json.dumps(v)}"
                for k, v in {
                    "name": name,
                    "description": description,
                    "model": settings.model,
                    "model_reasoning_effort": settings.reasoning_effort,
                    "sandbox_mode": "read-only",
                    "developer_instructions": instructions,
                }.items()
            )
            + "\n"
        )
    if not target.exists() or source.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(policy.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if existing_config is None:
        config_path.write_text(
            "# Project defaults; role files override settings for delegated scientific tasks.\n"
            'model = "gpt-6.1-sol"\nmodel_reasoning_effort = "medium"\n\n'
            '[agents]\ndefault_subagent_model = "gpt-6-luna"\n'
            'default_subagent_reasoning_effort = "medium"\n'
            f"max_concurrent_threads_per_session = {policy.max_concurrent_subagents}\n",
            encoding="utf-8",
        )
    return {
        "policyPath": str(target),
        "agentFiles": [str(p) for p in files],
        "configPath": str(config_path),
        "configPreserved": existing_config is not None,
        "note": "Reload Codex project configuration to discover new roles; existing chats may retain live settings.",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install")
    install.add_argument("--project", type=Path, required=True)
    install.add_argument("--policy", type=Path)
    for command in ("show", "resolve", "begin", "record"):
        p = commands.add_parser(command)
        p.add_argument("run_dir", type=Path)
        if command in {"resolve", "begin"}:
            p.add_argument("--skill", required=True)
            p.add_argument("--local", action="store_true")
        if command == "begin":
            p.add_argument("--hypothesis-id", default="")
        if command == "record":
            p.add_argument("--dispatch-id", required=True)
            p.add_argument("--session-id", default="")
            p.add_argument("--status", choices=("completed", "failed", "unavailable"), default="completed")
            p.add_argument("--findings", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI for installation, policy resolution and host dispatch audit."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            result = install_policy(args.project, policy_path=args.policy)
        else:
            if not args.run_dir.is_dir():
                raise ValueError("Run directory does not exist.")
            if args.command == "show":
                freeze_policy(args.run_dir)
                result = refresh_summary(args.run_dir)
            elif args.command == "resolve":
                result = resolve_task(args.run_dir, args.skill, local=args.local)
            elif args.command == "begin":
                result = begin_dispatch(args.run_dir, args.skill, local=args.local, hypothesis_id=args.hypothesis_id)
            else:
                result = finish_dispatch(
                    args.run_dir,
                    args.dispatch_id,
                    session_id=args.session_id,
                    status=args.status,
                    findings=args.findings,
                )
    except (ValueError, OSError) as exc:
        parser.exit(2, f"model routing: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
