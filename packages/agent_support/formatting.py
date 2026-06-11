"""Host-neutral formatting helpers for plans, hypotheses, reviews, and meta-review summaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def format_bullet_list(items: Sequence[str], *, indent: int = 0) -> str:
    """Format a sequence of strings as a Markdown bullet list."""
    if not items:
        return "(none)"
    prefix = " " * indent + "- "
    return "\n".join(f"{prefix}{item}" for item in items)


def format_research_plan_context(plan: Any) -> dict[str, str]:
    """Render a research plan object as a dictionary of Markdown context blocks."""
    return {
        "research_goal": getattr(plan, "research_goal", "") or "",
        "preferences": format_bullet_list(getattr(plan, "preferences", []) or []),
        "constraints": format_bullet_list(getattr(plan, "constraints", []) or []),
    }


def _format_assumptions(assumptions: Sequence[Any], depth: int = 0) -> str:
    """Recursively format reviewed assumptions as an indented bullet list."""
    lines: list[str] = []
    for assumption in assumptions:
        correctness = getattr(assumption, "correctness", "")
        correctness_suffix = f" [{correctness}]" if correctness else ""
        lines.append(f"{'  ' * depth}- {getattr(assumption, 'statement', '')}{correctness_suffix}")
        sub_assumptions = getattr(assumption, "sub_assumptions", None) or []
        if sub_assumptions:
            lines.append(_format_assumptions(sub_assumptions, depth + 1))
    return "\n".join(lines)


def format_review(review: Any, *, heading_level: int = 3) -> str:  # noqa: C901
    """Render a hypothesis review object as a Markdown section."""
    prefix = "#" * heading_level
    parts: list[str] = []

    review_summary = getattr(review, "review_summary", None)
    if review_summary is not None and getattr(review_summary, "status", "") == "completed":
        parts.append(
            f"{prefix} Review Summary\n\n{format_bullet_list(getattr(review_summary, 'summaries', []) or [])}"
        )
        return "\n".join(parts) if parts else "(no reviews completed)"

    initial_review = getattr(review, "initial_review", None)
    if initial_review is not None and getattr(initial_review, "status", "") == "completed":
        verdict = "PASS" if getattr(initial_review, "passed", False) else "FAIL"
        parts.append(f"{prefix} Initial Review ({verdict})")
        preferences = getattr(initial_review, "preferences", []) or []
        constraints = getattr(initial_review, "constraints", []) or []
        if preferences:
            parts.append(f"\n**Preferences:**\n{format_bullet_list(preferences)}")
        if constraints:
            parts.append(f"\n**Constraints:**\n{format_bullet_list(constraints)}")

    full_review = getattr(review, "full_review", None)
    if full_review is not None and getattr(full_review, "status", "") == "completed":
        parts.append(f"\n{prefix} Full Review")
        preferences = getattr(full_review, "preferences", []) or []
        constraints = getattr(full_review, "constraints", []) or []
        if preferences:
            parts.append(f"\n**Preferences:**\n{format_bullet_list(preferences)}")
        if constraints:
            parts.append(f"\n**Constraints:**\n{format_bullet_list(constraints)}")

    deep_verification_review = getattr(review, "deep_verification_review", None)
    if deep_verification_review is not None:
        assumptions = getattr(deep_verification_review, "assumptions", []) or []
        if getattr(deep_verification_review, "status", "") == "completed" and assumptions:
            parts.append(f"\n{prefix} Deep Verification\n")
            parts.append(_format_assumptions(assumptions))

    observation_review = getattr(review, "observation_review", None)
    if observation_review is not None:
        observations = getattr(observation_review, "observations", []) or []
        if getattr(observation_review, "status", "") == "completed" and observations:
            parts.append(f"\n{prefix} Observation Review\n")
            parts.extend(
                f"- [{getattr(observation, 'conclusion', '')}] {getattr(observation, 'reasoning', '')}"
                for observation in observations
            )

    simulation_review = getattr(review, "simulation_review", None)
    if simulation_review is not None and getattr(simulation_review, "status", "") == "completed":
        steps = getattr(simulation_review, "steps", []) or []
        failure_scenarios = getattr(simulation_review, "failure_scenarios", []) or []
        if steps:
            parts.append(f"\n{prefix} Simulation Steps\n")
            parts.append(format_bullet_list(steps))
        if failure_scenarios:
            parts.append(f"\n{prefix} Failure Scenarios\n")
            parts.append(format_bullet_list(failure_scenarios))

    return "\n".join(parts) if parts else "(no reviews completed)"


def format_hypothesis(hypothesis: Any, *, heading_level: int = 3) -> str:
    """Render a hypothesis object as a Markdown section."""
    prefix = "#" * heading_level
    origin = getattr(hypothesis, "origin", None)
    content = getattr(origin, "content", None) if origin is not None else None
    parts = [f"{prefix} Hypothesis {getattr(hypothesis, 'id', '')}"]
    if content is not None:
        parts.append(f"\n**Summary:** {getattr(content, 'summary', '')}")
        parts.append(f"\n**Statement:** {getattr(content, 'statement', '')}")
        parts.append(f"\n**Mechanism:** {getattr(content, 'mechanism', '')}")
        parts.append(f"\n**Experimental Design:** {getattr(content, 'experimental_design', '')}")
        parts.append(f"\n**Category:** {getattr(content, 'category', '')}")
    return "\n".join(parts)


def format_hypothesis_with_review(hypothesis: Any, *, heading_level: int = 3) -> str:
    """Render a hypothesis together with its review as a Markdown section."""
    parts = [
        format_hypothesis(hypothesis, heading_level=heading_level),
        "",
        format_review(getattr(hypothesis, "review", None), heading_level=heading_level + 1),
    ]
    return "\n".join(parts)


def format_meta_review_context(meta_review: Any) -> str:
    """Render a meta-review object as a Markdown context block."""
    insights = getattr(meta_review, "insights_from_reviews", None)
    if insights is not None and getattr(insights, "status", "") == "completed":
        content = getattr(insights, "content", []) or []
        if content:
            return format_bullet_list(content)
    return "(no meta-review available)"
