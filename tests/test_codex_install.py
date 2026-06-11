from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tools.install.codex_install import collect_codex_skill_mirror_parity, install_codex_project


def _write_skill(path: Path, name: str) -> None:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill {name}.\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _build_source_repo(repo_root: Path) -> None:
    _write_skill(repo_root / "skills" / "co-scientist-pipeline", "co-scientist-pipeline")
    _write_skill(repo_root / "skills" / "literature-search", "literature-search")
    _write_skill(repo_root / "skills" / "skills-codex-entry" / "co-scientist-start", "co-scientist-start")
    _write_skill(repo_root / "skills" / "skills-codex-entry" / "co-scientist-run", "co-scientist-run")
    _write_skill(repo_root / "skills" / "skills-claude-entry" / "co-scientist-start", "co-scientist-start")
    (repo_root / "skills" / "shared-references").mkdir(parents=True)
    (repo_root / "skills" / "shared-references" / "artifact-contract.md").write_text(
        "# Artifact Contract\n",
        encoding="utf-8",
    )
    (repo_root / "templates" / "codex").mkdir(parents=True)
    (repo_root / "templates" / "codex" / "config.toml.example").write_text(
        "[mcp_servers.co_scientist_search_bridge]\n"
        'command = "uv"\n'
        'args = ["run", "python", "mcp-servers/search-bridge/server.py"]\n',
        encoding="utf-8",
    )


def test_install_codex_project_writes_agents_skills_manifest_and_agents_md() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        result = install_codex_project(project_root=project_root, repo_root=repo_root, action="install")

        assert result.action == "install"
        assert (project_root / ".agents" / "skills" / "co-scientist-pipeline" / "SKILL.md").exists()
        assert (project_root / ".agents" / "skills" / "literature-search" / "SKILL.md").exists()
        assert (project_root / ".agents" / "skills" / "shared-references" / "artifact-contract.md").exists()
        assert (project_root / ".agents" / "skills" / "co-scientist-start" / "SKILL.md").exists()
        assert (project_root / ".agents" / "skills" / "co-scientist-run" / "SKILL.md").exists()
        assert not (project_root / ".claude" / "skills").exists()

        manifest = json.loads(
            (project_root / ".co-scientist" / "installed-codex-skills.json").read_text(encoding="utf-8")
        )
        installed_names = {record["name"] for record in manifest["records"]}
        assert installed_names == {
            "co-scientist-pipeline",
            "co-scientist-run",
            "co-scientist-start",
            "literature-search",
            "shared-references",
        }

        parity = collect_codex_skill_mirror_parity(project_root=project_root, repo_root=repo_root)
        assert parity["missingFiles"] == []
        assert parity["mismatchedFiles"] == []
        assert parity["extraFiles"] == []

        agents_md = (project_root / "AGENTS.md").read_text(encoding="utf-8")
        assert "Managed Co-Scientist Codex Skills" in agents_md
        assert ".agents/skills/" in agents_md
        assert "$co-scientist-start" in agents_md
        assert "python -m tools.host.project_cli" in agents_md
        assert "Do not call Claude-specific entrypoints" in agents_md
        assert "tools/install/install_co_scientist_codex.ps1" in agents_md


def test_install_codex_project_can_include_search_bridge_config_template() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        result = install_codex_project(
            project_root=project_root,
            repo_root=repo_root,
            action="install",
            include_search_bridge_config=True,
        )

        assert "[mcp_servers.co_scientist_search_bridge]" in result.search_bridge_config
        assert "mcp-servers/search-bridge/server.py" in result.search_bridge_config
        assert not (project_root / ".codex").exists()


def test_reconcile_preserves_agents_md_user_suffix() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        install_codex_project(project_root=project_root, repo_root=repo_root, action="install")
        agents_md_path = project_root / "AGENTS.md"
        agents_md_path.write_text(
            agents_md_path.read_text(encoding="utf-8") + "\n## User Notes\n\n- keep this section\n",
            encoding="utf-8",
        )

        install_codex_project(project_root=project_root, repo_root=repo_root, action="reconcile")

        agents_md = agents_md_path.read_text(encoding="utf-8")
        assert "Managed Co-Scientist Codex Skills" in agents_md
        assert "## User Notes" in agents_md
        assert "- keep this section" in agents_md


def test_uninstall_removes_only_managed_codex_skill_entries_and_managed_block() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        install_codex_project(project_root=project_root, repo_root=repo_root, action="install")
        unmanaged_dir = project_root / ".agents" / "skills" / "custom-skill"
        unmanaged_dir.mkdir(parents=True)
        (unmanaged_dir / "SKILL.md").write_text("# custom-skill\n", encoding="utf-8")
        agents_md_path = project_root / "AGENTS.md"
        agents_md_path.write_text(
            agents_md_path.read_text(encoding="utf-8") + "\n## User Notes\n\n- keep this section\n",
            encoding="utf-8",
        )

        result = install_codex_project(project_root=project_root, repo_root=repo_root, action="uninstall")

        assert sorted(result.removed_skills) == [
            "co-scientist-pipeline",
            "co-scientist-run",
            "co-scientist-start",
            "literature-search",
            "shared-references",
        ]
        assert not (project_root / ".agents" / "skills" / "co-scientist-pipeline").exists()
        assert unmanaged_dir.exists()
        assert not (project_root / ".co-scientist" / "installed-codex-skills.json").exists()
        agents_md = agents_md_path.read_text(encoding="utf-8")
        assert "Managed Co-Scientist Codex Skills" not in agents_md
        assert "## User Notes" in agents_md


def test_install_codex_project_refuses_unmanaged_conflict() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)
        conflict_dir = project_root / ".agents" / "skills" / "co-scientist-pipeline"
        conflict_dir.mkdir(parents=True)
        (conflict_dir / "SKILL.md").write_text("# unmanaged\n", encoding="utf-8")

        with pytest.raises(FileExistsError, match="Refusing to overwrite unmanaged Codex project skill path"):
            install_codex_project(project_root=project_root, repo_root=repo_root, action="install")


def test_codex_install_module_help_succeeds() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.install.codex_install",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Install Co-Scientist project skills for Codex" in result.stdout
