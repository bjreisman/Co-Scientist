from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.install.claude_install import collect_claude_skill_mirror_parity, install_claude_project


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
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-run").mkdir(parents=True)
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-run" / "SKILL.md").write_text(
        "# co-scientist-run\n",
        encoding="utf-8",
    )
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-install").mkdir(parents=True)
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-install" / "SKILL.md").write_text(
        "# co-scientist-install\n",
        encoding="utf-8",
    )
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-doctor").mkdir(parents=True)
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-doctor" / "SKILL.md").write_text(
        "# co-scientist-doctor\n",
        encoding="utf-8",
    )
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-start").mkdir(parents=True)
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-start" / "SKILL.md").write_text(
        "# co-scientist-start\n",
        encoding="utf-8",
    )
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-params").mkdir(parents=True)
    (repo_root / "skills" / "skills-claude-entry" / "co-scientist-params" / "SKILL.md").write_text(
        "# co-scientist-params\n",
        encoding="utf-8",
    )


def test_install_claude_project_writes_managed_skills_and_claude_md() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        result = install_claude_project(project_root=project_root, repo_root=repo_root, action="install")

        assert result.action == "install"
        assert (project_root / ".claude" / "skills" / "co-scientist-pipeline" / "SKILL.md").exists()
        assert (project_root / ".claude" / "skills" / "shared-references" / "artifact-contract.md").exists()
        assert (project_root / ".claude" / "skills" / "co-scientist-run" / "SKILL.md").exists()
        assert (project_root / ".claude" / "skills" / "co-scientist-install" / "SKILL.md").exists()
        assert (project_root / ".claude" / "skills" / "co-scientist-doctor" / "SKILL.md").exists()
        assert (project_root / ".claude" / "skills" / "co-scientist-start" / "SKILL.md").exists()
        assert (project_root / ".claude" / "skills" / "co-scientist-params" / "SKILL.md").exists()

        manifest = json.loads((project_root / ".co-scientist" / "installed-skills.json").read_text(encoding="utf-8"))
        installed_names = {record["name"] for record in manifest["records"]}
        assert installed_names == {
            "co-scientist-pipeline",
            "co-scientist-install",
            "co-scientist-doctor",
            "shared-references",
            "co-scientist-run",
            "co-scientist-start",
            "co-scientist-params",
        }
        parity = collect_claude_skill_mirror_parity(project_root=project_root, repo_root=repo_root)
        assert parity["missingFiles"] == []
        assert parity["mismatchedFiles"] == []
        assert parity["extraFiles"] == []

        claude_md = (project_root / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Managed Co-Scientist Project Skills" in claude_md
        assert "packages/agent_contracts/" in claude_md
        assert "/co-scientist-install" in claude_md
        assert "/co-scientist-doctor" in claude_md
        assert "/co-scientist-start" in claude_md
        assert "/co-scientist-params" in claude_md
        assert "/co-scientist-run <run-dir-or-config-path>" in claude_md
        assert "python -m tools.host.claude_project_cli params" in claude_md
        assert "Treat `budget` as per-round intensity" in claude_md
        assert "human-checkpoint=auto" in claude_md
        assert "background dashboard bootstrap" in claude_md
        assert "/co-scientist-dashboard <run-dir>" in claude_md
        assert "dashboard/LINKS.md" in claude_md
        assert "`inspect_state` or `validation blocked`" in claude_md
        assert "tools/contracts/" not in claude_md
        assert "tools/mechanics/" not in claude_md
        assert "tools/artifacts/" not in claude_md
        assert "".join(["lega", "cy", "/backend"]) not in claude_md


def test_uninstall_removes_only_managed_skill_entries() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        install_claude_project(project_root=project_root, repo_root=repo_root, action="install")
        unmanaged_dir = project_root / ".claude" / "skills" / "custom-skill"
        unmanaged_dir.mkdir(parents=True)
        (unmanaged_dir / "SKILL.md").write_text("# custom-skill\n", encoding="utf-8")

        result = install_claude_project(project_root=project_root, repo_root=repo_root, action="uninstall")

        assert sorted(result.removed_skills) == [
            "co-scientist-doctor",
            "co-scientist-install",
            "co-scientist-params",
            "co-scientist-pipeline",
            "co-scientist-run",
            "co-scientist-start",
            "shared-references",
        ]
        assert not (project_root / ".claude" / "skills" / "co-scientist-pipeline").exists()
        assert unmanaged_dir.exists()


def test_reconcile_rewrites_legacy_claude_preamble_and_preserves_suffix() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir) / "repo"
        project_root = Path(temp_dir) / "project"
        repo_root.mkdir()
        project_root.mkdir()
        _build_source_repo(repo_root)

        legacy_claude = "\n".join(
            [
                "# Co-Scientist for Claude Code",
                "",
                "This repository exposes a project-local Co-Scientist workflow for Claude Code.",
                "",
                "Canonical workflow and contract sources live in:",
                "",
                "- `skills/`",
                "- `skills/shared-references/`",
                "- `tools/contracts/`",
                "- `tools/validation/contract_validation.py`",
                "- `runs/<run_id>/`",
                "",
                "<!-- CO_SCIENTIST:BEGIN -->",
                "outdated managed block",
                "<!-- CO_SCIENTIST:END -->",
                "",
                "## User Notes",
                "",
                "- keep this section",
                "",
            ]
        )
        (project_root / "CLAUDE.md").write_text(legacy_claude, encoding="utf-8")

        install_claude_project(project_root=project_root, repo_root=repo_root, action="reconcile")

        claude_md = (project_root / "CLAUDE.md").read_text(encoding="utf-8")
        assert "packages/agent_contracts/" in claude_md
        assert "tools/contracts/" not in claude_md
        assert "tools/mechanics/" not in claude_md
        assert "tools/artifacts/" not in claude_md
        assert "".join(["lega", "cy", "/backend"]) not in claude_md
        assert "The preamble above and the managed block below are maintained" in claude_md
        assert "python -m tools.host.claude_project_cli params" in claude_md
        assert "Treat `budget` as per-round intensity" in claude_md
        assert "human-checkpoint=auto" in claude_md
        assert "background dashboard bootstrap" in claude_md
        assert "dashboard/LINKS.md" in claude_md
        assert "`inspect_state` or `validation blocked`" in claude_md
        assert "## User Notes" in claude_md
        assert "- keep this section" in claude_md
