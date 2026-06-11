from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
PUBLIC_SKILL_EXCLUDES = {"shared-references", "skills-claude-entry", "skills-codex-entry"}
CLAUDE_ONLY_MARKERS = ("Claude Code", "claude_project_cli", ".claude", "CLAUDE.md")


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    closing = text.find("\n---\n", 4)
    assert closing != -1
    metadata: dict[str, str] = {}
    for line in text[4:closing].splitlines():
        key, separator, value = line.partition(":")
        assert separator == ":", f"Invalid frontmatter line: {line!r}"
        metadata[key.strip()] = value.strip()
    return metadata


def _skill_markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("*/SKILL.md") if path.is_file())


def test_public_workflow_skills_have_codex_readable_frontmatter() -> None:
    skill_files = [
        path for path in _skill_markdown_files(SKILLS_ROOT) if path.parent.name not in PUBLIC_SKILL_EXCLUDES
    ]

    assert skill_files
    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8")
        metadata = _frontmatter(text)
        assert metadata["name"] == skill_file.parent.name
        assert metadata["description"]


def test_codex_entry_skills_have_frontmatter_and_route_to_tools() -> None:
    entry_root = SKILLS_ROOT / "skills-codex-entry"
    entry_files = _skill_markdown_files(entry_root)

    assert {path.parent.name for path in entry_files} == {
        "co-scientist-dashboard",
        "co-scientist-doctor",
        "co-scientist-params",
        "co-scientist-resume",
        "co-scientist-run",
        "co-scientist-start",
        "co-scientist-validate",
    }
    for skill_file in entry_files:
        text = skill_file.read_text(encoding="utf-8")
        metadata = _frontmatter(text)
        assert metadata["name"] == skill_file.parent.name
        assert metadata["description"]
        assert len(text.splitlines()) < 120
        assert "python -m tools.host.project_cli" in text or "python -m tools.validation.contract_validation" in text


def test_public_and_codex_skill_surfaces_do_not_depend_on_claude_only_entrypoints() -> None:
    checked_files = [
        skill_file
        for skill_file in _skill_markdown_files(SKILLS_ROOT)
        if skill_file.parent.name not in PUBLIC_SKILL_EXCLUDES
    ]
    checked_files.extend(_skill_markdown_files(SKILLS_ROOT / "skills-codex-entry"))

    assert checked_files
    for skill_file in checked_files:
        text = skill_file.read_text(encoding="utf-8")
        for marker in CLAUDE_ONLY_MARKERS:
            assert marker not in text, f"{skill_file} contains Claude-only marker {marker!r}"


def test_codex_entry_skills_do_not_duplicate_canonical_workflow_body() -> None:
    entry_root = SKILLS_ROOT / "skills-codex-entry"

    for skill_file in _skill_markdown_files(entry_root):
        text = skill_file.read_text(encoding="utf-8")
        assert "tools.host.project_cli" in text or "tools.validation.contract_validation" in text
        assert "hypothesis-generation-pipeline" not in text
        assert "hypothesis-review-pipeline" not in text
        assert "hypothesis-ranking-pipeline" not in text


def test_codex_reviewer_agent_template_is_parseable() -> None:
    template_path = REPO_ROOT / "templates" / "codex" / "co-scientist-reviewer.toml.example"

    payload = tomllib.loads(template_path.read_text(encoding="utf-8"))

    assert payload["name"] == "co-scientist-reviewer"
    assert "Review artifacts cold" in payload["developer_instructions"]
    assert payload["sandbox_mode"] == "workspace-write"


def test_review_skills_document_optional_codex_reviewer_route() -> None:
    shared_reference = SKILLS_ROOT / "shared-references" / "codex-reviewer-routing.md"
    shared_text = shared_reference.read_text(encoding="utf-8")

    assert "reviewerRoute" in shared_text
    assert "local_main_thread" in shared_text
    assert "codex_subagent" in shared_text
    assert "must not write canonical review artifacts" in shared_text

    for skill_name in ("hypothesis-review-pipeline", "hypothesis-full-review", "hypothesis-deep-verification"):
        text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "skills/shared-references/codex-reviewer-routing.md" in text
        assert "reviewerRoute = local_main_thread" in text
        assert "schema validation" in text


def test_shared_references_use_host_neutral_entry_language() -> None:
    shared_root = SKILLS_ROOT / "shared-references"

    for shared_file in (
        shared_root / "execution-modes.md",
        shared_root / "integration-contract.md",
        shared_root / "skill-structure-contract.md",
        shared_root / "start-parameters.md",
    ):
        text = shared_file.read_text(encoding="utf-8")
        assert "Claude Code style hosts" not in text
        assert "slash-command arguments" not in text
        assert "slash-command inputs" not in text

    start_parameters = (shared_root / "start-parameters.md").read_text(encoding="utf-8")
    assert "/co-scientist-start" in start_parameters
    assert "$co-scientist-start" in start_parameters
