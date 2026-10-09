"""Validator-first helpers and CLI for host-agent artifact checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.append(str(_REPO_ROOT))
    from packages.agent_contracts import (  # type: ignore[no-redef]
        CompletionDecisionContract,
        CurrentStageContract,
        EvidenceBundleContract,
        EvolutionRoundRecordContract,
        EvolutionStateContract,
        HypothesisContract,
        HypothesisMatchupContract,
        InsightsFromReviewsContract,
        IslandStateContract,
        MetaReviewContract,
        PaperCandidateContract,
        PaperVerificationContract,
        PipelineStateContract,
        PolicyDecisionContract,
        ProximityEmbeddingReceiptContract,
        ProximityGraphContract,
        ProximityStatusContract,
        RankingUpdateReceiptContract,
        ResearchOverviewContract,
        ResearchPlanContract,
        ResolvedRunConfigContract,
        ReviewContract,
        RunPolicyContract,
        SearchProviderReceiptContract,
        SearchRequestContract,
        StartRequestContract,
        StrategyDecisionRecordContract,
        StrategyPlanContract,
        TournamentMatchContract,
        proximity_config_hash,
    )
    from packages.agent_mechanics import (  # type: ignore[no-redef]
        apply_elo_updates,
        get_top_k_hypotheses,
        select_ranked_opponents,
        should_run_ranked_tournament,
    )
    from packages.agent_support.pipeline_semantics import (  # type: ignore[no-redef]
        normalize_stage_trail,
        skill_for_stage,
    )
    from packages.agent_support.resolved_config import validate_resolved_config_bounds  # type: ignore[no-redef]
    from packages.run_artifacts import REVIEW_STAGE_FILE_MAP, review_stage_content_issue  # type: ignore[no-redef]
    from packages.run_artifacts.pipeline_state import ACTIVE_RUNTIME_PHASES  # type: ignore[no-redef]
else:
    from packages.agent_contracts import (
        CompletionDecisionContract,
        CurrentStageContract,
        EvidenceBundleContract,
        EvolutionRoundRecordContract,
        EvolutionStateContract,
        HypothesisContract,
        HypothesisMatchupContract,
        InsightsFromReviewsContract,
        IslandStateContract,
        MetaReviewContract,
        PaperCandidateContract,
        PaperVerificationContract,
        PipelineStateContract,
        PolicyDecisionContract,
        ProximityEmbeddingReceiptContract,
        ProximityGraphContract,
        ProximityStatusContract,
        RankingUpdateReceiptContract,
        ResearchOverviewContract,
        ResearchPlanContract,
        ResolvedRunConfigContract,
        ReviewContract,
        RunPolicyContract,
        SearchProviderReceiptContract,
        SearchRequestContract,
        StartRequestContract,
        StrategyDecisionRecordContract,
        StrategyPlanContract,
        TournamentMatchContract,
        proximity_config_hash,
    )
    from packages.agent_mechanics import (
        apply_elo_updates,
        get_top_k_hypotheses,
        select_ranked_opponents,
        should_run_ranked_tournament,
    )
    from packages.agent_support.pipeline_semantics import (
        normalize_stage_trail,
        skill_for_stage,
    )
    from packages.agent_support.resolved_config import validate_resolved_config_bounds
    from packages.run_artifacts import REVIEW_STAGE_FILE_MAP, review_stage_content_issue
    from packages.run_artifacts.pipeline_state import ACTIVE_RUNTIME_PHASES


ValidationSeverity = Literal["error", "warning"]
_SINGLE_ISLAND_STRATEGIES = {
    "grounding_evolution",
    "coherence_evolution",
    "feasibility_evolution",
    "simplification_evolution",
}
_MULTI_ISLAND_STRATEGIES = {
    "inspiration_evolution",
    "combination_evolution",
    "out_of_box_evolution",
}
_RESEARCH_PLAN_REQUIRED_PHASES = frozenset(
    {
        "Generation",
        "Evolution",
        "Reflection",
        "Insights from Reviews",
        "Proximity",
        "Ranking",
        "Research Overview",
        "Completed",
    }
)
_RESEARCH_PLAN_REQUIRED_ACTIONS = frozenset(
    {
        "run_generation",
        "run_review",
        "run_insights",
        "run_proximity",
        "run_ranking",
        "continue_evolution",
        "return_to_generation",
        "generate_overview",
    }
)
_TOP_K_TEXT_PATTERN = re.compile(r"\btop[- ]?(\d+)\b", flags=re.IGNORECASE)
_SAFETY_LIMIT_TEXT_PATTERN = re.compile(
    r"\bsafety(?:[_ -]?iteration)?(?:[_ -]?(?:limit|ceiling|max(?:imum)?))?\D{0,12}(\d+)\b",
    flags=re.IGNORECASE,
)
_POSITIVE_CONVERGENCE_CLAIM_PATTERNS = (
    re.compile(r"\bfrontier\s+converged\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:run|evolution|frontier)\s+converged\s+on\b", flags=re.IGNORECASE),
    re.compile(r"\bconvergence\s+(?:threshold\s+)?(?:was\s+)?reached\b", flags=re.IGNORECASE),
    re.compile(r"\breached\s+convergence\b", flags=re.IGNORECASE),
)
_COMPREHENSIVE_LITERATURE_CLAIM_PATTERNS = (
    re.compile(
        r"\b(?:comprehensive|complete|exhaustive|full)\s+"
        r"(?:literature|external\s+evidence|evidence)\s+"
        r"(?:coverage|review|search|scan|assessment)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\ball\s+relevant\s+(?:literature|external\s+evidence)\b", flags=re.IGNORECASE),
)
_EMBEDDING_RANKING_CLAIM_PATTERNS = (
    re.compile(r"\bembedding[- ](?:informed|based|driven)\s+ranking\b", flags=re.IGNORECASE),
    re.compile(
        r"\b(?:proximity|similarity)[- ](?:informed|based|driven)\s+(?:ranking|placement)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\branking\s+(?:used|uses|relied\s+on)\s+(?:embedding|proximity|similarity)\b", flags=re.IGNORECASE),
)
_LITERATURE_LIMITATION_PATTERNS = (
    re.compile(
        r"\b(?:literature|external\s+evidence|evidence|retrieval|search|coverage)"
        r"[\s\S]{0,120}\b(?:partial|blocked|limited|limitation|limitations|incomplete)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:partial|blocked|limited|incomplete)[\s\S]{0,120}"
        r"\b(?:literature|external\s+evidence|evidence|retrieval|search|coverage)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\bprovider\s+coverage\s+(?:was\s+)?(?:partial|limited|incomplete)\b", flags=re.IGNORECASE),
)
_PROXIMITY_LIMITATION_PATTERNS = (
    re.compile(
        r"\b(?:proximity|embedding|similarity)[\s\S]{0,120}"
        r"\b(?:skipped|unavailable|failed|disabled|fallback|not\s+available|not\s+used)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:skipped|unavailable|failed|disabled|fallback)[\s\S]{0,120}"
        r"\b(?:proximity|embedding|similarity)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\branking[\s\S]{0,120}\b(?:fallback|not\s+(?:embedding|proximity|similarity)[- ]informed)\b",
        flags=re.IGNORECASE,
    ),
)
_NEGATED_CONVERGENCE_PREFIX_PATTERN = re.compile(
    r"\b(?:not|not yet|has not|have not|had not|did not|without)\W*$",
    flags=re.IGNORECASE,
)
_NEGATED_CLAIM_PREFIX_PATTERN = re.compile(
    r"\b(?:not|not yet|no|without|did not|does not|do not|was not|were not|cannot|must not)\W*$",
    flags=re.IGNORECASE,
)
_PROXIMITY_FALLBACK_STATUSES = {
    "skipped_disabled",
    "skipped_provider_unavailable",
    "failed_provider_error",
    "failed_invalid_embedding",
}
_PLACEHOLDER_HYPOTHESIS_PATTERNS = {
    "statement": (
        re.compile(
            r"^evolved\s+from\s+.+\(round\s+\d+\):\s+refined\s+mechanism\s+with\s+improved\s+"
            r"experimental\s+controls\s+and\s+quantitative\s+benchmarks\.?$",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"^evolved\s+hypothesis\s+\(round\s+\d+\):\s+refined\s+mechanism\s+with\s+improved\s+"
            r"experimental\s+validation\.?$",
            flags=re.IGNORECASE,
        ),
    ),
    "mechanism": (
        re.compile(
            r"^refinement\s+of\s+.+\s+addressing\s+review-identified\s+weaknesses\s+through\s+"
            r"targeted\s+mechanistic\s+and\s+design\s+improvements\.?$",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"^refinement\s+addressing\s+review-identified\s+weaknesses\s+through\s+targeted\s+"
            r"improvements\.?$",
            flags=re.IGNORECASE,
        ),
    ),
    "summary": (
        re.compile(
            r"^refined\s+.+\s+with\s+improved\s+performance\s+and\s+experimental\s+validation\.?$",
            flags=re.IGNORECASE,
        ),
        re.compile(r"^refined\s+hypothesis\s+with\s+improved\s+performance\.?$", flags=re.IGNORECASE),
    ),
}
_PLACEHOLDER_EXPERIMENTAL_DESIGN_PHRASES = (
    "apply targeted improvement",
    "characterize with standard techniques",
    "benchmark against parent",
    "validate improvement quantitatively",
    "characterize structure",
    "test activity",
)
_CONTINUE_EVOLUTION_ROUTER_SIGNAL_TYPES: dict[str, type | tuple[type, ...]] = {
    "hypothesis_count": int,
    "viable_hypothesis_count": int,
    "convergence_count": int,
    "convergence_threshold": int,
    "entered_top_k_last_round": (bool, type(None)),
    "top_hypothesis_ids": list,
    "research_plan_status": str,
    "selection_strategy": str,
    "selected_parent_ids": list,
    "selected_island_ids": list,
}
_STRATEGY_DECISION_RESULT_KEYS = {
    "child_hypothesis_id",
    "child_island_id",
    "chosen_evolution_strategy",
    "convergence_count_after",
    "convergence_count_before",
    "current_top_k_ids",
    "entered_top_k",
    "placement_match_ids",
    "previous_top_k_ids",
    "proximity_receipt_status",
    "ranked_match_ids",
    "review_passed",
    "tournament_match_ids",
}
_CANONICAL_ISLAND_ITEM_KEYS = {"id", "decayed_reward", "decayed_visits", "visit_count"}
_DEPRECATED_ISLAND_ITEM_KEYS = {"island_id", "reward", "stagnation_count", "last_updated"}


def _validate_continue_evolution_router_signals(
    decision: StrategyDecisionRecordContract,
    raw_payload: object,
) -> list[str]:
    """Validate that a continue-evolution decision is a router plan, not a round-result receipt."""
    issues: list[str] = []
    signals = decision.signals
    for key, expected_type in _CONTINUE_EVOLUTION_ROUTER_SIGNAL_TYPES.items():
        value = signals.get(key)
        if key not in signals:
            issues.append(f"continue_evolution strategy decision is missing router signal `{key}`.")
            continue
        if isinstance(value, bool) and expected_type is int:
            issues.append(f"continue_evolution strategy decision router signal `{key}` must be an integer.")
            continue
        if not isinstance(value, expected_type):
            issues.append(f"continue_evolution strategy decision router signal `{key}` has an invalid type.")

    for key in ("top_hypothesis_ids", "selected_parent_ids", "selected_island_ids"):
        value = signals.get(key)
        if isinstance(value, list) and not all(isinstance(item, str) and item for item in value):
            issues.append(f"continue_evolution strategy decision router signal `{key}` must contain string IDs.")

    if signals.get("selection_strategy") not in {"single_island", "multi_island"}:
        issues.append("continue_evolution strategy decision router signal `selection_strategy` is invalid.")

    if isinstance(raw_payload, dict):
        forbidden_top_level = sorted(set(raw_payload).intersection(_STRATEGY_DECISION_RESULT_KEYS))
        if forbidden_top_level:
            issues.append(
                "STRATEGY_DECISIONS.jsonl must not contain round-result fields at the top level: "
                + ", ".join(forbidden_top_level)
                + "."
            )
        raw_signals = raw_payload.get("signals")
        if isinstance(raw_signals, dict):
            forbidden_signals = sorted(set(raw_signals).intersection(_STRATEGY_DECISION_RESULT_KEYS))
            if forbidden_signals:
                issues.append(
                    "STRATEGY_DECISIONS.jsonl `signals` must not contain round-result fields: "
                    + ", ".join(forbidden_signals)
                    + "."
                )
    return issues


def _continue_evolution_decision_signature(decision: StrategyDecisionRecordContract) -> tuple[object, ...] | None:
    if decision.current_phase != "Evolution" or decision.next_action != "continue_evolution":
        return None
    return (
        decision.current_phase,
        decision.next_action,
        tuple(decision.selected_evolution_strategies),
        decision.max_new_hypotheses,
        _freeze_strategy_signature_value(decision.signals),
    )


def _continue_evolution_pre_round_signature(decision: StrategyDecisionRecordContract) -> tuple[object, ...] | None:
    if decision.current_phase != "Evolution" or decision.next_action != "continue_evolution":
        return None
    pre_round_signals = {
        key: value
        for key, value in decision.signals.items()
        if key not in {"selection_strategy", "selected_parent_ids", "selected_island_ids"}
    }
    return (
        decision.current_phase,
        decision.next_action,
        decision.max_new_hypotheses,
        _freeze_strategy_signature_value(pre_round_signals),
    )


def _freeze_strategy_signature_value(value: object) -> object:
    if isinstance(value, dict):
        return tuple(
            (str(key), _freeze_strategy_signature_value(item))
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        )
    if isinstance(value, list):
        return tuple(_freeze_strategy_signature_value(item) for item in value)
    return value


def _validate_unique_open_continue_evolution_decisions(
    decisions: Sequence[StrategyDecisionRecordContract],
    consumed_decision_indices: set[int],
) -> list[str]:
    open_decisions_by_signature: dict[tuple[object, ...], list[int]] = {}
    open_decisions_by_pre_round_signature: dict[tuple[object, ...], list[int]] = {}
    for decision in sorted(decisions, key=lambda item: item.decision_index):
        if decision.decision_index in consumed_decision_indices:
            continue
        signature = _continue_evolution_decision_signature(decision)
        if signature is not None:
            open_decisions_by_signature.setdefault(signature, []).append(decision.decision_index)
        pre_round_signature = _continue_evolution_pre_round_signature(decision)
        if pre_round_signature is not None:
            open_decisions_by_pre_round_signature.setdefault(pre_round_signature, []).append(decision.decision_index)

    messages = [
        "Found equivalent open continue_evolution strategy decisions that are not consumed by "
        "EVOLUTION_ROUNDS.jsonl: " + ", ".join(f"`{index}`" for index in decision_indices) + "."
        for decision_indices in open_decisions_by_signature.values()
        if len(decision_indices) > 1
    ]
    messages.extend(
        "Found multiple open continue_evolution strategy decisions for the same pre-round state that are not "
        "consumed by EVOLUTION_ROUNDS.jsonl: " + ", ".join(f"`{index}`" for index in decision_indices) + "."
        for decision_indices in open_decisions_by_pre_round_signature.values()
        if len(decision_indices) > 1
    )
    return messages


def _candidate_owned_match_ids(
    match_ids: Sequence[str],
    *,
    child_hypothesis_id: str,
    strategy: Literal["placement_tournament", "ranked_tournament"],
    tournament_payloads_by_id: dict[str, TournamentMatchContract],
) -> list[str]:
    owned_match_ids: list[str] = []
    for match_id in match_ids:
        match_payload = tournament_payloads_by_id.get(match_id)
        if (
            match_payload is not None
            and match_payload.match_strategy == strategy
            and match_payload.hypothesis_1_id == child_hypothesis_id
        ):
            owned_match_ids.append(match_id)
    return owned_match_ids


def _invalid_round_match_owner_ids(
    match_ids: Sequence[str],
    *,
    child_hypothesis_id: str,
    strategy: Literal["placement_tournament", "ranked_tournament"],
    tournament_payloads_by_id: dict[str, TournamentMatchContract],
) -> list[str]:
    invalid_match_ids: list[str] = []
    for match_id in match_ids:
        match_payload = tournament_payloads_by_id.get(match_id)
        if (
            match_payload is None
            or match_payload.match_strategy != strategy
            or match_payload.hypothesis_1_id != child_hypothesis_id
        ):
            invalid_match_ids.append(match_id)
    return invalid_match_ids


def _duplicate_items(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _validate_pipeline_state_semantics(payload: PipelineStateContract) -> list[str]:
    """Validate phase/stage semantics against the shared pipeline definitions."""
    issues: list[str] = []
    if payload.status == "not_started" and payload.currentPhase in ACTIVE_RUNTIME_PHASES:
        issues.append(
            "PIPELINE_STATE.json `status` must be `running` when `currentPhase` is an active runtime phase; "
            f"found `not_started` for `{payload.currentPhase}`."
        )
    seen_completed_skills: set[str] = set()
    duplicate_completed_skills: list[str] = []
    for skill in payload.completedSkills:
        if skill in seen_completed_skills and skill not in duplicate_completed_skills:
            duplicate_completed_skills.append(skill)
        seen_completed_skills.add(skill)
    if duplicate_completed_skills:
        issues.append(
            "PIPELINE_STATE.json `completedSkills` must not contain duplicate entries: "
            + ", ".join(duplicate_completed_skills)
            + "."
        )
    if payload.currentPhase and payload.stageTrail:
        normalized_stage_trail = normalize_stage_trail(payload.stageTrail)
        if normalized_stage_trail and payload.currentPhase != normalized_stage_trail[-1]:
            issues.append(
                "PIPELINE_STATE.json `currentPhase` must match the last entry in `stageTrail` when both are present."
            )
    if payload.currentPhase and payload.currentSkill:
        expected_skill = skill_for_stage(payload.currentPhase)
        if expected_skill and payload.currentSkill != expected_skill:
            issues.append(
                "PIPELINE_STATE.json `currentSkill` must match the canonical skill for the active "
                "`currentPhase` when both are present."
            )
    return issues


def _validate_current_stage_semantics(payload: CurrentStageContract) -> list[str]:
    """Validate the internal CURRENT_STAGE linkage semantics."""
    issues: list[str] = []
    if payload.stageTrail and payload.stage != payload.stageTrail[-1]:
        issues.append("CURRENT_STAGE.json `stage` must match the last entry in `stageTrail` when both are present.")
    return issues


def _validate_stage_artifact_alignment(
    pipeline_state: PipelineStateContract,
    current_stage: CurrentStageContract,
) -> list[str]:
    """Validate cross-artifact alignment between PIPELINE_STATE and CURRENT_STAGE."""
    issues: list[str] = []
    if pipeline_state.currentPhase and current_stage.stage and pipeline_state.currentPhase != current_stage.stage:
        issues.append(
            "PIPELINE_STATE.json `currentPhase` must match CURRENT_STAGE.json `stage` when both artifacts are present."
        )
    if pipeline_state.stageTrail and current_stage.stageTrail:
        pipeline_trail = normalize_stage_trail(pipeline_state.stageTrail)
        current_stage_trail = normalize_stage_trail(current_stage.stageTrail)
        if pipeline_trail != current_stage_trail:
            issues.append(
                "PIPELINE_STATE.json `stageTrail` must match CURRENT_STAGE.json `stageTrail` when both "
                "artifacts are present."
            )
    return issues


def _validate_evolution_resolved_config_alignment(
    evolution_state: EvolutionStateContract,
    resolved_config: ResolvedRunConfigContract,
) -> list[str]:
    """Validate safety and frontier metadata shared by evolution state and resolved config."""
    issues: list[str] = []
    resolved_safety_max_iterations = resolved_config.convergence.safety_max_iterations
    if evolution_state.safetyMaxIterations != resolved_safety_max_iterations:
        issues.append(
            "EVOLUTION_STATE.json `safetyMaxIterations` must equal "
            "RESOLVED_RUN_CONFIG.convergence.safety_max_iterations "
            f"({resolved_safety_max_iterations}); found {evolution_state.safetyMaxIterations}."
        )
    if evolution_state.stopReason == "safety_iteration_limit_reached":
        if evolution_state.iterationCount < resolved_safety_max_iterations:
            issues.append(
                "EVOLUTION_STATE.json recorded `safety_iteration_limit_reached` before the resolved safety "
                f"ceiling was met ({evolution_state.iterationCount}/{resolved_safety_max_iterations})."
            )
        if not evolution_state.safetyLimitHit:
            issues.append(
                "EVOLUTION_STATE.json recorded `safety_iteration_limit_reached` but `safetyLimitHit` is false."
            )
    return issues


class HostAgentValidationIssue(BaseModel):
    """One validation issue discovered while checking a run directory."""

    path: str = Field(default="")
    message: str = Field(default="")
    severity: ValidationSeverity = Field(default="error")


class HostAgentValidationSummary(BaseModel):
    """Validation summary for host-agent execution handoff."""

    status: Literal["valid", "invalid"] = Field(default="valid")
    checkedArtifacts: list[str] = Field(default_factory=list)
    issues: list[HostAgentValidationIssue] = Field(default_factory=list)
    errorCount: int = Field(default=0)
    warningCount: int = Field(default=0)
    resumeReady: bool = Field(default=False)
    requestedSkill: str = Field(default="")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for artifact validation."""
    parser = argparse.ArgumentParser(description="Validate Co-Scientist host-agent artifacts for one run directory.")
    parser.add_argument("run_dir", type=Path, help="Path to the run directory.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Validate resume-critical artifacts and fail if resume state is incomplete.",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default="",
        help="Optional requested top-level skill name to include in the validation summary.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the validation summary JSON.",
    )
    return parser.parse_args(argv)


def _relative_to_run(run_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_non_empty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _missing_required_keys(payload: Any, required_keys: Sequence[str]) -> list[str]:
    if not isinstance(payload, dict):
        return list(required_keys)
    return [key for key in required_keys if key not in payload]


def _record_issue(
    issues: list[HostAgentValidationIssue],
    run_dir: Path,
    path: Path,
    message: str,
    severity: ValidationSeverity,
) -> None:
    issues.append(
        HostAgentValidationIssue(
            path=_relative_to_run(run_dir, path),
            message=message,
            severity=severity,
        )
    )


def _is_blank_text(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _extract_top_k_text_values(items: Sequence[str]) -> list[int]:
    values: list[int] = []
    for item in items:
        values.extend(int(match.group(1)) for match in _TOP_K_TEXT_PATTERN.finditer(item))
    return values


def _extract_safety_limit_text_values(items: Sequence[str]) -> list[int]:
    values: list[int] = []
    for item in items:
        values.extend(int(match.group(1)) for match in _SAFETY_LIMIT_TEXT_PATTERN.finditer(item))
    return values


def _has_positive_convergence_claim(value: str) -> bool:
    for pattern in _POSITIVE_CONVERGENCE_CLAIM_PATTERNS:
        for match in pattern.finditer(value):
            prefix = value[max(0, match.start() - 32) : match.start()]
            if _NEGATED_CONVERGENCE_PREFIX_PATTERN.search(prefix):
                continue
            return True
    return False


def _has_non_negated_claim(value: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    for pattern in patterns:
        for match in pattern.finditer(value):
            prefix = value[max(0, match.start() - 48) : match.start()]
            if _NEGATED_CLAIM_PREFIX_PATTERN.search(prefix):
                continue
            return True
    return False


def _has_pattern_match(value: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def _validate_model_file(
    model_type: type[BaseModel],
    path: Path,
    checked_artifacts: list[str],
) -> str | None:
    checked_artifacts.append(str(path.resolve()))
    try:
        model_type.model_validate(_load_json(path))
    except json.JSONDecodeError as exc:
        return str(exc)
    except ValidationError as exc:
        return str(exc)
    return None


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _validate_islands_artifact(
    run_dir: Path,
    islands_path: Path,
    checked_artifacts: list[str],
    issues: list[HostAgentValidationIssue],
) -> tuple[list[dict[str, Any]], bool]:
    """Validate and return canonical island item payloads."""
    checked_artifacts.append(str(islands_path.resolve()))
    try:
        islands_raw = _load_json(islands_path)
    except json.JSONDecodeError as exc:
        _record_issue(issues, run_dir, islands_path, str(exc), "error")
        return [], False

    if not isinstance(islands_raw, dict):
        _record_issue(issues, run_dir, islands_path, "ISLANDS.json must serialize a wrapper object.", "error")
        return [], False

    raw_items = islands_raw.get("items")
    if not isinstance(raw_items, list):
        _record_issue(issues, run_dir, islands_path, "ISLANDS.json must contain an `items` list.", "error")
        return [], False

    valid = True
    item_payloads: list[dict[str, Any]] = []
    seen_island_ids: set[str] = set()
    for index, item in enumerate(raw_items):
        item_context = f"ISLANDS.json items[{index}]"
        if not isinstance(item, dict):
            _record_issue(issues, run_dir, islands_path, f"{item_context} must serialize an object.", "error")
            valid = False
            continue

        item_payloads.append(item)
        deprecated_keys = sorted(set(item).intersection(_DEPRECATED_ISLAND_ITEM_KEYS))
        if deprecated_keys:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                f"{item_context} contains deprecated non-canonical keys: " + ", ".join(deprecated_keys) + ".",
                "error",
            )
            valid = False

        non_canonical_keys = sorted(set(item).difference(_CANONICAL_ISLAND_ITEM_KEYS | _DEPRECATED_ISLAND_ITEM_KEYS))
        if non_canonical_keys:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                f"{item_context} contains non-canonical keys: " + ", ".join(non_canonical_keys) + ".",
                "error",
            )
            valid = False

        missing_keys = sorted(_CANONICAL_ISLAND_ITEM_KEYS.difference(item))
        if missing_keys:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                f"{item_context} is missing canonical keys: " + ", ".join(missing_keys) + ".",
                "error",
            )
            valid = False

        island_id = item.get("id")
        if _is_blank_text(island_id):
            _record_issue(issues, run_dir, islands_path, f"{item_context} must keep `id` non-empty.", "error")
            valid = False
        elif island_id in seen_island_ids:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                f"{item_context} duplicates island id `{island_id}`.",
                "error",
            )
            valid = False
        elif isinstance(island_id, str):
            seen_island_ids.add(island_id)

        for field_name in ("decayed_reward", "decayed_visits"):
            if field_name in item and not _is_number(item[field_name]):
                _record_issue(
                    issues,
                    run_dir,
                    islands_path,
                    f"{item_context} canonical field `{field_name}` must be numeric.",
                    "error",
                )
                valid = False
        visit_count = item.get("visit_count")
        if "visit_count" in item and (not isinstance(visit_count, int) or isinstance(visit_count, bool)):
            _record_issue(
                issues,
                run_dir,
                islands_path,
                f"{item_context} canonical field `visit_count` must be an integer.",
                "error",
            )
            valid = False

        try:
            IslandStateContract.from_payload(item)
        except ValidationError as exc:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                f"{item_context} failed IslandStateContract validation: {exc}",
                "error",
            )
            valid = False

    return item_payloads, valid


def _load_model_list_file(
    model_type: type[BaseModel],
    path: Path,
    checked_artifacts: list[str],
) -> tuple[list[BaseModel], str | None]:
    checked_artifacts.append(str(path.resolve()))
    try:
        payload = _load_json(path)
    except json.JSONDecodeError as exc:
        return [], str(exc)
    if not isinstance(payload, list):
        return [], f"{path.name} must serialize a JSON list."
    items: list[BaseModel] = []
    for index, raw_item in enumerate(payload):
        try:
            items.append(model_type.model_validate(raw_item))
        except ValidationError as exc:
            return [], f"{path.name}[{index}] failed schema validation: {exc}"
    return items, None


def _validate_literature_artifacts(
    run_dir: Path,
    checked_artifacts: list[str],
    issues: list[HostAgentValidationIssue],
) -> bool:
    """Validate search bridge artifacts when a run contains literature outputs."""
    resume_ready = True
    literature_root = run_dir / "literature"
    queries_root = literature_root / "queries"
    bundles_root = literature_root / "bundles"
    query_bundles_by_id: dict[str, EvidenceBundleContract] = {}

    if not literature_root.exists():
        return resume_ready

    if queries_root.exists():
        for query_dir in sorted(path for path in queries_root.iterdir() if path.is_dir()):
            query_id = query_dir.name
            request_path = query_dir / "REQUEST.json"
            receipts_path = query_dir / "PROVIDER_RECEIPTS.json"
            candidates_path = query_dir / "CANDIDATE_PAPERS.json"
            verifications_path = query_dir / "VERIFIED_PAPERS.json"
            bundle_path = query_dir / "EVIDENCE_BUNDLE.json"

            request_payload: SearchRequestContract | None = None
            receipts: list[SearchProviderReceiptContract] = []
            candidates: list[PaperCandidateContract] = []
            verifications: list[PaperVerificationContract] = []

            if request_path.exists():
                error = _validate_model_file(SearchRequestContract, request_path, checked_artifacts)
                if error is not None:
                    _record_issue(issues, run_dir, request_path, str(error), "error")
                    resume_ready = False
                else:
                    request_payload = SearchRequestContract.from_json_file(request_path)
                    if request_payload.query_id != query_id:
                        _record_issue(
                            issues,
                            run_dir,
                            request_path,
                            "REQUEST.json `query_id` must match the literature query directory name.",
                            "error",
                        )
                        resume_ready = False
            else:
                _record_issue(
                    issues,
                    run_dir,
                    request_path,
                    "Literature query directory is missing REQUEST.json.",
                    "error",
                )
                resume_ready = False

            if receipts_path.exists():
                receipt_models, error = _load_model_list_file(
                    SearchProviderReceiptContract,
                    receipts_path,
                    checked_artifacts,
                )
                if error is not None:
                    _record_issue(issues, run_dir, receipts_path, error, "error")
                    resume_ready = False
                else:
                    receipts = [item for item in receipt_models if isinstance(item, SearchProviderReceiptContract)]
            else:
                _record_issue(
                    issues,
                    run_dir,
                    receipts_path,
                    "Literature query directory is missing PROVIDER_RECEIPTS.json.",
                    "error",
                )
                resume_ready = False

            if candidates_path.exists():
                candidate_models, error = _load_model_list_file(
                    PaperCandidateContract,
                    candidates_path,
                    checked_artifacts,
                )
                if error is not None:
                    _record_issue(issues, run_dir, candidates_path, error, "error")
                    resume_ready = False
                else:
                    candidates = [item for item in candidate_models if isinstance(item, PaperCandidateContract)]
                    duplicate_paper_ids = _duplicate_values([candidate.paper_id for candidate in candidates])
                    if duplicate_paper_ids:
                        _record_issue(
                            issues,
                            run_dir,
                            candidates_path,
                            "CANDIDATE_PAPERS.json contains duplicate `paper_id` values: "
                            + ", ".join(duplicate_paper_ids),
                            "error",
                        )
                        resume_ready = False
            elif bundle_path.exists():
                _record_issue(
                    issues,
                    run_dir,
                    candidates_path,
                    "Literature query has EVIDENCE_BUNDLE.json but is missing CANDIDATE_PAPERS.json.",
                    "error",
                )
                resume_ready = False

            if verifications_path.exists():
                verification_models, error = _load_model_list_file(
                    PaperVerificationContract,
                    verifications_path,
                    checked_artifacts,
                )
                if error is not None:
                    _record_issue(issues, run_dir, verifications_path, error, "error")
                    resume_ready = False
                else:
                    verifications = [
                        item for item in verification_models if isinstance(item, PaperVerificationContract)
                    ]

            if bundle_path.exists():
                error = _validate_model_file(EvidenceBundleContract, bundle_path, checked_artifacts)
                if error is not None:
                    _record_issue(issues, run_dir, bundle_path, str(error), "error")
                    resume_ready = False
                    continue
                bundle = EvidenceBundleContract.from_json_file(bundle_path)
                query_bundles_by_id[bundle.bundle_id] = bundle
                for message in _validate_evidence_bundle_consistency(
                    bundle,
                    query_id=query_id,
                    request=request_payload,
                    receipts=receipts,
                    candidates=candidates,
                    verifications=verifications,
                ):
                    _record_issue(issues, run_dir, bundle_path, message, "error")
                    resume_ready = False

    if bundles_root.exists():
        for bundle_copy_path in sorted(
            path for path in bundles_root.iterdir() if path.is_file() and path.suffix == ".json"
        ):
            error = _validate_model_file(EvidenceBundleContract, bundle_copy_path, checked_artifacts)
            if error is not None:
                _record_issue(issues, run_dir, bundle_copy_path, str(error), "error")
                resume_ready = False
                continue
            bundle_copy = EvidenceBundleContract.from_json_file(bundle_copy_path)
            if bundle_copy_path.stem != bundle_copy.bundle_id:
                _record_issue(
                    issues,
                    run_dir,
                    bundle_copy_path,
                    "Literature bundle filename must match `bundle_id`.",
                    "error",
                )
                resume_ready = False
            query_bundle = query_bundles_by_id.get(bundle_copy.bundle_id)
            if query_bundle is None:
                _record_issue(
                    issues,
                    run_dir,
                    bundle_copy_path,
                    "Literature bundle copy does not have a matching query EVIDENCE_BUNDLE.json.",
                    "error",
                )
                resume_ready = False
            elif bundle_copy.model_dump(mode="json") != query_bundle.model_dump(mode="json"):
                _record_issue(
                    issues,
                    run_dir,
                    bundle_copy_path,
                    "Literature bundle copy must match the query EVIDENCE_BUNDLE.json payload.",
                    "error",
                )
                resume_ready = False

    return resume_ready


def _validate_evidence_bundle_consistency(
    bundle: EvidenceBundleContract,
    *,
    query_id: str,
    request: SearchRequestContract | None,
    receipts: list[SearchProviderReceiptContract],
    candidates: list[PaperCandidateContract],
    verifications: list[PaperVerificationContract],
) -> list[str]:
    issues: list[str] = []
    if bundle.query_id != query_id:
        issues.append("EVIDENCE_BUNDLE.json `query_id` must match the literature query directory name.")
    if bundle.request.query_id != bundle.query_id:
        issues.append("EVIDENCE_BUNDLE.json `request.query_id` must match bundle `query_id`.")
    if request is not None and bundle.request.model_dump(mode="json") != request.model_dump(mode="json"):
        issues.append("EVIDENCE_BUNDLE.json embedded `request` must match REQUEST.json.")

    candidate_ids = [candidate.paper_id for candidate in bundle.papers]
    duplicate_candidate_ids = _duplicate_values(candidate_ids)
    if duplicate_candidate_ids:
        issues.append("EVIDENCE_BUNDLE.json contains duplicate paper IDs: " + ", ".join(duplicate_candidate_ids))
    candidate_id_set = set(candidate_ids)
    artifact_candidate_id_set = {candidate.paper_id for candidate in candidates}
    if candidates and candidate_id_set != artifact_candidate_id_set:
        issues.append("EVIDENCE_BUNDLE.json `papers` must match CANDIDATE_PAPERS.json paper IDs.")

    verification_ids = [verification.paper_id for verification in bundle.verified_papers]
    duplicate_verification_ids = _duplicate_values(verification_ids)
    if duplicate_verification_ids:
        issues.append(
            "EVIDENCE_BUNDLE.json contains duplicate verification records: " + ", ".join(duplicate_verification_ids)
        )
    unknown_verification_ids = sorted(set(verification_ids).difference(candidate_id_set))
    if unknown_verification_ids:
        issues.append(
            "EVIDENCE_BUNDLE.json verification records reference unknown paper IDs: "
            + ", ".join(unknown_verification_ids)
        )
    artifact_verification_ids = {verification.paper_id for verification in verifications}
    if verifications and set(verification_ids) != artifact_verification_ids:
        issues.append("EVIDENCE_BUNDLE.json `verified_papers` must match VERIFIED_PAPERS.json paper IDs.")

    for finding in bundle.synthesized_findings:
        unknown_refs = sorted(set(finding.paper_refs).difference(candidate_id_set))
        if unknown_refs:
            issues.append(
                f"EVIDENCE_BUNDLE.json finding `{finding.finding_id}` references unknown paper IDs: "
                + ", ".join(unknown_refs)
            )

    receipt_statuses = [receipt.status for receipt in bundle.provider_receipts]
    if receipts and [receipt.model_dump(mode="json") for receipt in bundle.provider_receipts] != [
        receipt.model_dump(mode="json") for receipt in receipts
    ]:
        issues.append("EVIDENCE_BUNDLE.json `provider_receipts` must match PROVIDER_RECEIPTS.json.")
    attempted = [receipt.provider for receipt in bundle.provider_receipts]
    succeeded = [receipt.provider for receipt in bundle.provider_receipts if receipt.status == "succeeded"]
    metadata = bundle.retrieval_metadata
    if metadata.providers_attempted != attempted:
        issues.append("EVIDENCE_BUNDLE.json `retrieval_metadata.providers_attempted` must match provider receipts.")
    if metadata.providers_succeeded != succeeded:
        issues.append("EVIDENCE_BUNDLE.json `retrieval_metadata.providers_succeeded` must match successful receipts.")
    if metadata.total_raw_results < metadata.total_deduped_results:
        issues.append("EVIDENCE_BUNDLE.json `total_raw_results` cannot be smaller than `total_deduped_results`.")
    if metadata.total_deduped_results != len(bundle.papers):
        issues.append("EVIDENCE_BUNDLE.json `total_deduped_results` must match the paper count.")
    if metadata.verified_count != sum(
        1 for verification in bundle.verified_papers if verification.status == "verified"
    ):
        issues.append("EVIDENCE_BUNDLE.json `verified_count` must match verified paper records.")
    if metadata.unverified_count != sum(
        1 for verification in bundle.verified_papers if verification.status == "unverified"
    ):
        issues.append("EVIDENCE_BUNDLE.json `unverified_count` must match verified paper records.")
    if metadata.pending_count != sum(
        1 for verification in bundle.verified_papers if verification.status == "verify_pending"
    ):
        issues.append("EVIDENCE_BUNDLE.json `pending_count` must match verified paper records.")
    if metadata.status == "blocked" and succeeded:
        issues.append("EVIDENCE_BUNDLE.json cannot be `blocked` when a provider succeeded.")
    if metadata.status in {"succeeded", "partial"} and not succeeded:
        issues.append("EVIDENCE_BUNDLE.json cannot be successful or partial without a successful provider receipt.")
    if metadata.status == "succeeded" and any(status != "succeeded" for status in receipt_statuses):
        issues.append("EVIDENCE_BUNDLE.json cannot be `succeeded` unless all provider receipts succeeded.")
    if metadata.status == "partial" and not any(status != "succeeded" for status in receipt_statuses):
        issues.append("EVIDENCE_BUNDLE.json cannot be `partial` unless at least one provider did not succeed.")
    return issues


def _duplicate_values(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _collect_literature_ids(run_dir: Path) -> tuple[set[str], set[str]]:
    """Collect known evidence bundle ids and query ids from literature artifacts."""
    literature_root = run_dir / "literature"
    bundle_ids: set[str] = set()
    query_ids: set[str] = set()
    queries_root = literature_root / "queries"
    if queries_root.exists():
        for query_dir in sorted(path for path in queries_root.iterdir() if path.is_dir()):
            query_ids.add(query_dir.name)
            bundle_path = query_dir / "EVIDENCE_BUNDLE.json"
            if bundle_path.exists():
                try:
                    bundle_ids.add(EvidenceBundleContract.from_json_file(bundle_path).bundle_id)
                except (json.JSONDecodeError, ValidationError):
                    continue
    bundles_root = literature_root / "bundles"
    if bundles_root.exists():
        for bundle_path in sorted(
            path for path in bundles_root.iterdir() if path.is_file() and path.suffix == ".json"
        ):
            try:
                bundle_ids.add(EvidenceBundleContract.from_json_file(bundle_path).bundle_id)
            except (json.JSONDecodeError, ValidationError):
                continue
    return bundle_ids, query_ids


def _collect_literature_bundle_statuses(run_dir: Path) -> dict[str, str]:
    """Collect evidence-bundle retrieval statuses from canonical literature artifacts."""
    statuses: dict[str, str] = {}
    literature_root = run_dir / "literature"
    queries_root = literature_root / "queries"
    if queries_root.exists():
        for bundle_path in sorted(queries_root.glob("*/EVIDENCE_BUNDLE.json")):
            try:
                bundle = EvidenceBundleContract.from_json_file(bundle_path)
            except (json.JSONDecodeError, ValidationError):
                continue
            statuses[bundle.bundle_id] = bundle.retrieval_metadata.status

    bundles_root = literature_root / "bundles"
    if bundles_root.exists():
        for bundle_path in sorted(
            path for path in bundles_root.iterdir() if path.is_file() and path.suffix == ".json"
        ):
            try:
                bundle = EvidenceBundleContract.from_json_file(bundle_path)
            except (json.JSONDecodeError, ValidationError):
                continue
            statuses.setdefault(bundle.bundle_id, bundle.retrieval_metadata.status)
    return statuses


def _validate_retrieval_linkage(
    *,
    retrieval_results: Sequence[Any],
    evidence_bundle_ids: Sequence[str],
    literature_query_ids: Sequence[str],
    available_bundle_ids: set[str],
    available_query_ids: set[str],
    context: str,
) -> list[str]:
    """Validate that legacy retrieval results point back to evidence bundle artifacts."""
    if not retrieval_results:
        return []
    issues: list[str] = []
    if not evidence_bundle_ids:
        issues.append(f"{context} has non-empty `retrieval_results` but no `evidence_bundle_ids` linkage.")
    if not literature_query_ids:
        issues.append(f"{context} has non-empty `retrieval_results` but no `literature_query_ids` linkage.")
    unknown_bundle_ids = sorted(set(evidence_bundle_ids).difference(available_bundle_ids))
    if unknown_bundle_ids:
        issues.append(f"{context} references unknown evidence bundle IDs: " + ", ".join(unknown_bundle_ids))
    unknown_query_ids = sorted(set(literature_query_ids).difference(available_query_ids))
    if unknown_query_ids:
        issues.append(f"{context} references unknown literature query IDs: " + ", ".join(unknown_query_ids))
    return issues


def _validate_literature_generation_origin(
    *,
    strategy: str,
    retrieval_results: Sequence[Any],
    evidence_bundle_ids: Sequence[str],
    literature_query_ids: Sequence[str],
    available_bundle_ids: set[str],
    available_query_ids: set[str],
) -> list[str]:
    """Validate mandatory bridge linkage for literature-generation hypotheses."""
    if strategy != "literature_exploration_generation":
        return []

    issues: list[str] = []
    if not retrieval_results:
        issues.append(
            "Literature generation hypotheses must include `origin.retrieval_results` derived from an "
            "EvidenceBundleContract produced by `tools.search_literature(...)`."
        )
    if not evidence_bundle_ids:
        issues.append(
            "Literature generation hypotheses must include `origin.evidence_bundle_ids` from the search bridge."
        )
    if not literature_query_ids:
        issues.append(
            "Literature generation hypotheses must include `origin.literature_query_ids` from the search bridge."
        )
    unknown_bundle_ids = sorted(set(evidence_bundle_ids).difference(available_bundle_ids))
    if unknown_bundle_ids:
        issues.append(
            "Literature generation hypotheses reference unknown evidence bundle IDs: " + ", ".join(unknown_bundle_ids)
        )
    unknown_query_ids = sorted(set(literature_query_ids).difference(available_query_ids))
    if unknown_query_ids:
        issues.append(
            "Literature generation hypotheses reference unknown literature query IDs: " + ", ".join(unknown_query_ids)
        )
    return issues


def _validate_evolved_hypothesis_content_quality(hypothesis: HypothesisContract) -> list[str]:
    """Detect deterministic placeholder content in evolved hypothesis artifacts."""
    if not hypothesis.parent_ids:
        return []

    issues: list[str] = []
    content = hypothesis.origin.content
    for field_name, patterns in _PLACEHOLDER_HYPOTHESIS_PATTERNS.items():
        value = getattr(content, field_name)
        if _has_pattern_match(value, patterns):
            issues.append(
                f"Evolved hypotheses must not use placeholder `{field_name}` content; "
                "run the selected `hypothesis-evolve-*` skill with parent-specific scientific details."
            )

    experimental_design = content.experimental_design.lower()
    placeholder_phrase_count = sum(
        1 for phrase in _PLACEHOLDER_EXPERIMENTAL_DESIGN_PHRASES if phrase in experimental_design
    )
    if placeholder_phrase_count >= 3:
        issues.append(
            "Evolved hypotheses must include a specific experimental design rather than placeholder steps such as "
            "`Apply targeted improvement`, `Characterize structure`, or `Benchmark against parent`."
        )
    return issues


def _research_plan_requirement_message(
    research_plan_status: str,
    *,
    pipeline_state: PipelineStateContract | None,
    strategy_plan: StrategyPlanContract | None,
) -> str | None:
    if research_plan_status == "valid":
        return None

    contexts: list[str] = []
    if pipeline_state is not None and pipeline_state.currentPhase in _RESEARCH_PLAN_REQUIRED_PHASES:
        contexts.append(f"currentPhase=`{pipeline_state.currentPhase}`")
    if strategy_plan is not None and strategy_plan.next_action in _RESEARCH_PLAN_REQUIRED_ACTIONS:
        contexts.append(f"next_action=`{strategy_plan.next_action}`")

    if not contexts:
        return None

    return (
        "A valid research_plan/RESEARCH_PLAN.json is required before generation or later pipeline work can run; "
        f"found research-plan status `{research_plan_status}` while " + " and ".join(contexts) + "."
    )


def _ordered_tournament_replay_groups(
    tournament_payloads_by_id: dict[str, TournamentMatchContract],
    evolution_round_records: Sequence[EvolutionRoundRecordContract],
) -> list[tuple[str, list[str]]]:
    """Return deterministic Elo replay groups using available round receipts."""
    groups: list[tuple[str, list[str]]] = []
    round_match_ids: set[str] = set()
    for record in evolution_round_records:
        round_match_ids.update(record.placement_match_ids)
        round_match_ids.update(record.ranked_match_ids)

    for strategy in ("placement_tournament", "ranked_tournament"):
        initial_match_ids = [
            match_id
            for match_id, match_payload in sorted(tournament_payloads_by_id.items())
            if match_id not in round_match_ids
            and match_payload.status == "completed"
            and match_payload.match_strategy == strategy
        ]
        if initial_match_ids:
            groups.append((strategy, initial_match_ids))

    for record in sorted(evolution_round_records, key=lambda item: item.round_index):
        placement_match_ids = [
            match_id
            for match_id in record.placement_match_ids
            if (match_payload := tournament_payloads_by_id.get(match_id)) is not None
            and match_payload.status == "completed"
            and match_payload.match_strategy == "placement_tournament"
        ]
        if placement_match_ids:
            groups.append(("placement_tournament", placement_match_ids))
        ranked_match_ids = [
            match_id
            for match_id in record.ranked_match_ids
            if (match_payload := tournament_payloads_by_id.get(match_id)) is not None
            and match_payload.status == "completed"
            and match_payload.match_strategy == "ranked_tournament"
        ]
        if ranked_match_ids:
            groups.append(("ranked_tournament", ranked_match_ids))

    return groups


def _validate_completed_tournament_elo_writeback(
    *,
    run_dir: Path,
    issues: list[HostAgentValidationIssue],
    hypothesis_payloads_by_id: dict[str, HypothesisContract],
    hypothesis_paths_by_id: dict[str, Path],
    tournament_payloads_by_id: dict[str, TournamentMatchContract],
    evolution_round_records: Sequence[EvolutionRoundRecordContract],
    resolved_config_payload: ResolvedRunConfigContract | None,
) -> bool:
    """Replay completed tournaments and validate persisted hypothesis Elo ratings."""
    if not tournament_payloads_by_id or not hypothesis_payloads_by_id:
        return True

    k_factor = resolved_config_payload.ranking.elo_k_factor if resolved_config_payload is not None else 32.0
    replay_hypotheses_by_id = {
        hypothesis_id: hypothesis.model_copy(
            deep=True,
            update={"elo_rating": 1200.0, "placement_match_ids": [], "ranked_match_ids": []},
        )
        for hypothesis_id, hypothesis in hypothesis_payloads_by_id.items()
    }
    processed_match_ids_by_hypothesis: dict[str, list[str]] = {}

    for strategy, match_ids in _ordered_tournament_replay_groups(tournament_payloads_by_id, evolution_round_records):
        matches: list[TournamentMatchContract] = []
        matchups: list[HypothesisMatchupContract] = []
        for match_id in match_ids:
            match_payload = tournament_payloads_by_id[match_id]
            hypothesis_1 = replay_hypotheses_by_id.get(match_payload.hypothesis_1_id)
            hypothesis_2 = replay_hypotheses_by_id.get(match_payload.hypothesis_2_id)
            if hypothesis_1 is None or hypothesis_2 is None:
                continue
            matches.append(match_payload)
            matchups.append(HypothesisMatchupContract(hypothesis_1=hypothesis_1, hypothesis_2=hypothesis_2))
            processed_match_ids_by_hypothesis.setdefault(hypothesis_1.id, []).append(match_payload.id)
            processed_match_ids_by_hypothesis.setdefault(hypothesis_2.id, []).append(match_payload.id)
        if matches:
            apply_elo_updates(matches, matchups, strategy, k_factor=k_factor)

    valid = True
    for hypothesis_id, processed_match_ids in sorted(processed_match_ids_by_hypothesis.items()):
        persisted_hypothesis = hypothesis_payloads_by_id[hypothesis_id]
        replayed_hypothesis = replay_hypotheses_by_id[hypothesis_id]
        if abs(persisted_hypothesis.elo_rating - replayed_hypothesis.elo_rating) <= 1e-6:
            continue
        _record_issue(
            issues,
            run_dir,
            hypothesis_paths_by_id.get(hypothesis_id, run_dir / "hypotheses"),
            "HYPOTHESIS.json Elo rating for "
            f"`{hypothesis_id}` does not match replayed completed tournament results from match ids: "
            f"{', '.join(sorted(set(processed_match_ids)))}. Expected `{replayed_hypothesis.elo_rating:.6g}`, "
            f"found `{persisted_hypothesis.elo_rating:.6g}`. Re-run `ranking-elo-update` through "
            "`tools.apply_and_persist_elo_updates(...)` before marking ranking complete.",
            "error",
        )
        valid = False

    return valid


def _validate_ranking_update_receipts(
    *,
    run_dir: Path,
    issues: list[HostAgentValidationIssue],
    hypothesis_payloads_by_id: dict[str, HypothesisContract],
    hypothesis_paths_by_id: dict[str, Path],
    tournament_payloads_by_id: dict[str, TournamentMatchContract],
    ranking_receipts_by_id: dict[str, RankingUpdateReceiptContract],
    ranking_receipts_root: Path,
    tournaments_root: Path,
) -> bool:
    """Validate ranking update receipt coverage and receipt-to-artifact consistency."""
    valid = True
    covered_match_ids: set[str] = set()
    latest_receipt_by_hypothesis: dict[str, RankingUpdateReceiptContract] = {}
    for receipt_id, receipt in sorted(ranking_receipts_by_id.items()):
        receipt_path = ranking_receipts_root / f"{receipt_id}.json"
        known_matches: list[TournamentMatchContract] = []
        for match_id in receipt.match_ids:
            match_payload = tournament_payloads_by_id.get(match_id)
            if match_payload is None:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    f"Ranking update receipt `{receipt_id}` references unknown tournament match `{match_id}`.",
                    "error",
                )
                valid = False
                continue
            known_matches.append(match_payload)
            if match_payload.status == "completed":
                covered_match_ids.add(match_id)
            if match_payload.match_strategy != receipt.strategy:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    f"Ranking update receipt `{receipt_id}` strategy `{receipt.strategy}` does not match "
                    f"tournament match `{match_id}` strategy `{match_payload.match_strategy}`.",
                    "error",
                )
                valid = False

        expected_touched_ids = {
            hypothesis_id
            for match_payload in known_matches
            for hypothesis_id in (match_payload.hypothesis_1_id, match_payload.hypothesis_2_id)
            if hypothesis_id
        }
        receipt_touched_ids = set(receipt.touched_hypothesis_ids)
        missing_touched_ids = sorted(expected_touched_ids.difference(receipt_touched_ids))
        if missing_touched_ids:
            _record_issue(
                issues,
                run_dir,
                receipt_path,
                f"Ranking update receipt `{receipt_id}` is missing touched hypothesis ids: "
                + ", ".join(missing_touched_ids),
                "error",
            )
            valid = False
        unknown_touched_ids = sorted(receipt_touched_ids.difference(hypothesis_payloads_by_id))
        if unknown_touched_ids:
            _record_issue(
                issues,
                run_dir,
                receipt_path,
                f"Ranking update receipt `{receipt_id}` references unknown touched hypothesis ids: "
                + ", ".join(unknown_touched_ids),
                "error",
            )
            valid = False

        for hypothesis_id in sorted(receipt_touched_ids.intersection(hypothesis_payloads_by_id)):
            if hypothesis_id not in receipt.elo_after:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    f"Ranking update receipt `{receipt_id}` is missing `elo_after` for `{hypothesis_id}`.",
                    "error",
                )
                valid = False
                continue
            latest_receipt = latest_receipt_by_hypothesis.get(hypothesis_id)
            if latest_receipt is None or receipt.created_at >= latest_receipt.created_at:
                latest_receipt_by_hypothesis[hypothesis_id] = receipt

    for hypothesis_id, receipt in sorted(latest_receipt_by_hypothesis.items()):
        persisted_hypothesis = hypothesis_payloads_by_id[hypothesis_id]
        if abs(persisted_hypothesis.elo_rating - receipt.elo_after[hypothesis_id]) <= 1e-6:
            continue
        receipt_path = ranking_receipts_root / f"{receipt.id}.json"
        _record_issue(
            issues,
            run_dir,
            hypothesis_paths_by_id.get(hypothesis_id, receipt_path),
            "HYPOTHESIS.json Elo rating for "
            f"`{hypothesis_id}` does not match the latest ranking update receipt `{receipt.id}` `elo_after`. "
            f"Expected `{receipt.elo_after[hypothesis_id]:.6g}`, found "
            f"`{persisted_hypothesis.elo_rating:.6g}`.",
            "error",
        )
        valid = False

    completed_match_ids = sorted(
        match_id
        for match_id, match_payload in tournament_payloads_by_id.items()
        if match_payload.status == "completed"
    )
    missing_receipt_match_ids = sorted(set(completed_match_ids).difference(covered_match_ids))
    if missing_receipt_match_ids:
        _record_issue(
            issues,
            run_dir,
            ranking_receipts_root if ranking_receipts_root.exists() else tournaments_root,
            "completed tournament match artifacts are missing ranking update receipt coverage: "
            + ", ".join(missing_receipt_match_ids)
            + ". Call `tools.apply_and_persist_elo_updates(...)`; match refs alone are not a ranking update receipt.",
            "error",
        )
        valid = False

    return valid


def validate_run_artifacts(
    run_dir: Path,
    *,
    resume: bool = False,
    requested_skill: str = "",
) -> HostAgentValidationSummary:
    """Validate host-agent-visible artifacts under one run directory."""
    run_dir = run_dir.resolve()
    checked_artifacts: list[str] = []
    issues: list[HostAgentValidationIssue] = []

    manifest_path = run_dir / "MANIFEST.md"
    if manifest_path.exists():
        checked_artifacts.append(str(manifest_path.resolve()))
    else:
        _record_issue(issues, run_dir, manifest_path, "Manifest is missing and will need to be created.", "warning")

    pipeline_state_path = run_dir / "state" / "PIPELINE_STATE.json"
    current_stage_path = run_dir / "state" / "CURRENT_STAGE.json"
    start_request_path = run_dir / "state" / "START_REQUEST.json"
    run_policy_path = run_dir / "RUN_POLICY.yaml"
    policy_decision_path = run_dir / "state" / "POLICY_DECISION.json"
    resolved_config_path = run_dir / "state" / "RESOLVED_RUN_CONFIG.json"
    strategy_plan_path = run_dir / "state" / "STRATEGY_PLAN.json"
    strategy_decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
    evolution_rounds_path = run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
    evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
    completion_decision_path = run_dir / "state" / "COMPLETION_DECISION.json"
    research_plan_path = run_dir / "research_plan" / "RESEARCH_PLAN.json"
    insights_path = run_dir / "meta" / "INSIGHTS_FROM_REVIEWS.json"
    overview_path = run_dir / "meta" / "RESEARCH_OVERVIEW.json"
    dashboard_links_path = run_dir / "dashboard" / "LINKS.json"
    pipeline_state_payload: PipelineStateContract | None = None
    current_stage_payload: CurrentStageContract | None = None
    resolved_config_payload: ResolvedRunConfigContract | None = None
    strategy_plan_payload: StrategyPlanContract | None = None
    completion_decision_payload: CompletionDecisionContract | None = None
    overview_payload: ResearchOverviewContract | None = None
    research_plan_status = "missing"

    resume_ready = resume
    if start_request_path.exists():
        error = _validate_model_file(StartRequestContract, start_request_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, start_request_path, str(error), "error")
            resume_ready = False
    else:
        _record_issue(
            issues,
            run_dir,
            start_request_path,
            "START_REQUEST.json is not present; the run may have been created through the low-level config "
            "entrypoint.",
            "warning",
        )

    if run_policy_path.exists():
        checked_artifacts.append(str(run_policy_path.resolve()))
        try:
            RunPolicyContract.from_yaml_file(run_policy_path)
        except (ValueError, ValidationError) as exc:
            _record_issue(issues, run_dir, run_policy_path, str(exc), "error")
            resume_ready = False
    else:
        _record_issue(
            issues,
            run_dir,
            run_policy_path,
            "RUN_POLICY.yaml is not present yet; bootstrap should materialize the effective run policy.",
            "warning",
        )

    if pipeline_state_path.exists():
        error = _validate_model_file(PipelineStateContract, pipeline_state_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, pipeline_state_path, str(error), "error")
            resume_ready = False
        else:
            pipeline_state_raw = _load_json(pipeline_state_path)
            missing_keys = _missing_required_keys(
                pipeline_state_raw,
                (
                    "runId",
                    "updatedAt",
                    "iterationCount",
                    "convergenceCount",
                    "hypothesisCount",
                    "viableHypothesisCount",
                    "topHypothesisIds",
                    "mode",
                    "status",
                    "currentPhase",
                    "currentSkill",
                    "completedSkills",
                    "stageTrail",
                ),
            )
            if missing_keys:
                _record_issue(
                    issues,
                    run_dir,
                    pipeline_state_path,
                    "PIPELINE_STATE.json is missing canonical keys: " + ", ".join(missing_keys),
                    "error",
                )
                resume_ready = False
            pipeline_state_payload = PipelineStateContract.model_validate(pipeline_state_raw)
            for message in _validate_pipeline_state_semantics(pipeline_state_payload):
                _record_issue(issues, run_dir, pipeline_state_path, message, "error")
                resume_ready = False
    else:
        if resume:
            _record_issue(
                issues,
                run_dir,
                pipeline_state_path,
                "Resume was requested but PIPELINE_STATE.json is missing.",
                "error",
            )
            resume_ready = False
        else:
            _record_issue(
                issues,
                run_dir,
                pipeline_state_path,
                "Pipeline state is not present yet; a fresh host-agent run may create it.",
                "warning",
            )

    if current_stage_path.exists():
        error = _validate_model_file(CurrentStageContract, current_stage_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, current_stage_path, str(error), "error")
            resume_ready = False
        else:
            current_stage_payload = CurrentStageContract.from_json_file(current_stage_path)
            for message in _validate_current_stage_semantics(current_stage_payload):
                _record_issue(issues, run_dir, current_stage_path, message, "error")
                resume_ready = False
    elif resume:
        _record_issue(
            issues,
            run_dir,
            current_stage_path,
            "Resume was requested but CURRENT_STAGE.json is missing.",
            "error",
        )
        resume_ready = False

    if pipeline_state_payload is not None and current_stage_payload is not None:
        for message in _validate_stage_artifact_alignment(pipeline_state_payload, current_stage_payload):
            _record_issue(issues, run_dir, current_stage_path, message, "error")
            resume_ready = False

    if policy_decision_path.exists():
        error = _validate_model_file(PolicyDecisionContract, policy_decision_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, policy_decision_path, str(error), "error")
            resume_ready = False
    else:
        _record_issue(
            issues,
            run_dir,
            policy_decision_path,
            "Policy decision artifact is not present yet; bootstrap may still be pending.",
            "warning",
        )

    if resolved_config_path.exists():
        error = _validate_model_file(ResolvedRunConfigContract, resolved_config_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, resolved_config_path, str(error), "error")
            resume_ready = False
        else:
            resolved_config_payload = ResolvedRunConfigContract.from_json_file(resolved_config_path)
            for issue in validate_resolved_config_bounds(resolved_config_payload):
                _record_issue(issues, run_dir, resolved_config_path, issue, "error")
                resume_ready = False
    else:
        _record_issue(
            issues,
            run_dir,
            resolved_config_path,
            "Resolved numeric run configuration is not present yet; bootstrap may still be pending.",
            "warning",
        )

    if strategy_plan_path.exists():
        error = _validate_model_file(StrategyPlanContract, strategy_plan_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, strategy_plan_path, str(error), "error")
            resume_ready = False
        else:
            strategy_plan_payload = StrategyPlanContract.from_json_file(strategy_plan_path)
    else:
        _record_issue(
            issues,
            run_dir,
            strategy_plan_path,
            "Strategy plan artifact is not present yet; strategy routing may still be pending.",
            "warning",
        )

    if strategy_decisions_path.exists():
        checked_artifacts.append(str(strategy_decisions_path.resolve()))
        for line_number, line in enumerate(strategy_decisions_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                StrategyDecisionRecordContract.from_payload(json.loads(line))
            except (json.JSONDecodeError, ValidationError) as exc:
                _record_issue(
                    issues,
                    run_dir,
                    strategy_decisions_path,
                    f"Invalid strategy decision record on line {line_number}: {exc}",
                    "error",
                )
                resume_ready = False
    else:
        _record_issue(
            issues,
            run_dir,
            strategy_decisions_path,
            "Strategy decision audit log is not present yet; strategy routing may still be pending.",
            "warning",
        )

    evolution_round_records: list[EvolutionRoundRecordContract] = []
    if evolution_rounds_path.exists():
        checked_artifacts.append(str(evolution_rounds_path.resolve()))
        for line_number, line in enumerate(evolution_rounds_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                evolution_round_records.append(EvolutionRoundRecordContract.from_payload(json.loads(line)))
            except (json.JSONDecodeError, ValidationError) as exc:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"Invalid evolution round record on line {line_number}: {exc}",
                    "error",
                )
                resume_ready = False

    hypothesis_payloads_by_id: dict[str, HypothesisContract] = {}
    hypothesis_paths_by_id: dict[str, Path] = {}

    evolution_state_payload: EvolutionStateContract | None = None
    if evolution_state_path.exists():
        error = _validate_model_file(EvolutionStateContract, evolution_state_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, evolution_state_path, str(error), "error")
        else:
            evolution_state_payload = EvolutionStateContract.model_validate(_load_json(evolution_state_path))
            evolution_state_raw = _load_json(evolution_state_path)
            missing_keys = _missing_required_keys(
                evolution_state_raw,
                (
                    "status",
                    "iterationCount",
                    "convergenceCount",
                    "convergenceThreshold",
                    "maxIterations",
                    "effectiveTopK",
                    "enteredTopKLastRound",
                    "topHypothesisIds",
                    "updatedAt",
                ),
            )
            if missing_keys:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json is missing canonical keys: " + ", ".join(missing_keys),
                    "error",
                )
                resume_ready = False
            if evolution_state_payload.iterationCount > 0 and evolution_state_payload.enteredTopKLastRound is None:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json must record boolean `enteredTopKLastRound` after at least one "
                    "evolution iteration; persist the value returned by `tools.evaluate_convergence(...)`.",
                    "error",
                )
                resume_ready = False
            if evolution_state_payload.enteredTopKLastRound is True and evolution_state_payload.convergenceCount > 0:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json cannot keep `enteredTopKLastRound=true` while `convergenceCount` "
                    "remains above 0.",
                    "error",
                )
                resume_ready = False
            if (
                evolution_state_payload.stopReason == "convergence_reached"
                and evolution_state_payload.convergenceCount < evolution_state_payload.convergenceThreshold
            ):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json recorded `convergence_reached` before the stored convergence "
                    "threshold was met.",
                    "error",
                )
                resume_ready = False
            if (
                evolution_state_payload.effectiveTopK > 0
                and len(evolution_state_payload.topHypothesisIds) > evolution_state_payload.effectiveTopK
            ):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json cannot list more `topHypothesisIds` than `effectiveTopK`.",
                    "error",
                )
                resume_ready = False
            if evolution_state_payload.stopReason and evolution_state_payload.status not in {"blocked", "completed"}:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json cannot keep a non-terminal `status` after recording terminal `stopReason` "
                    f"`{evolution_state_payload.stopReason}`.",
                    "error",
                )
                resume_ready = False
            if (
                pipeline_state_payload is not None
                and pipeline_state_payload.status == "completed"
                and evolution_state_payload.status == "running"
            ):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json cannot remain `running` when PIPELINE_STATE.json is already `completed`.",
                    "error",
                )
                resume_ready = False

    if completion_decision_path.exists():
        error = _validate_model_file(CompletionDecisionContract, completion_decision_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, completion_decision_path, str(error), "error")
        else:
            completion_decision_payload = CompletionDecisionContract.from_json_file(completion_decision_path)
        if completion_decision_payload is not None and resolved_config_payload is not None:
            mismatched_top_k_values = [
                value
                for value in _extract_top_k_text_values(completion_decision_payload.rationale)
                if value != resolved_config_payload.ranking.tournament_top_k
            ]
            if mismatched_top_k_values:
                _record_issue(
                    issues,
                    run_dir,
                    completion_decision_path,
                    "COMPLETION_DECISION.json rationale references top-k values that do not match "
                    "RESOLVED_RUN_CONFIG.ranking.tournament_top_k "
                    f"`{resolved_config_payload.ranking.tournament_top_k}`: "
                    + ", ".join(str(value) for value in sorted(set(mismatched_top_k_values))),
                    "error",
                )
                resume_ready = False
            mismatched_safety_values = [
                value
                for value in _extract_safety_limit_text_values(completion_decision_payload.rationale)
                if value != resolved_config_payload.convergence.safety_max_iterations
            ]
            if mismatched_safety_values:
                _record_issue(
                    issues,
                    run_dir,
                    completion_decision_path,
                    "COMPLETION_DECISION.json rationale references safety limit values that do not match "
                    "RESOLVED_RUN_CONFIG.convergence.safety_max_iterations "
                    f"`{resolved_config_payload.convergence.safety_max_iterations}`: "
                    + ", ".join(str(value) for value in sorted(set(mismatched_safety_values))),
                    "error",
                )
                resume_ready = False
        if (
            completion_decision_payload is not None
            and evolution_state_payload is not None
            and evolution_state_payload.stopReason != "convergence_reached"
            and _has_positive_convergence_claim("\n".join(completion_decision_payload.rationale))
        ):
            _record_issue(
                issues,
                run_dir,
                completion_decision_path,
                "COMPLETION_DECISION.json rationale must not claim convergence unless "
                "EVOLUTION_STATE.stopReason is `convergence_reached`.",
                "error",
            )
            resume_ready = False
        if (
            completion_decision_payload is not None
            and evolution_state_payload is not None
            and not evolution_state_payload.stopReason
            and completion_decision_payload.decision in {"generate_overview", "complete"}
        ):
            _record_issue(
                issues,
                run_dir,
                completion_decision_path,
                "COMPLETION_DECISION.json cannot advance to overview or completion while evolution has no terminal "
                "stop reason.",
                "error",
            )
            resume_ready = False

    if research_plan_path.exists():
        error = _validate_model_file(ResearchPlanContract, research_plan_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, research_plan_path, str(error), "error")
            research_plan_status = "invalid"
            resume_ready = False
        else:
            research_plan_status = "valid"
    else:
        _record_issue(
            issues,
            run_dir,
            research_plan_path,
            "Research plan artifact is not present yet; configuration may still be pending.",
            "warning",
        )

    research_plan_requirement_issue = _research_plan_requirement_message(
        research_plan_status,
        pipeline_state=pipeline_state_payload,
        strategy_plan=strategy_plan_payload,
    )
    if research_plan_requirement_issue is not None:
        _record_issue(issues, run_dir, research_plan_path, research_plan_requirement_issue, "error")
        resume_ready = False

    if insights_path.exists():
        error = _validate_model_file(InsightsFromReviewsContract, insights_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, insights_path, str(error), "error")
    literature_bundle_statuses = _collect_literature_bundle_statuses(run_dir)
    degraded_literature_bundle_ids = sorted(
        bundle_id for bundle_id, status in literature_bundle_statuses.items() if status in {"partial", "blocked"}
    )
    if overview_path.exists():
        error = _validate_model_file(ResearchOverviewContract, overview_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, overview_path, str(error), "error")
        else:
            overview_payload = ResearchOverviewContract.from_json_file(overview_path)
            if (
                evolution_state_payload is not None
                and evolution_state_payload.stopReason != "convergence_reached"
                and _has_positive_convergence_claim(overview_payload.content)
            ):
                _record_issue(
                    issues,
                    run_dir,
                    overview_path,
                    "RESEARCH_OVERVIEW.json content must not claim convergence unless "
                    "EVOLUTION_STATE.stopReason is `convergence_reached`.",
                    "error",
                )
                resume_ready = False
            if degraded_literature_bundle_ids and _has_non_negated_claim(
                overview_payload.content,
                _COMPREHENSIVE_LITERATURE_CLAIM_PATTERNS,
            ):
                _record_issue(
                    issues,
                    run_dir,
                    overview_path,
                    "RESEARCH_OVERVIEW.json content must not claim comprehensive literature coverage when "
                    "any evidence bundle has `retrieval_metadata.status` of `partial` or `blocked`: "
                    + ", ".join(degraded_literature_bundle_ids),
                    "error",
                )
                resume_ready = False
            if degraded_literature_bundle_ids and not _has_pattern_match(
                overview_payload.content,
                _LITERATURE_LIMITATION_PATTERNS,
            ):
                _record_issue(
                    issues,
                    run_dir,
                    overview_path,
                    "RESEARCH_OVERVIEW.json content must include a concise literature retrieval limitation note "
                    "when any evidence bundle has `retrieval_metadata.status` of `partial` or `blocked`: "
                    + ", ".join(degraded_literature_bundle_ids),
                    "error",
                )
                resume_ready = False
            if (
                evolution_state_payload is not None
                and not evolution_state_payload.stopReason
                and overview_payload.status == "completed"
            ):
                _record_issue(
                    issues,
                    run_dir,
                    overview_path,
                    "RESEARCH_OVERVIEW.json cannot be completed while evolution has no terminal stop reason.",
                    "error",
                )
                resume_ready = False
    if insights_path.exists() and overview_path.exists():
        try:
            MetaReviewContract.model_validate(
                {
                    "insights_from_reviews": _load_json(insights_path),
                    "research_overview": _load_json(overview_path),
                }
            )
        except ValidationError as exc:
            _record_issue(issues, run_dir, insights_path, str(exc), "error")

    if dashboard_links_path.exists():
        checked_artifacts.append(str(dashboard_links_path.resolve()))
        try:
            payload = _load_json(dashboard_links_path)
            links = payload.get("links", {})
            if not isinstance(links, dict) or not all(isinstance(value, str) for value in links.values()):
                raise ValueError("LINKS.json must contain a `links` object with string URL values.")
        except (json.JSONDecodeError, ValueError) as exc:
            _record_issue(issues, run_dir, dashboard_links_path, str(exc), "error")

    if not _validate_literature_artifacts(run_dir, checked_artifacts, issues):
        resume_ready = False
    available_literature_bundle_ids, available_literature_query_ids = _collect_literature_ids(run_dir)

    islands_path = run_dir / "islands" / "ISLANDS.json"
    deprecated_state_islands_path = run_dir / "state" / "ISLANDS.json"
    island_items_payload: list[dict[str, Any]] = []
    if deprecated_state_islands_path.exists():
        checked_artifacts.append(str(deprecated_state_islands_path.resolve()))
        _record_issue(
            issues,
            run_dir,
            deprecated_state_islands_path,
            "`state/ISLANDS.json` is deprecated and must not be used. Persist canonical island state only at "
            "`islands/ISLANDS.json`.",
            "error",
        )
        resume_ready = False
    if islands_path.exists():
        island_items_payload, islands_artifact_valid = _validate_islands_artifact(
            run_dir,
            islands_path,
            checked_artifacts,
            issues,
        )
        if not islands_artifact_valid:
            resume_ready = False
    canonical_island_ids = {
        island_id
        for item in island_items_payload
        if isinstance((island_id := item.get("id")), str) and island_id.strip()
    }
    proximity_graph_path = run_dir / "state" / "PROXIMITY_GRAPH.json"
    proximity_status_path = run_dir / "state" / "PROXIMITY_STATUS.json"
    proximity_receipts_root = run_dir / "state" / "proximity_receipts"
    proximity_graph_payload: ProximityGraphContract | None = None
    proximity_status_payload: ProximityStatusContract | None = None
    proximity_receipts_by_hypothesis: dict[str, ProximityEmbeddingReceiptContract] = {}
    expected_proximity_config_hash = (
        proximity_config_hash(resolved_config_payload.proximity) if resolved_config_payload is not None else ""
    )
    expected_proximity_dimensions = (
        resolved_config_payload.proximity.dimensions if resolved_config_payload is not None else 0
    )
    if proximity_graph_path.exists():
        error = _validate_model_file(ProximityGraphContract, proximity_graph_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, proximity_graph_path, str(error), "error")
            resume_ready = False
        else:
            proximity_graph_payload = ProximityGraphContract.from_payload(_load_json(proximity_graph_path))

    if proximity_status_path.exists():
        error = _validate_model_file(ProximityStatusContract, proximity_status_path, checked_artifacts)
        if error is not None:
            _record_issue(issues, run_dir, proximity_status_path, str(error), "error")
            resume_ready = False
        else:
            proximity_status_payload = ProximityStatusContract.from_json_file(proximity_status_path)

    if proximity_receipts_root.exists():
        for receipt_path in sorted(
            path for path in proximity_receipts_root.iterdir() if path.is_file() and path.suffix == ".json"
        ):
            error = _validate_model_file(ProximityEmbeddingReceiptContract, receipt_path, checked_artifacts)
            if error is not None:
                _record_issue(issues, run_dir, receipt_path, str(error), "error")
                resume_ready = False
                continue
            receipt_payload = ProximityEmbeddingReceiptContract.from_json_file(receipt_path)
            if receipt_path.stem != receipt_payload.hypothesis_id:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    "Proximity receipt filename must match `hypothesis_id`.",
                    "error",
                )
                resume_ready = False
            if receipt_payload.hypothesis_id in proximity_receipts_by_hypothesis:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    f"Duplicate proximity receipt for hypothesis `{receipt_payload.hypothesis_id}`.",
                    "error",
                )
                resume_ready = False
            proximity_receipts_by_hypothesis[receipt_payload.hypothesis_id] = receipt_payload

            if receipt_payload.graph_updated and receipt_payload.status != "succeeded":
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    "Proximity receipt cannot set `graph_updated=true` unless `status` is `succeeded`.",
                    "error",
                )
                resume_ready = False
            if receipt_payload.graph_updated and (
                proximity_graph_payload is None
                or receipt_payload.hypothesis_id not in proximity_graph_payload.embeddings
            ):
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    "Proximity receipt records a graph update, but `state/PROXIMITY_GRAPH.json` does not contain "
                    f"an embedding for `{receipt_payload.hypothesis_id}`.",
                    "error",
                )
                resume_ready = False
            if expected_proximity_dimensions and receipt_payload.dimensions != expected_proximity_dimensions:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    "Proximity receipt dimensions do not match RESOLVED_RUN_CONFIG.proximity.dimensions.",
                    "error",
                )
                resume_ready = False
            if expected_proximity_config_hash and not receipt_payload.config_hash:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    "Proximity receipt is missing `config_hash`; rebuild the proximity receipt before relying on "
                    "config drift checks.",
                    "warning",
                )
            elif expected_proximity_config_hash and receipt_payload.config_hash != expected_proximity_config_hash:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    "Proximity receipt config hash does not match RESOLVED_RUN_CONFIG.proximity.",
                    "error",
                )
                resume_ready = False

    if proximity_receipts_by_hypothesis and proximity_status_payload is None:
        _record_issue(
            issues,
            run_dir,
            proximity_status_path,
            "Proximity receipts exist but run-level PROXIMITY_STATUS.json is missing.",
            "error",
        )
        resume_ready = False
    if proximity_status_payload is not None and proximity_status_payload.last_hypothesis_id:
        latest_receipt = proximity_receipts_by_hypothesis.get(proximity_status_payload.last_hypothesis_id)
        if latest_receipt is None:
            _record_issue(
                issues,
                run_dir,
                proximity_status_path,
                "PROXIMITY_STATUS.json `last_hypothesis_id` does not have a matching proximity receipt.",
                "error",
            )
            resume_ready = False
        elif proximity_status_payload.status != latest_receipt.status:
            _record_issue(
                issues,
                run_dir,
                proximity_status_path,
                "PROXIMITY_STATUS.json `status` must match the latest proximity receipt status.",
                "error",
            )
            resume_ready = False
        elif (
            proximity_status_payload.config_hash and proximity_status_payload.config_hash != latest_receipt.config_hash
        ):
            _record_issue(
                issues,
                run_dir,
                proximity_status_path,
                "PROXIMITY_STATUS.json `config_hash` must match the latest proximity receipt config hash.",
                "error",
            )
            resume_ready = False

    if (
        overview_payload is not None
        and proximity_status_payload is not None
        and proximity_status_payload.status in _PROXIMITY_FALLBACK_STATUSES
        and _has_non_negated_claim(overview_payload.content, _EMBEDDING_RANKING_CLAIM_PATTERNS)
    ):
        _record_issue(
            issues,
            run_dir,
            overview_path,
            "RESEARCH_OVERVIEW.json content must not describe ranking as embedding-, proximity-, or "
            "similarity-informed when PROXIMITY_STATUS.json records fallback status "
            f"`{proximity_status_payload.status}`.",
            "error",
        )
        resume_ready = False

    if (
        overview_payload is not None
        and proximity_status_payload is not None
        and proximity_status_payload.status in _PROXIMITY_FALLBACK_STATUSES
        and not _has_pattern_match(overview_payload.content, _PROXIMITY_LIMITATION_PATTERNS)
    ):
        _record_issue(
            issues,
            run_dir,
            overview_path,
            "RESEARCH_OVERVIEW.json content must include a concise proximity embedding fallback limitation "
            f"note when PROXIMITY_STATUS.json records fallback status `{proximity_status_payload.status}`.",
            "error",
        )
        resume_ready = False

    tournaments_root = run_dir / "tournaments"
    ranking_receipts_root = run_dir / "state" / "ranking_update_receipts"
    ranking_receipts_by_id: dict[str, RankingUpdateReceiptContract] = {}
    if ranking_receipts_root.exists():
        for receipt_path in sorted(
            path for path in ranking_receipts_root.iterdir() if path.is_file() and path.suffix == ".json"
        ):
            error = _validate_model_file(RankingUpdateReceiptContract, receipt_path, checked_artifacts)
            if error is not None:
                _record_issue(issues, run_dir, receipt_path, str(error), "error")
                resume_ready = False
                continue
            receipt_payload = RankingUpdateReceiptContract.from_json_file(receipt_path)
            if receipt_path.stem != receipt_payload.id:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    "Ranking update receipt filename must match `id`.",
                    "error",
                )
                resume_ready = False
            if receipt_payload.id in ranking_receipts_by_id:
                _record_issue(
                    issues,
                    run_dir,
                    receipt_path,
                    f"Duplicate ranking update receipt `{receipt_payload.id}`.",
                    "error",
                )
                resume_ready = False
            ranking_receipts_by_id[receipt_payload.id] = receipt_payload

    tournament_payloads_by_id: dict[str, TournamentMatchContract] = {}
    tournament_refs_by_hypothesis: dict[str, dict[str, set[str]]] = {}
    ranked_tournament_refs_by_hypothesis: dict[str, set[str]] = {}
    tournament_artifact_ids: set[str] = set()
    placement_candidate_ids: set[str] = set()
    ranked_challenger_ids: set[str] = set()
    if tournaments_root.exists():
        for tournament_path in sorted(
            path for path in tournaments_root.iterdir() if path.is_file() and path.suffix == ".json"
        ):
            error = _validate_model_file(TournamentMatchContract, tournament_path, checked_artifacts)
            if error is not None:
                _record_issue(issues, run_dir, tournament_path, str(error), "error")
                resume_ready = False
                continue
            tournament_payload = TournamentMatchContract.model_validate(_load_json(tournament_path))
            tournament_payloads_by_id[tournament_payload.id] = tournament_payload
            tournament_artifact_ids.add(tournament_payload.id)

            hypothesis_1_refs = tournament_refs_by_hypothesis.setdefault(
                tournament_payload.hypothesis_1_id,
                {"placement_match_ids": set(), "ranked_match_ids": set()},
            )
            hypothesis_2_refs = tournament_refs_by_hypothesis.setdefault(
                tournament_payload.hypothesis_2_id,
                {"placement_match_ids": set(), "ranked_match_ids": set()},
            )
            if tournament_payload.match_strategy == "placement_tournament":
                placement_candidate_ids.add(tournament_payload.hypothesis_1_id)
                hypothesis_1_refs["placement_match_ids"].add(tournament_payload.id)
                hypothesis_2_refs["ranked_match_ids"].add(tournament_payload.id)
            elif tournament_payload.match_strategy == "ranked_tournament":
                ranked_challenger_ids.add(tournament_payload.hypothesis_1_id)
                hypothesis_1_refs["ranked_match_ids"].add(tournament_payload.id)
                hypothesis_2_refs["ranked_match_ids"].add(tournament_payload.id)
                ranked_tournament_refs_by_hypothesis.setdefault(tournament_payload.hypothesis_1_id, set()).add(
                    tournament_payload.id
                )
                ranked_tournament_refs_by_hypothesis.setdefault(tournament_payload.hypothesis_2_id, set()).add(
                    tournament_payload.id
                )

    hypotheses_root = run_dir / "hypotheses"
    evolved_hypothesis_count = 0
    evolved_hypothesis_ids: set[str] = set()
    viable_hypothesis_count = 0
    if hypotheses_root.exists():
        for hypothesis_dir in sorted(path for path in hypotheses_root.iterdir() if path.is_dir()):
            hypothesis_path = hypothesis_dir / "HYPOTHESIS.json"
            hypothesis_payload: HypothesisContract | None = None
            if hypothesis_path.exists():
                error = _validate_model_file(HypothesisContract, hypothesis_path, checked_artifacts)
                if error is not None:
                    _record_issue(issues, run_dir, hypothesis_path, str(error), "error")
                else:
                    hypothesis_raw = _load_json(hypothesis_path)
                    missing_keys = _missing_required_keys(
                        hypothesis_raw,
                        (
                            "id",
                            "timestamp",
                            "elo_rating",
                            "origin",
                            "review",
                            "island_id",
                            "parent_ids",
                            "placement_match_ids",
                            "ranked_match_ids",
                        ),
                    )
                    if missing_keys:
                        _record_issue(
                            issues,
                            run_dir,
                            hypothesis_path,
                            "HYPOTHESIS.json is missing canonical keys: " + ", ".join(missing_keys),
                            "error",
                        )
                        resume_ready = False
                    hypothesis_payload = HypothesisContract.from_payload(hypothesis_raw)
                    hypothesis_payloads_by_id[hypothesis_payload.id] = hypothesis_payload
                    hypothesis_paths_by_id[hypothesis_payload.id] = hypothesis_path
                    for match_ref_field in ("placement_match_ids", "ranked_match_ids"):
                        duplicate_match_ids = _duplicate_items(getattr(hypothesis_payload, match_ref_field))
                        if duplicate_match_ids:
                            _record_issue(
                                issues,
                                run_dir,
                                hypothesis_path,
                                f"HYPOTHESIS.json `{match_ref_field}` must not contain duplicates: "
                                + ", ".join(duplicate_match_ids)
                                + ".",
                                "error",
                            )
                            resume_ready = False
                    if hypothesis_payload.is_viable:
                        viable_hypothesis_count += 1
                    if _is_blank_text(hypothesis_payload.origin.strategy):
                        _record_issue(
                            issues,
                            run_dir,
                            hypothesis_path,
                            "HYPOTHESIS.json must keep `origin.strategy` non-empty.",
                            "error",
                        )
                        resume_ready = False
                    content_fields = {
                        "statement": hypothesis_payload.origin.content.statement,
                        "mechanism": hypothesis_payload.origin.content.mechanism,
                        "experimental_design": hypothesis_payload.origin.content.experimental_design,
                        "summary": hypothesis_payload.origin.content.summary,
                        "category": hypothesis_payload.origin.content.category,
                    }
                    missing_content_fields = [
                        field_name for field_name, field_value in content_fields.items() if _is_blank_text(field_value)
                    ]
                    if missing_content_fields:
                        _record_issue(
                            issues,
                            run_dir,
                            hypothesis_path,
                            "HYPOTHESIS.json is missing required origin content fields: "
                            + ", ".join(missing_content_fields),
                            "error",
                        )
                        resume_ready = False
                    if _is_blank_text(hypothesis_payload.island_id):
                        _record_issue(
                            issues,
                            run_dir,
                            hypothesis_path,
                            "HYPOTHESIS.json must keep `island_id` non-empty once the round is finalized.",
                            "error",
                        )
                        resume_ready = False
                    if hypothesis_payload.parent_ids:
                        evolved_hypothesis_count += 1
                        evolved_hypothesis_ids.add(hypothesis_payload.id)
                        if not hypothesis_payload.origin.strategy.endswith("_evolution"):
                            _record_issue(
                                issues,
                                run_dir,
                                hypothesis_path,
                                "Evolved hypotheses must use an `_evolution` origin strategy.",
                                "error",
                            )
                            resume_ready = False
                        for message in _validate_evolved_hypothesis_content_quality(hypothesis_payload):
                            _record_issue(issues, run_dir, hypothesis_path, message, "error")
                            resume_ready = False
                    for message in _validate_literature_generation_origin(
                        strategy=hypothesis_payload.origin.strategy,
                        retrieval_results=hypothesis_payload.origin.retrieval_results,
                        evidence_bundle_ids=hypothesis_payload.origin.evidence_bundle_ids,
                        literature_query_ids=hypothesis_payload.origin.literature_query_ids,
                        available_bundle_ids=available_literature_bundle_ids,
                        available_query_ids=available_literature_query_ids,
                    ):
                        _record_issue(issues, run_dir, hypothesis_path, message, "error")
                        resume_ready = False
                    for message in _validate_retrieval_linkage(
                        retrieval_results=hypothesis_payload.origin.retrieval_results,
                        evidence_bundle_ids=hypothesis_payload.origin.evidence_bundle_ids,
                        literature_query_ids=hypothesis_payload.origin.literature_query_ids,
                        available_bundle_ids=available_literature_bundle_ids,
                        available_query_ids=available_literature_query_ids,
                        context="HYPOTHESIS.json origin",
                    ):
                        _record_issue(issues, run_dir, hypothesis_path, message, "error")
                        resume_ready = False
                    for message in _validate_retrieval_linkage(
                        retrieval_results=hypothesis_payload.review.full_review.retrieval_results,
                        evidence_bundle_ids=hypothesis_payload.review.full_review.evidence_bundle_ids,
                        literature_query_ids=hypothesis_payload.review.full_review.literature_query_ids,
                        available_bundle_ids=available_literature_bundle_ids,
                        available_query_ids=available_literature_query_ids,
                        context="HYPOTHESIS.json embedded full review",
                    ):
                        _record_issue(issues, run_dir, hypothesis_path, message, "error")
                        resume_ready = False
                    for field_name in REVIEW_STAGE_FILE_MAP:
                        embedded_stage_payload = getattr(hypothesis_payload.review, field_name)
                        content_issue = review_stage_content_issue(field_name, embedded_stage_payload)
                        if content_issue is not None:
                            _record_issue(
                                issues,
                                run_dir,
                                hypothesis_path,
                                f"Embedded hypothesis review payload issue for `{field_name}`: {content_issue}",
                                "error",
                            )
                            resume_ready = False
            else:
                _record_issue(
                    issues,
                    run_dir,
                    hypothesis_path,
                    "Hypothesis directory is missing HYPOTHESIS.json.",
                    "error",
                )
                continue

            review_dir = hypothesis_dir / "REVIEW"
            review_path = review_dir / "REVIEW_SUMMARY.json"
            if review_path.exists():
                aggregate_review: ReviewContract | None = None
                if hypothesis_payload is not None:
                    try:
                        aggregate_review = ReviewContract.model_validate(
                            hypothesis_payload.review.model_dump(mode="json")
                        )
                    except ValidationError as exc:
                        _record_issue(
                            issues,
                            run_dir,
                            hypothesis_path,
                            f"Embedded hypothesis review payload is invalid: {exc}",
                            "error",
                        )

                for field_name, (filename, contract_type) in REVIEW_STAGE_FILE_MAP.items():
                    stage_path = review_dir / filename
                    if not stage_path.exists():
                        continue
                    error = _validate_model_file(contract_type, stage_path, checked_artifacts)
                    if error is not None:
                        _record_issue(issues, run_dir, stage_path, str(error), "error")
                        resume_ready = False
                        continue
                    if aggregate_review is None:
                        continue
                    stage_payload = contract_type.model_validate(_load_json(stage_path))
                    content_issue = review_stage_content_issue(field_name, stage_payload)
                    if content_issue is not None:
                        _record_issue(issues, run_dir, stage_path, content_issue, "error")
                        resume_ready = False
                    if field_name == "full_review":
                        for message in _validate_retrieval_linkage(
                            retrieval_results=stage_payload.retrieval_results,
                            evidence_bundle_ids=stage_payload.evidence_bundle_ids,
                            literature_query_ids=stage_payload.literature_query_ids,
                            available_bundle_ids=available_literature_bundle_ids,
                            available_query_ids=available_literature_query_ids,
                            context="FULL_REVIEW.json",
                        ):
                            _record_issue(issues, run_dir, stage_path, message, "error")
                            resume_ready = False
                    embedded_payload = getattr(aggregate_review, field_name)
                    if embedded_payload.model_dump(mode="json") != stage_payload.model_dump(mode="json"):
                        _record_issue(
                            issues,
                            run_dir,
                            hypothesis_path,
                            f"Embedded hypothesis review payload does not match REVIEW/{filename}.",
                            "error",
                        )
                        resume_ready = False
            else:
                _record_issue(
                    issues,
                    run_dir,
                    review_path,
                    "Review summary artifact is missing for this hypothesis.",
                    "warning",
                )

    hypothesis_ids_for_ref_validation = sorted(set(tournament_refs_by_hypothesis) | set(hypothesis_payloads_by_id))
    for hypothesis_id in hypothesis_ids_for_ref_validation:
        expected_refs = tournament_refs_by_hypothesis.get(
            hypothesis_id,
            {"placement_match_ids": set(), "ranked_match_ids": set()},
        )
        hypothesis_payload = hypothesis_payloads_by_id.get(hypothesis_id)
        hypothesis_path = hypothesis_paths_by_id.get(hypothesis_id, tournaments_root)
        if hypothesis_payload is None:
            _record_issue(
                issues,
                run_dir,
                hypothesis_path,
                f"Tournament artifacts reference hypothesis `{hypothesis_id}` but its canonical HYPOTHESIS.json "
                "is missing or invalid.",
                "error",
            )
            resume_ready = False
            continue

        expected_placement_refs = expected_refs["placement_match_ids"]
        expected_ranked_refs = expected_refs["ranked_match_ids"]
        actual_placement_refs = set(hypothesis_payload.placement_match_ids)
        actual_ranked_refs = set(hypothesis_payload.ranked_match_ids)
        missing_placement_refs = sorted(expected_placement_refs.difference(actual_placement_refs))
        missing_ranked_refs = sorted(expected_ranked_refs.difference(actual_ranked_refs))
        extra_placement_refs = sorted(
            actual_placement_refs.intersection(tournament_artifact_ids).difference(expected_placement_refs)
        )
        extra_ranked_refs = sorted(
            actual_ranked_refs.intersection(tournament_artifact_ids).difference(expected_ranked_refs)
        )
        if missing_placement_refs:
            _record_issue(
                issues,
                run_dir,
                hypothesis_path,
                "HYPOTHESIS.json is missing placement tournament match refs: " + ", ".join(missing_placement_refs),
                "error",
            )
            resume_ready = False
        if missing_ranked_refs:
            _record_issue(
                issues,
                run_dir,
                hypothesis_path,
                "HYPOTHESIS.json is missing ranked tournament match refs: " + ", ".join(missing_ranked_refs),
                "error",
            )
            resume_ready = False
        if extra_placement_refs:
            _record_issue(
                issues,
                run_dir,
                hypothesis_path,
                "HYPOTHESIS.json contains extra placement tournament match refs: " + ", ".join(extra_placement_refs),
                "error",
            )
            resume_ready = False
        if extra_ranked_refs:
            _record_issue(
                issues,
                run_dir,
                hypothesis_path,
                "HYPOTHESIS.json contains extra ranked tournament match refs: " + ", ".join(extra_ranked_refs),
                "error",
            )
            resume_ready = False

    for hypothesis_id, hypothesis_payload in hypothesis_payloads_by_id.items():
        hypothesis_path = hypothesis_paths_by_id[hypothesis_id]
        referenced_tournament_ids = set(hypothesis_payload.placement_match_ids) | set(
            hypothesis_payload.ranked_match_ids
        )
        unknown_refs = sorted(referenced_tournament_ids.difference(tournament_artifact_ids))
        if unknown_refs:
            _record_issue(
                issues,
                run_dir,
                hypothesis_path,
                "HYPOTHESIS.json references tournament artifacts that do not exist: " + ", ".join(unknown_refs),
                "error",
            )
            resume_ready = False

    if not _validate_completed_tournament_elo_writeback(
        run_dir=run_dir,
        issues=issues,
        hypothesis_payloads_by_id=hypothesis_payloads_by_id,
        hypothesis_paths_by_id=hypothesis_paths_by_id,
        tournament_payloads_by_id=tournament_payloads_by_id,
        evolution_round_records=evolution_round_records,
        resolved_config_payload=resolved_config_payload,
    ):
        resume_ready = False

    if not _validate_ranking_update_receipts(
        run_dir=run_dir,
        issues=issues,
        hypothesis_payloads_by_id=hypothesis_payloads_by_id,
        hypothesis_paths_by_id=hypothesis_paths_by_id,
        tournament_payloads_by_id=tournament_payloads_by_id,
        ranking_receipts_by_id=ranking_receipts_by_id,
        ranking_receipts_root=ranking_receipts_root,
        tournaments_root=tournaments_root,
    ):
        resume_ready = False

    for candidate_id in sorted(ranked_challenger_ids.difference(placement_candidate_ids)):
        candidate = hypothesis_payloads_by_id.get(candidate_id)
        if candidate is None or not candidate.is_viable:
            continue
        _record_issue(
            issues,
            run_dir,
            hypothesis_paths_by_id[candidate_id],
            "Ranked tournament challenger "
            f"`{candidate_id}` has ranked_tournament match refs but no placement_tournament match refs; "
            "ranking must run placement selection, placement tournaments, and placement Elo before ranked gating. "
            "A proximity fallback receipt is not a substitute for the placement stage.",
            "error",
        )
        resume_ready = False

    frontier_hypothesis_ids: set[str] = set()
    if evolution_state_payload is not None:
        frontier_hypothesis_ids.update(evolution_state_payload.topHypothesisIds)
    if pipeline_state_payload is not None:
        frontier_hypothesis_ids.update(pipeline_state_payload.topHypothesisIds)
    for frontier_hypothesis_id in sorted(frontier_hypothesis_ids):
        frontier_hypothesis = hypothesis_payloads_by_id.get(frontier_hypothesis_id)
        if (
            frontier_hypothesis is None
            or not frontier_hypothesis.is_viable
            or not frontier_hypothesis.parent_ids
            or frontier_hypothesis.placement_match_ids
        ):
            continue
        _record_issue(
            issues,
            run_dir,
            hypothesis_paths_by_id.get(frontier_hypothesis_id, hypotheses_root),
            "Frontier hypothesis "
            f"`{frontier_hypothesis_id}` is an evolved viable child without placement tournament provenance; "
            "resume must not promote evolved children into the frontier before ranking provenance is persisted.",
            "error",
        )
        resume_ready = False

    if resolved_config_payload is not None and placement_candidate_ids:
        tournament_top_k = resolved_config_payload.ranking.tournament_top_k
        top_k_hypotheses = get_top_k_hypotheses(hypothesis_payloads_by_id, tournament_top_k)
        for candidate_id in sorted(placement_candidate_ids):
            candidate = hypothesis_payloads_by_id.get(candidate_id)
            if candidate is None or not candidate.is_viable:
                continue
            ranked_opponents = select_ranked_opponents(candidate, hypothesis_payloads_by_id, tournament_top_k)
            if (
                should_run_ranked_tournament(candidate, top_k_hypotheses, tournament_top_k)
                and ranked_opponents
                and not ranked_tournament_refs_by_hypothesis.get(candidate_id)
            ):
                _record_issue(
                    issues,
                    run_dir,
                    hypothesis_paths_by_id[candidate_id],
                    "Placement candidate entered the ranked frontier but has no ranked_tournament match refs; "
                    "ranking must run placement Elo before top-k gating and then run ranked tournament play.",
                    "error",
                )
                resume_ready = False

    if proximity_graph_payload is not None:
        graph_hypothesis_ids = set(proximity_graph_payload.embeddings) | set(proximity_graph_payload.similarities)
        for targets in proximity_graph_payload.similarities.values():
            graph_hypothesis_ids.update(targets)
        unknown_graph_ids = sorted(graph_hypothesis_ids.difference(hypothesis_payloads_by_id))
        if unknown_graph_ids:
            _record_issue(
                issues,
                run_dir,
                proximity_graph_path,
                "PROXIMITY_GRAPH.json references unknown hypothesis IDs: " + ", ".join(unknown_graph_ids),
                "error",
            )
            resume_ready = False
        for graph_hypothesis_id, embedding in proximity_graph_payload.embeddings.items():
            metadata = proximity_graph_payload.embedding_metadata.get(graph_hypothesis_id)
            if metadata is None:
                _record_issue(
                    issues,
                    run_dir,
                    proximity_graph_path,
                    "PROXIMITY_GRAPH.json embedding "
                    f"`{graph_hypothesis_id}` is missing embedding metadata; rebuild the graph before relying on "
                    "config/input drift checks.",
                    "warning",
                )
                continue
            if metadata.dimensions != len(embedding):
                _record_issue(
                    issues,
                    run_dir,
                    proximity_graph_path,
                    "PROXIMITY_GRAPH.json embedding metadata dimensions do not match the vector length for "
                    f"`{graph_hypothesis_id}`.",
                    "error",
                )
                resume_ready = False
            if expected_proximity_dimensions and metadata.dimensions != expected_proximity_dimensions:
                _record_issue(
                    issues,
                    run_dir,
                    proximity_graph_path,
                    "PROXIMITY_GRAPH.json embedding metadata dimensions do not match "
                    f"RESOLVED_RUN_CONFIG.proximity.dimensions for `{graph_hypothesis_id}`.",
                    "error",
                )
                resume_ready = False
            if expected_proximity_config_hash and not metadata.config_hash:
                _record_issue(
                    issues,
                    run_dir,
                    proximity_graph_path,
                    "PROXIMITY_GRAPH.json embedding metadata is missing `config_hash` for "
                    f"`{graph_hypothesis_id}`; rebuild the graph before relying on config drift checks.",
                    "warning",
                )
            elif expected_proximity_config_hash and metadata.config_hash != expected_proximity_config_hash:
                _record_issue(
                    issues,
                    run_dir,
                    proximity_graph_path,
                    "PROXIMITY_GRAPH.json embedding metadata config hash does not match "
                    f"RESOLVED_RUN_CONFIG.proximity for `{graph_hypothesis_id}`.",
                    "error",
                )
                resume_ready = False
        for source_id, targets in proximity_graph_payload.similarities.items():
            for target_id, score in targets.items():
                reverse_score = proximity_graph_payload.similarities.get(target_id, {}).get(source_id)
                if reverse_score is None or abs(reverse_score - score) > 1e-9:
                    _record_issue(
                        issues,
                        run_dir,
                        proximity_graph_path,
                        "PROXIMITY_GRAPH.json similarity edges must be symmetric; "
                        f"missing or mismatched reverse edge for `{source_id}` and `{target_id}`.",
                        "error",
                    )
                    resume_ready = False
                    break

    proximity_required_candidate_ids = placement_candidate_ids | ranked_challenger_ids
    for candidate_id in sorted(proximity_required_candidate_ids):
        candidate_path = hypothesis_paths_by_id.get(candidate_id, tournaments_root)
        receipt_payload = proximity_receipts_by_hypothesis.get(candidate_id)
        has_graph_embedding = (
            proximity_graph_payload is not None and candidate_id in proximity_graph_payload.embeddings
        )
        if receipt_payload is None:
            _record_issue(
                issues,
                run_dir,
                candidate_path,
                "Placement ranking for hypothesis "
                f"`{candidate_id}` requires a proximity embedding bridge receipt from "
                "`tools.update_hypothesis_proximity(run_dir, hypothesis_id)`.",
                "error",
            )
            resume_ready = False
            continue
        if receipt_payload.graph_updated and not has_graph_embedding:
            _record_issue(
                issues,
                run_dir,
                candidate_path,
                "Placement ranking has a proximity receipt with `graph_updated=true`, but the candidate is absent "
                "from PROXIMITY_GRAPH.json embeddings.",
                "error",
            )
            resume_ready = False
        if receipt_payload.status == "succeeded" and not has_graph_embedding:
            _record_issue(
                issues,
                run_dir,
                candidate_path,
                "Placement ranking has a successful proximity receipt, but the candidate is absent from "
                "PROXIMITY_GRAPH.json embeddings.",
                "error",
            )
            resume_ready = False
        if receipt_payload.status in _PROXIMITY_FALLBACK_STATUSES:
            continue
        if receipt_payload.status != "succeeded":
            _record_issue(
                issues,
                run_dir,
                candidate_path,
                f"Placement ranking has unsupported proximity receipt status `{receipt_payload.status}`.",
                "error",
            )
            resume_ready = False

    if viable_hypothesis_count and not islands_path.exists():
        _record_issue(
            issues,
            run_dir,
            islands_path,
            "Viable hypotheses exist but islands/ISLANDS.json is missing.",
            "error",
        )
        resume_ready = False
    elif viable_hypothesis_count and islands_path.exists():
        viable_hypothesis_island_ids = sorted(
            {
                hypothesis.island_id
                for hypothesis in hypothesis_payloads_by_id.values()
                if hypothesis.is_viable and hypothesis.island_id
            }
        )
        missing_hypothesis_island_ids = sorted(set(viable_hypothesis_island_ids).difference(canonical_island_ids))
        if missing_hypothesis_island_ids:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                "islands/ISLANDS.json is missing canonical island items for viable hypothesis island IDs: "
                + ", ".join(missing_hypothesis_island_ids)
                + ".",
                "error",
            )
            resume_ready = False
        unreferenced_island_ids = sorted(canonical_island_ids.difference(viable_hypothesis_island_ids))
        if unreferenced_island_ids:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                "islands/ISLANDS.json contains island IDs with no viable hypotheses: "
                + ", ".join(unreferenced_island_ids)
                + ".",
                "warning",
            )

    if pipeline_state_payload is not None:
        expected_summary_counts = {
            "hypothesisCount": len(hypothesis_payloads_by_id),
            "viableHypothesisCount": viable_hypothesis_count,
            "tournamentMatchCount": len(tournament_artifact_ids),
            "islandCount": len(island_items_payload) if islands_path.exists() else 0,
        }
        for field_name, expected_count in expected_summary_counts.items():
            actual_count = getattr(pipeline_state_payload, field_name)
            if actual_count != expected_count:
                _record_issue(
                    issues,
                    run_dir,
                    pipeline_state_path,
                    f"PIPELINE_STATE.json `{field_name}` must match the artifact tree count "
                    f"({expected_count}); found {actual_count}.",
                    "error",
                )
                resume_ready = False

    if evolution_state_payload is not None and resolved_config_payload is not None:
        for message in _validate_evolution_resolved_config_alignment(evolution_state_payload, resolved_config_payload):
            _record_issue(issues, run_dir, evolution_state_path, message, "error")
            resume_ready = False
        expected_effective_top_k = min(resolved_config_payload.ranking.tournament_top_k, viable_hypothesis_count)
        if evolution_state_payload.effectiveTopK != expected_effective_top_k:
            _record_issue(
                issues,
                run_dir,
                evolution_state_path,
                "EVOLUTION_STATE.json `effectiveTopK` must equal "
                "`min(RESOLVED_RUN_CONFIG.ranking.tournament_top_k, viable_hypothesis_count)` "
                f"({expected_effective_top_k}); found {evolution_state_payload.effectiveTopK}.",
                "error",
            )
            resume_ready = False
        if (
            pipeline_state_payload is not None
            and len(pipeline_state_payload.topHypothesisIds) > expected_effective_top_k
        ):
            _record_issue(
                issues,
                run_dir,
                pipeline_state_path,
                "PIPELINE_STATE.json cannot list more `topHypothesisIds` than the effective top-k frontier.",
                "error",
            )
            resume_ready = False

    if evolved_hypothesis_count and not evolution_state_path.exists():
        _record_issue(
            issues,
            run_dir,
            evolution_state_path,
            "Evolved hypotheses exist but EVOLUTION_STATE.json is missing.",
            "error",
        )
        resume_ready = False

    strategy_decision_count = _count_non_empty_lines(strategy_decisions_path)
    single_island_round_count = 0
    multi_island_round_count = 0
    selected_single_island_counts: Counter[str] = Counter()
    island_items_by_id: dict[str, dict[str, Any]] = {
        island_id: item
        for item in island_items_payload
        if isinstance((island_id := item.get("id")), str) and island_id.strip()
    }
    strategy_decisions_by_index: dict[int, StrategyDecisionRecordContract] = {}
    strategy_decision_raw_by_index: dict[int, object] = {}
    if evolved_hypothesis_count and strategy_decision_count < evolved_hypothesis_count + 1:
        _record_issue(
            issues,
            run_dir,
            strategy_decisions_path,
            "The strategy decision audit log is shorter than the evolved hypothesis chain and cannot support replay.",
            "error",
        )
        resume_ready = False
    elif strategy_decisions_path.exists():
        for line_number, line in enumerate(strategy_decisions_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            raw_decision_payload: object
            try:
                raw_decision_payload = json.loads(line)
                decision_payload = StrategyDecisionRecordContract.from_payload(raw_decision_payload)
            except (json.JSONDecodeError, ValidationError):
                continue
            if decision_payload.decision_index in strategy_decisions_by_index:
                _record_issue(
                    issues,
                    run_dir,
                    strategy_decisions_path,
                    f"Duplicate strategy decision index `{decision_payload.decision_index}`.",
                    "error",
                )
                resume_ready = False
            else:
                strategy_decisions_by_index[decision_payload.decision_index] = decision_payload
                strategy_decision_raw_by_index[decision_payload.decision_index] = raw_decision_payload
            if (
                decision_payload.current_phase == "Evolution"
                and decision_payload.next_action == "continue_evolution"
                and decision_payload.selected_evolution_strategies
            ):
                selected_parent_ids = decision_payload.signals.get("selected_parent_ids")
                selection_strategy = decision_payload.signals.get("selection_strategy")
                if not isinstance(selected_parent_ids, list) or not selected_parent_ids:
                    _record_issue(
                        issues,
                        run_dir,
                        strategy_decisions_path,
                        f"Evolution strategy decision on line {line_number} is missing selected_parent_ids.",
                        "error",
                    )
                    resume_ready = False
                if not isinstance(selection_strategy, str) or not selection_strategy:
                    _record_issue(
                        issues,
                        run_dir,
                        strategy_decisions_path,
                        f"Evolution strategy decision on line {line_number} is missing selection_strategy.",
                        "error",
                    )
                    resume_ready = False
                elif selection_strategy == "single_island":
                    single_island_round_count += 1
                    incompatible = [
                        strategy
                        for strategy in decision_payload.selected_evolution_strategies
                        if strategy not in _SINGLE_ISLAND_STRATEGIES
                    ]
                    if incompatible:
                        _record_issue(
                            issues,
                            run_dir,
                            strategy_decisions_path,
                            "Single-island evolution decisions may not expose incompatible strategies: "
                            + ", ".join(incompatible),
                            "error",
                        )
                        resume_ready = False
                elif selection_strategy == "multi_island":
                    multi_island_round_count += 1
                    incompatible = [
                        strategy
                        for strategy in decision_payload.selected_evolution_strategies
                        if strategy not in _MULTI_ISLAND_STRATEGIES
                    ]
                    if incompatible:
                        _record_issue(
                            issues,
                            run_dir,
                            strategy_decisions_path,
                            "Multi-island evolution decisions may not expose incompatible strategies: "
                            + ", ".join(incompatible),
                            "error",
                        )
                        resume_ready = False

    consumed_strategy_decision_indices: dict[int, str] = {}
    if evolved_hypothesis_count and not evolution_rounds_path.exists():
        _record_issue(
            issues,
            run_dir,
            evolution_rounds_path,
            "Evolved hypotheses exist but EVOLUTION_ROUNDS.jsonl is missing; replay will rely on existing "
            "strategy-decision inference until the run is migrated.",
            "warning",
        )
    elif evolution_round_records:
        round_records_by_child: dict[str, EvolutionRoundRecordContract] = {}
        previous_round_current_top_k_ids: list[str] | None = None
        previous_round_child_id = ""
        previous_round_record: EvolutionRoundRecordContract | None = None
        record_child_ids = {record.child_hypothesis_id for record in evolution_round_records}
        known_hypothesis_ids_before_round = set(hypothesis_payloads_by_id).difference(record_child_ids)
        for record in evolution_round_records:
            record_context = f"Evolution round record for child `{record.child_hypothesis_id}`"
            if record.selection_strategy == "single_island":
                selected_single_island_counts.update(record.selected_island_ids)
                missing_selected_island_ids = sorted(set(record.selected_island_ids).difference(canonical_island_ids))
                if missing_selected_island_ids:
                    _record_issue(
                        issues,
                        run_dir,
                        islands_path,
                        f"{record_context} selected island IDs are absent from canonical islands/ISLANDS.json: "
                        + ", ".join(missing_selected_island_ids)
                        + ".",
                        "error",
                    )
                    resume_ready = False
            existing_record = round_records_by_child.get(record.child_hypothesis_id)
            if existing_record is not None:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"Duplicate evolution round records for child `{record.child_hypothesis_id}`.",
                    "error",
                )
                resume_ready = False
            else:
                round_records_by_child[record.child_hypothesis_id] = record

            existing_decision_child_id = consumed_strategy_decision_indices.get(record.decision_index)
            if existing_decision_child_id is not None:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} reuses strategy decision index `{record.decision_index}` already consumed by "
                    f"child `{existing_decision_child_id}`; each continue_evolution router decision may produce only "
                    "one completed evolution round receipt.",
                    "error",
                )
                resume_ready = False
            else:
                consumed_strategy_decision_indices[record.decision_index] = record.child_hypothesis_id

            if (
                previous_round_current_top_k_ids is not None
                and record.previous_top_k_ids != previous_round_current_top_k_ids
            ):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} previous_top_k_ids must match the prior round current_top_k_ids from child "
                    f"`{previous_round_child_id}`.",
                    "error",
                )
                resume_ready = False
            previous_round_current_top_k_ids = record.current_top_k_ids
            previous_round_child_id = record.child_hypothesis_id

            decision_payload = strategy_decisions_by_index.get(record.decision_index)
            if decision_payload is None:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} references unknown strategy decision index `{record.decision_index}`.",
                    "error",
                )
                resume_ready = False
            else:
                if (
                    decision_payload.current_phase != "Evolution"
                    or decision_payload.next_action != "continue_evolution"
                ):
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} references a strategy decision that is not a continue_evolution route.",
                        "error",
                    )
                    resume_ready = False
                for message in _validate_continue_evolution_router_signals(
                    decision_payload,
                    strategy_decision_raw_by_index.get(
                        record.decision_index,
                        decision_payload.model_dump(mode="json"),
                    ),
                ):
                    _record_issue(issues, run_dir, evolution_rounds_path, f"{record_context} {message}", "error")
                    resume_ready = False
                expected_hypothesis_count_before_round = len(known_hypothesis_ids_before_round)
                expected_viable_count_before_round = sum(
                    1
                    for hypothesis_id in known_hypothesis_ids_before_round
                    if hypothesis_payloads_by_id[hypothesis_id].is_viable
                )
                signal_hypothesis_count = decision_payload.signals.get("hypothesis_count")
                if (
                    isinstance(signal_hypothesis_count, int)
                    and not isinstance(signal_hypothesis_count, bool)
                    and signal_hypothesis_count != expected_hypothesis_count_before_round
                ):
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} strategy decision signal `hypothesis_count` must equal the number of "
                        "hypotheses available before the child is created "
                        f"({expected_hypothesis_count_before_round}); found {signal_hypothesis_count}.",
                        "error",
                    )
                    resume_ready = False
                signal_viable_count = decision_payload.signals.get("viable_hypothesis_count")
                if (
                    isinstance(signal_viable_count, int)
                    and not isinstance(signal_viable_count, bool)
                    and signal_viable_count != expected_viable_count_before_round
                ):
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} strategy decision signal `viable_hypothesis_count` must equal the number "
                        "of viable hypotheses available before the child is created "
                        f"({expected_viable_count_before_round}); found {signal_viable_count}.",
                        "error",
                    )
                    resume_ready = False
                signal_convergence_count = decision_payload.signals.get("convergence_count")
                if isinstance(signal_convergence_count, int) and not isinstance(signal_convergence_count, bool):
                    if signal_convergence_count != record.convergence_count_before:
                        _record_issue(
                            issues,
                            run_dir,
                            evolution_rounds_path,
                            f"{record_context} strategy decision signal `convergence_count` must match "
                            f"`convergence_count_before` ({record.convergence_count_before}); found "
                            f"{signal_convergence_count}.",
                            "error",
                        )
                        resume_ready = False
                    if (
                        previous_round_record is not None
                        and signal_convergence_count != previous_round_record.convergence_count_after
                    ):
                        _record_issue(
                            issues,
                            run_dir,
                            evolution_rounds_path,
                            f"{record_context} strategy decision signal `convergence_count` must match the prior "
                            f"round convergence_count_after ({previous_round_record.convergence_count_after}); "
                            f"found {signal_convergence_count}.",
                            "error",
                        )
                        resume_ready = False
                signal_entered_top_k = decision_payload.signals.get("entered_top_k_last_round")
                if (
                    signal_entered_top_k is True
                    and isinstance(signal_convergence_count, int)
                    and not isinstance(signal_convergence_count, bool)
                    and signal_convergence_count != 0
                ):
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} strategy decision signal `entered_top_k_last_round=true` is inconsistent "
                        f"with positive `convergence_count` ({signal_convergence_count}).",
                        "error",
                    )
                    resume_ready = False
                if previous_round_record is not None and signal_entered_top_k != previous_round_record.entered_top_k:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} strategy decision signal `entered_top_k_last_round` must match the prior "
                        f"round entered_top_k result ({previous_round_record.entered_top_k}).",
                        "error",
                    )
                    resume_ready = False
                signal_top_hypothesis_ids = decision_payload.signals.get("top_hypothesis_ids")
                if (
                    isinstance(signal_top_hypothesis_ids, list)
                    and all(isinstance(item, str) for item in signal_top_hypothesis_ids)
                    and signal_top_hypothesis_ids != record.previous_top_k_ids
                ):
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} strategy decision signal `top_hypothesis_ids` must match "
                        "`previous_top_k_ids` from the consumed round receipt.",
                        "error",
                    )
                    resume_ready = False
                selected_parent_ids = decision_payload.signals.get("selected_parent_ids")
                if isinstance(selected_parent_ids, list) and selected_parent_ids != record.parent_hypothesis_ids:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} parent IDs do not match the referenced strategy decision.",
                        "error",
                    )
                    resume_ready = False
                if isinstance(selected_parent_ids, list) and all(
                    isinstance(parent_id, str) for parent_id in selected_parent_ids
                ):
                    unavailable_parent_ids = sorted(
                        parent_id
                        for parent_id in selected_parent_ids
                        if parent_id not in known_hypothesis_ids_before_round
                    )
                    nonviable_parent_ids = sorted(
                        parent_id
                        for parent_id in selected_parent_ids
                        if parent_id in known_hypothesis_ids_before_round
                        and not hypothesis_payloads_by_id[parent_id].is_viable
                    )
                    if unavailable_parent_ids:
                        _record_issue(
                            issues,
                            run_dir,
                            evolution_rounds_path,
                            f"{record_context} strategy decision selected parents that were not available before "
                            "the child was created: " + ", ".join(unavailable_parent_ids),
                            "error",
                        )
                        resume_ready = False
                    if nonviable_parent_ids:
                        _record_issue(
                            issues,
                            run_dir,
                            evolution_rounds_path,
                            f"{record_context} strategy decision selected non-viable parent hypotheses: "
                            + ", ".join(nonviable_parent_ids),
                            "error",
                        )
                        resume_ready = False
                selected_island_ids = decision_payload.signals.get("selected_island_ids")
                if isinstance(selected_island_ids, list) and selected_island_ids != record.selected_island_ids:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} selected island IDs do not match the referenced strategy decision.",
                        "error",
                    )
                    resume_ready = False
                if (
                    isinstance(selected_parent_ids, list)
                    and all(isinstance(parent_id, str) for parent_id in selected_parent_ids)
                    and isinstance(selected_island_ids, list)
                    and all(isinstance(island_id, str) for island_id in selected_island_ids)
                ):
                    expected_parent_island_ids = [
                        hypothesis_payloads_by_id[parent_id].island_id
                        for parent_id in selected_parent_ids
                        if parent_id in hypothesis_payloads_by_id
                    ]
                    if selected_island_ids != expected_parent_island_ids:
                        _record_issue(
                            issues,
                            run_dir,
                            evolution_rounds_path,
                            f"{record_context} strategy decision selected island IDs must match the selected "
                            "parents' persisted island IDs.",
                            "error",
                        )
                        resume_ready = False
                selection_strategy = decision_payload.signals.get("selection_strategy")
                if isinstance(selection_strategy, str) and selection_strategy != record.selection_strategy:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} selection strategy does not match the referenced strategy decision.",
                        "error",
                    )
                    resume_ready = False
                if record.chosen_evolution_strategy not in decision_payload.selected_evolution_strategies:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"{record_context} chosen strategy is not present in the referenced strategy decision bundle.",
                        "error",
                    )
                    resume_ready = False

            child_payload = hypothesis_payloads_by_id.get(record.child_hypothesis_id)
            if child_payload is None:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} references an unknown child hypothesis.",
                    "error",
                )
                resume_ready = False
                continue
            if not child_payload.parent_ids:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} references a hypothesis that is not marked as evolved.",
                    "error",
                )
                resume_ready = False
            if child_payload.parent_ids != record.parent_hypothesis_ids:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} parent IDs do not match the child hypothesis artifact.",
                    "error",
                )
                resume_ready = False
            if child_payload.origin.strategy != record.chosen_evolution_strategy:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} chosen strategy does not match the child hypothesis origin strategy.",
                    "error",
                )
                resume_ready = False
            if record.child_island_id and child_payload.island_id != record.child_island_id:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} child island ID does not match the child hypothesis artifact.",
                    "error",
                )
                resume_ready = False
            if record.review_passed is not None and child_payload.review.initial_review.passed != record.review_passed:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} review_passed does not match the child hypothesis review artifact.",
                    "error",
                )
                resume_ready = False
            receipt_payload = proximity_receipts_by_hypothesis.get(record.child_hypothesis_id)
            if record.proximity_receipt_status and receipt_payload is None:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} records proximity_receipt_status `{record.proximity_receipt_status}`, but "
                    "the matching per-child proximity receipt artifact is missing.",
                    "error",
                )
                resume_ready = False
            if (
                record.proximity_receipt_status
                and receipt_payload is not None
                and receipt_payload.status != record.proximity_receipt_status
            ):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} proximity receipt status does not match the persisted receipt.",
                    "error",
                )
                resume_ready = False
            for match_ref_field in ("placement_match_ids", "ranked_match_ids"):
                duplicate_match_ids = _duplicate_items(getattr(record, match_ref_field))
                if duplicate_match_ids:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_rounds_path,
                        f"EVOLUTION_ROUNDS.jsonl `{match_ref_field}` must not contain duplicates: "
                        + ", ".join(duplicate_match_ids)
                        + ".",
                        "error",
                    )
                    resume_ready = False
            invalid_placement_match_ids = _invalid_round_match_owner_ids(
                record.placement_match_ids,
                child_hypothesis_id=record.child_hypothesis_id,
                strategy="placement_tournament",
                tournament_payloads_by_id=tournament_payloads_by_id,
            )
            if invalid_placement_match_ids:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} placement match IDs must be child-owned placement_tournament matches: "
                    + ", ".join(invalid_placement_match_ids)
                    + ".",
                    "error",
                )
                resume_ready = False
            invalid_ranked_match_ids = _invalid_round_match_owner_ids(
                record.ranked_match_ids,
                child_hypothesis_id=record.child_hypothesis_id,
                strategy="ranked_tournament",
                tournament_payloads_by_id=tournament_payloads_by_id,
            )
            if invalid_ranked_match_ids:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} ranked match IDs must be child-owned ranked_tournament matches: "
                    + ", ".join(invalid_ranked_match_ids)
                    + ".",
                    "error",
                )
                resume_ready = False
            expected_placement_match_ids = _candidate_owned_match_ids(
                child_payload.placement_match_ids,
                child_hypothesis_id=record.child_hypothesis_id,
                strategy="placement_tournament",
                tournament_payloads_by_id=tournament_payloads_by_id,
            )
            if set(record.placement_match_ids) != set(expected_placement_match_ids):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} placement match IDs must match child-owned placement_tournament refs from "
                    "the child hypothesis artifact.",
                    "error",
                )
                resume_ready = False
            expected_ranked_match_ids = _candidate_owned_match_ids(
                child_payload.ranked_match_ids,
                child_hypothesis_id=record.child_hypothesis_id,
                strategy="ranked_tournament",
                tournament_payloads_by_id=tournament_payloads_by_id,
            )
            if set(record.ranked_match_ids) != set(expected_ranked_match_ids):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} ranked match IDs must match child-owned ranked_tournament refs from the child "
                    "hypothesis artifact.",
                    "error",
                )
                resume_ready = False
            if (
                child_payload.is_viable
                and record.review_passed is not False
                and record.child_hypothesis_id in record.current_top_k_ids
                and not child_payload.placement_match_ids
            ):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} entered or remained in the top-k frontier without placement tournament "
                    "provenance; completed evolution rounds must persist ranking artifacts before updating top-k "
                    "state.",
                    "error",
                )
                resume_ready = False
            if (
                previous_round_record is not None
                and record.convergence_count_before != previous_round_record.convergence_count_after
            ):
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} convergence_count_before must match the prior round "
                    f"convergence_count_after ({previous_round_record.convergence_count_after}).",
                    "error",
                )
                resume_ready = False
            expected_entered_top_k = (
                record.child_hypothesis_id in record.current_top_k_ids
                and record.child_hypothesis_id not in record.previous_top_k_ids
            )
            if record.entered_top_k != expected_entered_top_k:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} entered_top_k does not match previous/current top-k IDs.",
                    "error",
                )
                resume_ready = False
            expected_convergence_count = 0 if record.entered_top_k else record.convergence_count_before + 1
            if record.convergence_count_after != expected_convergence_count:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_rounds_path,
                    f"{record_context} convergence_count_after does not match the canonical convergence rule.",
                    "error",
                )
                resume_ready = False

            known_hypothesis_ids_before_round.add(record.child_hypothesis_id)
            previous_round_record = record

        missing_round_child_ids = sorted(evolved_hypothesis_ids.difference(round_records_by_child))
        if missing_round_child_ids:
            _record_issue(
                issues,
                run_dir,
                evolution_rounds_path,
                "EVOLUTION_ROUNDS.jsonl is missing completed round receipts for evolved hypotheses: "
                + ", ".join(missing_round_child_ids),
                "error",
            )
            resume_ready = False

        if previous_round_record is not None and evolution_state_payload is not None:
            if evolution_state_payload.iterationCount < previous_round_record.round_index:
                _record_issue(
                    issues,
                    run_dir,
                    evolution_state_path,
                    "EVOLUTION_STATE.json `iterationCount` is stale relative to the latest completed "
                    f"EVOLUTION_ROUNDS.jsonl record ({evolution_state_payload.iterationCount}/"
                    f"{previous_round_record.round_index}).",
                    "error",
                )
                resume_ready = False
            else:
                if evolution_state_payload.convergenceCount != previous_round_record.convergence_count_after:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_state_path,
                        "EVOLUTION_STATE.json `convergenceCount` must match the latest completed "
                        "EVOLUTION_ROUNDS.jsonl record.",
                        "error",
                    )
                    resume_ready = False
                if evolution_state_payload.enteredTopKLastRound != previous_round_record.entered_top_k:
                    _record_issue(
                        issues,
                        run_dir,
                        evolution_state_path,
                        "EVOLUTION_STATE.json `enteredTopKLastRound` must match the latest completed "
                        "EVOLUTION_ROUNDS.jsonl record.",
                        "error",
                    )
                    resume_ready = False

        if (
            previous_round_record is not None
            and strategy_plan_payload is not None
            and strategy_plan_payload.next_action == "continue_evolution"
        ):
            expected_strategy_signals = {
                "hypothesis_count": len(hypothesis_payloads_by_id),
                "viable_hypothesis_count": viable_hypothesis_count,
                "convergence_count": (
                    evolution_state_payload.convergenceCount
                    if evolution_state_payload is not None
                    else previous_round_record.convergence_count_after
                ),
                "entered_top_k_last_round": (
                    evolution_state_payload.enteredTopKLastRound
                    if evolution_state_payload is not None
                    else previous_round_record.entered_top_k
                ),
            }
            for signal_name, expected_signal_value in expected_strategy_signals.items():
                actual_signal_value = strategy_plan_payload.signals.get(signal_name)
                if actual_signal_value is not None and actual_signal_value != expected_signal_value:
                    _record_issue(
                        issues,
                        run_dir,
                        strategy_plan_path,
                        f"STRATEGY_PLAN.json `signals.{signal_name}` is stale relative to current artifacts; "
                        f"expected `{expected_signal_value}`, found `{actual_signal_value}`. Refresh routing "
                        "with `python -m tools.policy.plan_strategy <run_dir>` before continuing evolution.",
                        "error",
                    )
                    resume_ready = False

    for message in _validate_unique_open_continue_evolution_decisions(
        list(strategy_decisions_by_index.values()),
        set(consumed_strategy_decision_indices),
    ):
        _record_issue(issues, run_dir, strategy_decisions_path, message, "error")
        resume_ready = False

    # A routed selection may remain open at a budget checkpoint. Only completed
    # round receipts require island reward/visit writeback.
    if (
        selected_single_island_counts or (evolved_hypothesis_count and single_island_round_count)
    ) and island_items_payload:
        all_visit_counts_zero = all(int(item.get("visit_count", 0)) == 0 for item in island_items_payload)
        all_decayed_visits_zero = all(float(item.get("decayed_visits") or 0.0) == 0.0 for item in island_items_payload)
        if all_visit_counts_zero:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                "Single-island evolution rounds were recorded, but every island still has `visit_count = 0`.",
                "error",
            )
            resume_ready = False
        if all_decayed_visits_zero:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                "Single-island evolution rounds were recorded, but every island still has `decayed_visits = 0`.",
                "error",
            )
            resume_ready = False

    for island_id, selected_count in sorted(selected_single_island_counts.items()):
        item = island_items_by_id.get(island_id)
        if item is None:
            continue
        visit_count = item.get("visit_count", 0)
        decayed_visits = item.get("decayed_visits", 0.0)
        if isinstance(visit_count, int) and not isinstance(visit_count, bool):
            if visit_count == 0:
                _record_issue(
                    issues,
                    run_dir,
                    islands_path,
                    f"Island `{island_id}` was selected by completed single-island evolution rounds but still has "
                    "`visit_count = 0`.",
                    "error",
                )
                resume_ready = False
            elif visit_count < selected_count:
                _record_issue(
                    issues,
                    run_dir,
                    islands_path,
                    f"Island `{island_id}` was selected by completed single-island evolution rounds "
                    f"`{selected_count}` times but has `visit_count = {visit_count}`.",
                    "error",
                )
                resume_ready = False
        if _is_number(decayed_visits) and float(decayed_visits) == 0.0:
            _record_issue(
                issues,
                run_dir,
                islands_path,
                f"Island `{island_id}` was selected by completed single-island evolution rounds but still has "
                "`decayed_visits = 0`.",
                "error",
            )
            resume_ready = False

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    return HostAgentValidationSummary(
        status="invalid" if error_count else "valid",
        checkedArtifacts=checked_artifacts,
        issues=issues,
        errorCount=error_count,
        warningCount=warning_count,
        resumeReady=resume_ready and error_count == 0,
        requestedSkill=requested_skill,
    )


def validate_resume_state(run_dir: Path) -> HostAgentValidationSummary:
    """Validate only the resume-critical artifacts for one run."""
    return validate_run_artifacts(run_dir, resume=True)


def _write_summary_json(path: Path, summary: HostAgentValidationSummary) -> None:
    """Write one validation summary JSON artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary.model_dump_json(indent=2) + "\n", encoding="utf-8")


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the validator CLI and return a process exit code."""
    args = _parse_args(argv)
    run_dir = args.run_dir.resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        return 2

    summary = validate_run_artifacts(
        run_dir,
        resume=bool(args.resume),
        requested_skill=args.skill,
    )
    if args.json_out is not None:
        _write_summary_json(args.json_out.resolve(), summary)

    print(summary.model_dump_json(indent=2))
    return 0 if summary.status == "valid" else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.validation.contract_validation`."""
    try:
        return run_cli(argv)
    except Exception as exc:
        print(f"Validator execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
