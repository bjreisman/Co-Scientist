"""Environment diagnostics for Co-Scientist project-local usage."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .claude_install import collect_claude_skill_mirror_parity
from .codex_install import MANAGED_BLOCK_BEGIN as CODEX_MANAGED_BLOCK_BEGIN
from .codex_install import collect_codex_skill_mirror_parity


CheckStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class DoctorCheck:
    """One environment or installation check."""

    name: str
    status: CheckStatus
    summary: str
    hint: str = ""
    details: dict[str, Any] | None = None


def _safe_run(command: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(  # noqa: S603 - commands are built from fixed diagnostic checks.
            command,
            cwd=str(cwd) if cwd is not None else None,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return False, str(exc)
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output


def _importable(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except Exception:
        return False
    return True


def _python_file_importable(path: Path, module_name: str) -> tuple[bool, str]:
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return False, "Could not create an import spec."
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
    return True, ""


def collect_environment_doctor_payload(project_root: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Collect a stable environment diagnostic payload."""
    project_root = project_root.resolve()
    repo_root = (repo_root or project_root).resolve()
    checks: list[DoctorCheck] = []

    python_ok = sys.version_info >= (3, 12)
    checks.append(
        DoctorCheck(
            name="python",
            status="pass" if python_ok else "fail",
            summary=f"Python {sys.version.split()[0]} detected.",
            hint="" if python_ok else "Use Python 3.12 or newer for the supported host-agent runtime.",
            details={"executable": sys.executable},
        )
    )

    required_modules = ("yaml", "pydantic", "numpy")
    missing_modules = [name for name in required_modules if not _importable(name)]
    checks.append(
        DoctorCheck(
            name="python-deps",
            status="pass" if not missing_modules else "fail",
            summary="Runtime Python dependencies are importable."
            if not missing_modules
            else f"Missing Python modules: {', '.join(missing_modules)}.",
            hint=""
            if not missing_modules
            else (
                "Install project dependencies in your current environment, for example "
                "`uv sync --extra dev --extra mcp` or `pip install -e .[dev]`."
            ),
            details={"required": list(required_modules), "missing": missing_modules},
        )
    )

    embedding_provider = os.environ.get("CO_SCIENTIST_EMBEDDING_PROVIDER", "openai_compatible").strip().lower()
    if embedding_provider == "gemini":
        gemini_importable = _importable("google.genai")
        gemini_key_env = os.environ.get("CO_SCIENTIST_EMBEDDING_API_KEY_ENV", "GEMINI_API_KEY").strip()
        gemini_key_env = gemini_key_env or "GEMINI_API_KEY"
        gemini_key_present = bool(os.environ.get(gemini_key_env, "").strip())
        gemini_ready = gemini_importable and gemini_key_present
        checks.append(
            DoctorCheck(
                name="gemini-embedding-provider",
                status="pass" if gemini_ready else "warn",
                summary="Gemini embedding provider is ready."
                if gemini_ready
                else "Gemini embedding provider is selected but not fully ready.",
                hint=""
                if gemini_ready
                else (
                    "Install the `google-genai` package with `uv sync --extra gemini` and set "
                    f"`{gemini_key_env}` before starting a run."
                ),
                details={
                    "provider": embedding_provider,
                    "module": "google.genai",
                    "moduleImportable": gemini_importable,
                    "apiKeyEnv": gemini_key_env,
                    "apiKeyPresent": gemini_key_present,
                },
            )
        )

    active_env = {
        "conda": (sys.prefix if bool(sys.prefix) else ""),
        "condaEnv": str(os.environ.get("CONDA_DEFAULT_ENV", "")),
        "virtualEnv": str(os.environ.get("VIRTUAL_ENV", "")),
    }
    env_active = bool(active_env["condaEnv"] or active_env["virtualEnv"])
    checks.append(
        DoctorCheck(
            name="python-env",
            status="pass" if env_active else "warn",
            summary="An isolated Python environment is active."
            if env_active
            else "No active conda/virtualenv detected.",
            hint=""
            if env_active
            else "Prefer launching Claude Code from the target environment or use `conda run -n <env> python ...`.",
            details=active_env,
        )
    )

    node_path = shutil.which("node")
    pnpm_path = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    node_ok, node_output = _safe_run([node_path, "--version"]) if node_path else (False, "")
    pnpm_ok, pnpm_output = _safe_run([pnpm_path, "--version"]) if pnpm_path else (False, "")
    dashboard_tooling_ok = node_ok and pnpm_ok
    checks.append(
        DoctorCheck(
            name="dashboard-tooling",
            status="pass" if dashboard_tooling_ok else "fail",
            summary="Node.js and pnpm are available for the dashboard."
            if dashboard_tooling_ok
            else "Node.js or pnpm is missing for the dashboard.",
            hint=""
            if dashboard_tooling_ok
            else "Install Node.js and pnpm, then run `pnpm --dir apps/dashboard install`.",
            details={"node": node_output, "pnpm": pnpm_output},
        )
    )

    dashboard_root = repo_root / "apps" / "dashboard"
    node_modules_exists = (dashboard_root / "node_modules").exists()
    output_exists = (dashboard_root / ".output").exists()
    checks.append(
        DoctorCheck(
            name="dashboard-install",
            status="pass" if node_modules_exists else "warn",
            summary="Dashboard npm dependencies are installed."
            if node_modules_exists
            else "Dashboard npm dependencies are not installed yet.",
            hint="" if node_modules_exists else "Run `pnpm --dir apps/dashboard install` before using the dashboard.",
            details={"nodeModules": node_modules_exists, "buildWarm": output_exists},
        )
    )

    build_status: CheckStatus = "pass" if output_exists else "warn"
    build_summary = (
        "Dashboard build artifacts are present; preview startup should be faster."
        if output_exists
        else "Dashboard build artifacts are missing; first startup will fall back to dev mode."
    )
    checks.append(
        DoctorCheck(
            name="dashboard-build",
            status=build_status,
            summary=build_summary,
            hint=""
            if output_exists
            else "Optional: run `pnpm --dir apps/dashboard build` to warm the dashboard preview server.",
        )
    )

    codex_path = shutil.which("codex") or shutil.which("codex.cmd")
    checks.append(
        DoctorCheck(
            name="codex-cli",
            status="pass" if codex_path else "warn",
            summary="Codex CLI is available in PATH." if codex_path else "Codex CLI is not available in PATH.",
            hint=""
            if codex_path
            else "Install or launch Codex separately if you want to use the Codex skill surface.",
            details={"executable": codex_path or ""},
        )
    )

    search_bridge_server = repo_root / "mcp-servers" / "search-bridge" / "server.py"
    search_bridge_importable = False
    search_bridge_error = "server.py not found"
    if search_bridge_server.is_file():
        search_bridge_importable, search_bridge_error = _python_file_importable(
            search_bridge_server,
            "co_scientist_search_bridge_mcp_server_doctor",
        )
    checks.append(
        DoctorCheck(
            name="search-bridge-mcp-server",
            status="pass" if search_bridge_importable else "warn",
            summary="Literature search MCP server module is importable."
            if search_bridge_importable
            else "Literature search MCP server module is not importable.",
            hint=""
            if search_bridge_importable
            else (
                "Install optional MCP dependencies with `uv sync --extra mcp` and check "
                "mcp-servers/search-bridge/server.py."
            ),
            details={"path": str(search_bridge_server), "error": search_bridge_error},
        )
    )

    installed_manifest = project_root / ".co-scientist" / "installed-skills.json"
    claude_skill_root = project_root / ".claude" / "skills"
    installed = installed_manifest.exists() and (claude_skill_root / "co-scientist-start" / "SKILL.md").exists()
    checks.append(
        DoctorCheck(
            name="project-skill-install",
            status="pass" if installed else "warn",
            summary="Project-local Claude Code skills are installed."
            if installed
            else "Project-local Claude Code skills are not installed yet.",
            hint=""
            if installed
            else (
                "Run `powershell -File tools/install/install_co_scientist.ps1` or "
                "`bash tools/install/install_co_scientist.sh` from the repository root."
            ),
            details={"manifest": str(installed_manifest), "skillRoot": str(claude_skill_root)},
        )
    )
    if installed:
        mirror_parity = collect_claude_skill_mirror_parity(project_root=project_root, repo_root=repo_root)
        parity_clean = not (
            mirror_parity["missingFiles"] or mirror_parity["mismatchedFiles"] or mirror_parity["extraFiles"]
        )
        checks.append(
            DoctorCheck(
                name="project-skill-mirror",
                status="pass" if parity_clean else "warn",
                summary="Project-local Claude Code skill mirror matches the canonical repository skills."
                if parity_clean
                else "Project-local Claude Code skill mirror is stale relative to the canonical repository skills.",
                hint=""
                if parity_clean
                else (
                    "Run `powershell -File tools/install/install_co_scientist.ps1` or "
                    "`bash tools/install/install_co_scientist.sh` to refresh `.claude/skills`."
                ),
                details={
                    "skillRoot": str(claude_skill_root),
                    **mirror_parity,
                },
            )
        )

    codex_manifest = project_root / ".co-scientist" / "installed-codex-skills.json"
    codex_skill_root = project_root / ".agents" / "skills"
    agents_md_path = project_root / "AGENTS.md"
    agents_md_has_managed_block = agents_md_path.exists() and CODEX_MANAGED_BLOCK_BEGIN in agents_md_path.read_text(
        encoding="utf-8"
    )
    codex_installed = (
        codex_manifest.exists()
        and (codex_skill_root / "co-scientist-start" / "SKILL.md").exists()
        and agents_md_has_managed_block
    )
    checks.append(
        DoctorCheck(
            name="project-codex-skill-install",
            status="pass" if codex_installed else "warn",
            summary="Project-local Codex skills are installed."
            if codex_installed
            else "Project-local Codex skills are not installed yet.",
            hint=""
            if codex_installed
            else (
                "Run `powershell -File tools/install/install_co_scientist_codex.ps1` or "
                "`bash tools/install/install_co_scientist_codex.sh` from the repository root."
            ),
            details={
                "manifest": str(codex_manifest),
                "skillRoot": str(codex_skill_root),
                "agentsMd": str(agents_md_path),
                "agentsMdManagedBlock": agents_md_has_managed_block,
            },
        )
    )
    if codex_installed:
        codex_mirror_parity = collect_codex_skill_mirror_parity(project_root=project_root, repo_root=repo_root)
        codex_parity_clean = not (
            codex_mirror_parity["missingFiles"]
            or codex_mirror_parity["mismatchedFiles"]
            or codex_mirror_parity["extraFiles"]
        )
        checks.append(
            DoctorCheck(
                name="project-codex-skill-mirror",
                status="pass" if codex_parity_clean else "warn",
                summary="Project-local Codex skill mirror matches the canonical repository skills."
                if codex_parity_clean
                else "Project-local Codex skill mirror is stale relative to the canonical repository skills.",
                hint=""
                if codex_parity_clean
                else (
                    "Run `powershell -File tools/install/install_co_scientist_codex.ps1` or "
                    "`bash tools/install/install_co_scientist_codex.sh` to refresh `.agents/skills`."
                ),
                details={
                    "skillRoot": str(codex_skill_root),
                    **codex_mirror_parity,
                },
            )
        )

    runs_dir = project_root / "runs"
    checks.append(
        DoctorCheck(
            name="runs-dir",
            status="pass" if runs_dir.exists() else "warn",
            summary="`runs/` directory exists." if runs_dir.exists() else "`runs/` directory does not exist yet.",
            hint="" if runs_dir.exists() else "The directory will be created automatically on the first start.",
            details={"path": str(runs_dir)},
        )
    )

    overall: CheckStatus = "pass"
    if any(check.status == "fail" for check in checks):
        overall = "fail"
    elif any(check.status == "warn" for check in checks):
        overall = "warn"

    return {
        "status": overall,
        "projectRoot": str(project_root),
        "repoRoot": str(repo_root),
        "checks": [asdict(check) for check in checks],
        "recommendedCommands": {
            "uvQuickstart": "uv sync --extra dev --extra mcp",
            "installSkillsWindows": "powershell -File tools/install/install_co_scientist.ps1",
            "installSkillsUnix": "bash tools/install/install_co_scientist.sh",
            "installCodexSkillsWindows": "powershell -File tools/install/install_co_scientist_codex.ps1",
            "installCodexSkillsUnix": "bash tools/install/install_co_scientist_codex.sh",
            "doctor": "python -m tools.host.project_cli doctor",
            "showStartParams": "python -m tools.host.project_cli params",
            "completionDrivenStartExample": (
                'python -m tools.host.project_cli start --goal "<goal>" --iteration-policy completion_driven'
            ),
            "cappedStartExample": (
                'python -m tools.host.project_cli start --goal "<goal>" --budget low '
                "--iteration-policy capped --iteration-band 6_10"
            ),
            "validateArtifacts": (
                "python -m tools.validation.contract_validation <run-dir> --skill co-scientist-pipeline"
            ),
            "verifyCompletion": (
                "python -m tools.validation.verify_pipeline_completion <run-dir> --skill co-scientist-pipeline"
            ),
            "installDashboardDeps": "pnpm --dir apps/dashboard install",
            "warmDashboardBuild": "pnpm --dir apps/dashboard build",
            "resolveDashboardLinks": "python -m tools.host.project_cli dashboard <run-dir>",
        },
    }


def render_environment_doctor_text(payload: dict[str, Any]) -> str:
    """Render a concise human-readable environment diagnostic summary."""
    lines = [
        "Co-Scientist environment doctor",
        "",
        f"- status: {payload['status']}",
        f"- project root: {payload['projectRoot']}",
        "",
        "Checks:",
    ]
    for check in payload["checks"]:
        lines.append(f"- [{check['status']}] {check['name']}: {check['summary']}")
        hint = check.get("hint") or ""
        if hint:
            lines.append(f"  hint: {hint}")
    lines.extend(
        [
            "",
            "Recommended commands:",
            f"- uv quickstart: {payload['recommendedCommands']['uvQuickstart']}",
            f"- install project skills (Windows): {payload['recommendedCommands']['installSkillsWindows']}",
            f"- install project skills (Unix): {payload['recommendedCommands']['installSkillsUnix']}",
            f"- install Codex project skills (Windows): {payload['recommendedCommands']['installCodexSkillsWindows']}",
            f"- install Codex project skills (Unix): {payload['recommendedCommands']['installCodexSkillsUnix']}",
            f"- doctor: {payload['recommendedCommands']['doctor']}",
            f"- show start parameters: {payload['recommendedCommands']['showStartParams']}",
            f"- completion-driven start example: {payload['recommendedCommands']['completionDrivenStartExample']}",
            f"- capped start example: {payload['recommendedCommands']['cappedStartExample']}",
            f"- validate artifacts: {payload['recommendedCommands']['validateArtifacts']}",
            f"- verify completion: {payload['recommendedCommands']['verifyCompletion']}",
            f"- dashboard deps: {payload['recommendedCommands']['installDashboardDeps']}",
            f"- warm dashboard build: {payload['recommendedCommands']['warmDashboardBuild']}",
            f"- resolve ready dashboard links: {payload['recommendedCommands']['resolveDashboardLinks']}",
            "",
            "Iteration control model:",
            "- `budget` controls per-round intensity.",
            "- `iteration-policy` decides whether the run stops by semantic completion or by a user-chosen cap.",
            "- `iteration-band` is valid only for capped runs.",
            "- `stop-policy` adjusts how readily convergence should stop the run.",
            "- `human-checkpoint` decides when the operator should be asked to confirm continuation; "
            "`completion_driven` plus `auto` should not pause after every evolution round.",
            "- `inspect_state` or `validation blocked` means artifacts disagree and should be repaired before "
            "overview or resume.",
            "",
            "Dashboard usage:",
            "- `start`, `run`, and `resume` try a background dashboard bootstrap.",
            "- Use `runs/<run_id>/dashboard/LINKS.md` as the human-readable dashboard receipt.",
            "- Run the ready-link resolver when a bootstrap only returns `dashboard.status = starting`.",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.install.environment_doctor`."""
    parser = argparse.ArgumentParser(description="Run Co-Scientist environment diagnostics.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = collect_environment_doctor_payload(args.project_root, repo_root=args.repo_root)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_environment_doctor_text(payload))
    return 0


__all__ = [
    "DoctorCheck",
    "collect_environment_doctor_payload",
    "main",
    "render_environment_doctor_text",
]


if __name__ == "__main__":
    raise SystemExit(main())
