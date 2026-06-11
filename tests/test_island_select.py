from __future__ import annotations

from packages.agent_contracts import HypothesisContract, IslandStateContract
from packages.agent_mechanics import SelectionResult, select_island_hypotheses, select_island_ucb
from tests.conftest import build_hypothesis


class StubRng:
    def choice(self, items):
        return items[-1]

    def choices(self, population, weights, k):
        return [population[0]]


def test_select_island_hypotheses_switches_to_multi_island_when_stagnating() -> None:
    islands = {
        "island-a": IslandStateContract(id="island-a", decayed_reward=0.01, decayed_visits=1.0, visit_count=3),
        "island-b": IslandStateContract(id="island-b", decayed_reward=0.02, decayed_visits=1.0, visit_count=3),
        "island-c": IslandStateContract(id="island-c", decayed_reward=0.03, decayed_visits=1.0, visit_count=3),
    }
    hypotheses = {
        "hyp-a": build_hypothesis("hyp-a", 1410.0, "island-a"),
        "hyp-b": build_hypothesis("hyp-b", 1360.0, "island-b"),
        "hyp-c": build_hypothesis("hyp-c", 1280.0, "island-c"),
    }

    result = select_island_hypotheses(
        islands,
        hypotheses,
        iteration_count=5,
        ucb_exploration_constant=1.4,
        softmax_temperature=1.0,
        stagnation_epsilon=0.05,
        rng=StubRng(),
    )

    assert result.strategy == "multi_island"
    assert [hypothesis.id for hypothesis in result.hypotheses] == ["hyp-a", "hyp-b"]


def test_select_island_ucb_prefers_unvisited_islands() -> None:
    islands = {
        "visited": IslandStateContract(id="visited", decayed_reward=0.5, decayed_visits=1.0, visit_count=2),
        "unvisited-a": IslandStateContract(id="unvisited-a", decayed_reward=0.0, decayed_visits=0.0, visit_count=0),
        "unvisited-b": IslandStateContract(id="unvisited-b", decayed_reward=0.0, decayed_visits=0.0, visit_count=0),
    }

    selected = select_island_ucb(islands, iteration_count=10, ucb_exploration_constant=1.4, rng=StubRng())

    assert selected.id == "unvisited-b"


def test_selection_result_accepts_model_like_hypothesis_payloads() -> None:
    hypothesis = build_hypothesis("hyp-a", 1410.0, "island-a")

    result = SelectionResult(strategy="single_island", hypotheses=[hypothesis.model_dump(mode="json")])

    assert result.strategy == "single_island"
    assert result.hypotheses[0].id == "hyp-a"
    assert isinstance(result.hypotheses[0], HypothesisContract)
