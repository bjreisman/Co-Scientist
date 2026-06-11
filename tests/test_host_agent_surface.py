from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    CoScientistStateContract,
    IslandStateContract,
    ResearchPlanContract,
    StrategyPlanContract,
)
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis
from tools.host.host_agent_surface import (
    bootstrap_host_agent_run,
    ensure_dashboard_for_run,
    ensure_dashboard_links_for_run,
)


def _write_config(run_dir: Path) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Host-Agent Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text("input_file: input.md\n", encoding="utf-8")
    return config_path


def _seed_evolution_state(run_dir: Path) -> ArtifactStore:
    store = ArtifactStore(run_dir, top_k_limit=3)
    hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
    state = CoScientistStateContract(
        research_plan=ResearchPlanContract(status="completed", research_goal="Investigate adaptive response."),
        hypotheses={hypothesis.id: hypothesis},
        islands={
            "island-001": IslandStateContract(
                id="island-001",
                decayed_reward=0.4,
                decayed_visits=1.0,
                visit_count=2,
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
        completed_skills=["research-config", "hypothesis-generation-pipeline"],
        stage_trail=["Generation", "Evolution"],
    )
    store.write_current_stage("Evolution", ["Generation", "Evolution"])
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
    return store


class _FakeDashboardSupervisor:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir

    def ensure_started(self, *, wait_for_health: bool = True) -> dict[str, object]:
        return {
            "status": "running" if wait_for_health else "starting",
            "api": {"baseUrl": "http://127.0.0.1:8000"},
            "frontend": {"baseUrl": "http://127.0.0.1:3000", "status": "running" if wait_for_health else "starting"},
        }

    def build_run_links(self, run_id: str, runtime: dict[str, object]) -> dict[str, str]:
        frontend_base = str(runtime["frontend"]["baseUrl"])  # type: ignore[index]
        return {
            "dashboard": f"{frontend_base}/?run={run_id}",
            "ranking": f"{frontend_base}/ranking?run={run_id}",
            "evolution": f"{frontend_base}/evolution?run={run_id}",
            "metaReviews": f"{frontend_base}/meta-reviews?run={run_id}",
        }


def test_bootstrap_host_agent_run_writes_handoff_and_dashboard_links() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)

        result = bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=True,
            dashboard_supervisor_factory=lambda runs_dir: _FakeDashboardSupervisor(runs_dir),
        )

        links_payload = json.loads((run_dir / "dashboard" / "LINKS.json").read_text(encoding="utf-8"))
        links_markdown = (run_dir / "dashboard" / "LINKS.md").read_text(encoding="utf-8")
        policy_payload = (run_dir / "RUN_POLICY.yaml").read_text(encoding="utf-8")
        policy_decision = json.loads((run_dir / "state" / "POLICY_DECISION.json").read_text(encoding="utf-8"))
        resolved_config = json.loads((run_dir / "state" / "RESOLVED_RUN_CONFIG.json").read_text(encoding="utf-8"))
        strategy_plan = json.loads((run_dir / "state" / "STRATEGY_PLAN.json").read_text(encoding="utf-8"))
        assert links_payload["links"]["dashboard"].endswith("/?run=run")
        assert links_payload["links"]["ranking"].endswith("/ranking?run=run")
        assert "- **dashboard**: http://127.0.0.1:3000/?run=run" in links_markdown
        assert "exploration_mode: balanced" in policy_payload
        assert policy_decision["policy"]["budget_profile"] == "medium"
        assert resolved_config["profile"] == "balanced"
        assert resolved_config["convergence"]["max_iterations"] == 0
        assert resolved_config["convergence"]["safety_max_iterations"] == 30
        assert strategy_plan["current_phase"] == "Configuration"
        assert strategy_plan["next_action"] == "run_configuration"
        assert result.handoff.dashboardLinks["dashboard"].endswith("/?run=run")
        assert result.handoff.dashboardLinks["ranking"].endswith("/ranking?run=run")
        assert result.dashboard_runtime["status"] == "starting"
        assert result.handoff.artifactPaths["runPolicy"].endswith("RUN_POLICY.yaml")
        assert result.handoff.artifactPaths["policyDecision"].endswith("POLICY_DECISION.json")
        assert result.handoff.artifactPaths["resolvedConfig"].endswith("RESOLVED_RUN_CONFIG.json")
        assert result.handoff.artifactPaths["strategyPlan"].endswith("STRATEGY_PLAN.json")
        assert result.handoff.artifactPaths["strategyDecisions"].endswith("STRATEGY_DECISIONS.jsonl")
        assert result.handoff.artifactPaths["evolutionRounds"].endswith("EVOLUTION_ROUNDS.jsonl")
        assert any(
            "do not ask the user whether to continue after each evolution round" in item
            for item in result.handoff.nextActions
        )
        assert any("tools.ensure_run_islands_for_hypotheses" in item for item in result.handoff.nextActions)
        assert any("newly created islands must remain unvisited" in item for item in result.handoff.nextActions)
        assert any("hypothesis_ids" in item and "ucb_score" in item for item in result.handoff.nextActions)
        assert any("artifactPaths.evolutionRounds" in item for item in result.handoff.nextActions)
        assert (run_dir / "MANIFEST.md").exists()
        assert result.handoff_json_path.exists()
        assert result.handoff_markdown_path.exists()


def test_ensure_dashboard_links_for_run_refreshes_links() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        links = ensure_dashboard_links_for_run(
            run_dir,
            dashboard_supervisor_factory=lambda runs_dir: _FakeDashboardSupervisor(runs_dir),
        )

        assert links["dashboard"].endswith("/?run=run")
        assert links["metaReviews"].endswith("/meta-reviews?run=run")
        payload = json.loads((run_dir / "dashboard" / "LINKS.json").read_text(encoding="utf-8"))
        assert payload["links"] == links


def test_ensure_dashboard_for_run_returns_runtime_and_links() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        result = ensure_dashboard_for_run(
            run_dir,
            dashboard_supervisor_factory=lambda runs_dir: _FakeDashboardSupervisor(runs_dir),
            wait_for_health=True,
        )

        assert result.runtime["status"] == "running"
        assert result.links["dashboard"].endswith("/?run=run")
        assert result.links["ranking"].endswith("/ranking?run=run")


def test_bootstrap_host_agent_run_supports_run_dir_without_config_yaml() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        (run_dir / "input.md").write_text("# Host-Agent Run\n\nInvestigate adaptive response.\n", encoding="utf-8")

        result = bootstrap_host_agent_run(
            run_dir,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        assert (run_dir / "RUN_POLICY.yaml").exists()
        assert (run_dir / "state" / "RESOLVED_RUN_CONFIG.json").exists()
        assert result.handoff.runDir == str(run_dir.resolve())


def test_bootstrap_host_agent_run_resume_preserves_existing_control_plane_artifacts() -> None:
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
        _seed_evolution_state(run_dir)

        policy_decision_path = run_dir / "state" / "POLICY_DECISION.json"
        resolved_config_path = run_dir / "state" / "RESOLVED_RUN_CONFIG.json"
        strategy_plan_path = run_dir / "state" / "STRATEGY_PLAN.json"
        strategy_decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"

        policy_decision = json.loads(policy_decision_path.read_text(encoding="utf-8"))
        policy_decision["rationale"] = ["Preserve this policy decision during resume."]
        policy_decision["updated_at"] = "2000-01-01T00:00:00Z"
        policy_decision_path.write_text(json.dumps(policy_decision, indent=2) + "\n", encoding="utf-8")

        resolved_config = json.loads(resolved_config_path.read_text(encoding="utf-8"))
        resolved_config["updated_at"] = "2000-01-01T00:00:00Z"
        resolved_config_path.write_text(json.dumps(resolved_config, indent=2) + "\n", encoding="utf-8")

        preserved_plan = StrategyPlanContract(
            current_phase="Evolution",
            next_action="continue_evolution",
            selected_evolution_strategies=["grounding_evolution"],
            reasoning=["Preserve this strategy plan during resume."],
        )
        strategy_plan_path.write_text(preserved_plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        decision_lines_before = strategy_decisions_path.read_text(encoding="utf-8").splitlines()

        result = bootstrap_host_agent_run(
            run_dir,
            requested_skill="co-scientist-pipeline",
            resume=True,
            ensure_dashboard=False,
        )

        assert json.loads(policy_decision_path.read_text(encoding="utf-8"))["rationale"] == [
            "Preserve this policy decision during resume."
        ]
        assert json.loads(resolved_config_path.read_text(encoding="utf-8"))["updated_at"] == "2000-01-01T00:00:00Z"
        resumed_plan = StrategyPlanContract.from_json_file(strategy_plan_path)
        assert resumed_plan.current_phase == "Evolution"
        assert resumed_plan.next_action == "continue_evolution"
        assert strategy_decisions_path.read_text(encoding="utf-8").splitlines() == decision_lines_before
        assert result.handoff.validation.resumeReady is True


def test_bootstrap_host_agent_run_resume_rebuilds_missing_strategy_plan_from_persisted_state() -> None:
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
        _seed_evolution_state(run_dir)

        strategy_plan_path = run_dir / "state" / "STRATEGY_PLAN.json"
        strategy_decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        strategy_plan_path.unlink()
        decision_count_before = len(strategy_decisions_path.read_text(encoding="utf-8").splitlines())

        result = bootstrap_host_agent_run(
            run_dir,
            requested_skill="co-scientist-pipeline",
            resume=True,
            ensure_dashboard=False,
        )

        rebuilt_plan = StrategyPlanContract.from_json_file(strategy_plan_path)
        assert rebuilt_plan.current_phase == "Evolution"
        assert rebuilt_plan.next_action == "continue_evolution"
        assert len(strategy_decisions_path.read_text(encoding="utf-8").splitlines()) == decision_count_before + 1
        assert result.handoff.validation.resumeReady is True


def test_bootstrap_host_agent_run_resume_reconstructs_current_stage_from_pipeline_state() -> None:
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
        _seed_evolution_state(run_dir)

        current_stage_path = run_dir / "state" / "CURRENT_STAGE.json"
        current_stage_path.unlink()

        result = bootstrap_host_agent_run(
            run_dir,
            requested_skill="co-scientist-pipeline",
            resume=True,
            ensure_dashboard=False,
        )

        restored_stage = json.loads(current_stage_path.read_text(encoding="utf-8"))
        assert restored_stage["stage"] == "Evolution"
        assert restored_stage["stageTrail"] == ["Generation", "Evolution"]
        assert result.handoff.validation.resumeReady is True


def test_bootstrap_host_agent_run_resume_rebuilds_substage_strategy_plan_from_pipeline_state() -> None:
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
        store = _seed_evolution_state(run_dir)
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate adaptive response."),
            hypotheses={
                "hyp-001": build_hypothesis("hyp-001", 1320.0, "island-001"),
            },
            islands={
                "island-001": IslandStateContract(
                    id="island-001",
                    decayed_reward=0.4,
                    decayed_visits=1.0,
                    visit_count=2,
                )
            },
            iteration_count=1,
            convergence_count=0,
        )
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            completed_skills=["research-config", "hypothesis-generation-pipeline"],
            stage_trail=["Generation", "Evolution", "Ranking"],
        )
        store.write_current_stage("Ranking", ["Generation", "Evolution", "Ranking"])

        strategy_plan_path = run_dir / "state" / "STRATEGY_PLAN.json"
        strategy_plan_path.unlink()

        result = bootstrap_host_agent_run(
            run_dir,
            requested_skill="co-scientist-pipeline",
            resume=True,
            ensure_dashboard=False,
        )

        rebuilt_plan = StrategyPlanContract.from_json_file(strategy_plan_path)
        assert rebuilt_plan.current_phase == "Ranking"
        assert rebuilt_plan.next_action == "run_ranking"
        assert result.handoff.validation.resumeReady is True
