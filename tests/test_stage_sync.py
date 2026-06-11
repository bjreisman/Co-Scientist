from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.agent_contracts import CoScientistStateContract, ResearchPlanContract
from packages.run_artifacts import ArtifactStore, sync_pipeline_stage_artifacts


def _build_minimal_state() -> CoScientistStateContract:
    return CoScientistStateContract(
        research_plan=ResearchPlanContract(status="completed", research_goal="Test stage synchronization."),
    )


def test_sync_pipeline_stage_artifacts_updates_pipeline_state_and_current_stage_together() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.bootstrap()
        state = _build_minimal_state()
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Generation",
            current_skill="hypothesis-generation-pipeline",
            stage_trail=["Generation"],
        )

        pipeline_state, current_stage = sync_pipeline_stage_artifacts(
            run_dir,
            current_phase="Proximity",
            current_skill="hypothesis-proximity-update",
        )

        persisted_pipeline = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        persisted_stage = json.loads((run_dir / "state" / "CURRENT_STAGE.json").read_text(encoding="utf-8"))

        assert pipeline_state.currentPhase == "Proximity"
        assert pipeline_state.currentSkill == "hypothesis-proximity-update"
        assert current_stage.stage == "Proximity"
        assert persisted_pipeline["currentPhase"] == "Proximity"
        assert persisted_pipeline["currentSkill"] == "hypothesis-proximity-update"
        assert persisted_pipeline["stageTrail"] == ["Generation", "Proximity"]
        assert persisted_stage["stage"] == "Proximity"
        assert persisted_stage["stageTrail"] == ["Generation", "Proximity"]


def test_sync_pipeline_stage_artifacts_rejects_non_canonical_skill_for_phase() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.bootstrap()
        state = _build_minimal_state()
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Generation",
            current_skill="hypothesis-generation-pipeline",
            stage_trail=["Generation"],
        )

        with pytest.raises(ValueError, match="expects 'hypothesis-proximity-update'"):
            sync_pipeline_stage_artifacts(
                run_dir,
                current_phase="Proximity",
                current_skill="insights-from-reviews",
            )


def test_sync_pipeline_stage_artifacts_supports_fresh_bootstrap_configuration_transition() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.bootstrap()

        pipeline_state, current_stage = sync_pipeline_stage_artifacts(
            run_dir,
            current_phase="Configuration",
            current_skill="research-config",
        )

        persisted_pipeline = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        persisted_stage = json.loads((run_dir / "state" / "CURRENT_STAGE.json").read_text(encoding="utf-8"))

        assert pipeline_state.currentPhase == "Configuration"
        assert pipeline_state.currentSkill == "research-config"
        assert pipeline_state.status == "not_started"
        assert current_stage.stage == "Configuration"
        assert persisted_pipeline["currentPhase"] == "Configuration"
        assert persisted_pipeline["currentSkill"] == "research-config"
        assert persisted_pipeline["stageTrail"] == []
        assert persisted_stage["stage"] == "Configuration"
        assert persisted_stage["stageTrail"] == []


def test_sync_pipeline_stage_artifacts_normalizes_not_started_for_active_phase() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=2)
        store.bootstrap()

        pipeline_state, _ = sync_pipeline_stage_artifacts(
            run_dir,
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )

        persisted_pipeline = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))

        assert pipeline_state.currentPhase == "Evolution"
        assert pipeline_state.status == "running"
        assert persisted_pipeline["status"] == "running"
