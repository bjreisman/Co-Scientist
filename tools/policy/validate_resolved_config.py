"""Validate resolved numeric run configuration artifacts."""

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
    from packages.agent_support import validate_resolved_config_bounds  # type: ignore[no-redef]
else:
    from packages.agent_contracts import ResolvedRunConfigContract
    from packages.agent_support import validate_resolved_config_bounds


def validate_resolved_config_for_run(run_dir: Path) -> tuple[ResolvedRunConfigContract, list[str]]:
    """Load and validate the resolved config artifact for one run directory."""
    artifact_path = run_dir.resolve() / "state" / "RESOLVED_RUN_CONFIG.json"
    resolved = ResolvedRunConfigContract.from_json_file(artifact_path)
    return resolved, validate_resolved_config_bounds(resolved)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Co-Scientist state/RESOLVED_RUN_CONFIG.json for one run directory."
    )
    parser.add_argument(
        "run_dir", type=Path, help="Path to the run directory that contains state/RESOLVED_RUN_CONFIG.json."
    )
    return parser.parse_args(argv)


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the resolved-config validator CLI and return a process exit code."""
    args = _parse_args(argv)
    run_dir = args.run_dir.resolve()
    if not run_dir.exists():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        return 2

    try:
        resolved, issues = validate_resolved_config_for_run(run_dir)
    except FileNotFoundError:
        print(f"Resolved config artifact not found under: {run_dir}", file=sys.stderr)
        return 2

    payload = {
        "status": "valid" if not issues else "invalid",
        "issues": issues,
        "resolvedConfig": resolved.model_dump(mode="json"),
    }
    print(json.dumps(payload, indent=2))
    return 0 if not issues else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.policy.validate_resolved_config`."""
    try:
        return run_cli(argv)
    except Exception as exc:
        print(f"Resolved config validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
