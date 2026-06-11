from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from packages.agent_contracts import (
    CoScientistStateContract,
    EmbeddingProviderConfigContract,
    HypothesisMatchupContract,
    IslandStateContract,
    ResearchPlanContract,
    TournamentMatchContract,
)
from packages.agent_mechanics import update_hypothesis_proximity
from packages.run_artifacts import ArtifactStore, apply_and_persist_elo_updates
from tests.conftest import build_hypothesis
from tools.validation.contract_validation import validate_run_artifacts


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_config(run_dir: Path) -> None:
    (run_dir / "input.md").write_text("# Backfill Run\n\nInvestigate response drift.\n", encoding="utf-8")
    (run_dir / "config.yaml").write_text("input_file: input.md\n", encoding="utf-8")


def _write_strategy_decisions(
    run_dir: Path,
    *,
    round_signal_updates: dict[str, Any] | None = None,
) -> None:
    round_signals = {
        "hypothesis_count": 1,
        "viable_hypothesis_count": 1,
        "selection_strategy": "single_island",
        "selected_parent_ids": ["hyp-001"],
        "selected_island_ids": ["island-001"],
        "top_hypothesis_ids": ["hyp-001"],
        "convergence_count": 1,
        "convergence_threshold": 3,
        "entered_top_k_last_round": None,
        "research_plan_status": "valid",
    }
    if round_signal_updates:
        for key, value in round_signal_updates.items():
            if value is None:
                round_signals.pop(key, None)
            else:
                round_signals[key] = value

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
                "reasoning": ["Seed the frontier."],
                "advisory_recommendation": "inspect_state",
                "signals": {"top_hypothesis_ids": []},
                "status": "planned",
            }
        )
        + "\n"
        + json.dumps(
            {
                "run_id": run_dir.name,
                "decision_index": 2,
                "current_phase": "Evolution",
                "next_action": "continue_evolution",
                "selected_generation_strategies": [],
                "selected_evolution_strategies": ["grounding_evolution", "coherence_evolution"],
                "max_new_hypotheses": 0,
                "reasoning": ["Continue evolving."],
                "advisory_recommendation": "continue_evolution",
                "signals": round_signals,
                "status": "planned",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _prepare_backfill_run(
    run_dir: Path,
    *,
    round_signal_updates: dict[str, Any] | None = None,
) -> None:
    _write_config(run_dir)
    store = ArtifactStore(run_dir, top_k_limit=3)
    store.bootstrap()
    parent = build_hypothesis("hyp-001", 1200.0, "island-001")
    child = build_hypothesis(
        "hyp-002",
        1200.0,
        "island-001",
        parent_ids=["hyp-001"],
        strategy="grounding_evolution",
    )
    match = TournamentMatchContract(
        id="match-001",
        status="completed",
        hypothesis_1_id=child.id,
        hypothesis_2_id=parent.id,
        match_strategy="placement_tournament",
        reasoning="The evolved child is more specific and testable than its parent.",
        winner_id=child.id,
    )
    state = CoScientistStateContract(
        research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
        hypotheses={parent.id: parent, child.id: child},
        tournament_matches={match.id: match},
        islands={
            "island-001": IslandStateContract(id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5)
        },
        iteration_count=1,
        convergence_count=0,
    )
    store.write_research_plan(state.research_plan)
    store.write_hypothesis(parent)
    store.write_hypothesis(child)
    update_hypothesis_proximity(
        run_dir,
        child.id,
        config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
    )
    store.write_tournaments(state)
    apply_and_persist_elo_updates(
        run_dir,
        [match],
        [HypothesisMatchupContract(hypothesis_1=child, hypothesis_2=parent)],
        "placement_tournament",
        top_k_limit=3,
    )
    store.write_islands(state)
    store.write_pipeline_state(
        state,
        mode="host-agent",
        status="running",
        current_phase="Evolution",
        current_skill="hypothesis-evolution-loop",
        stage_trail=["Generation", "Evolution"],
    )
    store.write_evolution_state(
        state,
        convergence_threshold=3,
        max_iterations=6,
        safety_max_iterations=12,
        effective_top_k=2,
        status="running",
        entered_top_k_last_round=True,
        last_selected_strategy="grounding_evolution",
        last_selected_island="island-001",
    )
    _write_strategy_decisions(run_dir, round_signal_updates=round_signal_updates)


def _run_backfill(run_dir: Path, *, apply: bool = False) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "tools.migration.backfill_evolution_rounds", str(run_dir)]
    if apply:
        command.append("--apply")
    return subprocess.run(
        command,
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_evolution_round_backfill_dry_run_does_not_write_records() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_backfill_run(run_dir)

        result = _run_backfill(run_dir)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "ready"
        assert payload["apply"] is False
        assert payload["proposed_record_count"] == 1
        assert payload["records"][0]["child_hypothesis_id"] == "hyp-002"
        assert not (run_dir / "state" / "EVOLUTION_ROUNDS.jsonl").exists()


def test_evolution_round_backfill_keeps_only_child_owned_ranked_matches_in_round_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_backfill_run(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        parent = build_hypothesis("hyp-001", 1250.0, "island-001")
        child = build_hypothesis(
            "hyp-002",
            1310.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="grounding_evolution",
        )
        later_challenger = build_hypothesis("hyp-003", 1260.0, "island-002", passed=False)
        placement_match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=child.id,
            hypothesis_2_id=parent.id,
            match_strategy="placement_tournament",
            reasoning="The evolved child is more specific and testable than its parent.",
            winner_id=child.id,
        )
        child_owned_ranked_match = TournamentMatchContract(
            id="match-002",
            status="completed",
            hypothesis_1_id=child.id,
            hypothesis_2_id=parent.id,
            match_strategy="ranked_tournament",
            reasoning="The evolved child remains stronger in a ranked comparison.",
            winner_id=child.id,
        )
        opponent_owned_ranked_match = TournamentMatchContract(
            id="match-003",
            status="completed",
            hypothesis_1_id=later_challenger.id,
            hypothesis_2_id=child.id,
            match_strategy="ranked_tournament",
            reasoning="The later challenger still loses to the evolved child.",
            winner_id=child.id,
        )
        parent = parent.model_copy(update={"ranked_match_ids": ["match-001", "match-002"]})
        child = child.model_copy(
            update={
                "placement_match_ids": ["match-001"],
                "ranked_match_ids": ["match-002", "match-003"],
            }
        )
        later_challenger = later_challenger.model_copy(update={"ranked_match_ids": ["match-003"]})
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={parent.id: parent, child.id: child, later_challenger.id: later_challenger},
            tournament_matches={
                placement_match.id: placement_match,
                child_owned_ranked_match.id: child_owned_ranked_match,
                opponent_owned_ranked_match.id: opponent_owned_ranked_match,
            },
        )
        store.write_hypothesis(parent)
        store.write_hypothesis(child)
        store.write_hypothesis(later_challenger)
        store.write_tournaments(state)

        result = _run_backfill(run_dir)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["records"][0]["ranked_match_ids"] == ["match-002"]


def test_evolution_round_backfill_apply_writes_valid_records() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_backfill_run(run_dir)

        result = _run_backfill(run_dir, apply=True)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "applied"
        output_path = run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
        assert len(output_path.read_text(encoding="utf-8").splitlines()) == 1
        validation = validate_run_artifacts(run_dir, requested_skill="co-scientist-pipeline")
        assert validation.status == "valid"


def test_evolution_round_backfill_blocks_when_top_k_signal_is_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_backfill_run(run_dir, round_signal_updates={"top_hypothesis_ids": None})

        result = _run_backfill(run_dir, apply=True)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "blocked"
        assert payload["unresolved_count"] == 1
        assert "top_hypothesis_ids" in payload["unresolved"][0]["reason"]
        assert not (run_dir / "state" / "EVOLUTION_ROUNDS.jsonl").exists()


def test_evolution_round_backfill_refuses_existing_round_log() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_backfill_run(run_dir)
        first_result = _run_backfill(run_dir, apply=True)
        assert first_result.returncode == 0, first_result.stderr

        second_result = _run_backfill(run_dir, apply=True)

        assert second_result.returncode == 1, second_result.stderr
        payload = json.loads(second_result.stdout)
        assert payload["status"] == "blocked"
        assert payload["existing_record_count"] == 1
