from __future__ import annotations

from packages.agent_mechanics import did_enter_top_k, evaluate_convergence, update_convergence_count


def test_did_enter_top_k_detects_new_entry() -> None:
    assert did_enter_top_k("hyp-1", {"hyp-2"}, {"hyp-1", "hyp-2"}) is True
    assert did_enter_top_k("hyp-1", {"hyp-1"}, {"hyp-1", "hyp-2"}) is False


def test_update_convergence_count_resets_on_entry_and_increments_otherwise() -> None:
    assert update_convergence_count(3, entered_top_k=True) == 0
    assert update_convergence_count(3, entered_top_k=False) == 4


def test_evaluate_convergence_returns_both_fields() -> None:
    result = evaluate_convergence(
        "hyp-3",
        previous_top_k_ids={"hyp-1", "hyp-2"},
        current_top_k_ids={"hyp-1", "hyp-3"},
        current_convergence_count=2,
    )

    assert result.entered_top_k is True
    assert result.convergence_count == 0
