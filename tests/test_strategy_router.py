from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    CoScientistStateContract,
    IslandStateContract,
    ResearchPlanContract,
    StrategyDecisionRecordContract,
    StrategyPlanContract,
)
from packages.agent_mechanics.island_select import SelectionResult
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis
from tools.host.host_agent_surface import bootstrap_host_agent_run
from tools.host.host_config import HostSettings
from tools.policy.plan_strategy import plan_strategy_for_run


def _write_config(run_dir: Path, *, exploration_mode: str = "balanced") -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Strategy Router Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "input_file: input.md",
                "",
                "policy:",
                f"  exploration_mode: {exploration_mode}",
                "  generation_bias: mixed",
                "",
                "ranking:",
                "  tournament_top_k: 6",
                "",
                "convergence:",
                "  convergence_count_threshold: 4",
                "  max_iterations: 6",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config_path


def test_bootstrap_host_agent_run_writes_initial_strategy_plan() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)

        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        plan = json.loads((run_dir / "state" / "STRATEGY_PLAN.json").read_text(encoding="utf-8"))
        decisions = (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").read_text(encoding="utf-8").splitlines()

        assert plan["current_phase"] == "Configuration"
        assert plan["next_action"] == "run_configuration"
        assert plan["selected_generation_strategies"] == []
        assert plan["max_new_hypotheses"] == 0
        assert len(decisions) == 1


def test_plan_strategy_for_run_routes_to_configuration_when_research_plan_is_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.current_phase == "Configuration"
        assert plan.next_action == "run_configuration"
        assert plan.signals["research_plan_status"] == "missing"
        assert plan.signals["research_plan_required"] is True


def test_plan_strategy_for_run_allocates_decision_index_from_existing_maximum() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )
        plan_payload = json.loads((run_dir / "state" / "STRATEGY_PLAN.json").read_text(encoding="utf-8"))
        sparse_record = StrategyDecisionRecordContract(
            run_id=run_dir.name,
            decision_index=8,
            plan=StrategyPlanContract.from_payload(plan_payload),
        )
        (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").write_text(
            json.dumps(sparse_record.model_dump(mode="json"), sort_keys=True) + "\n",
            encoding="utf-8",
        )

        plan_strategy_for_run(config_path)

        decisions = [
            json.loads(line)
            for line in (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert [decision["decision_index"] for decision in decisions] == [8, 9]


def test_plan_strategy_for_run_blocks_non_canonical_island_item_keys() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )
        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        (run_dir / "islands").mkdir(parents=True, exist_ok=True)
        (run_dir / "islands" / "ISLANDS.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "island-001",
                            "decayed_reward": 0.0,
                            "decayed_visits": 0.0,
                            "visit_count": 0,
                            "strategy_label": "manual",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.next_action == "inspect_state"
        assert plan.signals["inspection_required"] is True
        assert "selected_parent_ids" not in plan.signals


def test_plan_strategy_for_run_transitions_from_configuration_to_generation_after_valid_research_plan() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={},
            iteration_count=0,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Configuration",
            current_skill="research-config",
        )
        store.write_current_stage("Configuration", [])

        plan = plan_strategy_for_run(config_path)

        assert plan.current_phase == "Generation"
        assert plan.next_action == "run_generation"
        assert len(plan.selected_generation_strategies) == 3


def test_plan_strategy_for_run_restores_configuration_from_current_stage_artifact() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(),
            hypotheses={},
            iteration_count=0,
            convergence_count=0,
        )
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Configuration",
            current_skill="research-config",
        )
        store.write_current_stage("Configuration", [])

        plan = plan_strategy_for_run(config_path)

        assert plan.current_phase == "Configuration"
        assert plan.next_action == "run_configuration"
        assert plan.signals["research_plan_status"] == "missing"


def test_plan_strategy_for_run_returns_to_generation_when_frontier_stagnates() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir, exploration_mode="aggressive")
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1260.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", decayed_reward=0.01, decayed_visits=1.0, visit_count=3
                )
            },
            iteration_count=3,
            convergence_count=2,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.next_action == "return_to_generation"
        assert "scientific_debates_generation" in plan.selected_generation_strategies


def test_plan_strategy_for_run_continues_evolution_when_frontier_is_active() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", decayed_reward=0.4, decayed_visits=1.0, visit_count=2
                )
            },
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=True,
            last_selected_strategy="grounding_evolution",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.next_action == "continue_evolution"
        assert "grounding_evolution" in plan.selected_evolution_strategies
        assert "combination_evolution" not in plan.selected_evolution_strategies
        assert plan.signals["hypothesis_count"] == 1
        assert plan.signals["viable_hypothesis_count"] == 1
        assert plan.signals["convergence_count"] == 0
        assert plan.signals["entered_top_k_last_round"] is True
        assert plan.signals["top_hypothesis_ids"] == ["hyp-001"]
        assert plan.signals["selection_strategy"] == "single_island"
        assert plan.signals["selected_parent_ids"] == ["hyp-001"]


def test_plan_strategy_for_run_does_not_append_duplicate_open_continue_evolution_decision() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", decayed_reward=0.4, decayed_visits=1.0, visit_count=2
                )
            },
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=True,
            last_selected_strategy="grounding_evolution",
        )

        first_plan = plan_strategy_for_run(config_path)
        decision_lines_after_first_plan = (
            (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").read_text(encoding="utf-8").splitlines()
        )
        second_plan = plan_strategy_for_run(config_path)
        decision_lines_after_second_plan = (
            (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").read_text(encoding="utf-8").splitlines()
        )

        assert first_plan.next_action == "continue_evolution"
        assert second_plan.next_action == "continue_evolution"
        assert decision_lines_after_second_plan == decision_lines_after_first_plan


def test_plan_strategy_replays_open_continue_decision_before_resampling_unvisited_islands(monkeypatch) -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir, exploration_mode="aggressive")
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis_one = build_hypothesis("hyp-001", 1300.0, "island-001")
        hypothesis_two = build_hypothesis("hyp-002", 1290.0, "island-002")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis_one.id: hypothesis_one, hypothesis_two.id: hypothesis_two},
            islands={
                "island-001": IslandStateContract(id="island-001"),
                "island-002": IslandStateContract(id="island-002"),
            },
            iteration_count=0,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis_one)
        store.write_hypothesis(hypothesis_two)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=2,
            status="running",
            entered_top_k_last_round=None,
            last_selected_strategy="grounding_evolution",
        )

        selections = iter(
            [
                SelectionResult(strategy="single_island", hypotheses=[hypothesis_one]),
                SelectionResult(strategy="single_island", hypotheses=[hypothesis_two]),
            ]
        )

        def select_next_island(*args, **kwargs):
            return next(selections)

        monkeypatch.setattr("tools.policy.plan_strategy.select_island_hypotheses", select_next_island)

        first_plan = plan_strategy_for_run(config_path)
        decision_lines_after_first_plan = (
            (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").read_text(encoding="utf-8").splitlines()
        )
        second_plan = plan_strategy_for_run(config_path)
        decision_lines_after_second_plan = (
            (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").read_text(encoding="utf-8").splitlines()
        )

        assert first_plan.signals["selected_parent_ids"] == ["hyp-001"]
        assert second_plan.signals["selected_parent_ids"] == ["hyp-001"]
        assert decision_lines_after_second_plan == decision_lines_after_first_plan


def test_plan_strategy_explores_unvisited_seed_islands_before_stagnation() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir, exploration_mode="aggressive")
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis_one = build_hypothesis("hyp-001", 1300.0, "island-001")
        hypothesis_two = build_hypothesis("hyp-002", 1290.0, "island-002")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis_one.id: hypothesis_one, hypothesis_two.id: hypothesis_two},
            islands={
                "island-001": IslandStateContract(id="island-001"),
                "island-002": IslandStateContract(id="island-002"),
            },
            iteration_count=0,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis_one)
        store.write_hypothesis(hypothesis_two)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=2,
            status="running",
            entered_top_k_last_round=None,
            last_selected_strategy="grounding_evolution",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.next_action == "continue_evolution"
        assert plan.signals["selection_strategy"] == "single_island"
        assert len(plan.signals["selected_parent_ids"]) == 1
        assert plan.signals["selected_parent_ids"][0] in {"hyp-001", "hyp-002"}
        assert plan.selected_evolution_strategies
        assert "combination_evolution" not in plan.selected_evolution_strategies


def test_plan_strategy_for_run_blocks_deprecated_island_payload_instead_of_defaulting_metrics() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", decayed_reward=0.4, decayed_visits=1.0, visit_count=2
                )
            },
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        (run_dir / "islands").mkdir(exist_ok=True)
        (run_dir / "islands" / "ISLANDS.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "island_id": "island-001",
                            "reward": 0.4,
                            "decayed_visits": 1.0,
                            "visit_count": 2,
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=True,
            last_selected_strategy="grounding_evolution",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.next_action == "inspect_state"
        assert plan.signals["inspection_required"] is True
        assert "selected_parent_ids" not in plan.signals


def test_plan_strategy_for_run_records_multi_island_parent_selection_when_stagnating() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir, exploration_mode="aggressive")
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis_one = build_hypothesis("hyp-001", 1330.0, "island-001")
        hypothesis_two = build_hypothesis("hyp-002", 1290.0, "island-002")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis_one.id: hypothesis_one, hypothesis_two.id: hypothesis_two},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", decayed_reward=0.01, decayed_visits=1.0, visit_count=3
                ),
                "island-002": IslandStateContract(
                    id="island-002", decayed_reward=0.02, decayed_visits=1.0, visit_count=3
                ),
            },
            iteration_count=5,
            convergence_count=1,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis_one)
        store.write_hypothesis(hypothesis_two)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=2,
            status="running",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.next_action == "continue_evolution"
        assert plan.signals["selection_strategy"] == "multi_island"
        assert len(plan.signals["selected_parent_ids"]) == 2
        assert plan.selected_evolution_strategies == ["combination_evolution"]


def test_strategy_plan_contract_normalizes_legacy_research_overview_phase() -> None:
    plan = StrategyPlanContract.from_payload(
        {
            "current_phase": "ResearchOverview",
            "next_action": "generate_overview",
        }
    )

    assert plan.current_phase == "Research Overview"


def test_plan_strategy_for_run_routes_research_overview_from_current_stage_artifact() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", decayed_reward=0.4, decayed_visits=1.0, visit_count=2
                )
            },
            iteration_count=4,
            convergence_count=4,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
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
            max_iterations=6,
            effective_top_k=1,
            status="completed",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            stop_reason="convergence_reached",
            overview_eligible=True,
        )
        current_stage_path = run_dir / "state" / "CURRENT_STAGE.json"
        current_stage_path.write_text(
            json.dumps({"stage": "Research Overview", "stageTrail": ["Generation", "Evolution", "Research Overview"]}),
            encoding="utf-8",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.current_phase == "Research Overview"
        assert plan.next_action == "generate_overview"


def test_plan_strategy_for_run_routes_insights_stage_from_current_stage_artifact() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", decayed_reward=0.4, decayed_visits=1.0, visit_count=2
                )
            },
            iteration_count=2,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Insights from Reviews",
            current_skill="insights-from-reviews",
            stage_trail=["Generation", "Evolution", "Insights from Reviews"],
        )
        store.write_evolution_state(
            state,
            convergence_threshold=4,
            max_iterations=6,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=True,
            last_selected_strategy="grounding_evolution",
            last_selected_island="island-001",
        )
        current_stage_path = run_dir / "state" / "CURRENT_STAGE.json"
        current_stage_path.write_text(
            json.dumps(
                {
                    "stage": "Insights from Reviews",
                    "stageTrail": ["Generation", "Evolution", "Insights from Reviews"],
                }
            ),
            encoding="utf-8",
        )

        plan = plan_strategy_for_run(config_path)

        assert plan.current_phase == "Insights from Reviews"
        assert plan.next_action == "run_insights"


def test_plan_strategy_for_run_blocks_when_completion_advisory_requires_state_inspection() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)
        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        settings = HostSettings.from_yaml(config_path)
        store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        hypothesis.review.full_review.status = "pending"
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            iteration_count=3,
            convergence_count=3,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=6,
            effective_top_k=1,
            status="completed",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            stop_reason="convergence_reached",
            overview_eligible=True,
        )
        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["enteredTopKLastRound"] = True
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        plan = plan_strategy_for_run(config_path)

        assert plan.status == "blocked"
        assert plan.current_phase == "Evolution"
        assert plan.next_action == "inspect_state"
        assert plan.signals["inspection_required"] is True
