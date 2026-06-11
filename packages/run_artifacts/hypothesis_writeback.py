"""Deterministic helpers for persisting touched hypothesis artifacts."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from packages.agent_contracts import HypothesisContract

from .artifact_io import ArtifactStore


def persist_hypotheses(
    run_dir: str | Path,
    hypotheses: Iterable[HypothesisContract],
    *,
    top_k_limit: int = 10,
) -> list[str]:
    """Persist touched hypotheses back to canonical artifact bundles.

    Standalone review files are intentionally left untouched.
    """
    resolved_run_dir = Path(run_dir).resolve()
    artifact_store = ArtifactStore(resolved_run_dir, top_k_limit=top_k_limit)
    artifact_store.ensure_layout()

    updated_ids: list[str] = []
    seen_ids: set[str] = set()
    for hypothesis in hypotheses:
        if not hypothesis.id or hypothesis.id in seen_ids:
            continue
        artifact_store.write_hypothesis(hypothesis, write_review_stage_files=False)
        seen_ids.add(hypothesis.id)
        updated_ids.append(hypothesis.id)

    return [
        str((resolved_run_dir / "hypotheses" / hypothesis_id / "HYPOTHESIS.json").resolve())
        for hypothesis_id in updated_ids
    ]


__all__ = ["persist_hypotheses"]
