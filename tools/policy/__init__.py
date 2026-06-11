"""Policy and resolved-config command helpers.

Keep package imports lazy so ``python -m tools.policy.<module>`` entry points do
not pre-import the target module during package initialization.
"""

from __future__ import annotations

import importlib


_LAZY_EXPORTS = {
    "plan_strategy_for_run": ("tools.policy.plan_strategy", "plan_strategy_for_run"),
    "resolve_run_config_for_path": ("tools.policy.resolve_run_config", "resolve_run_config_for_path"),
    "validate_resolved_config_for_run": ("tools.policy.validate_resolved_config", "validate_resolved_config_for_run"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = importlib.import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
