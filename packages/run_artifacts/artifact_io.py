"""Artifact writers for run-local JSON, Markdown, and dashboard snapshot outputs."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from packages.agent_contracts import (
    CompletionDecisionContract,
    CoScientistStateContract,
    EvolutionRoundRecordContract,
    EvolutionStateContract,
    PolicyDecisionContract,
    ResolvedRunConfigContract,
    RunPolicyContract,
    StartRequestContract,
    StrategyDecisionRecordContract,
    StrategyPlanContract,
)
from packages.agent_support import format_hypothesis_with_review, format_research_plan_context
from packages.dashboard_contracts.dashboard import DashboardRoutingArtifacts, InsightSection
from packages.dashboard_contracts.snapshot_projection import build_dashboard_snapshot
from packages.run_artifacts.pipeline_state import build_current_stage_payload, build_pipeline_state_payload


if TYPE_CHECKING:
    from packages.agent_contracts import CoScientistStateContract as CoScientistState
    from packages.agent_contracts import HypothesisContract as Hypothesis
    from packages.agent_contracts import ProximityGraphContract as ProximityGraph
    from packages.agent_contracts import ResearchPlanContract as ResearchPlan


__all__ = ["ArtifactStore"]


_ITERATION_STRATEGY_TITLE = "Iteration Strategy"
_STOP_REASON_SUMMARIES = {
    "convergence_reached": "The run stopped because the convergence threshold was reached.",
    "max_iterations_reached": "The run stopped because it hit the user-selected capped iteration limit.",
    "safety_iteration_limit_reached": "The run stopped because it hit the internal safety iteration ceiling.",
    "candidate_quality_plateau": "The run stopped because candidate quality plateaued.",
    "no_viable_candidates": "The run stopped because no viable candidates remained.",
    "operator_stop": "The run stopped because the operator requested a stop.",
    "validation_blocked": "The run stopped because validation blocked further execution.",
    "budget_exhausted": "The run stopped because the configured budget guard was exhausted.",
    "manual_override_complete": "The run stopped because a manual override marked it complete.",
}
_OVERVIEW_ELIGIBLE_STOP_REASONS = {
    "convergence_reached",
    "max_iterations_reached",
    "safety_iteration_limit_reached",
    "no_viable_candidates",
}
_BLOCKED_STOP_REASONS = {
    "budget_exhausted",
    "operator_stop",
    "validation_blocked",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in value]
    return value


def _read_strategy_decision_indices(path: Path) -> set[int]:
    if not path.exists():
        return set()
    indices: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
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
            indices.add(decision_index)
    return indices


def _format_iteration_band(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("_", "-")


def _has_initialized_island_metrics(state: CoScientistState) -> bool:
    return any(
        island.visit_count > 0 or island.decayed_visits > 0 or island.decayed_reward > 0
        for island in state.islands.values()
    )


def _has_convergence_signal_conflict(evolution_state: EvolutionStateContract | None) -> bool:
    return (
        evolution_state is not None
        and evolution_state.enteredTopKLastRound is True
        and evolution_state.convergenceCount > 0
    )


def _normalize_evolution_status(status: str, *, stop_reason: str, overview_eligible: bool) -> str:
    if not stop_reason or status in {"blocked", "completed"}:
        return status
    if stop_reason in _BLOCKED_STOP_REASONS:
        return "blocked"
    if overview_eligible:
        return "completed"
    return "completed"


def _replace_iteration_strategy_section(
    sections: list[InsightSection],
    section: InsightSection,
) -> list[InsightSection]:
    retained = [item for item in sections if item.title != _ITERATION_STRATEGY_TITLE]
    retained.append(section)
    return retained


def _build_iteration_strategy_section(
    routing: DashboardRoutingArtifacts,
    *,
    state: CoScientistState | None = None,
    evolution_state: EvolutionStateContract | None = None,
    completion_decision: CompletionDecisionContract | None = None,
) -> InsightSection:
    policy = routing.policy_decision.policy if routing.policy_decision is not None else None
    convergence = routing.resolved_config.convergence if routing.resolved_config is not None else None

    items: list[str] = []
    badge = "Pending"
    latest_selection_strategy = (
        routing.latest_strategy_decision.signals.get("selection_strategy")
        if routing.latest_strategy_decision is not None
        else None
    )
    evolved_hypothesis_count = (
        len([hypothesis for hypothesis in state.hypotheses.values() if hypothesis.parent_ids])
        if state is not None
        else 0
    )

    if policy is not None:
        items.append(f"Budget profile is `{policy.budget_profile}` and controls per-round intensity.")
        if policy.iteration_policy == "capped":
            band_label = _format_iteration_band(policy.iteration_band)
            if band_label:
                items.append(f"Iteration policy is `capped` with user-selected band `{band_label}`.")
            else:
                items.append("Iteration policy is `capped`.")
        else:
            items.append(
                "Iteration policy is `completion_driven`, so semantic completion signals decide when "
                "the run should stop."
            )
        items.append(f"Stop policy is `{policy.stop_policy}`.")
        items.append(f"Human checkpoint policy is `{policy.human_checkpoint}`.")
        badge = "Configured"

    if convergence is not None:
        if convergence.max_iterations > 0:
            items.append(
                f"Resolved hard cap is `{convergence.max_iterations}` iterations from "
                f"`{convergence.iteration_cap_source}`."
            )
        else:
            items.append(
                "Resolved hard cap is disabled for the user-facing run; semantic completion is guarded "
                "by an internal safety ceiling."
            )
        items.append(f"Safety iteration ceiling is `{convergence.safety_max_iterations}`.")
        badge = "Configured"

    if evolution_state is not None:
        items.append(
            "Current progress is "
            f"`{evolution_state.iterationCount}` iterations with convergence "
            f"`{evolution_state.convergenceCount}/{evolution_state.convergenceThreshold}`."
        )
        if isinstance(latest_selection_strategy, str) and latest_selection_strategy:
            items.append(f"Latest routing mode is `{latest_selection_strategy}`.")
        if evolution_state.lastSelectedIsland:
            items.append(f"Last selected island was `{evolution_state.lastSelectedIsland}`.")
        if evolution_state.lastSelectedStrategy:
            items.append(f"Last concrete evolution strategy was `{evolution_state.lastSelectedStrategy}`.")
        if evolution_state.stopReason:
            items.append(
                _STOP_REASON_SUMMARIES.get(
                    evolution_state.stopReason,
                    f"The run recorded stop reason `{evolution_state.stopReason}`.",
                )
            )
            badge = "Stopped"
        elif evolution_state.status == "running":
            items.append("The run is still active and has not recorded a stop reason yet.")
            badge = "Running"

    if completion_decision is not None and completion_decision.decision != "continue_evolution":
        items.append(f"Current completion action is `{completion_decision.decision}`.")
        if completion_decision.decision == "inspect_state":
            items.append(
                "Validation or completion inspection blocked autonomous continuation. Resolve the reported "
                "artifact inconsistency before resuming."
            )
        if badge == "Pending":
            badge = "Configured"

    if state is not None and evolved_hypothesis_count > 0 and not _has_initialized_island_metrics(state):
        items.append(
            f"**Warning:** island metrics remain uninitialized even though `{evolved_hypothesis_count}` "
            "evolved hypotheses exist. UCB selection and stagnation-driven multi-island routing may be "
            "unreliable for this run."
        )
        badge = "Warning"

    if _has_convergence_signal_conflict(evolution_state):
        items.append(
            "**Warning:** convergence signals are inconsistent because `enteredTopKLastRound` is `true` "
            "while `convergenceCount` remains above `0`."
        )
        badge = "Warning"

    if not items:
        items.append("No iteration strategy summary available yet.")

    return InsightSection(
        title=_ITERATION_STRATEGY_TITLE,
        badge=badge,
        icon="brain",
        items=items,
    )


class ArtifactStore:
    """Manage run-local canonical artifact trees."""

    def __init__(self, run_dir: Path, top_k_limit: int = 10) -> None:
        """Initialize the store for one run directory."""
        self.run_dir = run_dir.resolve()
        self.top_k_limit = top_k_limit
        self.runs_dir = self.run_dir.parent

    def ensure_layout(self) -> None:
        """Create the minimum stable artifact directory tree."""
        for relative_path in (
            "state",
            "research_plan",
            "hypotheses",
            "tournaments",
            "islands",
            "meta",
            "dashboard",
            "traces",
        ):
            (self.run_dir / relative_path).mkdir(parents=True, exist_ok=True)
        (self.runs_dir / "_dashboard").mkdir(parents=True, exist_ok=True)

    def bootstrap(self) -> None:
        """Initialize manifest, stage state, and global dashboard runtime placeholders."""
        self.ensure_layout()
        self._ensure_manifest()
        self._ensure_dashboard_runtime_placeholder()
        self.write_pipeline_state(
            CoScientistStateContract(),
            mode="host-agent",
            status="not_started",
            current_phase="Bootstrap",
            current_skill="",
            stage_trail=[],
        )
        self.write_current_stage("Bootstrap", [])

    def prepare_resume_bootstrap(self) -> None:
        """Ensure resume-safe filesystem prerequisites without resetting stage state."""
        self.ensure_layout()
        self._ensure_manifest()
        self._ensure_dashboard_runtime_placeholder()

    def append_manifest_entry(self, message: str) -> None:
        """Append a timestamped entry to the run manifest."""
        self._ensure_manifest()
        timestamp = _now_iso()
        with (self.run_dir / "MANIFEST.md").open("a", encoding="utf-8") as handle:
            handle.write(f"- `{timestamp}` {message}\n")

    def write_current_stage(self, stage: str, stage_trail: list[str]) -> None:
        """Write the current stage artifact."""
        self.write_json(
            self.run_dir / "state" / "CURRENT_STAGE.json",
            build_current_stage_payload(self.run_dir.name, stage, stage_trail, _now_iso()),
        )

    def write_pipeline_state(
        self,
        state: CoScientistState,
        *,
        mode: str | None = None,
        status: str | None = None,
        current_phase: str | None = None,
        current_skill: str | None = None,
        completed_skills: list[str] | None = None,
        failed_skill: str | None = None,
        resume_inputs: dict[str, Any] | None = None,
        stage_trail: list[str] | None = None,
    ) -> None:
        """Write a run-level pipeline state summary and execution metadata."""
        existing = self.read_pipeline_state() or {}
        updated_at = _now_iso()
        payload = build_pipeline_state_payload(
            self.run_dir.name,
            updated_at,
            state,
            top_k_limit=self.top_k_limit,
            existing=existing if isinstance(existing, dict) else {},
            mode=mode,
            status=status,
            current_phase=current_phase,
            current_skill=current_skill,
            completed_skills=completed_skills,
            failed_skill=failed_skill,
            resume_inputs=resume_inputs,
            stage_trail=stage_trail,
        )
        self.write_json(
            self.run_dir / "state" / "PIPELINE_STATE.json",
            payload,
        )
        if current_phase is not None or current_skill is not None or stage_trail is not None:
            self.write_json(
                self.run_dir / "state" / "CURRENT_STAGE.json",
                build_current_stage_payload(
                    self.run_dir.name,
                    str(payload.get("currentPhase", "")),
                    payload.get("stageTrail", []),
                    updated_at,
                ),
            )

    def write_evolution_state(
        self,
        state: CoScientistState,
        *,
        convergence_threshold: int,
        max_iterations: int,
        safety_max_iterations: int = 0,
        effective_top_k: int,
        status: str,
        last_selected_island: str = "",
        last_selected_strategy: str = "",
        entered_top_k_last_round: bool | None = None,
        stop_policy: str = "",
        iteration_policy: str = "",
        iteration_band: str = "",
        safety_limit_hit: bool = False,
        stop_reason: str = "",
        overview_eligible: bool = False,
    ) -> None:
        """Write the evolution loop state artifact."""
        resolved_config_payload = self.read_resolved_run_config()
        resolved_safety_max_iterations: int | None = None
        if isinstance(resolved_config_payload, dict):
            resolved_safety_max_iterations = ResolvedRunConfigContract.from_payload(
                resolved_config_payload
            ).convergence.safety_max_iterations
            if safety_max_iterations == 0:
                safety_max_iterations = resolved_safety_max_iterations
            elif safety_max_iterations != resolved_safety_max_iterations:
                raise ValueError(
                    "Cannot persist EVOLUTION_STATE.json with `safetyMaxIterations` that differs from "
                    "RESOLVED_RUN_CONFIG.convergence.safety_max_iterations."
                )
        if state.iteration_count > 0 and entered_top_k_last_round is None:
            raise ValueError(
                "Cannot persist evolution iteration state without `enteredTopKLastRound`; use "
                "`tools.evaluate_convergence(...)` and pass the returned top-k entry result."
            )
        if entered_top_k_last_round is True and state.convergence_count > 0:
            raise ValueError("Cannot persist `enteredTopKLastRound=true` while `convergenceCount` remains above 0.")
        if stop_reason == "convergence_reached" and state.convergence_count < convergence_threshold:
            raise ValueError("Cannot persist `convergence_reached` before the stored convergence threshold is met.")
        if stop_reason == "max_iterations_reached" and (
            iteration_policy == "completion_driven" or max_iterations <= 0
        ):
            raise ValueError(
                "Completion-driven runs must not persist `max_iterations_reached`; use "
                "`safety_iteration_limit_reached` for the internal ceiling."
            )
        if stop_reason == "safety_iteration_limit_reached":
            effective_safety_max_iterations = (
                resolved_safety_max_iterations if resolved_safety_max_iterations is not None else safety_max_iterations
            )
            if effective_safety_max_iterations <= 0:
                raise ValueError("Cannot persist `safety_iteration_limit_reached` without a safety ceiling.")
            if state.iteration_count < effective_safety_max_iterations:
                raise ValueError(
                    "Cannot persist `safety_iteration_limit_reached` before the resolved safety ceiling is met."
                )
            if not safety_limit_hit:
                raise ValueError("Cannot persist `safety_iteration_limit_reached` with `safetyLimitHit=false`.")

        viable_hypotheses = [hypothesis for hypothesis in state.hypotheses.values() if hypothesis.is_viable]
        normalized_effective_top_k = max(0, min(effective_top_k, self.top_k_limit, len(viable_hypotheses)))
        normalized_iteration_band = iteration_band if iteration_policy == "capped" else ""
        normalized_overview_eligible = overview_eligible or stop_reason in _OVERVIEW_ELIGIBLE_STOP_REASONS
        normalized_status = _normalize_evolution_status(
            status,
            stop_reason=stop_reason,
            overview_eligible=normalized_overview_eligible,
        )
        top_hypotheses = sorted(
            viable_hypotheses,
            key=lambda item: item.elo_rating,
            reverse=True,
        )[:normalized_effective_top_k]
        self.write_json(
            self.run_dir / "state" / "EVOLUTION_STATE.json",
            {
                "status": normalized_status,
                "iterationCount": state.iteration_count,
                "convergenceCount": state.convergence_count,
                "convergenceThreshold": convergence_threshold,
                "maxIterations": max_iterations,
                "safetyMaxIterations": safety_max_iterations,
                "effectiveTopK": normalized_effective_top_k,
                "lastSelectedIsland": last_selected_island,
                "lastSelectedStrategy": last_selected_strategy,
                "enteredTopKLastRound": entered_top_k_last_round,
                "stopPolicy": stop_policy,
                "iterationPolicy": iteration_policy,
                "iterationBand": normalized_iteration_band,
                "safetyLimitHit": safety_limit_hit,
                "stopReason": stop_reason,
                "overviewEligible": normalized_overview_eligible,
                "topHypothesisIds": [hypothesis.id for hypothesis in top_hypotheses],
                "updatedAt": _now_iso(),
            },
        )

    def write_completion_decision(
        self,
        *,
        decision: str,
        verifier_recommendation: str,
        requested_skill: str,
        override: bool,
        rationale: list[str] | None = None,
    ) -> CompletionDecisionContract:
        """Write the completion decision artifact."""
        contract = CompletionDecisionContract(
            decision=decision,
            verifierRecommendation=verifier_recommendation,
            override=override,
            rationale=rationale or [],
            requestedSkill=requested_skill,
        )
        self.write_json(self.run_dir / "state" / "COMPLETION_DECISION.json", contract)
        return contract

    def write_run_policy(self, policy: RunPolicyContract) -> None:
        """Write the canonical run policy artifact."""
        self.write_yaml(self.run_dir / "RUN_POLICY.yaml", policy.model_dump(mode="json"))

    def write_start_request(self, request: StartRequestContract) -> StartRequestContract:
        """Write the canonical start request artifact."""
        self.write_json(self.run_dir / "state" / "START_REQUEST.json", request)
        return request

    def write_policy_decision(self, decision: PolicyDecisionContract) -> PolicyDecisionContract:
        """Write the policy decision artifact."""
        self.write_json(self.run_dir / "state" / "POLICY_DECISION.json", decision)
        return decision

    def write_resolved_run_config(self, resolved_config: ResolvedRunConfigContract) -> ResolvedRunConfigContract:
        """Write the resolved numeric run configuration artifact."""
        self.write_json(self.run_dir / "state" / "RESOLVED_RUN_CONFIG.json", resolved_config)
        return resolved_config

    def write_strategy_plan(self, plan: StrategyPlanContract) -> StrategyPlanContract:
        """Write the current strategy plan artifact."""
        self.write_json(self.run_dir / "state" / "STRATEGY_PLAN.json", plan)
        return plan

    def append_strategy_decision(self, decision: StrategyDecisionRecordContract) -> StrategyDecisionRecordContract:
        """Append one strategy decision record to the audit log."""
        path = self.run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        if decision.decision_index in _read_strategy_decision_indices(path):
            raise ValueError(f"Duplicate strategy decision index `{decision.decision_index}`.")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_jsonable(decision), ensure_ascii=False, sort_keys=True) + "\n")
        return decision

    def append_evolution_round_record(
        self,
        record: EvolutionRoundRecordContract,
    ) -> EvolutionRoundRecordContract:
        """Append one completed evolution round replay record."""
        path = self.run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_jsonable(record), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_evolution_round_records(self) -> list[EvolutionRoundRecordContract]:
        """Read append-only evolution round replay records."""
        path = self.run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
        return EvolutionRoundRecordContract.from_jsonl_file(path)

    def write_research_plan(self, plan: ResearchPlan) -> None:
        """Write research plan JSON and companion Markdown."""
        plan_dir = self.run_dir / "research_plan"
        self.write_json(plan_dir / "RESEARCH_PLAN.json", plan)
        rendered_context = format_research_plan_context(plan)
        markdown = "\n".join(
            [
                "# Research Plan",
                "",
                f"## Goal\n\n{getattr(plan, 'research_goal', '') or '(empty)'}",
                "",
                f"## Preferences\n\n{rendered_context['preferences']}",
                "",
                f"## Constraints\n\n{rendered_context['constraints']}",
                "",
                f"## Status\n\n`{getattr(plan, 'status', '')}`",
                "",
            ]
        )
        self.write_markdown(plan_dir / "RESEARCH_PLAN.md", markdown)

    def write_hypothesis(self, hypothesis: Hypothesis, *, write_review_stage_files: bool = True) -> None:
        """Write a hypothesis artifact bundle, optionally including standalone review stage files."""
        hypothesis_dir = self.run_dir / "hypotheses" / hypothesis.id
        review_dir = hypothesis_dir / "REVIEW"
        hypothesis_dir.mkdir(parents=True, exist_ok=True)
        review_dir.mkdir(parents=True, exist_ok=True)

        self.write_json(hypothesis_dir / "HYPOTHESIS.json", hypothesis)
        self.write_markdown(
            hypothesis_dir / "HYPOTHESIS.md", format_hypothesis_with_review(hypothesis, heading_level=1)
        )
        self.write_json(hypothesis_dir / "ORIGIN.json", hypothesis.origin)

        if write_review_stage_files:
            self.write_json(review_dir / "INITIAL_REVIEW.json", hypothesis.review.initial_review)
            self.write_json(review_dir / "FULL_REVIEW.json", hypothesis.review.full_review)
            self.write_json(review_dir / "DEEP_VERIFICATION.json", hypothesis.review.deep_verification_review)
            self.write_json(review_dir / "OBSERVATION_REVIEW.json", hypothesis.review.observation_review)
            self.write_json(review_dir / "SIMULATION_REVIEW.json", hypothesis.review.simulation_review)
            self.write_json(review_dir / "REVIEW_SUMMARY.json", hypothesis.review.review_summary)

    def write_tournaments(self, state: CoScientistState) -> None:
        """Write per-match tournament artifacts."""
        tournaments_dir = self.run_dir / "tournaments"
        tournaments_dir.mkdir(parents=True, exist_ok=True)
        for match in state.tournament_matches.values():
            self.write_json(tournaments_dir / f"{match.id}.json", match)

    def write_proximity_graph(self, graph: ProximityGraph) -> None:
        """Write the proximity graph artifact."""
        self.write_json(self.run_dir / "state" / "PROXIMITY_GRAPH.json", graph)

    def write_islands(self, state: CoScientistState) -> None:
        """Write island summary artifact."""
        island_payload = {
            "runId": self.run_dir.name,
            "updatedAt": _now_iso(),
            "items": [
                island.model_dump(mode="json") for island in sorted(state.islands.values(), key=lambda item: item.id)
            ],
        }
        self.write_json(self.run_dir / "islands" / "ISLANDS.json", island_payload)

    def write_meta(self, state: CoScientistState) -> None:
        """Write meta-review artifacts and a top-k summary."""
        viable = sorted(
            (hypothesis for hypothesis in state.hypotheses.values() if hypothesis.is_viable),
            key=lambda item: item.elo_rating,
            reverse=True,
        )[: self.top_k_limit]
        top_k = [
            {
                "id": hypothesis.id,
                "eloRating": hypothesis.elo_rating,
                "islandId": hypothesis.island_id,
                "summary": hypothesis.origin.content.summary,
                "category": hypothesis.origin.content.category,
            }
            for hypothesis in viable
        ]
        meta_dir = self.run_dir / "meta"
        self.write_json(meta_dir / "INSIGHTS_FROM_REVIEWS.json", state.meta_review.insights_from_reviews)
        self.write_json(meta_dir / "RESEARCH_OVERVIEW.json", state.meta_review.research_overview)
        self.write_json(meta_dir / "TOP_K.json", {"updatedAt": _now_iso(), "items": top_k})

    def write_dashboard_snapshot(self, state: CoScientistState) -> None:
        """Write the dashboard snapshot artifact."""
        snapshot = build_dashboard_snapshot(self.run_dir.name, _now_iso(), state)
        snapshot.routing = self._build_dashboard_routing_artifacts()
        evolution_state = self.read_evolution_state()
        completion_decision = self.read_completion_decision()
        snapshot.insightSections = _replace_iteration_strategy_section(
            snapshot.insightSections,
            _build_iteration_strategy_section(
                snapshot.routing,
                state=state,
                evolution_state=EvolutionStateContract.from_payload(evolution_state)
                if isinstance(evolution_state, dict)
                else None,
                completion_decision=CompletionDecisionContract.from_payload(completion_decision)
                if isinstance(completion_decision, dict)
                else None,
            ),
        )
        self.write_json(self.run_dir / "dashboard" / "SNAPSHOT.json", snapshot)

    def write_dashboard_links(self, links: dict[str, str]) -> None:
        """Write the human-readable and machine-readable dashboard link artifacts."""
        dashboard_dir = self.run_dir / "dashboard"
        self.write_json(dashboard_dir / "LINKS.json", {"updatedAt": _now_iso(), "links": links})
        markdown_lines = ["# Dashboard Links", ""]
        for label, url in links.items():
            markdown_lines.append(f"- **{label}**: {url}")
        markdown_lines.append("")
        self.write_markdown(dashboard_dir / "LINKS.md", "\n".join(markdown_lines))

    def read_pipeline_state(self) -> dict[str, Any] | None:
        """Read the pipeline state artifact if present."""
        return self.read_json(self.run_dir / "state" / "PIPELINE_STATE.json")

    def read_evolution_state(self) -> dict[str, Any] | None:
        """Read the evolution state artifact if present."""
        return self.read_json(self.run_dir / "state" / "EVOLUTION_STATE.json")

    def read_current_stage(self) -> dict[str, Any] | None:
        """Read the current stage artifact if present."""
        return self.read_json(self.run_dir / "state" / "CURRENT_STAGE.json")

    def read_completion_decision(self) -> dict[str, Any] | None:
        """Read the completion decision artifact if present."""
        return self.read_json(self.run_dir / "state" / "COMPLETION_DECISION.json")

    def read_policy_decision(self) -> dict[str, Any] | None:
        """Read the policy decision artifact if present."""
        return self.read_json(self.run_dir / "state" / "POLICY_DECISION.json")

    def read_start_request(self) -> dict[str, Any] | None:
        """Read the start request artifact if present."""
        return self.read_json(self.run_dir / "state" / "START_REQUEST.json")

    def read_run_policy(self) -> dict[str, Any] | None:
        """Read the run policy artifact if present."""
        return self.read_yaml(self.run_dir / "RUN_POLICY.yaml")

    def read_resolved_run_config(self) -> dict[str, Any] | None:
        """Read the resolved numeric run configuration artifact if present."""
        return self.read_json(self.run_dir / "state" / "RESOLVED_RUN_CONFIG.json")

    def read_strategy_plan(self) -> dict[str, Any] | None:
        """Read the current strategy plan artifact if present."""
        return self.read_json(self.run_dir / "state" / "STRATEGY_PLAN.json")

    def read_dashboard_runtime(self) -> dict[str, Any] | None:
        """Read the shared dashboard runtime artifact if present."""
        return self.read_json(self.runs_dir / "_dashboard" / "runtime.json")

    def read_proximity_graph(self) -> dict[str, Any] | None:
        """Read the persisted proximity graph artifact if present."""
        return self.read_json(self.run_dir / "state" / "PROXIMITY_GRAPH.json")

    def write_dashboard_runtime(self, runtime: dict[str, Any]) -> None:
        """Write the shared dashboard runtime artifact."""
        self.write_json(self.runs_dir / "_dashboard" / "runtime.json", runtime)

    def read_dashboard_links(self) -> dict[str, Any] | None:
        """Read the run-local dashboard links artifact if present."""
        return self.read_json(self.run_dir / "dashboard" / "LINKS.json")

    def sync_state(self, state: CoScientistState) -> None:
        """Write the complete stable artifact set from the canonical state."""
        self.ensure_layout()
        self.write_research_plan(state.research_plan)
        for hypothesis in state.hypotheses.values():
            self.write_hypothesis(hypothesis)
        self.write_tournaments(state)
        self.write_proximity_graph(state.proximity_graph)
        self.write_islands(state)
        self.write_meta(state)
        self.write_pipeline_state(state)
        self.write_dashboard_snapshot(state)

    def write_json(self, path: Path, data: Any) -> None:
        """Write JSON atomically with UTF-8 encoding."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_jsonable(data), ensure_ascii=False, indent=2, sort_keys=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(payload + "\n", encoding="utf-8")
        temp_path.replace(path)

    def read_json(self, path: Path) -> dict[str, Any] | list[Any] | None:
        """Read a JSON artifact if it exists."""
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_markdown(self, path: Path, content: str) -> None:
        """Write Markdown atomically with UTF-8 encoding."""
        self.write_text(path, content)

    def write_yaml(self, path: Path, data: Any) -> None:
        """Write YAML atomically with UTF-8 encoding."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = yaml.safe_dump(_jsonable(data), allow_unicode=True, sort_keys=False)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(path)

    def write_text(self, path: Path, content: str) -> None:
        """Write plain text atomically with UTF-8 encoding."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        temp_path.replace(path)

    def _ensure_manifest(self) -> None:
        manifest_path = self.run_dir / "MANIFEST.md"
        if manifest_path.exists():
            return
        body = "\n".join(
            [
                "# Run Manifest",
                "",
                f"- `createdAt`: `{_now_iso()}`",
                f"- `runId`: `{self.run_dir.name}`",
                "",
                "## Events",
                "",
            ]
        )
        self.write_markdown(manifest_path, body)

    def read_yaml(self, path: Path) -> dict[str, Any] | list[Any] | None:
        """Read a YAML artifact if it exists."""
        if not path.exists():
            return None
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def _ensure_dashboard_runtime_placeholder(self) -> None:
        runtime_path = self.runs_dir / "_dashboard" / "runtime.json"
        if runtime_path.exists():
            return
        self.write_json(
            runtime_path,
            {
                "updatedAt": _now_iso(),
                "status": "not_started",
                "api": {
                    "status": "not_started",
                    "host": "127.0.0.1",
                    "port": 8000,
                    "baseUrl": "http://127.0.0.1:8000",
                },
                "frontend": {
                    "status": "not_started",
                    "host": "127.0.0.1",
                    "port": 3000,
                    "baseUrl": "http://127.0.0.1:3000",
                },
            },
        )

    def _build_dashboard_routing_artifacts(self) -> DashboardRoutingArtifacts:
        policy_decision = self.read_policy_decision()
        resolved_config = self.read_resolved_run_config()
        strategy_plan = self.read_strategy_plan()
        latest_strategy_decision = self._read_latest_strategy_decision()
        strategy_decision_count = self._read_strategy_decision_count()
        return DashboardRoutingArtifacts(
            policy_decision=PolicyDecisionContract.from_payload(policy_decision)
            if isinstance(policy_decision, dict)
            else None,
            resolved_config=ResolvedRunConfigContract.from_payload(resolved_config)
            if isinstance(resolved_config, dict)
            else None,
            strategy_plan=StrategyPlanContract.from_payload(strategy_plan)
            if isinstance(strategy_plan, dict)
            else None,
            latest_strategy_decision=StrategyDecisionRecordContract.from_payload(latest_strategy_decision)
            if isinstance(latest_strategy_decision, dict)
            else None,
            strategy_decision_count=strategy_decision_count,
        )

    def _read_latest_strategy_decision(self) -> dict[str, Any] | None:
        path = self.run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        if not path.exists():
            return None
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])

    def _read_strategy_decision_count(self) -> int:
        path = self.run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        if not path.exists():
            return 0
        return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
