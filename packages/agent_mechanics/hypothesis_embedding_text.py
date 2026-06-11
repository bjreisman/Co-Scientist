"""Canonical text formatting for hypothesis embedding input."""

from __future__ import annotations

from packages.agent_contracts import HypothesisContract


def format_hypothesis_for_embedding(hypothesis: HypothesisContract) -> str:
    """Return stable text used as the canonical embedding input for one hypothesis."""
    content = hypothesis.origin.content
    review = hypothesis.review
    review_summaries = [
        summary.strip() for summary in review.review_summary.summaries if isinstance(summary, str) and summary.strip()
    ]
    assumptions = [
        assumption.statement.strip()
        for assumption in review.deep_verification_review.assumptions
        if assumption.statement.strip()
    ]
    observations = [
        observation.reasoning.strip()
        for observation in review.observation_review.observations
        if observation.reasoning.strip()
    ]

    lines = [
        f"Hypothesis ID: {hypothesis.id}",
        f"Category: {content.category}",
        f"Summary: {content.summary}",
        f"Statement: {content.statement}",
        f"Mechanism: {content.mechanism}",
        f"Experimental design: {content.experimental_design}",
        f"Origin strategy: {hypothesis.origin.strategy}",
    ]
    if review_summaries:
        lines.append("Review summaries:")
        lines.extend(f"- {summary}" for summary in review_summaries)
    if assumptions:
        lines.append("Reviewed assumptions:")
        lines.extend(f"- {assumption}" for assumption in assumptions)
    if observations:
        lines.append("Reviewed observations:")
        lines.extend(f"- {observation}" for observation in observations)
    return "\n".join(lines).strip() + "\n"


__all__ = ["format_hypothesis_for_embedding"]
