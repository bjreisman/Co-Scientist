"""Validation helpers for host-agent execution."""

from __future__ import annotations

import importlib


_LAZY_EXPORTS = {
    "CompletionAdvisory": ("tools.validation.verify_pipeline_completion", "CompletionAdvisory"),
    "HostAgentValidationIssue": ("tools.validation.contract_validation", "HostAgentValidationIssue"),
    "HostAgentValidationSummary": ("tools.validation.contract_validation", "HostAgentValidationSummary"),
    "PipelineStateContract": ("tools.validation.contract_validation", "PipelineStateContract"),
    "advise_pipeline_completion": ("tools.validation.verify_pipeline_completion", "advise_pipeline_completion"),
    "record_completion_decision": ("tools.validation.verify_pipeline_completion", "record_completion_decision"),
    "validate_resume_state": ("tools.validation.contract_validation", "validate_resume_state"),
    "validate_run_artifacts": ("tools.validation.contract_validation", "validate_run_artifacts"),
    "verify_codex_integration_surface": (
        "tools.validation.verify_codex_integration_surface",
        "verify_codex_integration_surface",
    ),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str):
    """Lazily resolve validation helpers to avoid runpy re-import warnings."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = importlib.import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
