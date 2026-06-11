from __future__ import annotations

import json
import shutil
from pathlib import Path

from packages.agent_contracts import (
    EvidenceBundleContract,
    PaperCandidateContract,
    PaperVerificationContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
)
from packages.agent_contracts.export_contract_artifacts import export_agent_contract_schemas


def test_search_request_contract_validates_nested_filters() -> None:
    request = SearchRequestContract.from_payload(
        {
            "run_id": "run-a",
            "query_id": "q-001",
            "goal": "Find catalyst mechanism evidence.",
            "query": "ammonia synthesis catalyst active site",
            "query_type": "mechanism_support",
            "keywords": ["ammonia", "catalyst"],
            "providers": ["openalex", "crossref"],
            "filters": {"year_min": 2020, "max_results": 5},
            "consumer": "hypothesis-generate-literature",
        }
    )

    assert request.query_id == "q-001"
    assert request.filters.year_min == 2020
    assert request.filters.max_results == 5
    assert request.providers == ["openalex", "crossref"]


def test_evidence_bundle_contract_preserves_traceable_paper_references() -> None:
    request = SearchRequestContract(query_id="q-001", query="ammonia catalyst")
    receipt = SearchProviderReceiptContract(
        provider="openalex",
        status="succeeded",
        result_count=1,
    )
    paper = PaperCandidateContract(
        paper_id="paper-001",
        title="Catalyst active sites for ammonia synthesis",
        provider_sources=["openalex"],
        doi="10.1000/example",
    )
    verification = PaperVerificationContract(
        paper_id="paper-001",
        status="verified",
        method="crossref",
        confidence="high",
    )

    bundle = EvidenceBundleContract.from_payload(
        {
            "bundle_id": "bundle-001",
            "query_id": "q-001",
            "request": request.model_dump(mode="json"),
            "provider_receipts": [receipt.model_dump(mode="json")],
            "papers": [paper.model_dump(mode="json")],
            "verified_papers": [verification.model_dump(mode="json")],
            "synthesized_findings": [
                {
                    "finding_id": "finding-001",
                    "type": "support",
                    "statement": "The mechanism is supported by one verified paper.",
                    "paper_refs": ["paper-001"],
                    "confidence": "medium",
                }
            ],
        }
    )

    assert bundle.bundle_id == "bundle-001"
    assert bundle.provider_receipts[0].status == "succeeded"
    assert bundle.papers[0].paper_id == "paper-001"
    assert bundle.verified_papers[0].status == "verified"
    assert bundle.synthesized_findings[0].paper_refs == ["paper-001"]


def test_literature_contract_schemas_are_exported() -> None:
    export_root = Path("tests/.tmp_literature_schema_export")
    if export_root.exists():
        shutil.rmtree(export_root)
    try:
        written = export_agent_contract_schemas(export_root)
        filenames = {path.name for path in written}

        assert "search_request.schema.json" in filenames
        assert "search_provider_receipt.schema.json" in filenames
        assert "evidence_bundle.schema.json" in filenames

        evidence_schema = json.loads((export_root / "schema" / "evidence_bundle.schema.json").read_text())
        assert evidence_schema["title"] == "EvidenceBundleContract"
    finally:
        if export_root.exists():
            shutil.rmtree(export_root)
