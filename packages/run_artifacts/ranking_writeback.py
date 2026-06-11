"""Canonical ranking Elo closeout helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from packages.agent_contracts import (
    HypothesisContract,
    HypothesisMatchupContract,
    RankingUpdateReceiptContract,
    TournamentMatchContract,
)

from .hypothesis_writeback import persist_hypotheses


def apply_and_persist_elo_updates(
    run_dir: str | Path,
    matches: list[TournamentMatchContract],
    matchups: list[HypothesisMatchupContract],
    strategy: str,
    *,
    k_factor: float = 32.0,
    top_k_limit: int = 10,
    receipt_id: str | None = None,
) -> RankingUpdateReceiptContract:
    """Apply Elo updates, persist touched hypotheses, and write a ranking receipt."""
    from packages.agent_mechanics.elo_update import apply_elo_updates

    resolved_run_dir = Path(run_dir).resolve()
    stable_receipt_id = receipt_id or _ranking_receipt_id(strategy, [match.id for match in matches])
    receipt_path = resolved_run_dir / "state" / "ranking_update_receipts" / f"{stable_receipt_id}.json"
    if receipt_path.exists():
        return RankingUpdateReceiptContract.from_json_file(receipt_path)

    touched_hypotheses = _touched_hypotheses(matchups)
    elo_before = {hypothesis.id: hypothesis.elo_rating for hypothesis in touched_hypotheses}

    apply_elo_updates(matches, matchups, strategy, k_factor=k_factor)

    elo_after = {hypothesis.id: hypothesis.elo_rating for hypothesis in touched_hypotheses}
    updated_paths = persist_hypotheses(resolved_run_dir, touched_hypotheses, top_k_limit=top_k_limit)
    receipt = RankingUpdateReceiptContract(
        id=stable_receipt_id,
        status="completed",
        strategy=strategy,  # type: ignore[arg-type]
        match_ids=[match.id for match in matches],
        touched_hypothesis_ids=[hypothesis.id for hypothesis in touched_hypotheses],
        elo_before=elo_before,
        elo_after=elo_after,
        updated_hypothesis_paths=updated_paths,
        receipt_path=str(receipt_path.resolve()),
        created_at=datetime.now(UTC),
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt


def _touched_hypotheses(matchups: list[HypothesisMatchupContract]) -> list[HypothesisContract]:
    touched: list[HypothesisContract] = []
    seen_ids: set[str] = set()
    for matchup in matchups:
        for hypothesis in (matchup.hypothesis_1, matchup.hypothesis_2):
            if not hypothesis.id or hypothesis.id in seen_ids:
                continue
            touched.append(hypothesis)
            seen_ids.add(hypothesis.id)
    return touched


def _ranking_receipt_id(strategy: str, match_ids: list[str]) -> str:
    encoded = "\n".join([strategy, *match_ids]).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:12]
    return f"{strategy}-{digest}"


__all__ = ["apply_and_persist_elo_updates"]
