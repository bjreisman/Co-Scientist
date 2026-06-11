"""Deterministic resolution helpers for numeric run configuration artifacts."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from packages.agent_contracts import (
    ResolvedProximityConfigContract,
    ResolvedRunConfigContract,
    RunPolicyContract,
    proximity_config_hash,
)


PROFILE_DEFAULTS: dict[str, dict[str, dict[str, float | int | str]]] = {
    "conservative": {
        "generation": {"num_debaters": 2, "max_debate_turns": 3},
        "island": {
            "ucb_exploration_constant": 1.0,
            "decay_factor": 0.95,
            "softmax_temperature": 0.8,
            "stagnation_epsilon": 0.03,
        },
        "ranking": {"placement_match_count": 6, "tournament_top_k": 5, "elo_k_factor": 24.0},
        "convergence": {"convergence_count_threshold": 3},
    },
    "balanced": {
        "generation": {"num_debaters": 3, "max_debate_turns": 5},
        "island": {
            "ucb_exploration_constant": 1.25,
            "decay_factor": 0.9,
            "softmax_temperature": 1.0,
            "stagnation_epsilon": 0.05,
        },
        "ranking": {"placement_match_count": 10, "tournament_top_k": 8, "elo_k_factor": 32.0},
        "convergence": {"convergence_count_threshold": 3},
    },
    "aggressive": {
        "generation": {"num_debaters": 4, "max_debate_turns": 6},
        "island": {
            "ucb_exploration_constant": 1.4,
            "decay_factor": 0.85,
            "softmax_temperature": 1.1,
            "stagnation_epsilon": 0.08,
        },
        "ranking": {"placement_match_count": 12, "tournament_top_k": 10, "elo_k_factor": 32.0},
        "convergence": {"convergence_count_threshold": 3},
    },
}

_BOUNDS: dict[str, tuple[float, float]] = {
    "generation.num_debaters": (2, 5),
    "generation.max_debate_turns": (2, 8),
    "island.ucb_exploration_constant": (0.8, 1.6),
    "island.decay_factor": (0.8, 0.98),
    "island.softmax_temperature": (0.7, 1.3),
    "island.stagnation_epsilon": (0.01, 0.15),
    "ranking.placement_match_count": (4, 20),
    "ranking.tournament_top_k": (3, 15),
    "ranking.elo_k_factor": (16.0, 40.0),
    "convergence.convergence_count_threshold": (1, 6),
    "convergence.max_iterations": (0, 30),
    "convergence.safety_max_iterations": (8, 40),
    "proximity.dimensions": (1, 65536),
    "proximity.timeout_seconds": (1, 600),
}

__all__ = ["PROFILE_DEFAULTS", "resolve_proximity_config", "resolve_run_config", "validate_resolved_config_bounds"]


_ITERATION_BAND_LIMITS: dict[str, int] = {
    "6_10": 8,
    "10_14": 12,
    "15_20": 18,
    "20_30": 24,
}

_LEGACY_PROFILE_LIMITS: dict[str, int] = {
    "conservative": 4,
    "balanced": 6,
    "aggressive": 8,
}

_DEFAULT_COMPLETION_DRIVEN_SAFETY_MAX = 30
_FALSE_VALUES = {"0", "false", "no", "off"}


def _default_proximity_model(provider: str) -> str:
    if provider == "gemini":
        return "gemini-embedding-2"
    if provider == "fake":
        return "fake-embedding"
    return "text-embedding-3-small"


def _default_proximity_dimensions(provider: str) -> int:
    if provider == "gemini":
        return 768
    return 1536


def _default_proximity_api_key_env(provider: str) -> str:
    if provider == "gemini":
        return "GEMINI_API_KEY"
    if provider == "fake":
        return ""
    return "OPENAI_API_KEY"


def _default_proximity_base_url_env(provider: str) -> str:
    if provider in {"gemini", "fake"}:
        return ""
    return "OPENAI_BASE_URL"


def resolve_run_config(
    run_policy: RunPolicyContract,
    config_payload: dict[str, Any],
) -> ResolvedRunConfigContract:
    """Resolve a bounded numeric configuration from high-level policy and config overrides."""
    profile = _select_profile(run_policy)
    defaults = deepcopy(PROFILE_DEFAULTS[profile])
    defaults["convergence"] = _resolve_convergence_defaults(run_policy, profile)
    overrides = _extract_overrides(config_payload)

    for section, values in overrides.items():
        section_defaults = defaults.get(section)
        if not isinstance(section_defaults, dict):
            continue
        for key, value in values.items():
            section_defaults[key] = _clamp(f"{section}.{key}", value)

    _finalize_convergence_defaults(defaults["convergence"], config_payload)
    defaults["proximity"] = resolve_proximity_config(config_payload).model_dump(mode="json")
    payload = {"profile": profile, **defaults}
    return ResolvedRunConfigContract.from_payload(payload)


def resolve_proximity_config(config_payload: dict[str, Any] | None = None) -> ResolvedProximityConfigContract:
    """Resolve run-frozen proximity embedding settings from environment variables and config overrides."""
    provider = os.environ.get("CO_SCIENTIST_EMBEDDING_PROVIDER", "openai_compatible").strip() or "openai_compatible"
    payload: dict[str, Any] = {
        "enabled": os.environ.get("CO_SCIENTIST_PROXIMITY_ENABLED", "true").strip().lower() not in _FALSE_VALUES,
        "provider": provider,
        "model": os.environ.get("CO_SCIENTIST_EMBEDDING_MODEL", _default_proximity_model(provider)).strip()
        or _default_proximity_model(provider),
        "dimensions": _parse_positive_int(
            os.environ.get("CO_SCIENTIST_EMBEDDING_DIMENSIONS", str(_default_proximity_dimensions(provider))),
            default=_default_proximity_dimensions(provider),
        ),
        "base_url_env": os.environ.get(
            "CO_SCIENTIST_EMBEDDING_BASE_URL_ENV",
            _default_proximity_base_url_env(provider),
        ).strip()
        or _default_proximity_base_url_env(provider),
        "api_key_env": os.environ.get(
            "CO_SCIENTIST_EMBEDDING_API_KEY_ENV",
            _default_proximity_api_key_env(provider),
        ).strip()
        or _default_proximity_api_key_env(provider),
        "timeout_seconds": _parse_positive_int(
            os.environ.get("CO_SCIENTIST_EMBEDDING_TIMEOUT_SECONDS", "60"),
            default=60,
        ),
    }

    proximity_payload = (config_payload or {}).get("proximity")
    if isinstance(proximity_payload, dict):
        _apply_proximity_overrides(payload, proximity_payload)
    resolved = ResolvedProximityConfigContract.from_payload(payload)
    return resolved.model_copy(update={"config_hash": proximity_config_hash(resolved)})


def validate_resolved_config_bounds(resolved_config: ResolvedRunConfigContract) -> list[str]:
    """Return any bound violations found in a resolved config artifact."""
    payload = resolved_config.model_dump(mode="json")
    issues: list[str] = []
    for dotted_key, (lower, upper) in _BOUNDS.items():
        section, key = dotted_key.split(".", maxsplit=1)
        section_payload = payload.get(section, {})
        if not isinstance(section_payload, dict):
            issues.append(f"Missing section `{section}` in resolved config.")
            continue
        value = section_payload.get(key)
        if not isinstance(value, int | float):
            issues.append(f"Missing numeric field `{dotted_key}` in resolved config.")
            continue
        if value < lower or value > upper:
            issues.append(
                f"Resolved config field `{dotted_key}` is out of bounds: {value} "
                f"(expected {lower} <= value <= {upper})."
            )
    return issues


def _select_profile(run_policy: RunPolicyContract) -> str:
    policy = run_policy.policy
    if policy.exploration_mode == "aggressive" or policy.budget_profile == "high":
        return "aggressive"
    if policy.exploration_mode == "conservative" or policy.budget_profile == "low":
        return "conservative"
    return "balanced"


def _extract_overrides(config_payload: dict[str, Any]) -> dict[str, dict[str, float | int]]:
    generation_payload = config_payload.get("generation")
    island_payload = config_payload.get("island")
    ranking_payload = config_payload.get("ranking")
    convergence_payload = config_payload.get("convergence")

    overrides: dict[str, dict[str, float | int]] = {}

    if isinstance(generation_payload, dict):
        debates_payload = generation_payload.get("scientific_debates_generation")
        if isinstance(debates_payload, dict):
            generation_values: dict[str, float | int] = {}
            for source_key, target_key in (
                ("num_debaters", "num_debaters"),
                ("max_debate_turns", "max_debate_turns"),
            ):
                value = debates_payload.get(source_key)
                if isinstance(value, int) and not isinstance(value, bool):
                    generation_values[target_key] = value
            if generation_values:
                overrides["generation"] = generation_values

    if isinstance(island_payload, dict):
        island_values = _collect_numeric_values(
            island_payload,
            (
                "ucb_exploration_constant",
                "decay_factor",
                "softmax_temperature",
                "stagnation_epsilon",
            ),
        )
        if island_values:
            overrides["island"] = island_values

    if isinstance(ranking_payload, dict):
        ranking_values = _collect_numeric_values(
            ranking_payload,
            (
                "placement_match_count",
                "tournament_top_k",
                "elo_k_factor",
            ),
        )
        if ranking_values:
            overrides["ranking"] = ranking_values

    if isinstance(convergence_payload, dict):
        convergence_values = _collect_numeric_values(
            convergence_payload,
            (
                "convergence_count_threshold",
                "max_iterations",
                "safety_max_iterations",
            ),
        )
        if convergence_values:
            overrides["convergence"] = convergence_values

    return overrides


def _collect_numeric_values(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float | int]:
    values: dict[str, float | int] = {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool) or isinstance(value, float):
            values[key] = value
    return values


def _apply_proximity_overrides(payload: dict[str, Any], proximity_payload: dict[str, Any]) -> None:
    enabled = proximity_payload.get("enabled")
    if isinstance(enabled, bool):
        payload["enabled"] = enabled

    provider = proximity_payload.get("provider")
    if isinstance(provider, str) and provider.strip():
        normalized_provider = provider.strip()
        payload["provider"] = normalized_provider
        payload["model"] = _default_proximity_model(normalized_provider)
        payload["dimensions"] = _default_proximity_dimensions(normalized_provider)
        payload["base_url_env"] = _default_proximity_base_url_env(normalized_provider)
        payload["api_key_env"] = _default_proximity_api_key_env(normalized_provider)

    for key in ("model", "base_url_env", "api_key_env"):
        value = proximity_payload.get(key)
        if isinstance(value, str) and value.strip():
            payload[key] = value.strip()

    for key in ("dimensions", "timeout_seconds"):
        value = proximity_payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            payload[key] = max(1, value)


def _parse_positive_int(raw_value: str | None, *, default: int) -> int:
    try:
        value = int(str(raw_value or "").strip())
    except ValueError:
        return default
    return max(1, value)


def _clamp(dotted_key: str, value: float | int) -> float | int:
    lower, upper = _BOUNDS[dotted_key]
    clamped = min(max(float(value), lower), upper)
    if isinstance(value, int) and float(value).is_integer():
        return int(round(clamped))
    return round(clamped, 4)


def _resolve_convergence_defaults(
    run_policy: RunPolicyContract,
    profile: str,
) -> dict[str, int | str]:
    policy = run_policy.policy
    defaults: dict[str, int | str] = {
        "convergence_count_threshold": 3,
        "max_iterations": 0,
        "safety_max_iterations": _DEFAULT_COMPLETION_DRIVEN_SAFETY_MAX,
        "iteration_cap_source": "completion_driven_default",
    }
    if policy.iteration_policy == "capped":
        if policy.iteration_band is not None:
            capped_limit = _ITERATION_BAND_LIMITS[policy.iteration_band]
            defaults["max_iterations"] = capped_limit
            defaults["safety_max_iterations"] = capped_limit
            defaults["iteration_cap_source"] = "iteration_band"
        else:
            legacy_limit = _LEGACY_PROFILE_LIMITS[profile]
            defaults["max_iterations"] = legacy_limit
            defaults["safety_max_iterations"] = legacy_limit
            defaults["iteration_cap_source"] = "legacy_budget_profile"
    return defaults


def _finalize_convergence_defaults(
    convergence_defaults: dict[str, float | int | str],
    config_payload: dict[str, Any],
) -> None:
    convergence_payload = config_payload.get("convergence")
    explicit_max_iterations = False
    explicit_safety_max = False
    if isinstance(convergence_payload, dict):
        explicit_max_iterations = isinstance(convergence_payload.get("max_iterations"), int) and not isinstance(
            convergence_payload.get("max_iterations"), bool
        )
        explicit_safety_max = isinstance(convergence_payload.get("safety_max_iterations"), int) and not isinstance(
            convergence_payload.get("safety_max_iterations"), bool
        )

    max_iterations = int(convergence_defaults["max_iterations"])
    safety_max_iterations = int(convergence_defaults["safety_max_iterations"])

    if explicit_max_iterations:
        convergence_defaults["iteration_cap_source"] = "config_override"
    if max_iterations > 0 and safety_max_iterations < max_iterations:
        convergence_defaults["safety_max_iterations"] = max_iterations
    elif max_iterations == 0 and explicit_safety_max:
        convergence_defaults["safety_max_iterations"] = max(safety_max_iterations, 8)
