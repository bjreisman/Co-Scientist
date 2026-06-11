from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.agent_contracts import FullReviewContract, InitialReviewContract, ReviewContract, ReviewSummaryContract
from packages.run_artifacts import ArtifactStore, sync_hypothesis_review
from tests.conftest import build_hypothesis


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_sync_hypothesis_review_updates_embedded_payload_from_stage_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=4)
        hypothesis = build_hypothesis("hyp-001", 1200.0, "island-a").model_copy(update={"review": ReviewContract()})
        store.write_hypothesis(hypothesis)

        review_dir = run_dir / "hypotheses" / "hyp-001" / "REVIEW"
        initial_review = InitialReviewContract(
            status="completed",
            passed=True,
            preferences=["Mechanistically plausible"],
            constraints=["Needs experimental confirmation"],
        )
        full_review = FullReviewContract(
            status="completed",
            preferences=["Grounded in prior work"],
            constraints=["Needs broader literature coverage"],
        )
        review_summary = ReviewSummaryContract(
            status="completed",
            summaries=["Initial and full review both completed."],
        )

        _write_json(review_dir / "INITIAL_REVIEW.json", initial_review.model_dump(mode="json"))
        _write_json(review_dir / "FULL_REVIEW.json", full_review.model_dump(mode="json"))
        _write_json(review_dir / "REVIEW_SUMMARY.json", review_summary.model_dump(mode="json"))

        result = sync_hypothesis_review(run_dir, "hyp-001", top_k_limit=4)

        assert result["hypothesisPath"].endswith("hypotheses\\hyp-001\\HYPOTHESIS.json")
        assert set(result["syncedSections"]) == {
            "initial_review",
            "full_review",
            "deep_verification_review",
            "observation_review",
            "simulation_review",
            "review_summary",
        }
        assert set(result["changedSections"]) == {"initial_review", "full_review", "review_summary"}

        payload = json.loads((run_dir / "hypotheses" / "hyp-001" / "HYPOTHESIS.json").read_text(encoding="utf-8"))
        assert payload["review"]["initial_review"]["status"] == "completed"
        assert payload["review"]["initial_review"]["passed"] is True
        assert payload["review"]["full_review"]["status"] == "completed"
        assert payload["review"]["review_summary"]["status"] == "completed"
        assert payload["review"]["review_summary"]["summaries"] == ["Initial and full review both completed."]
        assert payload["review"]["deep_verification_review"]["status"] == "pending"

        initial_stage_payload = json.loads((review_dir / "INITIAL_REVIEW.json").read_text(encoding="utf-8"))
        assert initial_stage_payload["status"] == "completed"
        assert initial_stage_payload["passed"] is True


def test_sync_hypothesis_review_rejects_completed_review_summary_without_content() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        store = ArtifactStore(run_dir, top_k_limit=4)
        hypothesis = build_hypothesis("hyp-001", 1200.0, "island-a").model_copy(update={"review": ReviewContract()})
        store.write_hypothesis(hypothesis)

        review_dir = run_dir / "hypotheses" / "hyp-001" / "REVIEW"
        _write_json(review_dir / "REVIEW_SUMMARY.json", {"status": "completed", "summaries": []})

        with pytest.raises(
            ValueError, match="Completed review summary artifacts must include at least one summary item."
        ):
            sync_hypothesis_review(run_dir, "hyp-001", top_k_limit=4)
