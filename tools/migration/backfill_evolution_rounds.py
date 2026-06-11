"""Backfill append-only evolution round replay records from existing run artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.append(str(_REPO_ROOT))
    from packages.agent_contracts import (  # type: ignore[no-redef]
        EvolutionRoundRecordContract,
        EvolutionStateContract,
        HypothesisContract,
        StrategyDecisionRecordContract,
        TournamentMatchContract,
    )
    from packages.run_artifacts import ArtifactStore  # type: ignore[no-redef]
else:
    from packages.agent_contracts import (
        EvolutionRoundRecordContract,
        EvolutionStateContract,
        HypothesisContract,
        StrategyDecisionRecordContract,
        TournamentMatchContract,
    )
    from packages.run_artifacts import ArtifactStore


class BackfillUnresolvedRound(BaseModel):
    """One evolved child that cannot be safely converted into a replay record."""

    model_config = ConfigDict(extra="ignore")

    child_hypothesis_id: str
    reason: str


class EvolutionRoundBackfillSummary(BaseModel):
    """Structured migration summary returned by the backfill command."""

    model_config = ConfigDict(extra="ignore")

    status: str
    apply: bool
    run_id: str
    output_path: str
    existing_record_count: int
    proposed_record_count: int
    unresolved_count: int
    records: list[EvolutionRoundRecordContract] = Field(default_factory=list)
    unresolved: list[BackfillUnresolvedRound] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill state/EVOLUTION_ROUNDS.jsonl from existing hypothesis and strategy artifacts."
    )
    parser.add_argument("run_dir", type=Path, help="Path to the run directory.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write state/EVOLUTION_ROUNDS.jsonl when every evolved child can be safely inferred.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the migration summary JSON.",
    )
    return parser.parse_args(argv)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_non_empty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _natural_id_key(value: str) -> tuple[str, int, str]:
    match = re.search(r"(\d+)$", value)
    if match is None:
        return value, -1, value
    return value[: match.start()], int(match.group(1)), value


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def _load_hypotheses(run_dir: Path) -> list[HypothesisContract]:
    hypotheses_root = run_dir / "hypotheses"
    if not hypotheses_root.exists():
        return []
    hypotheses: list[HypothesisContract] = []
    for hypothesis_dir in sorted(path for path in hypotheses_root.iterdir() if path.is_dir()):
        hypothesis_path = hypothesis_dir / "HYPOTHESIS.json"
        if hypothesis_path.exists():
            hypotheses.append(HypothesisContract.from_json_file(hypothesis_path))
    return hypotheses


def _load_strategy_decisions(run_dir: Path) -> list[StrategyDecisionRecordContract]:
    decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
    if not decisions_path.exists():
        return []
    decisions = [
        StrategyDecisionRecordContract.from_payload(json.loads(line))
        for line in decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return sorted(decisions, key=lambda item: item.decision_index)


def _load_tournament_matches(run_dir: Path) -> dict[str, TournamentMatchContract]:
    tournaments_root = run_dir / "tournaments"
    if not tournaments_root.exists():
        return {}
    matches: dict[str, TournamentMatchContract] = {}
    for tournament_path in sorted(
        path for path in tournaments_root.iterdir() if path.is_file() and path.suffix == ".json"
    ):
        match = TournamentMatchContract.from_json_file(tournament_path)
        if match.id:
            matches[match.id] = match
    return matches


def _continue_evolution_decisions(
    decisions: list[StrategyDecisionRecordContract],
) -> list[StrategyDecisionRecordContract]:
    return [
        decision
        for decision in decisions
        if decision.current_phase == "Evolution"
        and decision.next_action == "continue_evolution"
        and decision.selected_evolution_strategies
    ]


def _top_hypothesis_ids_from_decision(decision: StrategyDecisionRecordContract) -> list[str] | None:
    return _string_list(decision.signals.get("top_hypothesis_ids"))


def _convergence_count_from_decision(decision: StrategyDecisionRecordContract) -> int | None:
    raw_value = decision.signals.get("convergence_count")
    if isinstance(raw_value, int) and raw_value >= 0:
        return raw_value
    return None


def _find_current_top_k_ids(
    *,
    decision_index: int,
    decisions: list[StrategyDecisionRecordContract],
    evolution_state: EvolutionStateContract | None,
) -> list[str] | None:
    for decision in decisions:
        if decision.decision_index <= decision_index:
            continue
        top_hypothesis_ids = _top_hypothesis_ids_from_decision(decision)
        if top_hypothesis_ids:
            return top_hypothesis_ids
    if evolution_state is not None and evolution_state.topHypothesisIds:
        return list(evolution_state.topHypothesisIds)
    return None


def _proximity_receipt_status(run_dir: Path, hypothesis_id: str) -> str:
    receipt_path = run_dir / "state" / "proximity_receipts" / f"{hypothesis_id}.json"
    if not receipt_path.exists():
        return ""
    payload = _load_json(receipt_path)
    status = payload.get("status")
    return status if isinstance(status, str) else ""


def _candidate_owned_match_ids(
    match_ids: list[str],
    *,
    child_hypothesis_id: str,
    strategy: str,
    tournament_matches: dict[str, TournamentMatchContract],
) -> list[str]:
    owned_match_ids: list[str] = []
    for match_id in match_ids:
        match = tournament_matches.get(match_id)
        if match is None:
            continue
        if match.match_strategy == strategy and match.hypothesis_1_id == child_hypothesis_id:
            owned_match_ids.append(match_id)
    return owned_match_ids


def _match_decision_for_child(
    child: HypothesisContract,
    *,
    decisions: list[StrategyDecisionRecordContract],
    used_decision_indexes: set[int],
) -> tuple[StrategyDecisionRecordContract | None, str | None]:
    candidates: list[StrategyDecisionRecordContract] = []
    for decision in decisions:
        if decision.decision_index in used_decision_indexes:
            continue
        selected_parent_ids = _string_list(decision.signals.get("selected_parent_ids"))
        selected_island_ids = _string_list(decision.signals.get("selected_island_ids"))
        if selected_parent_ids != child.parent_ids:
            continue
        if selected_island_ids is None or child.island_id not in selected_island_ids:
            continue
        if child.origin.strategy not in decision.selected_evolution_strategies:
            continue
        candidates.append(decision)

    if not candidates:
        return None, "No unused continue_evolution strategy decision matches the child parents, island, and strategy."
    return min(candidates, key=lambda item: item.decision_index), None


def _build_record_for_child(
    child: HypothesisContract,
    *,
    run_dir: Path,
    round_index: int,
    decision: StrategyDecisionRecordContract,
    all_decisions: list[StrategyDecisionRecordContract],
    evolution_state: EvolutionStateContract | None,
    tournament_matches: dict[str, TournamentMatchContract],
) -> tuple[EvolutionRoundRecordContract | None, str | None]:
    selected_island_ids = _string_list(decision.signals.get("selected_island_ids"))
    if not selected_island_ids:
        return None, "The matched strategy decision does not expose selected_island_ids."

    selection_strategy = decision.signals.get("selection_strategy")
    if selection_strategy not in {"single_island", "multi_island"}:
        return None, "The matched strategy decision does not expose a supported selection_strategy."

    previous_top_k_ids = _top_hypothesis_ids_from_decision(decision)
    if previous_top_k_ids is None:
        return None, "The matched strategy decision does not expose top_hypothesis_ids."

    current_top_k_ids = _find_current_top_k_ids(
        decision_index=decision.decision_index,
        decisions=all_decisions,
        evolution_state=evolution_state,
    )
    if current_top_k_ids is None:
        return None, "No later strategy decision or EVOLUTION_STATE topHypothesisIds can prove the current top-k."

    convergence_count_before = _convergence_count_from_decision(decision)
    if convergence_count_before is None:
        return None, "The matched strategy decision does not expose a non-negative convergence_count."

    entered_top_k = child.id in current_top_k_ids and child.id not in previous_top_k_ids
    convergence_count_after = 0 if entered_top_k else convergence_count_before + 1
    return (
        EvolutionRoundRecordContract(
            run_id=run_dir.name,
            round_index=round_index,
            decision_index=decision.decision_index,
            selection_strategy=selection_strategy,
            selected_island_ids=selected_island_ids,
            parent_hypothesis_ids=list(child.parent_ids),
            chosen_evolution_strategy=child.origin.strategy,
            child_hypothesis_id=child.id,
            child_island_id=child.island_id,
            review_passed=child.review.initial_review.passed,
            proximity_receipt_status=_proximity_receipt_status(run_dir, child.id),
            placement_match_ids=_candidate_owned_match_ids(
                child.placement_match_ids,
                child_hypothesis_id=child.id,
                strategy="placement_tournament",
                tournament_matches=tournament_matches,
            ),
            ranked_match_ids=_candidate_owned_match_ids(
                child.ranked_match_ids,
                child_hypothesis_id=child.id,
                strategy="ranked_tournament",
                tournament_matches=tournament_matches,
            ),
            previous_top_k_ids=previous_top_k_ids,
            current_top_k_ids=current_top_k_ids,
            entered_top_k=entered_top_k,
            convergence_count_before=convergence_count_before,
            convergence_count_after=convergence_count_after,
        ),
        None,
    )


def _infer_round_records(
    *,
    run_dir: Path,
    evolved_hypotheses: list[HypothesisContract],
    all_decisions: list[StrategyDecisionRecordContract],
    evolution_decisions: list[StrategyDecisionRecordContract],
    evolution_state: EvolutionStateContract | None,
    tournament_matches: dict[str, TournamentMatchContract],
) -> tuple[list[EvolutionRoundRecordContract], list[BackfillUnresolvedRound]]:
    records: list[EvolutionRoundRecordContract] = []
    unresolved: list[BackfillUnresolvedRound] = []
    used_decision_indexes: set[int] = set()
    for child in evolved_hypotheses:
        decision, match_issue = _match_decision_for_child(
            child,
            decisions=evolution_decisions,
            used_decision_indexes=used_decision_indexes,
        )
        if decision is None:
            unresolved.append(BackfillUnresolvedRound(child_hypothesis_id=child.id, reason=str(match_issue)))
            continue
        record, record_issue = _build_record_for_child(
            child,
            run_dir=run_dir,
            round_index=len(records) + 1,
            decision=decision,
            all_decisions=all_decisions,
            evolution_state=evolution_state,
            tournament_matches=tournament_matches,
        )
        if record is None:
            unresolved.append(BackfillUnresolvedRound(child_hypothesis_id=child.id, reason=str(record_issue)))
            continue
        records.append(record)
        used_decision_indexes.add(decision.decision_index)
    return records, unresolved


def backfill_evolution_rounds(run_dir: Path, *, apply: bool = False) -> EvolutionRoundBackfillSummary:
    """Infer and optionally write evolution round replay records for one existing run."""
    run_dir = run_dir.resolve()
    output_path = run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
    existing_record_count = _count_non_empty_lines(output_path)
    hypotheses = _load_hypotheses(run_dir)
    evolved_hypotheses = sorted(
        [hypothesis for hypothesis in hypotheses if hypothesis.parent_ids],
        key=lambda item: (item.timestamp, _natural_id_key(item.id)),
    )
    all_decisions = _load_strategy_decisions(run_dir)
    evolution_decisions = _continue_evolution_decisions(all_decisions)
    tournament_matches = _load_tournament_matches(run_dir)
    evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
    evolution_state = (
        EvolutionStateContract.from_json_file(evolution_state_path) if evolution_state_path.exists() else None
    )
    records, unresolved = _infer_round_records(
        run_dir=run_dir,
        evolved_hypotheses=evolved_hypotheses,
        all_decisions=all_decisions,
        evolution_decisions=evolution_decisions,
        evolution_state=evolution_state,
        tournament_matches=tournament_matches,
    )
    warnings: list[str] = []
    if len(evolution_decisions) > len(records):
        warnings.append(
            "Some continue_evolution decisions were not converted because no matching evolved child could be proven."
        )

    status = "ready"
    if not records and not unresolved:
        status = "no_changes"
    elif unresolved:
        status = "blocked"
    if existing_record_count:
        status = "blocked"
        warnings.append("EVOLUTION_ROUNDS.jsonl already contains records; remove or archive it before applying.")

    if apply and status == "ready":
        store = ArtifactStore(run_dir)
        for record in records:
            store.append_evolution_round_record(record)
        status = "applied"
    elif apply and status != "ready":
        warnings.append("No records were written because the migration summary is not fully ready.")

    return EvolutionRoundBackfillSummary(
        status=status,
        apply=apply,
        run_id=run_dir.name,
        output_path=str(output_path),
        existing_record_count=existing_record_count,
        proposed_record_count=len(records),
        unresolved_count=len(unresolved),
        records=records,
        unresolved=unresolved,
        warnings=warnings,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for evolution round backfill."""
    args = _parse_args(argv)
    summary = backfill_evolution_rounds(args.run_dir, apply=args.apply)
    payload = summary.model_dump(mode="json")
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if summary.status in {"ready", "applied", "no_changes"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
