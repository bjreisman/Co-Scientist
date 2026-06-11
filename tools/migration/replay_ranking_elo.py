"""Dry-run and explicit repair tool for ranking Elo writeback drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.agent_contracts import (
    EvolutionRoundRecordContract,
    HypothesisContract,
    HypothesisMatchupContract,
    RankingUpdateReceiptContract,
    TournamentMatchContract,
)
from packages.run_artifacts import persist_hypotheses


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay ranking Elo updates and optionally repair run artifacts.")
    parser.add_argument("run_dir", type=Path, help="Path to the run directory.")
    parser.add_argument("--write", action="store_true", help="Persist repaired hypotheses and ranking receipts.")
    parser.add_argument("--top-k-limit", type=int, default=10, help="Top-k limit used by hypothesis persistence.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional path to write the JSON report.")
    return parser.parse_args(argv)


def _load_hypotheses(run_dir: Path) -> dict[str, HypothesisContract]:
    hypotheses_root = run_dir / "hypotheses"
    if not hypotheses_root.exists():
        return {}
    hypotheses: dict[str, HypothesisContract] = {}
    for hypothesis_dir in sorted(path for path in hypotheses_root.iterdir() if path.is_dir()):
        hypothesis_path = hypothesis_dir / "HYPOTHESIS.json"
        if not hypothesis_path.exists():
            continue
        hypothesis = HypothesisContract.from_json_file(hypothesis_path)
        hypotheses[hypothesis.id] = hypothesis
    return hypotheses


def _load_tournaments(run_dir: Path) -> dict[str, TournamentMatchContract]:
    tournaments_root = run_dir / "tournaments"
    if not tournaments_root.exists():
        return {}
    tournaments: dict[str, TournamentMatchContract] = {}
    for tournament_path in sorted(
        path for path in tournaments_root.iterdir() if path.is_file() and path.suffix == ".json"
    ):
        match = TournamentMatchContract.from_json_file(tournament_path)
        tournaments[match.id] = match
    return tournaments


def _load_evolution_rounds(run_dir: Path) -> list[EvolutionRoundRecordContract]:
    return EvolutionRoundRecordContract.from_jsonl_file(run_dir / "state" / "EVOLUTION_ROUNDS.jsonl")


def _ordered_tournament_replay_groups(
    tournament_payloads_by_id: dict[str, TournamentMatchContract],
    evolution_round_records: Sequence[EvolutionRoundRecordContract],
) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    round_match_ids: set[str] = set()
    for record in evolution_round_records:
        round_match_ids.update(record.placement_match_ids)
        round_match_ids.update(record.ranked_match_ids)

    for strategy in ("placement_tournament", "ranked_tournament"):
        initial_match_ids = [
            match_id
            for match_id, match_payload in sorted(tournament_payloads_by_id.items())
            if match_id not in round_match_ids
            and match_payload.status == "completed"
            and match_payload.match_strategy == strategy
        ]
        if initial_match_ids:
            groups.append((strategy, initial_match_ids))

    for record in sorted(evolution_round_records, key=lambda item: item.round_index):
        placement_match_ids = [
            match_id
            for match_id in record.placement_match_ids
            if (match_payload := tournament_payloads_by_id.get(match_id)) is not None
            and match_payload.status == "completed"
            and match_payload.match_strategy == "placement_tournament"
        ]
        if placement_match_ids:
            groups.append(("placement_tournament", placement_match_ids))
        ranked_match_ids = [
            match_id
            for match_id in record.ranked_match_ids
            if (match_payload := tournament_payloads_by_id.get(match_id)) is not None
            and match_payload.status == "completed"
            and match_payload.match_strategy == "ranked_tournament"
        ]
        if ranked_match_ids:
            groups.append(("ranked_tournament", ranked_match_ids))

    return groups


def _receipt_id(strategy: str, match_ids: list[str]) -> str:
    digest = hashlib.sha256("\n".join([strategy, *match_ids]).encode("utf-8")).hexdigest()[:12]
    return f"repair-{strategy}-{digest}"


def _hypothesis_path(run_dir: Path, hypothesis_id: str) -> str:
    return str((run_dir / "hypotheses" / hypothesis_id / "HYPOTHESIS.json").resolve())


def _build_diff(
    persisted: HypothesisContract,
    replayed: HypothesisContract,
) -> dict[str, Any] | None:
    rating_changed = abs(persisted.elo_rating - replayed.elo_rating) > 1e-6
    placement_changed = persisted.placement_match_ids != replayed.placement_match_ids
    ranked_changed = persisted.ranked_match_ids != replayed.ranked_match_ids
    if not (rating_changed or placement_changed or ranked_changed):
        return None
    return {
        "hypothesisId": persisted.id,
        "persistedElo": persisted.elo_rating,
        "expectedElo": replayed.elo_rating,
        "persistedPlacementMatchIds": persisted.placement_match_ids,
        "expectedPlacementMatchIds": replayed.placement_match_ids,
        "persistedRankedMatchIds": persisted.ranked_match_ids,
        "expectedRankedMatchIds": replayed.ranked_match_ids,
    }


def replay_ranking_elo(run_dir: str | Path, *, write: bool = False, top_k_limit: int = 10) -> dict[str, Any]:
    """Replay ranking Elo updates and optionally persist the repaired artifacts."""
    from packages.agent_mechanics.elo_update import apply_elo_updates

    resolved_run_dir = Path(run_dir).resolve()
    hypotheses = _load_hypotheses(resolved_run_dir)
    tournaments = _load_tournaments(resolved_run_dir)
    evolution_rounds = _load_evolution_rounds(resolved_run_dir)
    replay_hypotheses = {
        hypothesis_id: hypothesis.model_copy(
            deep=True,
            update={"elo_rating": 1200.0, "placement_match_ids": [], "ranked_match_ids": []},
        )
        for hypothesis_id, hypothesis in hypotheses.items()
    }
    touched_hypothesis_ids: set[str] = set()
    receipt_payloads: list[RankingUpdateReceiptContract] = []
    created_at = datetime.now(UTC)

    for group_index, (strategy, match_ids) in enumerate(
        _ordered_tournament_replay_groups(tournaments, evolution_rounds)
    ):
        matches: list[TournamentMatchContract] = []
        matchups: list[HypothesisMatchupContract] = []
        for match_id in match_ids:
            match = tournaments[match_id]
            hypothesis_1 = replay_hypotheses.get(match.hypothesis_1_id)
            hypothesis_2 = replay_hypotheses.get(match.hypothesis_2_id)
            if hypothesis_1 is None or hypothesis_2 is None:
                continue
            matches.append(match)
            matchups.append(HypothesisMatchupContract(hypothesis_1=hypothesis_1, hypothesis_2=hypothesis_2))
        if not matches:
            continue
        group_hypotheses = []
        seen_ids: set[str] = set()
        for matchup in matchups:
            for hypothesis in (matchup.hypothesis_1, matchup.hypothesis_2):
                if hypothesis.id in seen_ids:
                    continue
                group_hypotheses.append(hypothesis)
                seen_ids.add(hypothesis.id)
                touched_hypothesis_ids.add(hypothesis.id)
        elo_before = {hypothesis.id: hypothesis.elo_rating for hypothesis in group_hypotheses}
        apply_elo_updates(matches, matchups, strategy, k_factor=32.0)
        elo_after = {hypothesis.id: hypothesis.elo_rating for hypothesis in group_hypotheses}
        stable_receipt_id = _receipt_id(strategy, [match.id for match in matches])
        receipt_path = resolved_run_dir / "state" / "ranking_update_receipts" / f"{stable_receipt_id}.json"
        receipt_payloads.append(
            RankingUpdateReceiptContract(
                id=stable_receipt_id,
                status="completed",
                strategy=strategy,  # type: ignore[arg-type]
                match_ids=[match.id for match in matches],
                touched_hypothesis_ids=[hypothesis.id for hypothesis in group_hypotheses],
                elo_before=elo_before,
                elo_after=elo_after,
                updated_hypothesis_paths=[
                    _hypothesis_path(resolved_run_dir, hypothesis.id) for hypothesis in group_hypotheses
                ],
                receipt_path=str(receipt_path),
                created_at=created_at + timedelta(microseconds=group_index),
            )
        )

    diffs = [
        diff
        for hypothesis_id in sorted(touched_hypothesis_ids)
        if (diff := _build_diff(hypotheses[hypothesis_id], replay_hypotheses[hypothesis_id])) is not None
    ]
    status = "clean" if not diffs else "drift_found"
    updated_paths: list[str] = []
    written_receipts: list[str] = []
    if write and touched_hypothesis_ids:
        touched_hypotheses = [replay_hypotheses[hypothesis_id] for hypothesis_id in sorted(touched_hypothesis_ids)]
        updated_paths = persist_hypotheses(resolved_run_dir, touched_hypotheses, top_k_limit=top_k_limit)
        for receipt in receipt_payloads:
            receipt_path = Path(receipt.receipt_path)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
            written_receipts.append(str(receipt_path.resolve()))
        status = "repaired" if diffs else "clean"

    return {
        "status": status,
        "write": write,
        "runDir": str(resolved_run_dir),
        "completedTournamentMatchCount": sum(1 for match in tournaments.values() if match.status == "completed"),
        "replayGroupCount": len(receipt_payloads),
        "diffs": diffs,
        "updatedHypothesisIds": sorted(touched_hypothesis_ids) if write else [],
        "updatedHypothesisPaths": updated_paths,
        "rankingReceiptPaths": written_receipts,
    }


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run the ranking replay CLI and return a process exit code."""
    args = _parse_args(argv)
    report = replay_ranking_elo(args.run_dir, write=args.write, top_k_limit=args.top_k_limit)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.migration.replay_ranking_elo`."""
    try:
        return run_cli(argv)
    except Exception as exc:
        print(f"Ranking Elo replay failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
