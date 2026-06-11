"""Advisory completion verifier for host-agent and skills-first pipeline runs."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.append(str(_REPO_ROOT))
    from packages.agent_contracts import (  # type: ignore[no-redef]
        CompletionAction,
        CompletionDecisionContract,
        CompletionReadiness,
        EvolutionStateContract,
        HypothesisContract,
        ResearchOverviewContract,
        ReviewContract,
    )
    from packages.run_artifacts import REVIEW_STAGE_FILE_MAP, ArtifactStore  # type: ignore[no-redef]
    from tools.host.host_config import HostSettings  # type: ignore[no-redef]
    from tools.validation.contract_validation import validate_run_artifacts  # type: ignore[no-redef]
else:
    from packages.agent_contracts import (
        CompletionAction,
        CompletionDecisionContract,
        CompletionReadiness,
        EvolutionStateContract,
        HypothesisContract,
        ResearchOverviewContract,
        ReviewContract,
    )
    from packages.run_artifacts import REVIEW_STAGE_FILE_MAP, ArtifactStore

    from ..host.host_config import HostSettings
    from .contract_validation import validate_run_artifacts


class CompletionAdvisory(BaseModel):
    """Structured recommendation for what the pipeline should do next."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(default="advisory")
    completionReadiness: CompletionReadiness
    recommendedAction: CompletionAction
    reasons: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)
    overrideAllowed: bool = Field(default=True)
    requestedSkill: str = Field(default="co-scientist-pipeline")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Advise whether a Co-Scientist run should continue evolving, generate an overview, or complete."
    )
    parser.add_argument("run_dir", type=Path, help="Path to the run directory.")
    parser.add_argument(
        "--skill",
        type=str,
        default="co-scientist-pipeline",
        help="Requested top-level skill name for the advisory context.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the advisory JSON.",
    )
    parser.add_argument(
        "--write-decision",
        type=str,
        choices=("continue_evolution", "generate_overview", "complete", "inspect_state"),
        default="",
        help="Optional decision to persist as state/COMPLETION_DECISION.json.",
    )
    parser.add_argument(
        "--rationale",
        action="append",
        default=[],
        help="Optional rationale line to persist with --write-decision. Repeatable.",
    )
    return parser.parse_args(argv)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sync_review_from_stage_artifacts(hypothesis_dir: Path, review: ReviewContract) -> ReviewContract:
    synced_review = ReviewContract.from_model_like(review)
    review_dir = hypothesis_dir / "REVIEW"
    for field_name, (filename, contract_type) in REVIEW_STAGE_FILE_MAP.items():
        stage_path = review_dir / filename
        if not stage_path.exists():
            continue
        stage_payload = contract_type.model_validate(_load_json(stage_path))
        setattr(synced_review, field_name, stage_payload)
    return synced_review


def _load_hypotheses(run_dir: Path) -> list[HypothesisContract]:
    hypotheses_root = run_dir / "hypotheses"
    if not hypotheses_root.exists():
        return []
    hypotheses: list[HypothesisContract] = []
    for hypothesis_dir in sorted(path for path in hypotheses_root.iterdir() if path.is_dir()):
        hypothesis_path = hypothesis_dir / "HYPOTHESIS.json"
        if hypothesis_path.exists():
            hypothesis = HypothesisContract.from_json_file(hypothesis_path)
            synced_review = _sync_review_from_stage_artifacts(hypothesis_dir, hypothesis.review)
            hypotheses.append(hypothesis.model_copy(update={"review": synced_review}))
    return hypotheses


def _count_strategy_decisions(run_dir: Path) -> int:
    path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _review_bundle_complete(hypothesis: HypothesisContract) -> bool:
    review = hypothesis.review
    return all(
        (
            review.initial_review.status == "completed",
            review.full_review.status == "completed",
            review.deep_verification_review.status == "completed",
            review.observation_review.status == "completed",
            review.simulation_review.status == "completed",
            review.review_summary.status == "completed",
        )
    )


def _effective_convergence_threshold(base_threshold: int, stop_policy: str) -> int:
    """Adjust convergence sensitivity from the stop policy."""
    if stop_policy == "exploratory":
        return base_threshold + 1
    if stop_policy == "strict":
        return max(1, base_threshold - 1)
    return base_threshold


def _is_ranking_writeback_error(message: str) -> bool:
    normalized = message.lower()
    return any(
        marker in normalized
        for marker in (
            "elo rating",
            "ranking update receipt",
            "ranking-elo-update",
            "apply_and_persist_elo_updates",
        )
    )


def advise_pipeline_completion(
    run_dir: Path,
    *,
    requested_skill: str = "co-scientist-pipeline",
) -> CompletionAdvisory:
    """Return an advisory recommendation for pipeline continuation or completion."""
    run_dir = run_dir.resolve()
    settings = HostSettings.from_run_dir(run_dir)
    artifact_store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
    pipeline_state = artifact_store.read_pipeline_state() or {}
    evolution_state_payload = artifact_store.read_evolution_state()
    has_persisted_evolution_state = isinstance(evolution_state_payload, dict)
    evolution_state = (
        EvolutionStateContract.from_payload(evolution_state_payload)
        if has_persisted_evolution_state
        else EvolutionStateContract(
            convergenceThreshold=settings.convergence.convergence_count_threshold,
            maxIterations=settings.convergence.max_iterations,
        )
    )

    hypotheses = _load_hypotheses(run_dir)
    hypotheses_by_id = {hypothesis.id: hypothesis for hypothesis in hypotheses}
    evolved_hypotheses = [hypothesis for hypothesis in hypotheses if hypothesis.parent_ids]
    strategy_decision_count = _count_strategy_decisions(run_dir)
    viable_hypotheses = [hypothesis for hypothesis in hypotheses if hypothesis.is_viable]
    effective_top_k = min(settings.ranking.tournament_top_k, len(viable_hypotheses))
    persisted_effective_top_k = evolution_state.effectiveTopK
    effective_top_k_mismatch = has_persisted_evolution_state and persisted_effective_top_k != effective_top_k
    fallback_top_hypotheses = sorted(viable_hypotheses, key=lambda hypothesis: hypothesis.elo_rating, reverse=True)[
        :effective_top_k
    ]
    frontier_hypothesis_ids = [
        hypothesis_id
        for hypothesis_id in evolution_state.topHypothesisIds
        if isinstance(hypothesis_id, str) and hypothesis_id.strip()
    ]
    if frontier_hypothesis_ids:
        top_hypotheses = [
            hypotheses_by_id[hypothesis_id]
            for hypothesis_id in frontier_hypothesis_ids
            if hypothesis_id in hypotheses_by_id
        ]
    else:
        top_hypotheses = fallback_top_hypotheses
    missing_frontier_ids = [
        hypothesis_id for hypothesis_id in frontier_hypothesis_ids if hypothesis_id not in hypotheses_by_id
    ]
    non_viable_frontier_ids = [hypothesis.id for hypothesis in top_hypotheses if not hypothesis.is_viable]
    frontier_evolved_without_placement_ids = [
        hypothesis.id
        for hypothesis in top_hypotheses
        if hypothesis.is_viable and hypothesis.parent_ids and not hypothesis.placement_match_ids
    ]
    run_policy = settings.run_policy.policy
    stop_policy = run_policy.stop_policy
    iteration_policy = run_policy.iteration_policy
    iteration_band = run_policy.iteration_band or ""
    effective_convergence_threshold = _effective_convergence_threshold(
        settings.convergence.convergence_count_threshold,
        stop_policy,
    )
    safety_max_iterations = settings.convergence.safety_max_iterations
    has_resolved_run_config = settings.resolved_run_config is not None
    persisted_safety_max_iterations = evolution_state.safetyMaxIterations
    safety_max_iterations_mismatch = (
        has_persisted_evolution_state
        and has_resolved_run_config
        and persisted_safety_max_iterations != safety_max_iterations
    )
    safety_stop_before_resolved_ceiling = (
        evolution_state.stopReason == "safety_iteration_limit_reached"
        and has_resolved_run_config
        and safety_max_iterations > 0
        and evolution_state.iterationCount < safety_max_iterations
    )

    overview_path = run_dir / "meta" / "RESEARCH_OVERVIEW.json"
    overview_exists = overview_path.exists()
    overview_valid = False
    overview_status = ""
    overview_content_present = False
    if overview_exists:
        overview_contract = ResearchOverviewContract.from_json_file(overview_path)
        overview_status = overview_contract.status
        overview_content_present = bool(overview_contract.content.strip())
        overview_valid = overview_contract.status == "completed" and overview_content_present

    completed_skills = pipeline_state.get("completedSkills", [])
    if not isinstance(completed_skills, list):
        completed_skills = []
    completed_skills = [skill for skill in completed_skills if isinstance(skill, str)]
    validation_summary = validate_run_artifacts(run_dir, requested_skill=requested_skill)
    evolution_status_mismatch = (
        str(pipeline_state.get("status", "")) == "completed" and evolution_state.status == "running"
    )

    reasons: list[str] = []
    readiness: CompletionReadiness
    action: CompletionAction

    validation_errors = [issue.message for issue in validation_summary.issues if issue.severity == "error"]
    ranking_writeback_invalid = any(_is_ranking_writeback_error(message) for message in validation_errors)

    if validation_summary.status == "invalid":
        readiness = "blocked"
        action = "inspect_state"
        if evolution_state.enteredTopKLastRound is True and evolution_state.convergenceCount > 0:
            reasons.append(
                "The evolution state is inconsistent: `enteredTopKLastRound` is true while "
                "`convergenceCount` is still above 0."
            )
        if (
            evolution_state.stopReason == "convergence_reached"
            and evolution_state.convergenceCount < effective_convergence_threshold
        ):
            reasons.append(
                "The evolution state recorded `convergence_reached` before the effective convergence "
                "threshold was met."
            )
        if evolution_status_mismatch:
            reasons.append("The pipeline is completed while the evolution state is still marked `running`.")
        if effective_top_k_mismatch:
            reasons.append(
                "The evolution state effective top-k does not match the resolved ranking top-k and viable "
                "hypothesis count."
            )
        if safety_max_iterations_mismatch:
            reasons.append(
                "The evolution state safety ceiling does not match the resolved run configuration "
                f"({persisted_safety_max_iterations} != {safety_max_iterations})."
            )
        if safety_stop_before_resolved_ceiling:
            reasons.append(
                "The evolution state recorded `safety_iteration_limit_reached` before the resolved safety "
                f"ceiling was met ({evolution_state.iterationCount}/{safety_max_iterations})."
            )
        if ranking_writeback_invalid:
            reasons.append(
                "The ranking artifacts are inconsistent with Elo writeback or ranking update receipt coverage."
            )
            reasons.append("Resume should repair ranking before continuing evolution.")
        reasons.append("Artifact validation reported blocking inconsistencies.")
        reasons.extend(validation_errors[:3])
    elif not hypotheses:
        readiness = "blocked"
        action = "inspect_state"
        reasons.append("No hypothesis artifacts are present yet.")
    elif missing_frontier_ids:
        readiness = "blocked"
        action = "inspect_state"
        reasons.append(
            "The evolution frontier references hypothesis IDs that are missing from canonical HYPOTHESIS.json "
            "artifacts: " + ", ".join(missing_frontier_ids)
        )
    elif non_viable_frontier_ids:
        readiness = "blocked"
        action = "inspect_state"
        reasons.append(
            "The evolution frontier includes hypotheses that are not currently viable after canonical review "
            "synchronization: " + ", ".join(non_viable_frontier_ids)
        )
    elif frontier_evolved_without_placement_ids:
        readiness = "blocked"
        action = "inspect_state"
        reasons.append(
            "The evolution frontier includes evolved viable hypotheses without placement tournament provenance: "
            + ", ".join(frontier_evolved_without_placement_ids)
        )
    elif evolution_state.enteredTopKLastRound is True and evolution_state.convergenceCount > 0:
        readiness = "blocked"
        action = "inspect_state"
        reasons.append(
            "The evolution state is inconsistent: `enteredTopKLastRound` is true while `convergenceCount` "
            "is still above 0."
        )
    elif (
        evolution_state.stopReason == "convergence_reached"
        and evolution_state.convergenceCount < effective_convergence_threshold
    ):
        readiness = "blocked"
        action = "inspect_state"
        reasons.append(
            "The evolution state recorded `convergence_reached` before the effective convergence threshold was met."
        )
    elif evolved_hypotheses and strategy_decision_count < len(evolved_hypotheses) + 1:
        readiness = "blocked"
        action = "inspect_state"
        reasons.append(
            "The evolution audit log is incomplete: each evolved hypothesis must have a matching routing "
            "decision record."
        )
    elif overview_valid:
        readiness = "ready_for_completion"
        action = "complete"
        reasons.extend(
            [
                "A valid research overview artifact is already present.",
                "Top viable hypotheses have been materialized and can be summarized as final outputs.",
            ]
        )
    elif evolution_state.stopReason == "convergence_reached":
        readiness = "ready_for_overview"
        action = "generate_overview"
        reasons.append("Evolution recorded the stop reason `convergence_reached`.")
    elif evolution_state.stopReason == "max_iterations_reached":
        readiness = "ready_for_overview"
        action = "generate_overview"
        reasons.append("Evolution recorded the stop reason `max_iterations_reached` for a capped run.")
    elif evolution_state.stopReason == "safety_iteration_limit_reached":
        readiness = "ready_for_overview"
        action = "generate_overview"
        reasons.append("Evolution recorded the stop reason `safety_iteration_limit_reached`.")
    elif evolution_state.stopReason == "no_viable_candidates":
        readiness = "ready_for_overview"
        action = "generate_overview"
        reasons.append("Evolution recorded the stop reason `no_viable_candidates`.")
    elif (
        settings.convergence.max_iterations > 0
        and evolution_state.iterationCount >= settings.convergence.max_iterations
    ):
        readiness = "ready_for_overview"
        action = "generate_overview"
        reasons.append("Iteration count reached the configured capped-run max_iterations limit.")
    elif safety_max_iterations > 0 and evolution_state.iterationCount >= safety_max_iterations:
        readiness = "ready_for_overview"
        action = "generate_overview"
        reasons.append("Iteration count reached the configured safety_max_iterations ceiling.")
    elif evolution_state.convergenceCount >= effective_convergence_threshold:
        readiness = "ready_for_overview"
        action = "generate_overview"
        reasons.append(
            "Convergence count reached the effective threshold "
            f"({effective_convergence_threshold}) under stop_policy `{stop_policy}`."
        )
    else:
        readiness = "continue_evolution"
        action = "continue_evolution"
        if evolution_state.convergenceCount < effective_convergence_threshold:
            reasons.append(
                "Convergence threshold has not been reached under the active stop policy "
                f"(`{stop_policy}` requires {effective_convergence_threshold})."
            )
        if (
            settings.convergence.max_iterations > 0
            and evolution_state.iterationCount < settings.convergence.max_iterations
        ):
            reasons.append("Iteration count is still below the capped-run max_iterations limit.")
        if settings.convergence.max_iterations == 0 and evolution_state.iterationCount < safety_max_iterations:
            reasons.append("The run is completion-driven and remains below the safety_max_iterations ceiling.")
        if top_hypotheses:
            reasons.append("Top viable hypotheses remain available for additional evolution rounds.")

    if top_hypotheses and not all(_review_bundle_complete(hypothesis) for hypothesis in top_hypotheses):
        readiness = "blocked"
        action = "inspect_state"
        reasons = ["At least one active top hypothesis does not have a complete review bundle."]

    signals = {
        "runId": run_dir.name,
        "pipelineStatus": str(pipeline_state.get("status", "")),
        "evolutionStatus": evolution_state.status,
        "evolutionStatusMismatch": evolution_status_mismatch,
        "completedSkills": completed_skills,
        "currentSkill": str(pipeline_state.get("currentSkill", "")),
        "currentPhase": str(pipeline_state.get("currentPhase", "")),
        "hypothesisCount": len(hypotheses),
        "evolvedHypothesisCount": len(evolved_hypotheses),
        "viableHypothesisCount": len(viable_hypotheses),
        "strategyDecisionCount": strategy_decision_count,
        "topHypothesisIds": [hypothesis.id for hypothesis in top_hypotheses],
        "frontierHypothesisIds": frontier_hypothesis_ids or [hypothesis.id for hypothesis in fallback_top_hypotheses],
        "validatorStatus": validation_summary.status,
        "validatorErrorCount": validation_summary.errorCount,
        "validatorWarningCount": validation_summary.warningCount,
        "rankingWritebackInvalid": ranking_writeback_invalid,
        "iterationCount": evolution_state.iterationCount,
        "convergenceCount": evolution_state.convergenceCount,
        "convergenceThreshold": settings.convergence.convergence_count_threshold,
        "effectiveConvergenceThreshold": effective_convergence_threshold,
        "maxIterations": settings.convergence.max_iterations,
        "safetyMaxIterations": safety_max_iterations,
        "persistedSafetyMaxIterations": persisted_safety_max_iterations,
        "safetyMaxIterationsMismatch": safety_max_iterations_mismatch,
        "safetyStopBeforeResolvedCeiling": safety_stop_before_resolved_ceiling,
        "effectiveTopK": effective_top_k,
        "persistedEffectiveTopK": persisted_effective_top_k,
        "resolvedTopK": settings.ranking.tournament_top_k,
        "effectiveTopKMismatch": effective_top_k_mismatch,
        "overviewExists": overview_exists,
        "overviewValid": overview_valid,
        "overviewStatus": overview_status,
        "overviewContentPresent": overview_content_present,
        "stopPolicy": stop_policy,
        "iterationPolicy": iteration_policy,
        "iterationBand": iteration_band,
        "stopReason": evolution_state.stopReason,
        "overviewEligible": evolution_state.overviewEligible,
        "safetyLimitHit": evolution_state.safetyLimitHit
        or (safety_max_iterations > 0 and evolution_state.iterationCount >= safety_max_iterations),
    }
    if evolution_state.lastSelectedIsland:
        signals["lastSelectedIsland"] = evolution_state.lastSelectedIsland
    if evolution_state.lastSelectedStrategy:
        signals["lastSelectedStrategy"] = evolution_state.lastSelectedStrategy
    if evolution_state.enteredTopKLastRound is not None:
        signals["enteredTopKLastRound"] = evolution_state.enteredTopKLastRound
    if missing_frontier_ids:
        signals["missingFrontierIds"] = missing_frontier_ids
    if non_viable_frontier_ids:
        signals["nonViableFrontierIds"] = non_viable_frontier_ids
    if frontier_evolved_without_placement_ids:
        signals["frontierEvolvedWithoutPlacementIds"] = frontier_evolved_without_placement_ids

    return CompletionAdvisory(
        completionReadiness=readiness,
        recommendedAction=action,
        reasons=reasons,
        signals=signals,
        requestedSkill=requested_skill,
    )


def record_completion_decision(
    run_dir: Path,
    *,
    decision: CompletionAction,
    advisory: CompletionAdvisory,
    requested_skill: str,
    rationale: list[str] | None = None,
) -> CompletionDecisionContract:
    """Persist one completion decision artifact alongside the run state."""
    rationale = rationale or []
    override = decision != advisory.recommendedAction
    if override and not rationale:
        raise ValueError("Overriding the advisory recommendation requires at least one rationale entry.")
    if not override and not rationale:
        rationale = list(advisory.reasons)

    settings = HostSettings.from_run_dir(run_dir)
    artifact_store = ArtifactStore(run_dir.resolve(), top_k_limit=settings.ranking.tournament_top_k)
    return artifact_store.write_completion_decision(
        decision=decision,
        verifier_recommendation=advisory.recommendedAction,
        requested_skill=requested_skill,
        override=override,
        rationale=rationale,
    )


def _write_json(path: Path, payload: BaseModel | dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, BaseModel):
        content = payload.model_dump_json(indent=2)
    else:
        content = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(content + "\n", encoding="utf-8")


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the advisory completion verifier and return a process exit code."""
    args = _parse_args(argv)
    run_dir = args.run_dir.resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        return 2

    advisory = advise_pipeline_completion(run_dir, requested_skill=args.skill)
    decision_payload: dict[str, Any] | None = None
    if args.write_decision:
        decision = record_completion_decision(
            run_dir,
            decision=args.write_decision,
            advisory=advisory,
            requested_skill=args.skill,
            rationale=[item for item in args.rationale if item],
        )
        decision_payload = decision.model_dump(mode="json")

    output_payload: dict[str, Any] = {"advisory": advisory.model_dump(mode="json")}
    if decision_payload is not None:
        output_payload["decision"] = decision_payload

    if args.json_out is not None:
        _write_json(args.json_out.resolve(), output_payload)

    print(json.dumps(output_payload, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.validation.verify_pipeline_completion`."""
    try:
        return run_cli(argv)
    except Exception as exc:
        print(f"Completion verifier execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
