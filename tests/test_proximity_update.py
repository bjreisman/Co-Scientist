from __future__ import annotations

import pytest

from packages.agent_contracts import ProximityGraphContract
from packages.agent_mechanics import compute_cosine_similarities, update_proximity_graph


def test_compute_cosine_similarities_handles_zero_norm_embeddings() -> None:
    similarities = compute_cosine_similarities({"hyp-a": [0.0, 0.0], "hyp-b": [1.0, 0.0]}, [0.0, 1.0])

    assert similarities["hyp-a"] == 0.0
    assert similarities["hyp-b"] == pytest.approx(0.0)


def test_update_proximity_graph_adds_symmetric_similarity_entries() -> None:
    graph = ProximityGraphContract(
        embeddings={"hyp-a": [1.0, 0.0], "hyp-b": [0.0, 1.0]},
        similarities={"hyp-a": {"hyp-b": 0.0}, "hyp-b": {"hyp-a": 0.0}},
    )

    updated_graph = update_proximity_graph(graph, "hyp-c", [1.0, 1.0])

    assert updated_graph.embeddings["hyp-c"] == [1.0, 1.0]
    assert updated_graph.similarities["hyp-c"]["hyp-a"] == pytest.approx(0.70710678, rel=1e-6)
    assert updated_graph.similarities["hyp-a"]["hyp-c"] == pytest.approx(0.70710678, rel=1e-6)
    assert updated_graph.similarities["hyp-c"]["hyp-b"] == pytest.approx(0.70710678, rel=1e-6)


def test_update_proximity_graph_is_idempotent_for_existing_hypothesis() -> None:
    graph = ProximityGraphContract(
        embeddings={"hyp-a": [1.0, 0.0]},
        similarities={"hyp-a": {}},
    )

    updated_graph = update_proximity_graph(graph, "hyp-a", [0.0, 1.0])

    assert updated_graph.embeddings["hyp-a"] == [1.0, 0.0]
