from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    PaperCandidateContract,
    PaperVerificationContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
)
from packages.agent_mechanics.literature_providers.common import ProviderSearchResult
from tools.literature_search_client import (
    load_evidence_bundle,
    search_literature,
    verify_literature_candidates,
)


def _fake_openalex(request: SearchRequestContract) -> ProviderSearchResult:
    return ProviderSearchResult(
        candidates=[
            PaperCandidateContract(
                paper_id="doi:10.1000/example",
                title="Catalyst evidence",
                doi="10.1000/example",
                year=2024,
                venue="Journal of Catalysis",
                provider_sources=["openalex"],
                relevance_score=1.0,
            )
        ],
        receipt=SearchProviderReceiptContract(
            provider="openalex",
            status="succeeded",
            result_count=1,
        ),
    )


def _verified_probe(candidate: PaperCandidateContract):
    return PaperVerificationContract(
        paper_id=candidate.paper_id,
        status="verified",
        method="title_fuzzy",
        confidence="medium",
        reason="Test probe verified this candidate.",
    )


def test_search_literature_writes_query_and_bundle_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        bundle = search_literature(
            run_dir,
            {
                "query_id": "q-001",
                "query": "ammonia synthesis catalyst",
                "providers": ["openalex"],
                "filters": {"max_results": 5},
            },
            provider_searchers={"openalex": _fake_openalex},
            verification_probes=[_verified_probe],
        )

        query_dir = run_dir / "literature" / "queries" / "q-001"
        bundle_path = query_dir / "EVIDENCE_BUNDLE.json"
        bundle_copy_path = run_dir / "literature" / "bundles" / "bundle-q-001.json"

        assert bundle.retrieval_metadata.status == "succeeded"
        assert bundle.retrieval_metadata.verified_count == 1
        assert json.loads((query_dir / "REQUEST.json").read_text(encoding="utf-8"))["query_id"] == "q-001"
        assert (
            json.loads((query_dir / "PROVIDER_RECEIPTS.json").read_text(encoding="utf-8"))[0]["status"] == "succeeded"
        )
        assert (
            json.loads((query_dir / "CANDIDATE_PAPERS.json").read_text(encoding="utf-8"))[0]["paper_id"]
            == "doi:10.1000/example"
        )
        assert json.loads((query_dir / "VERIFIED_PAPERS.json").read_text(encoding="utf-8"))[0]["status"] == "verified"
        assert bundle_path.exists()
        assert bundle_copy_path.exists()
        assert "Catalyst evidence" in (query_dir / "EVIDENCE_BUNDLE.md").read_text(encoding="utf-8")

        loaded_bundle = load_evidence_bundle(run_dir, "bundle-q-001")
        assert loaded_bundle.bundle_id == "bundle-q-001"


def test_verify_literature_candidates_updates_existing_bundle() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        search_literature(
            run_dir,
            {"query_id": "q-001", "query": "test", "providers": ["openalex"]},
            provider_searchers={"openalex": _fake_openalex},
            verify=False,
        )

        verifications = verify_literature_candidates(
            run_dir,
            "q-001",
            verification_probes=[_verified_probe],
        )
        bundle = load_evidence_bundle(run_dir, "bundle-q-001")

        assert verifications[0].status == "verified"
        assert bundle.retrieval_metadata.verified_count == 1
        assert bundle.verified_papers[0].status == "verified"
