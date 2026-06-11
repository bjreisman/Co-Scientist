from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    CoScientistStateContract,
    EmbeddingProviderConfigContract,
    IslandStateContract,
    MetaReviewContract,
    ResearchOverviewContract,
    ResearchPlanContract,
    ResolvedRunConfigContract,
    ReviewContract,
    TournamentMatchContract,
)
from packages.agent_mechanics import update_hypothesis_proximity
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis
from tools.host.host_config import HostSettings
from tools.validation.verify_pipeline_completion import advise_pipeline_completion, record_completion_decision


def _write_config(
    run_dir: Path,
    *,
    max_iterations: int = 3,
    safety_max_iterations: int | None = None,
    top_k: int = 2,
    stop_policy: str = "standard",
    iteration_policy: str = "capped",
) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Completion Test\n\nInvestigate catalyst design.\n", encoding="utf-8")
    convergence_lines = [
        "convergence:",
        "  convergence_count_threshold: 3",
        f"  max_iterations: {max_iterations}",
    ]
    if safety_max_iterations is not None:
        convergence_lines.append(f"  safety_max_iterations: {safety_max_iterations}")
    config_path = run_dir / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "input_file: input.md",
                "",
                "policy:",
                f"  stop_policy: {stop_policy}",
                f"  iteration_policy: {iteration_policy}",
                "",
                "ranking:",
                f"  tournament_top_k: {top_k}",
                "",
                *convergence_lines,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config_path


def _prepare_run(
    run_dir: Path,
    *,
    iteration_count: int,
    convergence_count: int,
    stop_reason: str = "",
    max_iterations: int = 3,
    safety_max_iterations: int | None = None,
    stop_policy: str = "standard",
    iteration_policy: str = "capped",
    iteration_band: str = "6_10",
    entered_top_k_last_round: bool | None = False,
    include_overview: bool = False,
) -> ArtifactStore:
    config_path = _write_config(
        run_dir,
        max_iterations=max_iterations,
        safety_max_iterations=safety_max_iterations,
        stop_policy=stop_policy,
        iteration_policy=iteration_policy,
    )
    settings = HostSettings.from_yaml(config_path)
    store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
    store.bootstrap()

    hypothesis = build_hypothesis(
        "hyp-001",
        1230.0,
        "island-001",
        summary="Vacancy-mediated cobalt activation",
        category="catalyst-design",
    )
    state = CoScientistStateContract(
        research_plan=ResearchPlanContract(
            status="completed",
            research_goal="Identify one lanthanide-supported cobalt catalyst for ammonia synthesis.",
            preferences=["Explain the mechanism", "Predict one optimal particle size"],
            constraints=["No promoters", "Keep the run experimentally grounded"],
        ),
        hypotheses={hypothesis.id: hypothesis},
        meta_review=MetaReviewContract(
            research_overview=ResearchOverviewContract(
                status="completed" if include_overview else "pending",
                content="Final synthesis of the top catalyst direction." if include_overview else "",
            )
        ),
        islands={
            "island-001": IslandStateContract(id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5)
        },
        iteration_count=iteration_count,
        convergence_count=convergence_count,
    )

    store.write_research_plan(state.research_plan)
    store.write_hypothesis(hypothesis)
    store.write_islands(state)
    if include_overview:
        store.write_meta(state)
    store.write_pipeline_state(
        state,
        mode="host-agent",
        status="running",
        current_phase="Evolution",
        current_skill="hypothesis-evolution-loop",
        completed_skills=["research-config", "hypothesis-generation-pipeline", "hypothesis-review-pipeline"],
    )
    store.write_evolution_state(
        state,
        convergence_threshold=settings.convergence.convergence_count_threshold,
        max_iterations=settings.convergence.max_iterations,
        safety_max_iterations=settings.convergence.safety_max_iterations,
        effective_top_k=1,
        status="completed" if stop_reason else "running",
        last_selected_island="island-001",
        last_selected_strategy="grounding_evolution",
        entered_top_k_last_round=entered_top_k_last_round,
        stop_policy=settings.run_policy.policy.stop_policy,
        iteration_policy=settings.run_policy.policy.iteration_policy,
        iteration_band=iteration_band if iteration_policy == "capped" else "",
        safety_limit_hit=stop_reason == "safety_iteration_limit_reached",
        stop_reason=stop_reason,
        overview_eligible=stop_reason
        in {
            "convergence_reached",
            "max_iterations_reached",
            "safety_iteration_limit_reached",
            "no_viable_candidates",
        },
    )
    (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "decision_index": 1,
                "current_phase": "Generation",
                "next_action": "run_generation",
                "selected_generation_strategies": ["literature_exploration_generation"],
                "selected_evolution_strategies": [],
                "max_new_hypotheses": 1,
                "reasoning": ["Seed the initial frontier."],
                "advisory_recommendation": "inspect_state",
                "signals": {},
                "status": "planned",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return store


def test_completion_verifier_recommends_continue_when_evolution_can_continue() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(run_dir, iteration_count=1, convergence_count=0, max_iterations=4)

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "continue_evolution"
        assert advisory.recommendedAction == "continue_evolution"
        assert any("Convergence threshold has not been reached" in reason for reason in advisory.reasons)


def test_completion_verifier_blocks_when_convergence_signals_conflict() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=6,
            convergence_count=3,
            stop_reason="convergence_reached",
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
            entered_top_k_last_round=False,
        )
        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["enteredTopKLastRound"] = True
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert any("enteredTopKLastRound" in reason for reason in advisory.reasons)


def test_completion_verifier_recommends_overview_when_max_iterations_reached() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=3,
            convergence_count=1,
            stop_reason="max_iterations_reached",
            max_iterations=3,
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "ready_for_overview"
        assert advisory.recommendedAction == "generate_overview"
        assert advisory.signals["stopReason"] == "max_iterations_reached"
        assert advisory.signals["iterationPolicy"] == "capped"


def test_completion_verifier_recommends_complete_when_completed_overview_exists() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=3,
            convergence_count=3,
            stop_reason="convergence_reached",
            include_overview=True,
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "ready_for_completion"
        assert advisory.recommendedAction == "complete"
        assert advisory.signals["overviewValid"] is True


def test_completion_verifier_blocks_when_frontier_evolved_child_lacks_placement_provenance() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_run(
            run_dir,
            iteration_count=3,
            convergence_count=3,
            stop_reason="convergence_reached",
            include_overview=True,
        )
        parent = build_hypothesis(
            "hyp-001",
            1230.0,
            "island-001",
            summary="Vacancy-mediated cobalt activation",
            category="catalyst-design",
        )
        child = build_hypothesis(
            "hyp-002",
            1330.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="grounding_evolution",
            summary="Grounded cobalt activation child",
            category="catalyst-design",
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={parent.id: parent, child.id: child},
            meta_review=MetaReviewContract(
                research_overview=ResearchOverviewContract(
                    status="completed",
                    content="Final synthesis of the top catalyst direction.",
                )
            ),
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                )
            },
            iteration_count=3,
            convergence_count=3,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(parent)
        store.write_hypothesis(child)
        store.write_islands(state)
        store.write_meta(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Research Overview",
            current_skill="research-overview-pipeline",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=3,
            effective_top_k=2,
            status="completed",
            entered_top_k_last_round=False,
            stop_reason="convergence_reached",
            overview_eligible=True,
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["frontierEvolvedWithoutPlacementIds"] == ["hyp-002"]
        assert any("placement tournament provenance" in reason for reason in advisory.reasons)


def test_completion_verifier_completion_driven_runs_ignore_small_iteration_caps() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=5,
            convergence_count=1,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "continue_evolution"
        assert advisory.recommendedAction == "continue_evolution"
        assert advisory.signals["maxIterations"] == 0
        assert advisory.signals["safetyMaxIterations"] == 12
        assert advisory.signals["iterationPolicy"] == "completion_driven"


def test_completion_verifier_respects_exploratory_stop_policy_threshold() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=4,
            convergence_count=3,
            max_iterations=0,
            safety_max_iterations=12,
            stop_policy="exploratory",
            iteration_policy="completion_driven",
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "continue_evolution"
        assert advisory.signals["effectiveConvergenceThreshold"] == 4


def test_completion_verifier_recommends_overview_when_safety_limit_is_reached() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=12,
            convergence_count=1,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "ready_for_overview"
        assert advisory.recommendedAction == "generate_overview"
        assert advisory.signals["safetyLimitHit"] is True


def test_completion_verifier_blocks_when_safety_stop_precedes_resolved_ceiling() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_run(
            run_dir,
            iteration_count=20,
            convergence_count=1,
            max_iterations=0,
            safety_max_iterations=30,
            iteration_policy="completion_driven",
        )
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload.update(
            {
                "status": "completed",
                "safetyLimitHit": True,
                "stopReason": "safety_iteration_limit_reached",
                "overviewEligible": True,
            }
        )
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["safetyStopBeforeResolvedCeiling"] is True
        assert any("before the resolved safety ceiling was met" in reason for reason in advisory.reasons)


def test_completion_verifier_records_override_decision() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(run_dir, iteration_count=1, convergence_count=0, max_iterations=4)

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")
        decision = record_completion_decision(
            run_dir,
            decision="complete",
            advisory=advisory,
            requested_skill="co-scientist-pipeline",
            rationale=["This exploratory run has enough diversity to stop early."],
        )

        payload = json.loads((run_dir / "state" / "COMPLETION_DECISION.json").read_text(encoding="utf-8"))
        assert decision.override is True
        assert payload["decision"] == "complete"
        assert payload["override"] is True


def test_completion_verifier_blocks_when_evolution_audit_is_incomplete() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=3,
            convergence_count=3,
            stop_reason="convergence_reached",
            max_iterations=4,
        )

        evolved = build_hypothesis(
            "hyp-002",
            1240.0,
            "island-001",
            parent_ids=["hyp-001"],
            summary="Refined child",
            category="catalyst-design",
        )
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.write_hypothesis(evolved)

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["evolvedHypothesisCount"] == 1
        assert advisory.signals["strategyDecisionCount"] == 1


def test_completion_verifier_cli_writes_advisory_and_decision_json() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=3,
            convergence_count=3,
            stop_reason="convergence_reached",
            include_overview=True,
        )
        json_out = run_dir / "state" / "completion_advisory.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.verify_pipeline_completion",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
                "--json-out",
                str(json_out),
                "--write-decision",
                "complete",
            ],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["advisory"]["recommendedAction"] == "complete"
        assert payload["decision"]["decision"] == "complete"
        assert payload["decision"]["rationale"] == payload["advisory"]["reasons"]
        assert any("valid research overview" in reason for reason in payload["decision"]["rationale"])


def test_completion_verifier_blocks_when_validator_detects_review_drift() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=5,
            convergence_count=2,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )

        hypothesis_path = run_dir / "hypotheses" / "hyp-001" / "HYPOTHESIS.json"
        payload = json.loads(hypothesis_path.read_text(encoding="utf-8"))
        payload["review"] = ReviewContract().model_dump(mode="json")
        hypothesis_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["validatorStatus"] == "invalid"
        assert advisory.signals["validatorErrorCount"] > 0
        assert any("Artifact validation reported blocking inconsistencies." in reason for reason in advisory.reasons)


def test_completion_verifier_blocks_ranking_without_receipt_as_writeback_inconsistency() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(
            run_dir,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )
        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        store.bootstrap()

        candidate = build_hypothesis("hyp-001", 1216.0, "island-001")
        candidate = candidate.model_copy(update={"placement_match_ids": ["match-001"]})
        opponent = build_hypothesis("hyp-002", 1184.0, "island-002")
        opponent = opponent.model_copy(update={"ranked_match_ids": ["match-001"]})
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="placement_tournament",
            reasoning="The candidate is more directly testable.",
            winner_id=candidate.id,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate catalyst design."),
            hypotheses={candidate.id: candidate, opponent.id: opponent},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        update_hypothesis_proximity(
            run_dir,
            candidate.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=settings.convergence.convergence_count_threshold,
            max_iterations=settings.convergence.max_iterations,
            safety_max_iterations=settings.convergence.safety_max_iterations,
            effective_top_k=2,
            status="running",
            entered_top_k_last_round=False,
            stop_policy=settings.run_policy.policy.stop_policy,
            iteration_policy=settings.run_policy.policy.iteration_policy,
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["validatorStatus"] == "invalid"
        assert advisory.signals["rankingWritebackInvalid"] is True
        assert any("ranking artifacts are inconsistent with Elo writeback" in reason for reason in advisory.reasons)
        assert any("repair ranking before continuing evolution" in reason for reason in advisory.reasons)


def test_completion_verifier_reports_completed_pipeline_running_evolution_mismatch() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=2,
            convergence_count=1,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )

        pipeline_state_path = run_dir / "state" / "PIPELINE_STATE.json"
        pipeline_state_payload = json.loads(pipeline_state_path.read_text(encoding="utf-8"))
        pipeline_state_payload["status"] = "completed"
        pipeline_state_path.write_text(json.dumps(pipeline_state_payload) + "\n", encoding="utf-8")

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["pipelineStatus"] == "completed"
        assert advisory.signals["evolutionStatus"] == "running"
        assert advisory.signals["evolutionStatusMismatch"] is True
        assert any(
            "pipeline is completed while the evolution state is still marked `running`" in reason
            for reason in advisory.reasons
        )


def test_completion_verifier_reports_effective_top_k_mismatch() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=2,
            convergence_count=1,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )

        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["effectiveTopK"] = 2
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")
        ArtifactStore(run_dir, top_k_limit=2).write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"ranking": {"tournament_top_k": 2}})
        )

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["effectiveTopK"] == 1
        assert advisory.signals["persistedEffectiveTopK"] == 2
        assert advisory.signals["resolvedTopK"] == 2
        assert advisory.signals["effectiveTopKMismatch"] is True
        assert any("effective top-k does not match" in reason for reason in advisory.reasons)


def test_completion_verifier_blocks_when_completed_review_summary_has_no_content() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=5,
            convergence_count=2,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )

        review_summary_path = run_dir / "hypotheses" / "hyp-001" / "REVIEW" / "REVIEW_SUMMARY.json"
        review_summary_payload = json.loads(review_summary_path.read_text(encoding="utf-8"))
        review_summary_payload["summaries"] = []
        review_summary_path.write_text(json.dumps(review_summary_payload) + "\n", encoding="utf-8")

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["validatorStatus"] == "invalid"
        assert any(
            "Completed review summary artifacts must include at least one summary item." in reason
            for reason in advisory.reasons
        )


def test_completion_verifier_blocks_when_completed_simulation_review_has_no_steps() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_run(
            run_dir,
            iteration_count=5,
            convergence_count=2,
            max_iterations=0,
            safety_max_iterations=12,
            iteration_policy="completion_driven",
        )

        simulation_review_path = run_dir / "hypotheses" / "hyp-001" / "REVIEW" / "SIMULATION_REVIEW.json"
        simulation_review_payload = json.loads(simulation_review_path.read_text(encoding="utf-8"))
        simulation_review_payload["steps"] = []
        simulation_review_path.write_text(json.dumps(simulation_review_payload) + "\n", encoding="utf-8")

        advisory = advise_pipeline_completion(run_dir, requested_skill="co-scientist-pipeline")

        assert advisory.completionReadiness == "blocked"
        assert advisory.recommendedAction == "inspect_state"
        assert advisory.signals["validatorStatus"] == "invalid"
        assert any(
            "Completed simulation review artifacts must include at least one step." in reason
            for reason in advisory.reasons
        )
