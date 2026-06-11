from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError

from packages.agent_contracts import EvolutionRoundRecordContract


def _record_payload() -> dict[str, object]:
    return {
        "run_id": "run-001",
        "round_index": 1,
        "decision_index": 4,
        "status": "completed",
        "selection_strategy": "single_island",
        "selected_island_ids": ["island-001"],
        "parent_hypothesis_ids": ["hypothesis-001"],
        "chosen_evolution_strategy": "grounding_evolution",
        "child_hypothesis_id": "hypothesis-002",
        "child_island_id": "island-001",
        "review_passed": True,
        "proximity_receipt_status": "skipped_provider_unavailable",
        "placement_match_ids": ["match-002-001"],
        "ranked_match_ids": ["ranked-match-002-001"],
        "previous_top_k_ids": ["hypothesis-001"],
        "current_top_k_ids": ["hypothesis-001", "hypothesis-002"],
        "entered_top_k": True,
        "convergence_count_before": 1,
        "convergence_count_after": 0,
    }


def test_evolution_round_record_accepts_completed_receipt() -> None:
    record = EvolutionRoundRecordContract.from_payload(_record_payload())

    assert record.status == "completed"
    assert record.parent_hypothesis_ids == ["hypothesis-001"]
    assert record.child_hypothesis_id == "hypothesis-002"
    assert record.entered_top_k is True


def test_evolution_round_record_rejects_empty_child_id() -> None:
    payload = _record_payload()
    payload["child_hypothesis_id"] = ""

    with pytest.raises(ValidationError):
        EvolutionRoundRecordContract.from_payload(payload)


def test_evolution_round_record_rejects_invalid_status() -> None:
    payload = _record_payload()
    payload["status"] = "failed"

    with pytest.raises(ValidationError):
        EvolutionRoundRecordContract.from_payload(payload)


def test_evolution_round_record_loads_jsonl_file() -> None:
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "EVOLUTION_ROUNDS.jsonl"
        first = EvolutionRoundRecordContract.from_payload(_record_payload())
        second_payload = _record_payload()
        second_payload["round_index"] = 2
        second_payload["decision_index"] = 5
        second_payload["parent_hypothesis_ids"] = ["hypothesis-002"]
        second_payload["child_hypothesis_id"] = "hypothesis-003"
        second = EvolutionRoundRecordContract.from_payload(second_payload)
        path.write_text(
            first.model_dump_json() + "\n" + second.model_dump_json() + "\n",
            encoding="utf-8",
        )

        records = EvolutionRoundRecordContract.from_jsonl_file(path)

        assert [record.round_index for record in records] == [1, 2]
        assert records[1].child_hypothesis_id == "hypothesis-003"
