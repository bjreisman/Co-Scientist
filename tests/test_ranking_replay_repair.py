from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    CoScientistStateContract,
    EmbeddingProviderConfigContract,
    IslandStateContract,
    ResearchPlanContract,
    TournamentMatchContract,
)
from packages.agent_mechanics import update_hypothesis_proximity
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis
from tools.migration.replay_ranking_elo import replay_ranking_elo
from tools.validation.contract_validation import validate_run_artifacts


def _prepare_drifted_run(run_dir: Path) -> None:
    store = ArtifactStore(run_dir, top_k_limit=3)
    store.bootstrap()
    candidate = build_hypothesis("hyp-001", 1200.0, "island-001")
    candidate = candidate.model_copy(update={"placement_match_ids": ["match-001"]})
    opponent = build_hypothesis("hyp-002", 1200.0, "island-002")
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
            "island-001": IslandStateContract(id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5),
            "island-002": IslandStateContract(id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2),
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
        stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
    )
    store.write_current_stage("Ranking", ["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"])


def test_replay_ranking_elo_dry_run_reports_drift_without_writing() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_drifted_run(run_dir)

        report = replay_ranking_elo(run_dir, write=False, top_k_limit=3)

        assert report["status"] == "drift_found"
        assert report["write"] is False
        assert report["diffs"]
        assert not (run_dir / "state" / "ranking_update_receipts").exists()
        persisted_candidate = json.loads(
            (run_dir / "hypotheses" / "hyp-001" / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )
        assert persisted_candidate["elo_rating"] == 1200.0


def test_replay_ranking_elo_write_repairs_hypotheses_and_receipts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_drifted_run(run_dir)

        report = replay_ranking_elo(run_dir, write=True, top_k_limit=3)
        validation = validate_run_artifacts(run_dir, requested_skill="hypothesis-ranking-pipeline")

        assert report["status"] == "repaired"
        assert report["write"] is True
        assert report["updatedHypothesisIds"] == ["hyp-001", "hyp-002"]
        assert (run_dir / "state" / "ranking_update_receipts").exists()
        assert validation.status == "valid"
