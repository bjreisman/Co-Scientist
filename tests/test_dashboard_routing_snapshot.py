from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import CoScientistStateContract, IslandStateContract, ResearchPlanContract
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis
from tools.host.host_agent_surface import bootstrap_host_agent_run
from tools.host.host_config import HostSettings


def _write_config(run_dir: Path) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Dashboard Routing\n\nInvestigate adaptive response.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text("input_file: input.md\n", encoding="utf-8")
    return config_path


def test_dashboard_snapshot_embeds_routing_artifacts() -> None:
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
        hypothesis = build_hypothesis("hyp-001", 1280.0, "island-001", summary="Routing-aware catalyst")
        sample_state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_evolution_state(
            sample_state,
            convergence_threshold=settings.convergence.convergence_count_threshold,
            max_iterations=settings.convergence.max_iterations,
            safety_max_iterations=settings.convergence.safety_max_iterations,
            effective_top_k=settings.ranking.tournament_top_k,
            status="running",
            stop_policy=settings.run_policy.policy.stop_policy,
            iteration_policy=settings.run_policy.policy.iteration_policy,
            iteration_band=settings.run_policy.policy.iteration_band or "",
            entered_top_k_last_round=True,
        )
        store.write_dashboard_snapshot(sample_state)

        snapshot = json.loads((run_dir / "dashboard" / "SNAPSHOT.json").read_text(encoding="utf-8"))

        assert snapshot["routing"]["policy_decision"]["policy"]["exploration_mode"] == "balanced"
        assert snapshot["routing"]["policy_decision"]["policy"]["iteration_policy"] == "completion_driven"
        assert snapshot["routing"]["resolved_config"]["profile"] == "balanced"
        assert snapshot["routing"]["resolved_config"]["convergence"]["safety_max_iterations"] == 30
        assert snapshot["routing"]["strategy_plan"]["current_phase"] == "Configuration"
        assert snapshot["routing"]["strategy_plan"]["next_action"] == "run_configuration"
        assert snapshot["routing"]["strategy_decision_count"] == 1
        iteration_section = next(
            section for section in snapshot["insightSections"] if section["title"] == "Iteration Strategy"
        )
        assert any("completion_driven" in item for item in iteration_section["items"])
        assert any(item == "Safety iteration ceiling is `30`." for item in iteration_section["items"])
        assert any("Human checkpoint policy is" in item for item in iteration_section["items"])


def test_dashboard_snapshot_flags_uninitialized_island_metrics_for_evolved_runs() -> None:
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
        parent = build_hypothesis("hyp-001", 1280.0, "island-001", summary="Parent catalyst")
        child = build_hypothesis(
            "hyp-002",
            1290.0,
            "island-001",
            parent_ids=["hyp-001"],
            summary="Refined catalyst",
        )
        sample_state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={parent.id: parent, child.id: child},
            islands={"island-001": IslandStateContract(id="island-001")},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_hypothesis(parent)
        store.write_hypothesis(child)
        store.write_islands(sample_state)
        store.write_evolution_state(
            sample_state,
            convergence_threshold=settings.convergence.convergence_count_threshold,
            max_iterations=settings.convergence.max_iterations,
            safety_max_iterations=settings.convergence.safety_max_iterations,
            effective_top_k=settings.ranking.tournament_top_k,
            status="running",
            stop_policy=settings.run_policy.policy.stop_policy,
            iteration_policy=settings.run_policy.policy.iteration_policy,
            iteration_band=settings.run_policy.policy.iteration_band or "",
            entered_top_k_last_round=False,
            last_selected_island="island-001",
            last_selected_strategy="grounding_evolution",
        )
        store.write_dashboard_snapshot(sample_state)

        snapshot = json.loads((run_dir / "dashboard" / "SNAPSHOT.json").read_text(encoding="utf-8"))
        iteration_section = next(
            section for section in snapshot["insightSections"] if section["title"] == "Iteration Strategy"
        )

        assert iteration_section["badge"] == "Warning"
        assert any("uninitialized" in item for item in iteration_section["items"])


def test_dashboard_snapshot_graph_seed_uses_canonical_island_metrics() -> None:
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
        hypothesis = build_hypothesis("hyp-001", 1280.0, "island-001", summary="Metric-aware catalyst")
        sample_state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001",
                    decayed_reward=0.625,
                    decayed_visits=1.5,
                    visit_count=2,
                )
            },
            iteration_count=2,
            convergence_count=1,
        )
        store.write_hypothesis(hypothesis)
        store.write_islands(sample_state)
        store.write_dashboard_snapshot(sample_state)

        snapshot = json.loads((run_dir / "dashboard" / "SNAPSHOT.json").read_text(encoding="utf-8"))
        graph_island = snapshot["graphSeed"]["islands"][0]

        assert graph_island["id"] == "island-001"
        assert graph_island["metrics"]["decayedReward"] == 0.625
        assert graph_island["metrics"]["decayedVisits"] == 1.5
        assert graph_island["metrics"]["visitCount"] == 2


def test_dashboard_snapshot_surfaces_inspect_state_completion_block() -> None:
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
        hypothesis = build_hypothesis("hyp-001", 1280.0, "island-001", summary="Blocked catalyst")
        sample_state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Find a mechanism."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                )
            },
            iteration_count=2,
            convergence_count=1,
        )
        store.write_hypothesis(hypothesis)
        store.write_islands(sample_state)
        store.write_evolution_state(
            sample_state,
            convergence_threshold=settings.convergence.convergence_count_threshold,
            max_iterations=settings.convergence.max_iterations,
            safety_max_iterations=settings.convergence.safety_max_iterations,
            effective_top_k=1,
            status="blocked",
            stop_policy=settings.run_policy.policy.stop_policy,
            iteration_policy=settings.run_policy.policy.iteration_policy,
            iteration_band=settings.run_policy.policy.iteration_band or "",
            entered_top_k_last_round=False,
            stop_reason="validation_blocked",
            overview_eligible=False,
        )
        store.write_completion_decision(
            decision="inspect_state",
            verifier_recommendation="inspect_state",
            requested_skill="co-scientist-pipeline",
            override=False,
            rationale=["Ranking and review artifacts disagree."],
        )
        store.write_dashboard_snapshot(sample_state)

        snapshot = json.loads((run_dir / "dashboard" / "SNAPSHOT.json").read_text(encoding="utf-8"))
        iteration_section = next(
            section for section in snapshot["insightSections"] if section["title"] == "Iteration Strategy"
        )

        assert any("blocked autonomous continuation" in item for item in iteration_section["items"])
        assert any("validation blocked" in item.lower() for item in iteration_section["items"])
