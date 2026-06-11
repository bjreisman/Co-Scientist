"""Pure similarity update helpers for hypothesis proximity graphs."""

from __future__ import annotations

import numpy as np

from packages.agent_contracts import ProximityGraphContract as ProximityGraph


def compute_cosine_similarities(
    existing_embeddings: dict[str, list[float]],
    new_embedding: list[float],
) -> dict[str, float]:
    """Compute cosine similarity from a new embedding to all existing embeddings."""
    existing_ids = list(existing_embeddings)
    if not existing_ids:
        return {}

    new_vector = np.array(new_embedding, dtype=float)
    new_norm = np.linalg.norm(new_vector)
    existing_matrix = np.array([existing_embeddings[hypothesis_id] for hypothesis_id in existing_ids], dtype=float)
    existing_norms = np.linalg.norm(existing_matrix, axis=1)

    similarities = np.zeros(len(existing_ids), dtype=float)
    if new_norm > 0:
        dot_products = np.dot(existing_matrix, new_vector)
        valid_mask = existing_norms > 0
        similarities[valid_mask] = dot_products[valid_mask] / (new_norm * existing_norms[valid_mask])

    return {
        hypothesis_id: float(similarity) for hypothesis_id, similarity in zip(existing_ids, similarities, strict=True)
    }


def update_proximity_graph(
    graph: ProximityGraph,
    hypothesis_id: str,
    embedding: list[float],
) -> ProximityGraph:
    """Insert one embedding into the graph and update pairwise similarities."""
    if hypothesis_id in graph.embeddings:
        return graph

    similarity_updates = compute_cosine_similarities(graph.embeddings, embedding)
    graph.embeddings[hypothesis_id] = embedding
    graph.similarities[hypothesis_id] = {}

    for other_id, similarity in similarity_updates.items():
        graph.similarities[hypothesis_id][other_id] = similarity
        graph.similarities.setdefault(other_id, {})[hypothesis_id] = similarity

    return graph


__all__ = ["compute_cosine_similarities", "update_proximity_graph"]
