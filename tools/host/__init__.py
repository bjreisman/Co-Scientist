"""Host-agent and Claude Code entry helpers."""

from __future__ import annotations

import importlib


_LAZY_EXPORTS = {
    "CreatedRunArtifacts": ("tools.host.create_run", "CreatedRunArtifacts"),
    "ExecutionModeContract": ("tools.host.host_agent", "ExecutionModeContract"),
    "HostAgentBootstrapResult": ("tools.host.host_agent_surface", "HostAgentBootstrapResult"),
    "HostAgentHandoff": ("tools.host.host_agent", "HostAgentHandoff"),
    "TOP_LEVEL_SKILLS": ("tools.host.host_agent", "TOP_LEVEL_SKILLS"),
    "build_run_policy_from_controls": ("tools.host.create_run", "build_run_policy_from_controls"),
    "bootstrap_host_agent_run": ("tools.host.host_agent_surface", "bootstrap_host_agent_run"),
    "claude_project_cli_main": ("tools.host.claude_project_cli", "main"),
    "create_run_artifacts": ("tools.host.create_run", "create_run_artifacts"),
    "default_runs_dir": ("tools.host.create_run", "default_runs_dir"),
    "ensure_dashboard_for_run": ("tools.host.host_agent_surface", "ensure_dashboard_for_run"),
    "ensure_dashboard_links_for_run": ("tools.host.host_agent_surface", "ensure_dashboard_links_for_run"),
    "generate_run_id": ("tools.host.create_run", "generate_run_id"),
    "GUIDED_INTAKE_QUESTIONS": ("tools.host.intake_request", "GUIDED_INTAKE_QUESTIONS"),
    "get_execution_modes": ("tools.host.host_agent", "get_execution_modes"),
    "build_start_request_contract": ("tools.host.intake_request", "build_start_request_contract"),
    "build_start_request_preview": ("tools.host.intake_request", "build_start_request_preview"),
    "infer_interaction_mode": ("tools.host.intake_request", "infer_interaction_mode"),
    "prepare_host_agent_handoff": ("tools.host.host_agent", "prepare_host_agent_handoff"),
    "project_cli_main": ("tools.host.project_cli", "main"),
    "render_input_markdown": ("tools.host.create_run", "render_input_markdown"),
    "render_start_summary": ("tools.host.intake_request", "render_start_summary"),
    "write_host_agent_handoff": ("tools.host.host_agent", "write_host_agent_handoff"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str):
    """Lazily resolve host helpers to avoid runpy re-import warnings."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = importlib.import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
