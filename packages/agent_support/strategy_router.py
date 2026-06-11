"""Deterministic helpers for strategy routing decisions."""

from __future__ import annotations

from typing import Literal

from packages.agent_contracts import (
    ResolvedRunConfigContract,
    RunPolicyContract,
    StrategyDecisionRecordContract,
    StrategyPlanContract,
)
from packages.agent_support.pipeline_semantics import (
    PIPELINE_STAGE_CONFIGURATION,
    PIPELINE_STAGE_EVOLUTION,
    PIPELINE_STAGE_GENERATION,
    PIPELINE_STAGE_IDLE,
    PIPELINE_STAGE_INSIGHTS,
    PIPELINE_STAGE_PROXIMITY,
    PIPELINE_STAGE_RANKING,
    PIPELINE_STAGE_REFLECTION,
    PIPELINE_STAGE_RESEARCH_OVERVIEW,
    normalize_pipeline_stage,
)


EvolutionStyleName = Literal["exploit", "balanced", "diversify"]

_EVOLUTION_STYLE_MAP: dict[EvolutionStyleName, list[str]] = {
    "exploit": ["grounding_evolution", "feasibility_evolution", "coherence_evolution"],
    "balanced": ["grounding_evolution", "coherence_evolution", "combination_evolution"],
    "diversify": ["inspiration_evolution", "combination_evolution", "out_of_box_evolution"],
}

__all__ = ["build_strategy_decision_record", "build_strategy_plan"]


def build_strategy_plan(
    *,
    current_phase: str,
    run_policy: RunPolicyContract,
    resolved_config: ResolvedRunConfigContract,
    hypothesis_count: int,
    viable_hypothesis_count: int,
    convergence_count: int,
    convergence_threshold: int,
    top_hypothesis_ids: list[str],
    entered_top_k_last_round: bool | None,
    research_plan_status: str = "valid",
    advisory_recommendation: str = "",
) -> StrategyPlanContract:
    """Build a deterministic strategy plan from run artifacts and routing policy."""
    normalized_phase = _normalize_phase(current_phase, hypothesis_count)
    signals = {
        "hypothesis_count": hypothesis_count,
        "viable_hypothesis_count": viable_hypothesis_count,
        "convergence_count": convergence_count,
        "convergence_threshold": convergence_threshold,
        "top_hypothesis_ids": top_hypothesis_ids,
        "entered_top_k_last_round": entered_top_k_last_round,
        "research_plan_status": research_plan_status,
    }
    allowed_generation = list(run_policy.policy.allowed_generation_strategies)
    evolution_style = run_policy.policy.evolution_style

    if research_plan_status != "valid":
        signals["research_plan_required"] = True
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_CONFIGURATION,
            next_action="run_configuration",
            reasoning=[
                "A valid `research_plan/RESEARCH_PLAN.json` is required before generation or evolution can continue.",
                (
                    "The persisted research plan is missing."
                    if research_plan_status == "missing"
                    else "The persisted research plan exists but is invalid and must be rebuilt."
                ),
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if normalized_phase == PIPELINE_STAGE_CONFIGURATION:
        normalized_phase = PIPELINE_STAGE_GENERATION

    if advisory_recommendation == "inspect_state":
        signals["inspection_required"] = True
        return StrategyPlanContract(
            status="blocked",
            current_phase=normalized_phase,
            next_action="inspect_state",
            reasoning=[
                "The completion advisory reported a blocked pipeline state that requires manual inspection or repair.",
                "Do not dispatch generation, review, or evolution work until the persisted routing artifacts "
                "are consistent again.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if normalized_phase == PIPELINE_STAGE_GENERATION:
        selected_generation = _select_generation_strategies(
            allowed_generation,
            run_policy.policy.generation_bias,
            hypothesis_count=hypothesis_count,
            viable_hypothesis_count=viable_hypothesis_count,
            convergence_count=convergence_count,
            entered_top_k_last_round=entered_top_k_last_round,
        )
        reasoning = _build_generation_reasoning(
            selected_generation,
            hypothesis_count=hypothesis_count,
            viable_hypothesis_count=viable_hypothesis_count,
            convergence_count=convergence_count,
        )
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_GENERATION,
            next_action="run_generation",
            selected_generation_strategies=selected_generation,
            max_new_hypotheses=_determine_generation_batch_size(
                selected_generation,
                hypothesis_count=hypothesis_count,
                top_k_limit=resolved_config.ranking.tournament_top_k,
            ),
            reasoning=reasoning,
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if normalized_phase == PIPELINE_STAGE_REFLECTION:
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_REFLECTION,
            next_action="run_review",
            reasoning=[
                "Reflection was requested explicitly for the current routing phase.",
                "The canonical full review stack must run before evolution can continue.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if normalized_phase == PIPELINE_STAGE_INSIGHTS:
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_INSIGHTS,
            next_action="run_insights",
            reasoning=[
                "The persisted run state shows the active evolution round is currently in the insights "
                "aggregation step.",
                "Resume from run-level critique synthesis before continuing to proximity updates or ranking.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if normalized_phase == PIPELINE_STAGE_PROXIMITY:
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_PROXIMITY,
            next_action="run_proximity",
            reasoning=[
                "The persisted run state shows the active evolution round is currently in the proximity update step.",
                "Refresh similarity state before any ranking or further evolution routing decisions.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if normalized_phase == PIPELINE_STAGE_RANKING:
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_RANKING,
            next_action="run_ranking",
            reasoning=[
                "The persisted run state shows the active evolution round is currently in the ranking step.",
                "Resume tournament and Elo updates before attempting another evolution child or overview transition.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if normalized_phase == PIPELINE_STAGE_RESEARCH_OVERVIEW:
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_RESEARCH_OVERVIEW,
            next_action="generate_overview",
            reasoning=[
                "The routing phase already targets the final overview stage.",
                "No further generation or evolution routing is required before overview synthesis.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if advisory_recommendation == "generate_overview":
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_EVOLUTION,
            next_action="generate_overview",
            reasoning=[
                "The completion advisory recommends transitioning from evolution to the overview stage.",
                "The evolution stop conditions indicate the run is ready for synthesis.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if viable_hypothesis_count == 0 or hypothesis_count == 0:
        selected_generation = _select_generation_strategies(
            allowed_generation,
            run_policy.policy.generation_bias,
            hypothesis_count=hypothesis_count,
            viable_hypothesis_count=viable_hypothesis_count,
            convergence_count=convergence_count,
            entered_top_k_last_round=entered_top_k_last_round,
        )
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_EVOLUTION,
            next_action="return_to_generation",
            selected_generation_strategies=selected_generation,
            max_new_hypotheses=_determine_generation_batch_size(
                selected_generation,
                hypothesis_count=hypothesis_count,
                top_k_limit=resolved_config.ranking.tournament_top_k,
            ),
            reasoning=[
                "The run does not currently have enough viable candidates to justify more evolution.",
                "Routing back to generation should rebuild the frontier before ranking continues.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    if convergence_count >= max(1, convergence_threshold // 2) and entered_top_k_last_round is False:
        selected_generation = _select_generation_strategies(
            allowed_generation,
            run_policy.policy.generation_bias,
            hypothesis_count=hypothesis_count,
            viable_hypothesis_count=viable_hypothesis_count,
            convergence_count=convergence_count,
            entered_top_k_last_round=entered_top_k_last_round,
        )
        return StrategyPlanContract(
            current_phase=PIPELINE_STAGE_EVOLUTION,
            next_action="return_to_generation",
            selected_generation_strategies=selected_generation,
            max_new_hypotheses=_determine_generation_batch_size(
                selected_generation,
                hypothesis_count=hypothesis_count,
                top_k_limit=resolved_config.ranking.tournament_top_k,
            ),
            reasoning=[
                "Convergence is rising while the top-k frontier is not changing.",
                "A new generation pass should diversify the search frontier before more evolution.",
            ],
            advisory_recommendation=advisory_recommendation,
            signals=signals,
        )

    return StrategyPlanContract(
        current_phase=PIPELINE_STAGE_EVOLUTION,
        next_action="continue_evolution",
        selected_evolution_strategies=_EVOLUTION_STYLE_MAP.get(evolution_style, _EVOLUTION_STYLE_MAP["balanced"]),
        reasoning=[
            "The run still has viable frontier candidates and has not hit an overview boundary.",
            f"Evolution style `{evolution_style}` determines the active evolution strategy set.",
        ],
        advisory_recommendation=advisory_recommendation,
        signals=signals,
    )


def build_strategy_decision_record(
    *,
    run_id: str,
    decision_index: int,
    plan: StrategyPlanContract,
) -> StrategyDecisionRecordContract:
    """Build one append-only strategy decision record from the active plan."""
    payload = plan.model_dump(mode="json")
    payload["run_id"] = run_id
    payload["decision_index"] = decision_index
    return StrategyDecisionRecordContract.from_payload(payload)


def _normalize_phase(current_phase: str, hypothesis_count: int) -> str:
    normalized_phase = normalize_pipeline_stage(current_phase, default=PIPELINE_STAGE_IDLE)
    if normalized_phase in {
        PIPELINE_STAGE_GENERATION,
        PIPELINE_STAGE_REFLECTION,
        PIPELINE_STAGE_INSIGHTS,
        PIPELINE_STAGE_PROXIMITY,
        PIPELINE_STAGE_RANKING,
        PIPELINE_STAGE_EVOLUTION,
        PIPELINE_STAGE_RESEARCH_OVERVIEW,
        PIPELINE_STAGE_CONFIGURATION,
    }:
        return normalized_phase
    return PIPELINE_STAGE_GENERATION if hypothesis_count == 0 else PIPELINE_STAGE_EVOLUTION


def _select_generation_strategies(
    allowed_generation: list[str],
    generation_bias: str,
    *,
    hypothesis_count: int,
    viable_hypothesis_count: int,
    convergence_count: int,
    entered_top_k_last_round: bool | None,
) -> list[str]:
    if not allowed_generation:
        return []
    if hypothesis_count == 0:
        return list(allowed_generation)

    low_viability = viable_hypothesis_count == 0
    low_diversity = convergence_count > 0 and entered_top_k_last_round is False

    preferred: list[str] = []
    if low_viability:
        preferred.extend(["literature_exploration_generation", "assumptions_identification_generation"])
    elif low_diversity:
        preferred.extend(["scientific_debates_generation", "literature_exploration_generation"])
    elif generation_bias == "literature_heavy":
        preferred.extend(["literature_exploration_generation", "assumptions_identification_generation"])
    elif generation_bias == "debate_heavy":
        preferred.extend(["scientific_debates_generation", "literature_exploration_generation"])
    elif generation_bias == "assumptions_heavy":
        preferred.extend(["assumptions_identification_generation", "literature_exploration_generation"])
    else:
        preferred.extend(allowed_generation if hypothesis_count == 0 else allowed_generation[:2])

    selected: list[str] = []
    for strategy in preferred:
        if strategy in allowed_generation and strategy not in selected:
            selected.append(strategy)
    if not selected:
        return allowed_generation[:2]
    return selected[:2]


def _determine_generation_batch_size(
    selected_generation: list[str],
    *,
    hypothesis_count: int,
    top_k_limit: int,
) -> int:
    if not selected_generation:
        return 0
    if hypothesis_count == 0:
        return min(len(selected_generation), max(top_k_limit, 0))
    return max(1, min(len(selected_generation), max(top_k_limit, 0)))


def _build_generation_reasoning(
    selected_generation: list[str],
    *,
    hypothesis_count: int,
    viable_hypothesis_count: int,
    convergence_count: int,
) -> list[str]:
    reasoning = [
        "The generation plan is constrained by the effective run policy and selected strategy budget.",
        "Selected generation strategies: " + ", ".join(selected_generation) + ".",
    ]
    if hypothesis_count == 0:
        reasoning.append("The run does not have any persisted hypotheses yet, so generation must seed the frontier.")
    elif viable_hypothesis_count == 0:
        reasoning.append("The current frontier lacks viable hypotheses, so grounded regeneration is required.")
    elif convergence_count > 0:
        reasoning.append("The frontier is showing early signs of convergence, so generation should diversify inputs.")
    return reasoning
