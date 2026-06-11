"""Deterministic helpers for bootstrapping run policy artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.agent_contracts import (
    PolicyDecisionContract,
    RunPolicyContract,
    RunPolicySettingsContract,
)


DEFAULT_ALLOWED_GENERATION_STRATEGIES = [
    "literature_exploration_generation",
    "scientific_debates_generation",
    "assumptions_identification_generation",
]
DEFAULT_ALLOWED_REVIEW_MODES = [
    "full_review",
    "deep_verification_review",
    "observation_review",
    "simulation_review",
]

_GENERATION_STRATEGY_NAMES = set(DEFAULT_ALLOWED_GENERATION_STRATEGIES)

__all__ = [
    "DEFAULT_ALLOWED_GENERATION_STRATEGIES",
    "DEFAULT_ALLOWED_REVIEW_MODES",
    "build_policy_decision",
    "build_run_policy_from_config",
]


def build_run_policy_from_config(
    config_payload: dict[str, Any],
    *,
    run_dir: Path,
    input_file: str,
    log_file: str,
) -> RunPolicyContract:
    """Build a stable run policy from `config.yaml` and default host-agent heuristics."""
    explicit_policy = config_payload.get("policy", {})
    if not isinstance(explicit_policy, dict):
        explicit_policy = {}

    explicit_generation = explicit_policy.get("allowed_generation_strategies", [])
    explicit_review_rigor = explicit_policy.get("review_rigor")

    allowed_generation = _normalize_generation_strategies(explicit_generation) or _infer_generation_strategies(
        config_payload.get("generation")
    )
    allowed_review = list(DEFAULT_ALLOWED_REVIEW_MODES)

    settings = RunPolicySettingsContract(
        exploration_mode=_as_literal(explicit_policy.get("exploration_mode"), "balanced"),
        generation_bias=_as_literal(
            explicit_policy.get("generation_bias"),
            _infer_generation_bias(allowed_generation),
        ),
        review_rigor=_as_literal(explicit_review_rigor, _infer_review_rigor()),
        evolution_style=_as_literal(
            explicit_policy.get("evolution_style"),
            _infer_evolution_style(config_payload.get("evolution")),
        ),
        budget_profile=_as_literal(
            explicit_policy.get("budget_profile"),
            _infer_budget_profile(config_payload),
        ),
        stop_policy=_as_literal(explicit_policy.get("stop_policy"), "standard"),
        iteration_policy=_as_literal(
            explicit_policy.get("iteration_policy"),
            _infer_iteration_policy(config_payload),
        ),
        iteration_band=_infer_iteration_band(explicit_policy.get("iteration_band"), config_payload),
        allowed_generation_strategies=allowed_generation,
        allowed_review_modes=allowed_review,
        human_checkpoint=_as_literal(explicit_policy.get("human_checkpoint"), "auto"),
    )

    return RunPolicyContract(
        input_file=_relative_to_run(run_dir, input_file),
        log_file=_relative_to_run(run_dir, log_file),
        policy=settings,
    )


def build_policy_decision(
    run_id: str,
    run_policy: RunPolicyContract,
    *,
    source: str,
) -> PolicyDecisionContract:
    """Build a deterministic policy decision artifact from the effective run policy."""
    policy = run_policy.policy
    rationale = [
        f"The run policy was loaded from {source}.",
        f"Exploration mode is `{policy.exploration_mode}` with generation bias `{policy.generation_bias}`.",
        f"Review rigor is `{policy.review_rigor}` and the budget profile is `{policy.budget_profile}`.",
        f"Iteration policy is `{policy.iteration_policy}` and stop policy is `{policy.stop_policy}`.",
    ]
    if policy.iteration_band is not None:
        rationale.append(f"Iteration band override: `{policy.iteration_band}`.")
    if policy.allowed_generation_strategies:
        rationale.append("Allowed generation strategies: " + ", ".join(policy.allowed_generation_strategies) + ".")
    if policy.allowed_review_modes:
        rationale.append(
            "Allowed review modes remain fixed to the canonical full review stack: "
            + ", ".join(policy.allowed_review_modes)
            + "."
        )

    return PolicyDecisionContract(
        status="completed",
        run_id=run_id,
        policy=policy,
        rationale=rationale,
    )


def _infer_generation_strategies(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return list(DEFAULT_ALLOWED_GENERATION_STRATEGIES)

    strategies: list[str] = []
    if bool(payload.get("literature_exploration_generation", False)):
        strategies.append("literature_exploration_generation")

    debate_payload = payload.get("scientific_debates_generation")
    if isinstance(debate_payload, dict):
        if bool(debate_payload.get("enabled", False)):
            strategies.append("scientific_debates_generation")
    elif bool(debate_payload):
        strategies.append("scientific_debates_generation")

    if bool(payload.get("assumptions_identification_generation", False)):
        strategies.append("assumptions_identification_generation")

    return strategies or list(DEFAULT_ALLOWED_GENERATION_STRATEGIES)


def _normalize_generation_strategies(payload: Any) -> list[str]:
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if isinstance(item, str) and item in _GENERATION_STRATEGY_NAMES]


def _infer_generation_bias(allowed_generation: list[str]) -> str:
    unique = set(allowed_generation)
    if unique == {"literature_exploration_generation"}:
        return "literature_heavy"
    if unique == {"scientific_debates_generation"}:
        return "debate_heavy"
    if unique == {"assumptions_identification_generation"}:
        return "assumptions_heavy"
    return "mixed"


def _infer_review_rigor() -> str:
    return "standard"


def _infer_evolution_style(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "balanced"
    enabled = {key for key, value in payload.items() if bool(value)}
    if {"out_of_box_evolution", "combination_evolution"} & enabled:
        return "diversify"
    if {"grounding_evolution", "feasibility_evolution"} <= enabled:
        return "exploit"
    return "balanced"


def _infer_budget_profile(config_payload: dict[str, Any]) -> str:
    max_iterations = _read_int(config_payload, "convergence", "max_iterations")
    if max_iterations is not None and max_iterations >= 8:
        return "high"
    if max_iterations is not None and max_iterations <= 4:
        return "low"
    return "medium"


def _infer_iteration_policy(config_payload: dict[str, Any]) -> str:
    explicit_policy = config_payload.get("policy")
    if isinstance(explicit_policy, dict):
        explicit_band = explicit_policy.get("iteration_band")
        if isinstance(explicit_band, str) and explicit_band:
            return "capped"

    max_iterations = _read_int(config_payload, "convergence", "max_iterations")
    if max_iterations is not None:
        return "capped"
    return "completion_driven"


def _infer_iteration_band(explicit_value: Any, config_payload: dict[str, Any]) -> str | None:
    if isinstance(explicit_value, str) and explicit_value:
        return explicit_value

    max_iterations = _read_int(config_payload, "convergence", "max_iterations")
    if max_iterations is None:
        return None
    if 6 <= max_iterations <= 10:
        return "6_10"
    if 10 < max_iterations <= 14:
        return "10_14"
    if 15 <= max_iterations <= 20:
        return "15_20"
    if 20 < max_iterations <= 30:
        return "20_30"
    return None


def _read_int(payload: dict[str, Any], section: str, key: str) -> int | None:
    section_payload = payload.get(section)
    if not isinstance(section_payload, dict):
        return None
    value = section_payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _as_literal(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _relative_to_run(run_dir: Path, value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        return value
    try:
        return str(path.relative_to(run_dir))
    except ValueError:
        return str(path)
