"""Resolve deterministic numeric run configuration from the effective run policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.append(str(_REPO_ROOT))
    from packages.agent_contracts import ResolvedRunConfigContract  # type: ignore[no-redef]
    from packages.agent_support import resolve_run_config  # type: ignore[no-redef]
    from packages.run_artifacts import ArtifactStore  # type: ignore[no-redef]
    from tools.host.host_config import HostSettings  # type: ignore[no-redef]
else:
    from packages.agent_contracts import ResolvedRunConfigContract
    from packages.agent_support import resolve_run_config
    from packages.run_artifacts import ArtifactStore

    from ..host.host_config import HostSettings


def resolve_run_config_for_path(run_target: Path) -> ResolvedRunConfigContract:
    """Resolve and persist the effective numeric run config for one run."""
    settings = HostSettings.from_path(run_target)
    run_dir = Path(settings.run_dir).resolve()
    resolved = resolve_run_config(settings.run_policy, settings.raw_config)
    artifact_store = ArtifactStore(run_dir, top_k_limit=resolved.ranking.tournament_top_k)
    artifact_store.ensure_layout()
    artifact_store.write_resolved_run_config(resolved)
    return resolved


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve deterministic Co-Scientist numeric configuration from RUN_POLICY.yaml and optional "
            "compatibility config."
        )
    )
    parser.add_argument("run_target", type=Path, help="Run directory or compatibility config.yaml path.")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the resolved config payload.",
    )
    return parser.parse_args(argv)


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the resolved-config resolver CLI and return a process exit code."""
    args = _parse_args(argv)
    run_target = args.run_target.resolve()
    if not run_target.exists():
        print(f"Run target not found: {run_target}", file=sys.stderr)
        return 2

    resolved = resolve_run_config_for_path(run_target)
    payload = resolved.model_dump(mode="json")
    if args.json_out is not None:
        args.json_out.resolve().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.policy.resolve_run_config`."""
    try:
        return run_cli(argv)
    except Exception as exc:
        print(f"Resolved config execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
