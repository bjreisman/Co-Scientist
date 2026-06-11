from __future__ import annotations

from pathlib import Path


REMOVED_DIRECTORIES = [
    Path("tools/contracts"),
    Path("tools/mechanics"),
    Path("tools/artifacts"),
]

ACTIVE_DOCS = [
    Path("skills/shared-references/integration-contract.md"),
    Path("skills/shared-references/completion-contract.md"),
    Path("skills/shared-references/execution-modes.md"),
    Path("tools/host/host_agent.py"),
]


def test_compat_wrapper_directories_are_removed() -> None:
    for path in REMOVED_DIRECTORIES:
        assert not path.exists()


def test_active_docs_no_longer_present_wrappers_as_sources() -> None:
    blocked = ("tools/contracts/", "tools/mechanics/", "tools/artifacts/")
    for path in ACTIVE_DOCS:
        content = path.read_text(encoding="utf-8")
        for token in blocked:
            assert token not in content
