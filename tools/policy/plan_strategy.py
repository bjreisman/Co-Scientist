"""Plan the next strategy bundle for a run from persisted artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


_CANONICAL_ISLAND_ITEM_KEYS = {"id", "decayed_reward", "decayed_visits", "visit_count"}
_DEPRECATED_ISLAND_ITEM_KEYS = {"island_id", "reward", "stagnation_count", "last_updated"}
_EVOLUTION_SELECTION_SIGNAL_KEYS = {"selection_strategy", "selected_parent_ids", "selected_island_ids"}


if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.append(str(_REPO_ROOT))
    from packages.agent_contracts import (  # type: ignore[no-redef]
        HypothesisContract,
        IslandStateContract,
        ResearchPlanContract,
        ResolvedRunConfigContract,
        StrategyDecisionRecordContract,
        StrategyPlanContract,
    )
    from packages.agent_mechanics import select_island_hypotheses  # type: ignore[no-redef]
    from packages.agent_support import (  # type: ignore[no-redef]
        PIPELINE_STAGE_CONFIGURATION,
        PIPELINE_STAGE_EVOLUTION,
        PIPELINE_STAGE_GENERATION,
        PIPELINE_STAGE_INSIGHTS,
        PIPELINE_STAGE_PROXIMITY,
        PIPELINE_STAGE_RANKING,
        build_strategy_decision_record,
        build_strategy_plan,
        normalize_pipeline_stage,
    )
    from packages.run_artifacts import ArtifactStore  # type: ignore[no-redef]
    from tools.host.host_config import HostSettings  # type: ignore[no-redef]
    from tools.validation.verify_pipeline_completion import advise_pipeline_completion  # type: ignore[no-redef]
else:
    from packages.agent_contracts import (
        HypothesisContract,
        IslandStateContract,
        ResearchPlanContract,
        ResolvedRunConfigContract,
        StrategyDecisionRecordContract,
        StrategyPlanContract,
    )
    from packages.agent_mechanics import select_island_hypotheses
    from packages.agent_support import (
        PIPELINE_STAGE_CONFIGURATION,
        PIPELINE_STAGE_EVOLUTION,
        PIPELINE_STAGE_GENERATION,
        PIPELINE_STAGE_INSIGHTS,
        PIPELINE_STAGE_PROXIMITY,
        PIPELINE_STAGE_RANKING,
        build_strategy_decision_record,
        build_strategy_plan,
        normalize_pipeline_stage,
    )
    from packages.run_artifacts import ArtifactStore

    from ..host.host_config import HostSettings
    from ..validation.verify_pipeline_completion import advise_pipeline_completion


def plan_strategy_for_run(
    run_target: Path,
    *,
    current_phase: str | None = None,
) -> StrategyPlanContract:
    """Plan and persist the next strategy bundle for a run."""
    settings = HostSettings.from_path(run_target)
    run_dir = Path(settings.run_dir).resolve()
    artifact_store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
    artifact_store.ensure_layout()

    resolved_payload = artifact_store.read_resolved_run_config()
    if not isinstance(resolved_payload, dict):
        raise FileNotFoundError(f"Missing state/RESOLVED_RUN_CONFIG.json under {run_dir}")
    resolved_config = ResolvedRunConfigContract.from_payload(resolved_payload)

    pipeline_state = artifact_store.read_pipeline_state() or {}
    evolution_state = artifact_store.read_evolution_state() or {}
    hypotheses = _load_hypotheses(run_dir)
    viable_hypotheses = [hypothesis for hypothesis in hypotheses if hypothesis.review.initial_review.passed]
    research_plan_status = _read_research_plan_status(run_dir)
    advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

    inferred_phase = current_phase or _infer_phase(pipeline_state, run_dir, len(hypotheses))
    routing_advisory = _normalize_routing_advisory(
        inferred_phase,
        advisory.recommendedAction,
        hypothesis_count=len(hypotheses),
    )
    entered_top_k_last_round = evolution_state.get("enteredTopKLastRound")
    if not isinstance(entered_top_k_last_round, bool | type(None)):
        entered_top_k_last_round = None

    plan = build_strategy_plan(
        current_phase=inferred_phase,
        run_policy=settings.run_policy,
        resolved_config=resolved_config,
        hypothesis_count=len(hypotheses),
        viable_hypothesis_count=len(viable_hypotheses),
        convergence_count=_safe_int(evolution_state.get("convergenceCount")),
        convergence_threshold=_safe_int(evolution_state.get("convergenceThreshold"))
        or settings.convergence.convergence_count_threshold,
        top_hypothesis_ids=_read_top_hypothesis_ids(evolution_state),
        entered_top_k_last_round=entered_top_k_last_round,
        research_plan_status=research_plan_status,
        advisory_recommendation=routing_advisory,
    )
    replay_base_plan = plan
    if (
        inferred_phase == PIPELINE_STAGE_EVOLUTION
        and routing_advisory == "inspect_state"
        and plan.next_action == "inspect_state"
    ):
        replay_base_plan = build_strategy_plan(
            current_phase=inferred_phase,
            run_policy=settings.run_policy,
            resolved_config=resolved_config,
            hypothesis_count=len(hypotheses),
            viable_hypothesis_count=len(viable_hypotheses),
            convergence_count=_safe_int(evolution_state.get("convergenceCount")),
            convergence_threshold=_safe_int(evolution_state.get("convergenceThreshold"))
            or settings.convergence.convergence_count_threshold,
            top_hypothesis_ids=_read_top_hypothesis_ids(evolution_state),
            entered_top_k_last_round=entered_top_k_last_round,
            research_plan_status=research_plan_status,
            advisory_recommendation="",
        )

    replay_decision = _find_replayable_open_continue_evolution_decision(run_dir, replay_base_plan)
    if replay_decision is not None:
        _apply_continue_evolution_decision_to_plan(plan, replay_decision)
        artifact_store.write_strategy_plan(plan)
        return plan

    if plan.current_phase == PIPELINE_STAGE_EVOLUTION and plan.next_action == "continue_evolution":
        _enrich_evolution_plan(
            plan,
            run_dir=run_dir,
            hypotheses=hypotheses,
            resolved_config=resolved_config,
            iteration_count=_safe_int(evolution_state.get("iterationCount")),
        )

    artifact_store.write_strategy_plan(plan)
    if _find_equivalent_open_continue_evolution_decision(run_dir, plan) is not None:
        return plan

    decision_index = _next_decision_index(run_dir)
    decision_record = build_strategy_decision_record(
        run_id=run_dir.name,
        decision_index=decision_index,
        plan=plan,
    )
    artifact_store.append_strategy_decision(decision_record)
    return plan


def _apply_continue_evolution_decision_to_plan(
    plan: StrategyPlanContract,
    decision: StrategyDecisionRecordContract,
) -> None:
    plan.status = decision.status
    plan.current_phase = decision.current_phase
    plan.next_action = decision.next_action
    plan.selected_generation_strategies = list(decision.selected_generation_strategies)
    plan.selected_evolution_strategies = list(decision.selected_evolution_strategies)
    plan.max_new_hypotheses = decision.max_new_hypotheses
    plan.reasoning = list(decision.reasoning)
    plan.advisory_recommendation = decision.advisory_recommendation
    plan.signals = dict(decision.signals)


def _load_hypotheses(run_dir: Path) -> list[HypothesisContract]:
    hypotheses_root = run_dir / "hypotheses"
    if not hypotheses_root.exists():
        return []
    hypotheses: list[HypothesisContract] = []
    for hypothesis_dir in sorted(path for path in hypotheses_root.iterdir() if path.is_dir()):
        artifact_path = hypothesis_dir / "HYPOTHESIS.json"
        if artifact_path.exists():
            hypotheses.append(HypothesisContract.from_json_file(artifact_path))
    return hypotheses


def _parse_island_item(item: object, index: int) -> IslandStateContract:
    if not isinstance(item, dict):
        raise ValueError(f"islands/ISLANDS.json items[{index}] must serialize an object.")
    deprecated_keys = sorted(set(item).intersection(_DEPRECATED_ISLAND_ITEM_KEYS))
    if deprecated_keys:
        raise ValueError(
            f"islands/ISLANDS.json items[{index}] contains deprecated non-canonical keys: "
            + ", ".join(deprecated_keys)
            + "."
        )
    non_canonical_keys = sorted(set(item).difference(_CANONICAL_ISLAND_ITEM_KEYS | _DEPRECATED_ISLAND_ITEM_KEYS))
    if non_canonical_keys:
        raise ValueError(
            f"islands/ISLANDS.json items[{index}] contains non-canonical keys: " + ", ".join(non_canonical_keys) + "."
        )
    missing_keys = sorted(_CANONICAL_ISLAND_ITEM_KEYS.difference(item))
    if missing_keys:
        raise ValueError(
            f"islands/ISLANDS.json items[{index}] is missing canonical keys: " + ", ".join(missing_keys) + "."
        )
    return IslandStateContract.from_payload(item)


def _load_islands(run_dir: Path, hypotheses: list[HypothesisContract]) -> dict[str, IslandStateContract]:
    islands_path = run_dir / "islands" / "ISLANDS.json"
    viable_hypothesis_island_ids = {
        hypothesis.island_id for hypothesis in hypotheses if hypothesis.is_viable and hypothesis.island_id
    }
    if viable_hypothesis_island_ids and not islands_path.exists():
        raise FileNotFoundError(
            "Viable hypotheses exist but canonical islands/ISLANDS.json is missing; refresh or repair island state "
            "before planning evolution."
        )

    islands: dict[str, IslandStateContract] = {}
    if islands_path.exists():
        payload = json.loads(islands_path.read_text(encoding="utf-8"))
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if isinstance(items, list):
            for index, item in enumerate(items):
                island = _parse_island_item(item, index)
                if island.id:
                    islands[island.id] = island
    missing_island_ids = sorted(viable_hypothesis_island_ids.difference(islands))
    if missing_island_ids:
        raise ValueError(
            "islands/ISLANDS.json is missing canonical island items for viable hypothesis island IDs: "
            + ", ".join(missing_island_ids)
            + "."
        )
    return islands


def _enrich_evolution_plan(
    plan: StrategyPlanContract,
    *,
    run_dir: Path,
    hypotheses: list[HypothesisContract],
    resolved_config: ResolvedRunConfigContract,
    iteration_count: int,
) -> None:
    islands = _load_islands(run_dir, hypotheses)
    viable_hypotheses = [hypothesis for hypothesis in hypotheses if hypothesis.is_viable and hypothesis.island_id]
    if not islands or not viable_hypotheses:
        return

    hypotheses_by_id = {hypothesis.id: hypothesis for hypothesis in viable_hypotheses}
    try:
        selection = select_island_hypotheses(
            islands,
            hypotheses_by_id,
            iteration_count,
            ucb_exploration_constant=resolved_config.island.ucb_exploration_constant,
            softmax_temperature=resolved_config.island.softmax_temperature,
            stagnation_epsilon=resolved_config.island.stagnation_epsilon,
        )
    except ValueError:
        return

    selected_parent_ids = [hypothesis.id for hypothesis in selection.hypotheses]
    selected_island_ids = [hypothesis.island_id for hypothesis in selection.hypotheses if hypothesis.island_id]
    plan.selected_evolution_strategies = _filter_evolution_bundle_for_selection_strategy(
        plan.selected_evolution_strategies,
        selection.strategy,
    )
    plan.signals["selection_strategy"] = selection.strategy
    plan.signals["selected_parent_ids"] = selected_parent_ids
    plan.signals["selected_island_ids"] = selected_island_ids
    if selected_parent_ids:
        plan.reasoning.append(
            "The active evolution round must create exactly one new child hypothesis from the selected parent set: "
            + ", ".join(selected_parent_ids)
            + "."
        )


def _filter_evolution_bundle_for_selection_strategy(
    strategies: list[str],
    selection_strategy: str,
) -> list[str]:
    if selection_strategy == "single_island":
        allowed = {
            "grounding_evolution",
            "coherence_evolution",
            "feasibility_evolution",
            "simplification_evolution",
        }
    elif selection_strategy == "multi_island":
        allowed = {
            "inspiration_evolution",
            "combination_evolution",
            "out_of_box_evolution",
        }
    else:
        return strategies

    filtered = [strategy for strategy in strategies if strategy in allowed]
    return filtered or strategies


def _infer_phase(pipeline_state: dict[str, object], run_dir: Path, hypothesis_count: int) -> str:
    value = pipeline_state.get("currentPhase")
    if isinstance(value, str) and value:
        return normalize_pipeline_stage(
            value,
            default=PIPELINE_STAGE_GENERATION if hypothesis_count == 0 else PIPELINE_STAGE_EVOLUTION,
        )
    current_stage_path = run_dir / "state" / "CURRENT_STAGE.json"
    if current_stage_path.exists():
        payload = json.loads(current_stage_path.read_text(encoding="utf-8"))
        stage = payload.get("stage")
        if isinstance(stage, str):
            normalized_stage = normalize_pipeline_stage(
                stage,
                default=PIPELINE_STAGE_GENERATION if hypothesis_count == 0 else PIPELINE_STAGE_EVOLUTION,
            )
            if normalized_stage in {
                PIPELINE_STAGE_CONFIGURATION,
                PIPELINE_STAGE_GENERATION,
                "Reflection",
                PIPELINE_STAGE_INSIGHTS,
                PIPELINE_STAGE_PROXIMITY,
                PIPELINE_STAGE_RANKING,
                PIPELINE_STAGE_EVOLUTION,
                "Research Overview",
            }:
                return normalized_stage
    return PIPELINE_STAGE_GENERATION if hypothesis_count == 0 else PIPELINE_STAGE_EVOLUTION


def _read_research_plan_status(run_dir: Path) -> str:
    research_plan_path = run_dir / "research_plan" / "RESEARCH_PLAN.json"
    if not research_plan_path.exists():
        return "missing"
    try:
        ResearchPlanContract.from_json_file(research_plan_path)
    except Exception:
        return "invalid"
    return "valid"


def _normalize_routing_advisory(current_phase: str, recommended_action: str, *, hypothesis_count: int) -> str:
    """Ignore completion-side blocked advice during initial seeding, but honor it later."""
    if recommended_action != "inspect_state":
        return recommended_action
    normalized_phase = normalize_pipeline_stage(
        current_phase,
        default=PIPELINE_STAGE_GENERATION if hypothesis_count == 0 else PIPELINE_STAGE_EVOLUTION,
    )
    if normalized_phase in {PIPELINE_STAGE_CONFIGURATION, PIPELINE_STAGE_GENERATION} and hypothesis_count == 0:
        return ""
    return recommended_action


def _next_decision_index(run_dir: Path) -> int:
    decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
    if not decisions_path.exists():
        return 1
    max_decision_index = 0
    for line in decisions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        decision_index = payload.get("decision_index")
        if isinstance(decision_index, int) and not isinstance(decision_index, bool):
            max_decision_index = max(max_decision_index, decision_index)
    return max_decision_index + 1


def _find_equivalent_open_continue_evolution_decision(
    run_dir: Path,
    plan: StrategyPlanContract,
) -> StrategyDecisionRecordContract | None:
    target_signature = _continue_evolution_signature(plan)
    if target_signature is None:
        return None
    consumed_decision_indices = _read_consumed_strategy_decision_indices(run_dir)
    for decision in reversed(_read_strategy_decisions(run_dir)):
        if decision.decision_index in consumed_decision_indices:
            continue
        if _continue_evolution_signature(decision) == target_signature:
            return decision
    return None


def _find_replayable_open_continue_evolution_decision(
    run_dir: Path,
    plan: StrategyPlanContract,
) -> StrategyDecisionRecordContract | None:
    target_signature = _continue_evolution_base_signature(plan)
    if target_signature is None:
        return None
    consumed_decision_indices = _read_consumed_strategy_decision_indices(run_dir)
    for decision in reversed(_read_strategy_decisions(run_dir)):
        if decision.decision_index in consumed_decision_indices:
            continue
        if _continue_evolution_base_signature(decision) == target_signature:
            return decision
    return None


def _read_strategy_decisions(run_dir: Path) -> list[StrategyDecisionRecordContract]:
    decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
    if not decisions_path.exists():
        return []
    decisions: list[StrategyDecisionRecordContract] = []
    for line in decisions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            decisions.append(StrategyDecisionRecordContract.from_payload(json.loads(line)))
        except (json.JSONDecodeError, ValueError):
            continue
    return decisions


def _read_consumed_strategy_decision_indices(run_dir: Path) -> set[int]:
    rounds_path = run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
    if not rounds_path.exists():
        return set()
    consumed: set[int] = set()
    for line in rounds_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        decision_index = payload.get("decision_index")
        if isinstance(decision_index, int) and not isinstance(decision_index, bool):
            consumed.add(decision_index)
    return consumed


def _continue_evolution_signature(plan: StrategyPlanContract) -> tuple[object, ...] | None:
    if plan.current_phase != PIPELINE_STAGE_EVOLUTION or plan.next_action != "continue_evolution":
        return None
    return (
        plan.current_phase,
        plan.next_action,
        tuple(plan.selected_evolution_strategies),
        plan.max_new_hypotheses,
        _freeze_signature_value(plan.signals),
    )


def _continue_evolution_base_signature(plan: StrategyPlanContract) -> tuple[object, ...] | None:
    if plan.current_phase != PIPELINE_STAGE_EVOLUTION or plan.next_action != "continue_evolution":
        return None
    base_signals = {key: value for key, value in plan.signals.items() if key not in _EVOLUTION_SELECTION_SIGNAL_KEYS}
    return (
        plan.current_phase,
        plan.next_action,
        plan.max_new_hypotheses,
        _freeze_signature_value(base_signals),
    )


def _freeze_signature_value(value: object) -> object:
    if isinstance(value, dict):
        return tuple(
            (str(key), _freeze_signature_value(item))
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        )
    if isinstance(value, list):
        return tuple(_freeze_signature_value(item) for item in value)
    return value


def _read_top_hypothesis_ids(evolution_state: dict[str, object]) -> list[str]:
    payload = evolution_state.get("topHypothesisIds", [])
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload if isinstance(item, str)]


def _safe_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan the next Co-Scientist strategy bundle from run-local artifacts."
    )
    parser.add_argument("run_target", type=Path, help="Run directory or compatibility config.yaml path.")
    parser.add_argument(
        "--phase",
        type=str,
        default="",
        help="Optional explicit phase override for the planned strategy bundle.",
    )
    return parser.parse_args(argv)


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the strategy planner CLI and return a process exit code."""
    args = _parse_args(argv)
    run_target = args.run_target.resolve()
    if not run_target.exists():
        print(f"Run target not found: {run_target}", file=sys.stderr)
        return 2

    plan = plan_strategy_for_run(run_target, current_phase=args.phase or None)
    print(json.dumps(plan.model_dump(mode="json"), indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.policy.plan_strategy`."""
    try:
        return run_cli(argv)
    except Exception as exc:
        print(f"Strategy planning failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
