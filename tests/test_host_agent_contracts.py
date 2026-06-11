from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.host.host_agent import get_execution_modes, prepare_host_agent_handoff, write_host_agent_handoff
from tools.validation.contract_validation import validate_run_artifacts


def _write_config(run_dir: Path) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Host-Agent Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text("input_file: input.md\n", encoding="utf-8")
    return config_path


def test_execution_surface_exposes_only_host_agent() -> None:
    modes = get_execution_modes()

    assert len(modes) == 1
    assert modes[0].name == "host-agent"
    assert modes[0].entrypoint == "python -m tools.host.project_cli run <run-dir> --skill co-scientist-pipeline"
    assert modes[0].owns_llm_calls is False
    assert modes[0].repository_managed_runtime is False


def test_validate_run_artifacts_accepts_fresh_host_agent_run() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        summary = validate_run_artifacts(run_dir, resume=False, requested_skill="co-scientist-pipeline")

        assert summary.status == "valid"
        assert summary.errorCount == 0
        assert summary.warningCount >= 1


def test_prepare_host_agent_handoff_writes_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        (run_dir / "dashboard").mkdir(parents=True)
        config_path = _write_config(run_dir)
        (run_dir / "dashboard" / "LINKS.json").write_text(
            json.dumps(
                {
                    "updatedAt": "2026-05-24T00:00:00Z",
                    "links": {
                        "dashboard": "http://127.0.0.1:3000/?run=run",
                        "ranking": "http://127.0.0.1:3000/ranking?run=run",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        handoff = prepare_host_agent_handoff(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
        )
        json_path, markdown_path = write_host_agent_handoff(handoff)

        assert handoff.validation.status == "valid"
        assert handoff.validationSnapshot.status == handoff.validation.status
        assert handoff.validationSnapshot.generatedAt
        assert handoff.validationSnapshot.command.endswith(
            "python -m tools.validation.contract_validation <run_dir> --skill co-scientist-pipeline"
        )
        assert "handoff-time validation snapshot" in handoff.validationSnapshot.note
        assert handoff.dashboardLinks["dashboard"].endswith("/?run=run")
        assert handoff.dashboardLinks["ranking"].endswith("/ranking?run=run")
        assert Path(handoff.skillPath).name == "SKILL.md"
        assert "completionContract" in handoff.sharedReferences
        assert "schemaIndex" in handoff.sharedReferences
        assert "codeStructureContract" in handoff.sharedReferences
        assert "mechanicsIntegrationContract" in handoff.sharedReferences
        schema_index_path = handoff.sharedReferences["schemaIndex"].replace("\\", "/")
        code_structure_contract_path = handoff.sharedReferences["codeStructureContract"].replace("\\", "/")
        mechanics_integration_contract_path = handoff.sharedReferences["mechanicsIntegrationContract"].replace(
            "\\", "/"
        )
        research_plan_contract_path = handoff.sharedReferences["researchPlanContractPy"].replace("\\", "/")
        hypothesis_contract_path = handoff.sharedReferences["hypothesisContractPy"].replace("\\", "/")
        review_contract_path = handoff.sharedReferences["reviewContractPy"].replace("\\", "/")
        strategy_plan_contract_path = handoff.sharedReferences["strategyPlanContractPy"].replace("\\", "/")
        resolved_config_contract_path = handoff.sharedReferences["resolvedRunConfigContractPy"].replace("\\", "/")
        pipeline_state_contract_path = handoff.sharedReferences["pipelineStateContractPy"].replace("\\", "/")
        current_stage_contract_path = handoff.sharedReferences["currentStageContractPy"].replace("\\", "/")
        start_request_contract_path = handoff.sharedReferences["startRequestContractPy"].replace("\\", "/")
        evolution_state_contract_path = handoff.sharedReferences["evolutionStateContractPy"].replace("\\", "/")
        evolution_round_contract_path = handoff.sharedReferences["evolutionRoundContractPy"].replace("\\", "/")
        completion_decision_contract_path = handoff.sharedReferences["completionDecisionContractPy"].replace("\\", "/")
        insights_contract_path = handoff.sharedReferences["insightsContractPy"].replace("\\", "/")
        research_overview_contract_path = handoff.sharedReferences["researchOverviewContractPy"].replace("\\", "/")
        proximity_graph_contract_path = handoff.sharedReferences["proximityGraphContractPy"].replace("\\", "/")
        island_state_contract_path = handoff.sharedReferences["islandStateContractPy"].replace("\\", "/")
        tournament_match_contract_path = handoff.sharedReferences["tournamentMatchContractPy"].replace("\\", "/")
        assert schema_index_path.endswith("skills/shared-references/schema-index.md")
        assert code_structure_contract_path.endswith("skills/shared-references/code-structure-contract.md")
        assert mechanics_integration_contract_path.endswith(
            "skills/shared-references/mechanics-integration-contract.md"
        )
        assert start_request_contract_path.endswith("packages/agent_contracts/start_request.py")
        assert pipeline_state_contract_path.endswith("packages/agent_contracts/pipeline_runtime.py")
        assert current_stage_contract_path.endswith("packages/agent_contracts/pipeline_runtime.py")
        assert research_plan_contract_path.endswith("packages/agent_contracts/research_plan.py")
        assert hypothesis_contract_path.endswith("packages/agent_contracts/hypothesis.py")
        assert review_contract_path.endswith("packages/agent_contracts/review.py")
        assert strategy_plan_contract_path.endswith("packages/agent_contracts/strategy_plan.py")
        assert resolved_config_contract_path.endswith("packages/agent_contracts/resolved_config.py")
        assert evolution_state_contract_path.endswith("packages/agent_contracts/pipeline_control.py")
        assert evolution_round_contract_path.endswith("packages/agent_contracts/evolution_round.py")
        assert completion_decision_contract_path.endswith("packages/agent_contracts/pipeline_control.py")
        assert insights_contract_path.endswith("packages/agent_contracts/meta_review.py")
        assert research_overview_contract_path.endswith("packages/agent_contracts/meta_review.py")
        assert proximity_graph_contract_path.endswith("packages/agent_contracts/state.py")
        assert island_state_contract_path.endswith("packages/agent_contracts/state.py")
        assert tournament_match_contract_path.endswith("packages/agent_contracts/ranking.py")
        assert "startRequest" in handoff.artifactPaths
        assert "evolutionState" in handoff.artifactPaths
        assert handoff.artifactPaths["evolutionRounds"].endswith("EVOLUTION_ROUNDS.jsonl")
        assert "completionDecision" in handoff.artifactPaths
        assert "rankingUpdateReceipts" in handoff.artifactPaths
        assert "rankingUpdateReceiptContractPy" in handoff.sharedReferences
        assert "dashboardLinksMarkdown" in handoff.artifactPaths
        assert any("sharedReferences.schemaIndex" in action for action in handoff.nextActions)
        assert any("sharedReferences.mechanicsIntegrationContract" in action for action in handoff.nextActions)
        assert any("sync_pipeline_stage_artifacts" in action for action in handoff.nextActions)
        assert any("artifactPaths.dashboardLinksMarkdown" in action for action in handoff.nextActions)
        assert any(
            "python -m tools.policy.plan_strategy <run_dir>` when restoring persisted state" in action
            for action in handoff.nextActions
        )
        assert any(
            "Add `--phase <Configuration|Generation|Evolution|Insights from Reviews|Proximity|Ranking|"
            "Research Overview>` only when" in action
            for action in handoff.nextActions
        )
        assert any("next_action = run_configuration" in action for action in handoff.nextActions)
        assert any("research_plan/RESEARCH_PLAN.json" in action for action in handoff.nextActions)
        assert any("tools.update_hypothesis_proximity" in action for action in handoff.nextActions)
        assert any(
            "islands/ISLANDS.json" in action and "state/ISLANDS.json" in action for action in handoff.nextActions
        )
        assert any(
            "tools.update_run_single_island_reward" in action
            and "per-selected-island metrics validation" in action
            and "resumable blocked state" in action
            for action in handoff.nextActions
        )
        assert any(
            "proximity receipt" in action and "placeholder embeddings" in action for action in handoff.nextActions
        )
        assert any(
            "Ranking hard order is mandatory" in action
            and "tools.select_placement_opponents" in action
            and "tools.select_fallback_placement_opponents" in action
            and "tools.should_run_ranked_tournament" in action
            and "tools.apply_and_persist_elo_updates" in action
            and "ranking update receipt" in action
            and "implicit replacement for placement" in action
            for action in handoff.nextActions
        )
        assert any(
            "STRATEGY_DECISIONS.jsonl` is router-planning audit only" in action
            and "hypothesis counts" in action
            and "child IDs" in action
            and "artifactPaths.evolutionRounds" in action
            for action in handoff.nextActions
        )
        assert any(
            "Do not synthesize placeholder hypotheses" in action and "resumable blocked state" in action
            for action in handoff.nextActions
        )
        assert any(
            "exactly one router decision" in action
            and "one evolved child" in action
            and "one proximity receipt" in action
            for action in handoff.nextActions
        )
        assert any(
            "tools.append_evolution_round_record" in action and "ranking update receipts cover" in action
            for action in handoff.nextActions
        )
        assert any(
            "current convergence has not been reached" in action and "$co-scientist-resume" in action
            for action in handoff.nextActions
        )
        assert json_path.exists()
        assert markdown_path.exists()
        json_payload = json.loads(json_path.read_text(encoding="utf-8"))
        markdown_payload = markdown_path.read_text(encoding="utf-8")
        assert json_payload["validationSnapshot"]["status"] == "valid"
        assert "handoff-time validation snapshot" in json_payload["validationSnapshot"]["note"]
        assert "handoff-time validation snapshot" in markdown_payload
