from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    HypothesisContentContract,
    HypothesisContract,
    InitialReviewContract,
    IslandStateContract,
    OriginContract,
    ReviewContract,
)
from packages.agent_mechanics import (
    apply_decayed_island_update,
    compute_single_island_reward,
    update_single_island_reward,
)
from packages.run_artifacts import (
    ArtifactStore,
    ensure_run_islands_for_hypotheses,
    persist_run_islands,
    update_run_single_island_reward,
)


def make_hypothesis(hypothesis_id: str, rating: float, island_id: str, *, viable: bool = True) -> HypothesisContract:
    return HypothesisContract(
        id=hypothesis_id,
        elo_rating=rating,
        island_id=island_id,
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
        review=ReviewContract(initial_review=InitialReviewContract(status="completed", passed=viable)),
    )


def test_compute_single_island_reward_matches_existing_rule() -> None:
    candidate = make_hypothesis("candidate", 1450.0, "", viable=True)
    hypotheses = {
        "parent-a": make_hypothesis("parent-a", 1300.0, "island-a"),
        "parent-b": make_hypothesis("parent-b", 1250.0, "island-a"),
        "other": make_hypothesis("other", 1450.0, "island-b"),
        "candidate": candidate,
    }

    reward = compute_single_island_reward(hypotheses, "island-a", candidate)

    assert reward == 1.0


def test_apply_decayed_island_update_only_increments_selected_island() -> None:
    islands = {
        "island-a": IslandStateContract(id="island-a", decayed_reward=1.0, decayed_visits=2.0, visit_count=3),
        "island-b": IslandStateContract(id="island-b", decayed_reward=0.8, decayed_visits=1.5, visit_count=2),
    }

    apply_decayed_island_update(islands, "island-b", reward=0.5, decay_factor=0.5)

    assert islands["island-a"].decayed_reward == 0.5
    assert islands["island-a"].decayed_visits == 1.0
    assert islands["island-a"].visit_count == 3

    assert islands["island-b"].decayed_reward == 0.9
    assert islands["island-b"].decayed_visits == 1.75
    assert islands["island-b"].visit_count == 3


def test_update_single_island_reward_combines_compute_and_apply() -> None:
    candidate = make_hypothesis("candidate", 1380.0, "", viable=True)
    hypotheses = {
        "parent-a": make_hypothesis("parent-a", 1300.0, "island-a"),
        "parent-b": make_hypothesis("parent-b", 1200.0, "island-a"),
        "candidate": candidate,
    }
    islands = {"island-a": IslandStateContract(id="island-a", decayed_reward=1.0, decayed_visits=1.0, visit_count=1)}

    reward = update_single_island_reward(islands, hypotheses, "island-a", candidate, decay_factor=0.5)

    assert reward > 0.0
    assert islands["island-a"].visit_count == 2


def test_update_run_single_island_reward_persists_canonical_island_artifact() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)
        store.ensure_layout()
        hypotheses = {
            "parent-a": make_hypothesis("parent-a", 1300.0, "island-a"),
            "parent-b": make_hypothesis("parent-b", 1200.0, "island-a"),
            "candidate": make_hypothesis("candidate", 1380.0, "island-a"),
            "other": make_hypothesis("other", 1320.0, "island-b"),
        }
        for hypothesis in hypotheses.values():
            store.write_hypothesis(hypothesis)
        persist_run_islands(
            run_dir,
            {
                "island-a": IslandStateContract(
                    id="island-a",
                    decayed_reward=1.0,
                    decayed_visits=1.0,
                    visit_count=1,
                ),
                "island-b": IslandStateContract(
                    id="island-b",
                    decayed_reward=0.5,
                    decayed_visits=1.0,
                    visit_count=1,
                ),
            },
            hypotheses=hypotheses,
        )

        result = update_run_single_island_reward(
            run_dir,
            "island-a",
            "candidate",
            decay_factor=0.5,
        )

        assert result.selected_island_id == "island-a"
        assert result.candidate_hypothesis_id == "candidate"
        assert result.reward > 0.0
        assert result.updated_islands["island-a"].visit_count == 2
        payload = json.loads((run_dir / "islands" / "ISLANDS.json").read_text(encoding="utf-8"))
        assert {item["id"] for item in payload["items"]} == {"island-a", "island-b"}
        assert all("decayed_reward" in item for item in payload["items"])
        assert all("decayed_visits" in item for item in payload["items"])
        assert all("island_id" not in item for item in payload["items"])
        assert all("reward" not in item for item in payload["items"])


def test_ensure_run_islands_for_hypotheses_creates_unvisited_island_items() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)
        hypothesis = make_hypothesis("hyp-001", 1200.0, "island-001")
        store.write_hypothesis(hypothesis)

        result = ensure_run_islands_for_hypotheses(run_dir)

        payload = json.loads((run_dir / "islands" / "ISLANDS.json").read_text(encoding="utf-8"))
        assert result.initialized_island_ids == ["island-001"]
        assert result.preserved_island_ids == []
        assert payload["items"] == [
            {
                "id": "island-001",
                "decayed_reward": 0.0,
                "decayed_visits": 0.0,
                "visit_count": 0,
            }
        ]


def test_ensure_run_islands_for_hypotheses_preserves_existing_metrics() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir)
        hypothesis = make_hypothesis("hyp-001", 1300.0, "island-001")
        store.write_hypothesis(hypothesis)
        persist_run_islands(
            run_dir,
            {
                "island-001": IslandStateContract(
                    id="island-001",
                    decayed_reward=0.7,
                    decayed_visits=1.5,
                    visit_count=2,
                )
            },
            hypotheses={"hyp-001": hypothesis},
        )

        result = ensure_run_islands_for_hypotheses(run_dir)

        payload = json.loads((run_dir / "islands" / "ISLANDS.json").read_text(encoding="utf-8"))
        assert result.initialized_island_ids == []
        assert result.preserved_island_ids == ["island-001"]
        assert payload["items"][0]["decayed_reward"] == 0.7
        assert payload["items"][0]["decayed_visits"] == 1.5
        assert payload["items"][0]["visit_count"] == 2
