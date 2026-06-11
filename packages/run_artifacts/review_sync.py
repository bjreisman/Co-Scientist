"""Deterministic helpers for synchronizing review stage artifacts back into hypotheses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.agent_contracts import (
    DeepVerificationReviewContract,
    FullReviewContract,
    HypothesisContract,
    InitialReviewContract,
    ObservationReviewContract,
    ReviewContract,
    ReviewSummaryContract,
    SimulationReviewContract,
)

from .artifact_io import ArtifactStore


REVIEW_STAGE_FILE_MAP = {
    "initial_review": ("INITIAL_REVIEW.json", InitialReviewContract),
    "full_review": ("FULL_REVIEW.json", FullReviewContract),
    "deep_verification_review": ("DEEP_VERIFICATION.json", DeepVerificationReviewContract),
    "observation_review": ("OBSERVATION_REVIEW.json", ObservationReviewContract),
    "simulation_review": ("SIMULATION_REVIEW.json", SimulationReviewContract),
    "review_summary": ("REVIEW_SUMMARY.json", ReviewSummaryContract),
}

_PLACEHOLDER_REVIEW_TEXT = {
    "must outperform parent",
    "refined from parent",
    "viable evolved hypothesis",
    "synthesis reproducibility",
    "stability under reaction conditions",
    "synthesize evolved catalyst",
    "characterize structure",
    "test activity",
    "benchmark against parent",
}


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.lower().replace(".", " ").split())


def _has_only_placeholder_text(items: list[object]) -> bool:
    normalized_items = [_normalized_text(item) for item in items if _normalized_text(item)]
    if not normalized_items:
        return False
    return all(item in _PLACEHOLDER_REVIEW_TEXT for item in normalized_items)


def _initial_review_content_issue(stage_contract: Any) -> str | None:
    passed = bool(getattr(stage_contract, "passed", False))
    preferences = getattr(stage_contract, "preferences", []) or []
    constraints = getattr(stage_contract, "constraints", []) or []
    if passed and not (preferences or constraints):
        return "Completed passing initial review artifacts must include at least one preference or constraint."
    if passed and _has_only_placeholder_text([*preferences, *constraints]):
        return (
            "Completed passing initial review artifacts must include specific non-placeholder preferences "
            "or constraints."
        )
    return None


def _full_review_content_issue(stage_contract: Any) -> str | None:
    preferences = getattr(stage_contract, "preferences", []) or []
    constraints = getattr(stage_contract, "constraints", []) or []
    retrieval_results = getattr(stage_contract, "retrieval_results", []) or []
    evidence_bundle_ids = getattr(stage_contract, "evidence_bundle_ids", []) or []
    literature_query_ids = getattr(stage_contract, "literature_query_ids", []) or []
    if not (preferences or constraints or retrieval_results or evidence_bundle_ids or literature_query_ids):
        return (
            "Completed full review artifacts must include preferences, constraints, retrieval results, "
            "or evidence linkage."
        )
    return None


def _deep_verification_content_issue(stage_contract: Any) -> str | None:
    assumptions = getattr(stage_contract, "assumptions", []) or []
    if not assumptions:
        return "Completed deep verification review artifacts must include at least one assumption."
    return None


def _observation_review_content_issue(stage_contract: Any) -> str | None:
    observations = getattr(stage_contract, "observations", []) or []
    retrieval_results = getattr(stage_contract, "retrieval_results", []) or []
    if not (observations or retrieval_results):
        return "Completed observation review artifacts must include at least one observation or retrieval result."
    return None


def _simulation_review_content_issue(stage_contract: Any) -> str | None:
    steps = getattr(stage_contract, "steps", []) or []
    failure_scenarios = getattr(stage_contract, "failure_scenarios", []) or []
    if not steps:
        return "Completed simulation review artifacts must include at least one step."
    if not failure_scenarios:
        return "Completed simulation review artifacts must include at least one failure scenario."
    if _has_only_placeholder_text([*steps, *failure_scenarios]):
        return "Completed simulation review artifacts must include non-placeholder steps and failure scenarios."
    return None


def _review_summary_content_issue(stage_contract: Any) -> str | None:
    summaries = getattr(stage_contract, "summaries", []) or []
    if not summaries:
        return "Completed review summary artifacts must include at least one summary item."
    if _has_only_placeholder_text(summaries):
        return "Completed review summary artifacts must include non-placeholder summary content."
    return None


def review_stage_content_issue(field_name: str, stage_contract: Any) -> str | None:
    """Return a semantic content issue for a completed review stage, if any."""
    status = getattr(stage_contract, "status", "")
    if status != "completed":
        return None

    if field_name == "initial_review":
        return _initial_review_content_issue(stage_contract)

    if field_name == "full_review":
        return _full_review_content_issue(stage_contract)

    if field_name == "deep_verification_review":
        return _deep_verification_content_issue(stage_contract)

    if field_name == "observation_review":
        return _observation_review_content_issue(stage_contract)

    if field_name == "simulation_review":
        return _simulation_review_content_issue(stage_contract)

    if field_name == "review_summary":
        return _review_summary_content_issue(stage_contract)

    return None


def sync_hypothesis_review(
    run_dir: str | Path,
    hypothesis_id: str,
    *,
    top_k_limit: int = 10,
) -> dict[str, Any]:
    """Sync standalone review stage artifacts back into the canonical hypothesis artifact."""
    resolved_run_dir = Path(run_dir).resolve()
    hypothesis_path = resolved_run_dir / "hypotheses" / hypothesis_id / "HYPOTHESIS.json"
    if not hypothesis_path.exists():
        raise FileNotFoundError(f"Missing canonical hypothesis artifact: {hypothesis_path}")

    hypothesis = HypothesisContract.from_json_file(hypothesis_path)
    review_dir = hypothesis_path.parent / "REVIEW"

    updated_review = ReviewContract.from_model_like(hypothesis.review)
    synced_sections: list[str] = []
    changed_sections: list[str] = []
    stage_contracts: dict[str, Any] = {}

    for field_name, (filename, contract_type) in REVIEW_STAGE_FILE_MAP.items():
        stage_path = review_dir / filename
        if not stage_path.exists():
            continue

        stage_payload = json.loads(stage_path.read_text(encoding="utf-8"))
        stage_contract = contract_type.model_validate(stage_payload)
        content_issue = review_stage_content_issue(field_name, stage_contract)
        if content_issue is not None:
            raise ValueError(f"{content_issue} ({stage_path})")
        current_contract = getattr(updated_review, field_name)
        synced_sections.append(field_name)
        stage_contracts[field_name] = stage_contract
        if current_contract.model_dump(mode="json") != stage_contract.model_dump(mode="json"):
            setattr(updated_review, field_name, stage_contract)
            changed_sections.append(field_name)

    if not synced_sections:
        raise FileNotFoundError(f"Missing review stage artifacts under: {review_dir}")

    updated_hypothesis = hypothesis.model_copy(update={"review": updated_review})
    artifact_store = ArtifactStore(resolved_run_dir, top_k_limit=top_k_limit)
    artifact_store.ensure_layout()
    artifact_store.write_hypothesis(updated_hypothesis, write_review_stage_files=True)

    reloaded_hypothesis = HypothesisContract.from_json_file(hypothesis_path)
    reloaded_review = ReviewContract.from_model_like(reloaded_hypothesis.review)
    for field_name, stage_contract in stage_contracts.items():
        reloaded_contract = getattr(reloaded_review, field_name)
        if reloaded_contract.model_dump(mode="json") != stage_contract.model_dump(mode="json"):
            raise ValueError(
                f"Canonical hypothesis review payload drifted after sync for `{field_name}` under {hypothesis_path}."
            )

    return {
        "hypothesisPath": str(hypothesis_path.resolve()),
        "syncedSections": synced_sections,
        "changedSections": changed_sections,
    }


__all__ = ["REVIEW_STAGE_FILE_MAP", "review_stage_content_issue", "sync_hypothesis_review"]
