from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.agent_contracts import (
    HypothesisContentContract,
    HypothesisContract,
    HypothesisMatchupContract,
    InitialReviewContract,
    OriginContract,
    RankingUpdateReceiptContract,
    ReviewContract,
    ReviewSummaryContract,
    TournamentMatchContract,
)
from packages.agent_mechanics import apply_elo_updates
from packages.run_artifacts import ArtifactStore, apply_and_persist_elo_updates, persist_hypotheses


def make_hypothesis(hypothesis_id: str, rating: float) -> HypothesisContract:
    return HypothesisContract(
        id=hypothesis_id,
        elo_rating=rating,
        origin=OriginContract(
            status="completed",
            strategy="literature_exploration_generation",
            content=HypothesisContentContract(
                statement=f"Statement for {hypothesis_id}",
                mechanism="Mechanism",
                experimental_design="Experiment",
                summary=hypothesis_id,
                category="test",
            ),
        ),
        review=ReviewContract(initial_review=InitialReviewContract(status="completed", passed=True)),
    )


def make_match(
    match_id: str,
    hypothesis_1_id: str,
    hypothesis_2_id: str,
    winner_id: str,
    strategy: str,
) -> TournamentMatchContract:
    return TournamentMatchContract(
        id=match_id,
        status="completed",
        hypothesis_1_id=hypothesis_1_id,
        hypothesis_2_id=hypothesis_2_id,
        match_strategy=strategy,
        reasoning=f"{winner_id} wins",
        winner_id=winner_id,
    )


def test_apply_elo_updates_is_batch_order_independent() -> None:
    hypothesis_a = make_hypothesis("hyp-a", 1200.0)
    hypothesis_b = make_hypothesis("hyp-b", 1280.0)
    hypothesis_c = make_hypothesis("hyp-c", 1240.0)
    matchups = [
        HypothesisMatchupContract(hypothesis_1=hypothesis_a, hypothesis_2=hypothesis_b),
        HypothesisMatchupContract(hypothesis_1=hypothesis_c, hypothesis_2=hypothesis_a),
    ]
    matches = [
        make_match("match-1", "hyp-a", "hyp-b", "hyp-b", "placement_tournament"),
        make_match("match-2", "hyp-c", "hyp-a", "hyp-c", "placement_tournament"),
    ]
    apply_elo_updates(matches, matchups, "placement_tournament", k_factor=24.0)
    ordered_ratings = {
        hypothesis_a.id: hypothesis_a.elo_rating,
        hypothesis_b.id: hypothesis_b.elo_rating,
        hypothesis_c.id: hypothesis_c.elo_rating,
    }

    hypothesis_a_reversed = make_hypothesis("hyp-a", 1200.0)
    hypothesis_b_reversed = make_hypothesis("hyp-b", 1280.0)
    hypothesis_c_reversed = make_hypothesis("hyp-c", 1240.0)
    reversed_matchups = [
        HypothesisMatchupContract(hypothesis_1=hypothesis_c_reversed, hypothesis_2=hypothesis_a_reversed),
        HypothesisMatchupContract(hypothesis_1=hypothesis_a_reversed, hypothesis_2=hypothesis_b_reversed),
    ]
    reversed_matches = [
        make_match("match-2", "hyp-c", "hyp-a", "hyp-c", "placement_tournament"),
        make_match("match-1", "hyp-a", "hyp-b", "hyp-b", "placement_tournament"),
    ]
    apply_elo_updates(reversed_matches, reversed_matchups, "placement_tournament", k_factor=24.0)
    reversed_ratings = {
        hypothesis_a_reversed.id: hypothesis_a_reversed.elo_rating,
        hypothesis_b_reversed.id: hypothesis_b_reversed.elo_rating,
        hypothesis_c_reversed.id: hypothesis_c_reversed.elo_rating,
    }

    assert ordered_ratings == pytest.approx(reversed_ratings)


def test_apply_elo_updates_records_match_ids_for_placement_and_ranked_rounds() -> None:
    challenger = make_hypothesis("hyp-challenger", 1200.0)
    defender = make_hypothesis("hyp-defender", 1200.0)
    placement_matchup = [HypothesisMatchupContract(hypothesis_1=challenger, hypothesis_2=defender)]
    placement_matches = [make_match("placement-1", challenger.id, defender.id, challenger.id, "placement_tournament")]

    deltas = apply_elo_updates(placement_matches, placement_matchup, "placement_tournament", k_factor=16.0)

    assert deltas[challenger.id] > 0
    assert challenger.placement_match_ids == ["placement-1"]
    assert challenger.ranked_match_ids == []
    assert defender.ranked_match_ids == ["placement-1"]

    ranked_matches = [make_match("ranked-1", challenger.id, defender.id, defender.id, "ranked_tournament")]
    apply_elo_updates(ranked_matches, placement_matchup, "ranked_tournament", k_factor=16.0)

    assert challenger.ranked_match_ids == ["ranked-1"]
    assert defender.ranked_match_ids == ["placement-1", "ranked-1"]


def test_apply_elo_updates_is_idempotent_for_already_recorded_match_ids() -> None:
    challenger = make_hypothesis("hyp-challenger", 1200.0)
    defender = make_hypothesis("hyp-defender", 1200.0)
    matchups = [HypothesisMatchupContract(hypothesis_1=challenger, hypothesis_2=defender)]
    matches = [make_match("placement-1", challenger.id, defender.id, challenger.id, "placement_tournament")]

    apply_elo_updates(matches, matchups, "placement_tournament", k_factor=16.0)
    rating_after_first_apply = {
        challenger.id: challenger.elo_rating,
        defender.id: defender.elo_rating,
    }

    apply_elo_updates(matches, matchups, "placement_tournament", k_factor=16.0)

    assert {
        challenger.id: challenger.elo_rating,
        defender.id: defender.elo_rating,
    } == rating_after_first_apply
    assert challenger.placement_match_ids == ["placement-1"]
    assert defender.ranked_match_ids == ["placement-1"]


def test_persist_hypotheses_writes_touched_hypothesis_artifacts() -> None:
    challenger = make_hypothesis("hyp-challenger", 1200.0)
    defender = make_hypothesis("hyp-defender", 1200.0)
    matchups = [HypothesisMatchupContract(hypothesis_1=challenger, hypothesis_2=defender)]
    matches = [make_match("ranked-1", challenger.id, defender.id, defender.id, "ranked_tournament")]

    apply_elo_updates(matches, matchups, "ranked_tournament", k_factor=16.0)

    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        updated_paths = persist_hypotheses(run_dir, [challenger, defender], top_k_limit=8)

        assert len(updated_paths) == 2
        challenger_payload = json.loads(
            (run_dir / "hypotheses" / "hyp-challenger" / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )
        defender_payload = json.loads(
            (run_dir / "hypotheses" / "hyp-defender" / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )

        assert challenger_payload["ranked_match_ids"] == ["ranked-1"]
        assert defender_payload["ranked_match_ids"] == ["ranked-1"]
        assert challenger_payload["elo_rating"] != 1200.0
        assert defender_payload["elo_rating"] != 1200.0


def test_apply_and_persist_elo_updates_writes_ranking_receipt() -> None:
    challenger = make_hypothesis("hyp-challenger", 1200.0)
    defender = make_hypothesis("hyp-defender", 1200.0)
    matchups = [HypothesisMatchupContract(hypothesis_1=challenger, hypothesis_2=defender)]
    matches = [make_match("placement-1", challenger.id, defender.id, challenger.id, "placement_tournament")]

    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        receipt = apply_and_persist_elo_updates(
            run_dir,
            matches,
            matchups,
            "placement_tournament",
            k_factor=16.0,
            top_k_limit=8,
        )

        receipt_path = run_dir / "state" / "ranking_update_receipts" / f"{receipt.id}.json"
        persisted_receipt = RankingUpdateReceiptContract.from_json_file(receipt_path)
        challenger_payload = json.loads(
            (run_dir / "hypotheses" / challenger.id / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )
        defender_payload = json.loads(
            (run_dir / "hypotheses" / defender.id / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )

        assert receipt.status == "completed"
        assert persisted_receipt.id == receipt.id
        assert persisted_receipt.match_ids == ["placement-1"]
        assert persisted_receipt.strategy == "placement_tournament"
        assert persisted_receipt.touched_hypothesis_ids == ["hyp-challenger", "hyp-defender"]
        assert persisted_receipt.elo_before == {"hyp-challenger": 1200.0, "hyp-defender": 1200.0}
        assert persisted_receipt.elo_after["hyp-challenger"] > 1200.0
        assert persisted_receipt.elo_after["hyp-defender"] < 1200.0
        assert challenger_payload["elo_rating"] == persisted_receipt.elo_after["hyp-challenger"]
        assert defender_payload["elo_rating"] == persisted_receipt.elo_after["hyp-defender"]
        assert challenger_payload["placement_match_ids"] == ["placement-1"]
        assert defender_payload["ranked_match_ids"] == ["placement-1"]


def test_apply_and_persist_elo_updates_returns_existing_receipt_without_reapplying() -> None:
    challenger = make_hypothesis("hyp-challenger", 1200.0)
    defender = make_hypothesis("hyp-defender", 1200.0)
    matchups = [HypothesisMatchupContract(hypothesis_1=challenger, hypothesis_2=defender)]
    matches = [make_match("placement-1", challenger.id, defender.id, challenger.id, "placement_tournament")]

    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        first_receipt = apply_and_persist_elo_updates(
            run_dir,
            matches,
            matchups,
            "placement_tournament",
            k_factor=16.0,
            top_k_limit=8,
        )
        first_challenger_payload = json.loads(
            (run_dir / "hypotheses" / challenger.id / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )

        second_receipt = apply_and_persist_elo_updates(
            run_dir,
            matches,
            matchups,
            "placement_tournament",
            k_factor=16.0,
            top_k_limit=8,
        )
        second_challenger_payload = json.loads(
            (run_dir / "hypotheses" / challenger.id / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )

        assert second_receipt == first_receipt
        assert second_challenger_payload == first_challenger_payload
        assert second_challenger_payload["placement_match_ids"] == ["placement-1"]


def test_persist_hypotheses_does_not_overwrite_existing_review_stage_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=8)
        hypothesis = make_hypothesis("hyp-review", 1200.0).model_copy(
            update={
                "review": ReviewContract(
                    initial_review=InitialReviewContract(status="completed", passed=True),
                    review_summary=ReviewSummaryContract(
                        status="completed",
                        summaries=["Embedded summary before standalone review changes."],
                    ),
                )
            }
        )
        store.write_hypothesis(hypothesis)

        review_summary_path = run_dir / "hypotheses" / "hyp-review" / "REVIEW" / "REVIEW_SUMMARY.json"
        review_summary_path.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "summaries": ["Standalone review summary must survive Elo writeback."],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        touched_hypothesis = HypothesisContract.from_json_file(
            run_dir / "hypotheses" / "hyp-review" / "HYPOTHESIS.json"
        ).model_copy(update={"elo_rating": 1234.0})

        persist_hypotheses(run_dir, [touched_hypothesis], top_k_limit=8)

        stage_payload = json.loads(review_summary_path.read_text(encoding="utf-8"))
        hypothesis_payload = json.loads(
            (run_dir / "hypotheses" / "hyp-review" / "HYPOTHESIS.json").read_text(encoding="utf-8")
        )

        assert stage_payload["summaries"] == ["Standalone review summary must survive Elo writeback."]
        assert hypothesis_payload["elo_rating"] == 1234.0
