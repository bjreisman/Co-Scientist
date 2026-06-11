from __future__ import annotations

from pathlib import Path


RUNTIME_FILES = [
    Path("tools/validation/verify_pipeline_completion.py"),
    Path("tools/validation/contract_validation.py"),
    Path("tools/host/create_run.py"),
    Path("tools/host/host_agent_surface.py"),
]


def test_runtime_paths_do_not_depend_on_tools_contracts() -> None:
    for path in RUNTIME_FILES:
        content = path.read_text(encoding="utf-8")
        assert "tools.contracts" not in content
        assert "..contracts" not in content
