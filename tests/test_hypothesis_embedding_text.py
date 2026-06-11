from __future__ import annotations

from packages.agent_mechanics import format_hypothesis_for_embedding, input_text_hash
from tests.conftest import build_hypothesis


def test_format_hypothesis_for_embedding_is_stable() -> None:
    hypothesis = build_hypothesis(
        "hyp-001",
        1234.0,
        "island-001",
        summary="Vacancy-mediated catalyst activation",
        category="catalyst-design",
    )

    first = format_hypothesis_for_embedding(hypothesis)
    second = format_hypothesis_for_embedding(hypothesis)

    assert first == second
    assert "Hypothesis ID: hyp-001" in first
    assert "Vacancy-mediated catalyst activation" in first
    assert input_text_hash(first) == input_text_hash(second)
