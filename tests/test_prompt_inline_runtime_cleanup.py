from __future__ import annotations

from pathlib import Path

import packages.agent_support as agent_support


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agent_support_no_longer_exports_prompt_loader_symbols() -> None:
    assert not hasattr(agent_support, "load_prompt")
    assert not hasattr(agent_support, "validate_template_vars")
    assert not hasattr(agent_support, "retry_llm_call")


def test_active_runtime_docs_no_longer_describe_skill_local_prompt_loading() -> None:
    active_files = [
        REPO_ROOT / "skills" / "co-scientist-pipeline" / "SKILL.md",
        REPO_ROOT / "skills" / "skills-claude-entry" / "co-scientist-start" / "SKILL.md",
        REPO_ROOT / "skills" / "skills-claude-entry" / "co-scientist-run" / "SKILL.md",
        REPO_ROOT / "skills" / "shared-references" / "integration-contract.md",
        REPO_ROOT / "skills" / "shared-references" / "execution-modes.md",
        REPO_ROOT / "tools" / "install" / "claude_install.py",
    ]
    forbidden_snippets = [
        "Resolve prompts only from skill-local `prompts/` directories.",
        "Skill prompts live under `skills/<skill-name>/prompts/`.",
        "prompts under `skills/**/prompts/`",
    ]

    for path in active_files:
        content = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in content, f"{path} still contains legacy prompt-loading wording"


def test_shared_host_references_stay_host_neutral() -> None:
    active_files = [
        REPO_ROOT / "skills" / "shared-references" / "execution-modes.md",
        REPO_ROOT / "skills" / "shared-references" / "integration-contract.md",
        REPO_ROOT / "skills" / "shared-references" / "start-parameters.md",
    ]
    forbidden_snippets = [
        "claude_project_cli",
        "ARIS-like",
        "Claude-style",
    ]

    for path in active_files:
        content = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in content, f"{path} contains host-specific shared-reference wording"
