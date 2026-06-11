"""Verify the Codex integration surface without launching Codex."""

from __future__ import annotations

import argparse
import json
import tomllib
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from tools.install.codex_install import install_codex_project
from tools.install.environment_doctor import collect_environment_doctor_payload


CheckStatus = Literal["pass", "fail"]


REQUIRED_PATHS = {
    "neutral_project_cli": "tools/host/project_cli.py",
    "codex_installer": "tools/install/codex_install.py",
    "codex_entry_start": "skills/skills-codex-entry/co-scientist-start/SKILL.md",
    "codex_entry_run": "skills/skills-codex-entry/co-scientist-run/SKILL.md",
    "codex_entry_resume": "skills/skills-codex-entry/co-scientist-resume/SKILL.md",
    "search_bridge_server": "mcp-servers/search-bridge/server.py",
    "search_bridge_config_template": "templates/codex/config.toml.example",
    "reviewer_template": "templates/codex/co-scientist-reviewer.toml.example",
}


def _check(name: str, status: CheckStatus, summary: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "summary": summary, "details": details or {}}


def _load_toml_template(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def verify_codex_integration_surface(repo_root: Path) -> dict[str, Any]:
    """Run Codex integration checks that do not invoke the Codex executable."""
    repo_root = repo_root.resolve()
    checks: list[dict[str, Any]] = []

    for name, relative_path in REQUIRED_PATHS.items():
        path = repo_root / relative_path
        checks.append(
            _check(
                name,
                "pass" if path.exists() else "fail",
                f"{relative_path} exists." if path.exists() else f"{relative_path} is missing.",
                {"path": str(path)},
            )
        )

    try:
        search_config = _load_toml_template(repo_root / "templates" / "codex" / "config.toml.example")
        search_server = search_config["mcp_servers"]["co_scientist_search_bridge"]
        search_config_ok = "mcp-servers/search-bridge/server.py" in search_server["args"]
    except (OSError, KeyError, tomllib.TOMLDecodeError, TypeError) as exc:
        search_config_ok = False
        search_config_error = f"{exc.__class__.__name__}: {exc}"
    else:
        search_config_error = ""
    checks.append(
        _check(
            "search_bridge_config_parse",
            "pass" if search_config_ok else "fail",
            "Codex search bridge config template is parseable."
            if search_config_ok
            else "Codex search bridge config template is invalid.",
            {"error": search_config_error},
        )
    )

    try:
        reviewer_config = _load_toml_template(repo_root / "templates" / "codex" / "co-scientist-reviewer.toml.example")
        reviewer_config_ok = reviewer_config["name"] == "co-scientist-reviewer"
    except (OSError, KeyError, tomllib.TOMLDecodeError, TypeError) as exc:
        reviewer_config_ok = False
        reviewer_config_error = f"{exc.__class__.__name__}: {exc}"
    else:
        reviewer_config_error = ""
    checks.append(
        _check(
            "reviewer_template_parse",
            "pass" if reviewer_config_ok else "fail",
            "Codex reviewer template is parseable." if reviewer_config_ok else "Codex reviewer template is invalid.",
            {"error": reviewer_config_error},
        )
    )

    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "project"
        project_root.mkdir()
        install_result = install_codex_project(
            project_root=project_root,
            repo_root=repo_root,
            action="install",
            include_search_bridge_config=True,
        )
        doctor_payload = collect_environment_doctor_payload(project_root, repo_root=repo_root)
        doctor_checks = {check["name"]: check for check in doctor_payload["checks"]}
        codex_install_status = doctor_checks.get("project-codex-skill-install", {}).get("status")
        codex_mirror_status = doctor_checks.get("project-codex-skill-mirror", {}).get("status")
        project_codex_dir = project_root / ".codex"

        checks.append(
            _check(
                "temporary_install_surface",
                "pass" if codex_install_status == "pass" and codex_mirror_status == "pass" else "fail",
                "Temporary Codex install surface passes doctor and parity checks."
                if codex_install_status == "pass" and codex_mirror_status == "pass"
                else "Temporary Codex install surface failed doctor or parity checks.",
                {"installStatus": codex_install_status, "mirrorStatus": codex_mirror_status},
            )
        )
        checks.append(
            _check(
                "no_project_codex_directory",
                "pass" if not project_codex_dir.exists() else "fail",
                "Temporary install did not create a project .codex directory."
                if not project_codex_dir.exists()
                else "Temporary install created a project .codex directory.",
                {"path": str(project_codex_dir)},
            )
        )
        checks.append(
            _check(
                "search_bridge_config_output",
                "pass"
                if "[mcp_servers.co_scientist_search_bridge]" in install_result.search_bridge_config
                else "fail",
                "Installer can emit the search bridge config template without writing project Codex config."
                if "[mcp_servers.co_scientist_search_bridge]" in install_result.search_bridge_config
                else "Installer did not emit the search bridge config template.",
            )
        )

        install_codex_project(project_root=project_root, repo_root=repo_root, action="uninstall")

    status: CheckStatus = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    return {"status": status, "repoRoot": str(repo_root), "checks": checks}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Codex integration surface without launching Codex.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.validation.verify_codex_integration_surface`."""
    args = _parse_args(argv)
    payload = verify_codex_integration_surface(args.repo_root)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
