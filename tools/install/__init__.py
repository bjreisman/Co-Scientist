"""Install helpers for project-local host integrations."""

from __future__ import annotations

import importlib


_LAZY_EXPORTS = {
    "ClaudeInstallResult": ("tools.install.claude_install", "ClaudeInstallResult"),
    "CodexInstallResult": ("tools.install.codex_install", "CodexInstallResult"),
    "collect_codex_skill_mirror_parity": ("tools.install.codex_install", "collect_codex_skill_mirror_parity"),
    "collect_environment_doctor_payload": ("tools.install.environment_doctor", "collect_environment_doctor_payload"),
    "install_claude_project": ("tools.install.claude_install", "install_claude_project"),
    "install_codex_project": ("tools.install.codex_install", "install_codex_project"),
    "render_environment_doctor_text": ("tools.install.environment_doctor", "render_environment_doctor_text"),
    "main": ("tools.install.claude_install", "main"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str):
    """Lazily resolve install helpers to avoid runpy re-import warnings."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = importlib.import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
