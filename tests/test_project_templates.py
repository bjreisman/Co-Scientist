from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_input_template_contains_research_brief_sections() -> None:
    input_path = REPO_ROOT / "templates" / "INPUT_TEMPLATE.md"

    assert input_path.exists()
    input_text = input_path.read_text(encoding="utf-8")
    assert "# Research Brief" in input_text
    assert "## Goal" in input_text


def test_readme_points_to_natural_language_start_and_template_shell() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "/co-scientist-start" in readme_text
    assert "/co-scientist-params" in readme_text
    assert "/co-scientist-dashboard runs/<run_id>" in readme_text
    assert "$co-scientist-start" in readme_text
    assert "$co-scientist-dashboard runs/<run_id>" in readme_text
    assert "tools.host.project_cli start" in readme_text
    assert "tools.host.project_cli dashboard runs/<run_id>" in readme_text
    assert "install_co_scientist_codex.ps1" in readme_text
    assert ".agents/skills/" in readme_text
    assert "AGENTS.md" in readme_text
    assert "dashboard/LINKS.md" in readme_text
    assert "`--iteration-policy`" in readme_text
    assert "`--iteration-band`" in readme_text
    assert "Controls per-round intensity." in readme_text
    assert "Chooses semantic stopping or a user-selected iteration cap." in readme_text
    assert "Controls when the host should pause for confirmation." in readme_text
    assert "`validation blocked`" in readme_text
    assert "templates/" in readme_text
