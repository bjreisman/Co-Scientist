"""Convergence helpers for tracking top-k entry progress."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConvergenceCheckResult(BaseModel):
    """Result of checking whether a hypothesis entered the current top-k frontier."""

    model_config = ConfigDict(frozen=True)

    entered_top_k: bool = Field(description="Whether the hypothesis newly entered the top-k set.")
    convergence_count: int = Field(description="Updated convergence counter after applying the rule.")


def did_enter_top_k(
    hypothesis_id: str,
    previous_top_k_ids: set[str],
    current_top_k_ids: set[str],
) -> bool:
    """Return whether a hypothesis newly entered the top-k set."""
    return hypothesis_id in current_top_k_ids and hypothesis_id not in previous_top_k_ids


def update_convergence_count(current_convergence_count: int, entered_top_k: bool) -> int:
    """Apply the convergence counter update rule."""
    return 0 if entered_top_k else current_convergence_count + 1


def evaluate_convergence(
    hypothesis_id: str,
    previous_top_k_ids: set[str],
    current_top_k_ids: set[str],
    current_convergence_count: int,
) -> ConvergenceCheckResult:
    """Evaluate a single iteration's convergence update."""
    entered_top_k = did_enter_top_k(hypothesis_id, previous_top_k_ids, current_top_k_ids)
    return ConvergenceCheckResult(
        entered_top_k=entered_top_k,
        convergence_count=update_convergence_count(current_convergence_count, entered_top_k),
    )


__all__ = ["ConvergenceCheckResult", "did_enter_top_k", "evaluate_convergence", "update_convergence_count"]
