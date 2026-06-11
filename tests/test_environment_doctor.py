from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.install.claude_install import install_claude_project
from tools.install.codex_install import install_codex_project
from tools.install.environment_doctor import collect_environment_doctor_payload, render_environment_doctor_text


def _build_source_repo(repo_root: Path) -> None:
    (repo_root / "skills" / "co-scientist-pipeline").mkdir(parents=True)
    (repo_root / "skills" / "co-scientist-pipeline" / "SKILL.md").write_text(
        "# co-scientist-pipeline\n",
        encoding="utf-8",
    )
    (repo_root / "skills" / "shared-references").mkdir(parents=True)
    (repo_root / "skills" / "shared-references" / "artifact-contract.md").write_text(
        "# Artifact Contract\n",
        encoding="utf-8",
    )
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-start").mkdir(parents=True)
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-start" / "SKILL.md").write_text(
        "# co-scientist-start\n",
        encoding="utf-8",
    )
    (repo_root / "skills" / "skills-codex-entry" / "co-scientist-start").mkdir(parents=True)
    (repo_root / "skills" / "skills-codex-entry" / "co-scientist-start" / "SKILL.md").write_text(
        "---\nname: co-scientist-start\ndescription: Start a run.\n---\n\n# co-scientist-start\n",
        encoding="utf-8",
    )


def test_environment_doctor_collects_stable_payload() -> None:
    payload = collect_environment_doctor_payload(Path(__file__).resolve().parents[1])

    assert payload["status"] in {"pass", "warn", "fail"}
    assert payload["projectRoot"]
    assert any(check["name"] == "dashboard-tooling" for check in payload["checks"])
    assert any(check["name"] == "search-bridge-mcp-server" for check in payload["checks"])
    assert "doctor" in payload["recommendedCommands"]
    assert "uvQuickstart" in payload["recommendedCommands"]
    assert "resolveDashboardLinks" in payload["recommendedCommands"]
    assert "showStartParams" in payload["recommendedCommands"]
    assert "installCodexSkillsWindows" in payload["recommendedCommands"]
    assert "installCodexSkillsUnix" in payload["recommendedCommands"]
    assert "completionDrivenStartExample" in payload["recommendedCommands"]
    assert "cappedStartExample" in payload["recommendedCommands"]
    assert "validateArtifacts" in payload["recommendedCommands"]
    assert "verifyCompletion" in payload["recommendedCommands"]
    assert payload["recommendedCommands"]["uvQuickstart"] == "uv sync --extra dev --extra mcp"


def test_environment_doctor_renders_text_summary() -> None:
    payload = collect_environment_doctor_payload(Path(__file__).resolve().parents[1])
    text = render_environment_doctor_text(payload)

    assert "Co-Scientist environment doctor" in text
    assert "Recommended commands:" in text
    assert "uv quickstart:" in text
    assert "install Codex project skills (Windows):" in text
    assert "show start parameters:" in text
    assert "completion-driven start example:" in text
    assert "capped start example:" in text
    assert "validate artifacts:" in text
    assert "verify completion:" in text
    assert "resolve ready dashboard links:" in text
    assert "Iteration control model:" in text
    assert "`iteration-policy` decides whether the run stops by semantic completion or by a user-chosen cap." in text
    assert "`human-checkpoint` decides when the operator should be asked to confirm continuation" in text
    assert "`inspect_state` or `validation blocked` means artifacts disagree" in text
    assert "Dashboard usage:" in text
    assert "dashboard/LINKS.md" in text


def test_environment_doctor_warns_when_gemini_provider_missing_sdk(monkeypatch) -> None:
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "tools.install.environment_doctor._importable",
        lambda name: name != "google.genai",
    )

    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        payload = collect_environment_doctor_payload(project_root, repo_root=project_root)

    gemini_checks = [check for check in payload["checks"] if check["name"] == "gemini-embedding-provider"]
    assert gemini_checks
    assert gemini_checks[0]["status"] == "warn"
    assert "google-genai" in gemini_checks[0]["hint"]


def test_environment_doctor_does_not_require_gemini_when_not_selected(monkeypatch) -> None:
    monkeypatch.delenv("CO_SCIENTIST_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        payload = collect_environment_doctor_payload(project_root, repo_root=project_root)

    gemini_checks = [check for check in payload["checks"] if check["name"] == "gemini-embedding-provider"]
    assert not gemini_checks


def test_environment_doctor_module_help_succeeds() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.install.environment_doctor",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Run Co-Scientist environment diagnostics." in result.stdout


def test_environment_doctor_warns_when_claude_skill_mirror_is_stale() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        install_claude_project(project_root=project_root, repo_root=repo_root, action="install")
        fresh_payload = collect_environment_doctor_payload(project_root, repo_root=repo_root)
        fresh_checks = {check["name"]: check for check in fresh_payload["checks"]}
        assert fresh_checks["project-skill-install"]["status"] == "pass"
        assert fresh_checks["project-skill-mirror"]["status"] == "pass"

        stale_skill = project_root / ".claude" / "skills" / "co-scientist-pipeline" / "SKILL.md"
        stale_skill.write_text("# stale pipeline skill\n", encoding="utf-8")

        stale_payload = collect_environment_doctor_payload(project_root, repo_root=repo_root)
        stale_checks = {check["name"]: check for check in stale_payload["checks"]}
        assert stale_checks["project-skill-install"]["status"] == "pass"
        assert stale_checks["project-skill-mirror"]["status"] == "warn"
        assert "co-scientist-pipeline/SKILL.md" in stale_checks["project-skill-mirror"]["details"]["mismatchedFiles"]


def test_environment_doctor_reports_codex_install_and_stale_mirror() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        install_codex_project(project_root=project_root, repo_root=repo_root, action="install")
        fresh_payload = collect_environment_doctor_payload(project_root, repo_root=repo_root)
        fresh_checks = {check["name"]: check for check in fresh_payload["checks"]}
        assert fresh_checks["project-codex-skill-install"]["status"] == "pass"
        assert fresh_checks["project-codex-skill-mirror"]["status"] == "pass"
        assert fresh_checks["project-codex-skill-install"]["details"]["agentsMdManagedBlock"] is True

        stale_skill = project_root / ".agents" / "skills" / "co-scientist-start" / "SKILL.md"
        stale_skill.write_text("# stale codex start skill\n", encoding="utf-8")

        stale_payload = collect_environment_doctor_payload(project_root, repo_root=repo_root)
        stale_checks = {check["name"]: check for check in stale_payload["checks"]}
        assert stale_checks["project-codex-skill-install"]["status"] == "pass"
        assert stale_checks["project-codex-skill-mirror"]["status"] == "warn"
        mismatched_files = stale_checks["project-codex-skill-mirror"]["details"]["mismatchedFiles"]
        assert "co-scientist-start/SKILL.md" in mismatched_files
