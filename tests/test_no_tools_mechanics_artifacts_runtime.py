from __future__ import annotations

from pathlib import Path


RUNTIME_FILES = [
    Path("tools/host/host_agent_surface.py"),
    Path("tools/policy/plan_strategy.py"),
    Path("tools/policy/resolve_run_config.py"),
    Path("tools/validation/verify_pipeline_completion.py"),
    Path("tools/dashboard/serve.py"),
]


def test_runtime_paths_do_not_depend_on_tools_mechanics_or_artifacts() -> None:
    for path in RUNTIME_FILES:
        content = path.read_text(encoding="utf-8")
        assert "tools.mechanics" not in content
        assert "..mechanics" not in content
        assert "tools.artifacts" not in content
        assert "..artifacts" not in content
