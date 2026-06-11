from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.agent_contracts import (
    CoScientistStateContract,
    EvolutionRoundRecordContract,
    IslandStateContract,
    ResearchPlanContract,
    ResolvedRunConfigContract,
    StartRequestContract,
    StrategyDecisionRecordContract,
    StrategyPlanContract,
)
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis


def test_artifact_store_bootstrap_writes_manifest_and_stage() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)

        store.bootstrap()

        assert (run_dir / "MANIFEST.md").exists()
        assert (run_dir / "state" / "PIPELINE_STATE.json").exists()
        assert (run_dir / "state" / "CURRENT_STAGE.json").exists()
        pipeline_payload = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        payload = json.loads((run_dir / "state" / "CURRENT_STAGE.json").read_text(encoding="utf-8"))
        assert pipeline_payload["currentPhase"] == "Bootstrap"
        assert pipeline_payload["currentSkill"] == ""
        assert pipeline_payload["status"] == "not_started"
        assert pipeline_payload["stageTrail"] == []
        assert payload["stage"] == "Bootstrap"
        assert payload["stageTrail"] == []


def test_artifact_store_sync_state_writes_canonical_host_agent_artifacts(sample_state) -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)

        store.sync_state(sample_state)

        pipeline_state = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        assert pipeline_state["mode"] == "host-agent"
        assert pipeline_state["topHypothesisIds"] == ["hyp-001", "hyp-002"]
        assert (run_dir / "research_plan" / "RESEARCH_PLAN.json").exists()
        assert (run_dir / "hypotheses" / "hyp-001" / "HYPOTHESIS.json").exists()
        assert (run_dir / "dashboard" / "SNAPSHOT.json").exists()


def test_artifact_store_writes_start_request_artifact() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)

        contract = StartRequestContract(
            runId="run",
            requestText="Investigate adaptive resistance.",
            interactionMode="direct",
            explicitControls={"exploration": "aggressive"},
            inferredControls={"review": "standard"},
        )
        store.write_start_request(contract)

        payload = json.loads((run_dir / "state" / "START_REQUEST.json").read_text(encoding="utf-8"))
        assert payload["runId"] == "run"
        assert payload["interactionMode"] == "direct"
        assert payload["explicitControls"]["exploration"] == "aggressive"


def test_artifact_store_writes_canonical_island_artifact_shape() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-a")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-a": IslandStateContract(
                    id="island-a",
                    decayed_reward=0.75,
                    decayed_visits=1.25,
                    visit_count=3,
                )
            },
        )

        store.write_islands(state)

        payload = json.loads((run_dir / "islands" / "ISLANDS.json").read_text(encoding="utf-8"))
        assert payload["items"] == [
            {
                "id": "island-a",
                "decayed_reward": 0.75,
                "decayed_visits": 1.25,
                "visit_count": 3,
            }
        ]
        assert not (run_dir / "state" / "ISLANDS.json").exists()


def test_write_evolution_state_clamps_frontier_surface_to_effective_top_k() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        hypothesis_one = build_hypothesis("hyp-001", 1320.0, "island-a")
        hypothesis_two = build_hypothesis("hyp-002", 1290.0, "island-b")
        hypothesis_three = build_hypothesis("hyp-003", 1250.0, "island-c")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={
                hypothesis_one.id: hypothesis_one,
                hypothesis_two.id: hypothesis_two,
                hypothesis_three.id: hypothesis_three,
            },
            islands={
                "island-a": IslandStateContract(id="island-a", visit_count=1),
                "island-b": IslandStateContract(id="island-b", visit_count=1),
                "island-c": IslandStateContract(id="island-c", visit_count=1),
            },
            iteration_count=2,
            convergence_count=1,
        )

        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=6,
            safety_max_iterations=12,
            effective_top_k=5,
            status="running",
            entered_top_k_last_round=False,
            stop_policy="standard",
            iteration_policy="capped",
            iteration_band="6_10",
        )

        payload = json.loads((run_dir / "state" / "EVOLUTION_STATE.json").read_text(encoding="utf-8"))
        assert payload["effectiveTopK"] == 2
        assert payload["topHypothesisIds"] == ["hyp-001", "hyp-002"]


def test_write_evolution_state_clamps_effective_top_k_to_viable_count() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=5)
        viable = build_hypothesis("hyp-001", 1320.0, "island-a")
        non_viable = build_hypothesis("hyp-002", 1400.0, "island-b", passed=False)
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={viable.id: viable, non_viable.id: non_viable},
            islands={
                "island-a": IslandStateContract(id="island-a", visit_count=1),
                "island-b": IslandStateContract(id="island-b", visit_count=1),
            },
            iteration_count=2,
            convergence_count=1,
        )

        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=6,
            safety_max_iterations=12,
            effective_top_k=5,
            status="running",
            entered_top_k_last_round=False,
            stop_policy="standard",
            iteration_policy="capped",
            iteration_band="6_10",
        )

        payload = json.loads((run_dir / "state" / "EVOLUTION_STATE.json").read_text(encoding="utf-8"))
        assert payload["effectiveTopK"] == 1
        assert payload["topHypothesisIds"] == ["hyp-001"]


def test_write_evolution_state_normalizes_terminal_stop_status() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=1)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-a")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-a": IslandStateContract(id="island-a", visit_count=1)},
            iteration_count=3,
            convergence_count=3,
        )

        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=12,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=False,
            stop_policy="standard",
            iteration_policy="completion_driven",
            stop_reason="convergence_reached",
        )

        payload = json.loads((run_dir / "state" / "EVOLUTION_STATE.json").read_text(encoding="utf-8"))
        assert payload["status"] == "completed"
        assert payload["overviewEligible"] is True


def test_write_pipeline_state_keeps_current_stage_aligned_when_explicit_phase_is_supplied() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.bootstrap()
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
        )

        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Ranking"],
        )

        pipeline_state = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        current_stage = json.loads((run_dir / "state" / "CURRENT_STAGE.json").read_text(encoding="utf-8"))

        assert pipeline_state["currentPhase"] == "Ranking"
        assert pipeline_state["currentSkill"] == "hypothesis-ranking-pipeline"
        assert current_stage["stage"] == "Ranking"
        assert current_stage["stageTrail"] == ["Generation", "Ranking"]


def test_write_pipeline_state_normalizes_not_started_status_for_active_phase() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
        )

        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="not_started",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )

        pipeline_state = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        assert pipeline_state["currentPhase"] == "Evolution"
        assert pipeline_state["status"] == "running"


def test_write_pipeline_state_deduplicates_completed_skills() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
        )

        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Generation",
            current_skill="hypothesis-generation-pipeline",
            completed_skills=[
                "research-config",
                "hypothesis-generation-pipeline",
                "research-config",
            ],
        )

        pipeline_state = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        assert pipeline_state["completedSkills"] == ["research-config", "hypothesis-generation-pipeline"]


def test_write_evolution_state_rejects_convergence_signal_conflicts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-a")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-a": IslandStateContract(id="island-a", visit_count=1)},
            iteration_count=3,
            convergence_count=3,
        )

        with pytest.raises(ValueError, match="enteredTopKLastRound=true"):
            store.write_evolution_state(
                state,
                convergence_threshold=3,
                max_iterations=0,
                safety_max_iterations=12,
                effective_top_k=1,
                status="completed",
                entered_top_k_last_round=True,
                stop_policy="standard",
                iteration_policy="completion_driven",
                stop_reason="convergence_reached",
            )


def test_write_evolution_state_rejects_safety_ceiling_drift_from_resolved_config() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-a")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-a": IslandStateContract(id="island-a", visit_count=1)},
            iteration_count=20,
            convergence_count=1,
        )

        with pytest.raises(ValueError, match="safetyMaxIterations"):
            store.write_evolution_state(
                state,
                convergence_threshold=3,
                max_iterations=0,
                safety_max_iterations=20,
                effective_top_k=1,
                status="running",
                entered_top_k_last_round=False,
                stop_policy="standard",
                iteration_policy="completion_driven",
            )


def test_write_evolution_state_rejects_early_safety_stop() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-a")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-a": IslandStateContract(id="island-a", visit_count=1)},
            iteration_count=20,
            convergence_count=1,
        )

        with pytest.raises(ValueError, match="before the resolved safety ceiling is met"):
            store.write_evolution_state(
                state,
                convergence_threshold=3,
                max_iterations=0,
                safety_max_iterations=30,
                effective_top_k=1,
                status="completed",
                entered_top_k_last_round=False,
                stop_policy="standard",
                iteration_policy="completion_driven",
                safety_limit_hit=True,
                stop_reason="safety_iteration_limit_reached",
            )


def test_write_evolution_state_requires_top_k_signal_after_iterations() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-a")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find one catalyst."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-a": IslandStateContract(id="island-a", visit_count=1)},
            iteration_count=1,
            convergence_count=0,
        )

        with pytest.raises(ValueError, match="enteredTopKLastRound"):
            store.write_evolution_state(
                state,
                convergence_threshold=3,
                max_iterations=0,
                safety_max_iterations=12,
                effective_top_k=1,
                status="running",
                stop_policy="standard",
                iteration_policy="completion_driven",
            )


def test_artifact_store_appends_evolution_round_records() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)
        first = EvolutionRoundRecordContract(
            run_id="run",
            round_index=1,
            decision_index=4,
            selection_strategy="single_island",
            selected_island_ids=["island-001"],
            parent_hypothesis_ids=["hypothesis-001"],
            chosen_evolution_strategy="grounding_evolution",
            child_hypothesis_id="hypothesis-002",
            child_island_id="island-001",
            entered_top_k=True,
            convergence_count_before=1,
            convergence_count_after=0,
        )
        second = first.model_copy(
            update={
                "round_index": 2,
                "decision_index": 5,
                "parent_hypothesis_ids": ["hypothesis-002"],
                "child_hypothesis_id": "hypothesis-003",
                "entered_top_k": False,
                "convergence_count_before": 0,
                "convergence_count_after": 1,
            }
        )

        store.append_evolution_round_record(first)
        store.append_evolution_round_record(second)

        lines = (run_dir / "state" / "EVOLUTION_ROUNDS.jsonl").read_text(encoding="utf-8").splitlines()
        records = store.read_evolution_round_records()
        assert len(lines) == 2
        assert [record.child_hypothesis_id for record in records] == ["hypothesis-002", "hypothesis-003"]


def test_append_strategy_decision_rejects_duplicate_decision_index() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)
        decision = StrategyDecisionRecordContract(
            run_id="run",
            decision_index=4,
            plan=StrategyPlanContract(current_phase="Evolution", next_action="continue_evolution"),
        )

        store.append_strategy_decision(decision)

        with pytest.raises(ValueError, match="Duplicate strategy decision index `4`"):
            store.append_strategy_decision(decision)

        lines = (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
