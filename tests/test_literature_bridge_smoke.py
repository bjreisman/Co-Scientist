from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    PaperCandidateContract,
    PaperVerificationContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
)
from packages.agent_mechanics import (
    evidence_bundle_ids,
    literature_query_ids,
    retrieval_results_from_evidence_bundle,
)
from packages.agent_mechanics.literature_providers.common import ProviderSearchResult
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis
from tools.literature_search_client import search_literature
from tools.validation.contract_validation import validate_run_artifacts


def _write_config(run_dir: Path) -> None:
    input_path = run_dir / "input.md"
    input_path.write_text("# Smoke Run\n\nOptimize ammonia synthesis catalysts.\n", encoding="utf-8")
    (run_dir / "config.yaml").write_text("input_file: input.md\n", encoding="utf-8")


def _provider_result(provider: str, candidates: list[PaperCandidateContract]):
    def searcher(request: SearchRequestContract) -> ProviderSearchResult:
        return ProviderSearchResult(
            candidates=candidates,
            receipt=SearchProviderReceiptContract(
                provider=provider,
                status="succeeded",
                result_count=len(candidates),
            ),
        )

    return searcher


def _verification_probe(candidate: PaperCandidateContract) -> PaperVerificationContract:
    if candidate.doi == "10.1000/ammonia-mechanism":
        return PaperVerificationContract(
            paper_id=candidate.paper_id,
            status="verified",
            method="crossref",
            confidence="high",
            reason="Smoke verifier resolved the DOI.",
        )
    return PaperVerificationContract(
        paper_id=candidate.paper_id,
        status="verify_pending",
        method="none",
        confidence="low",
        reason="Smoke verifier leaves non-DOI records pending.",
    )


def test_literature_bridge_smoke_maps_real_artifact_flow_into_validator() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        provider_searchers = {
            "openalex": _provider_result(
                "openalex",
                [
                    PaperCandidateContract(
                        paper_id="doi:10.1000/ammonia-mechanism",
                        title="Ammonia synthesis active-site mechanism",
                        authors=["Jane Researcher"],
                        year=2024,
                        venue="Catalysis Letters",
                        doi="10.1000/ammonia-mechanism",
                        abstract="Surface nitrogen activation controls ammonia synthesis rates.",
                        provider_sources=["openalex"],
                        citation_count=42,
                        relevance_score=0.95,
                    )
                ],
            ),
            "crossref": _provider_result(
                "crossref",
                [
                    PaperCandidateContract(
                        paper_id="doi:10.1000/ammonia-mechanism",
                        title="Ammonia synthesis active-site mechanism",
                        authors=["Jane Researcher"],
                        year=2024,
                        venue="Catalysis Letters",
                        doi="10.1000/ammonia-mechanism",
                        provider_sources=["crossref"],
                        citation_count=40,
                        relevance_score=0.9,
                    )
                ],
            ),
            "europe_pmc": _provider_result(
                "europe_pmc",
                [
                    PaperCandidateContract(
                        paper_id="pmid:12345678",
                        title="Heterogeneous catalyst support effects in ammonia synthesis",
                        authors=["Alex Chemist"],
                        year=2023,
                        venue="Applied Catalysis",
                        pmid="12345678",
                        abstract="Support defects alter adsorbed nitrogen intermediates.",
                        provider_sources=["europe_pmc"],
                        citation_count=12,
                        relevance_score=0.8,
                    )
                ],
            ),
        }

        bundle = search_literature(
            run_dir,
            {
                "query_id": "q-smoke-ammonia",
                "goal": "optimize ammonia synthesis catalysts",
                "query": "ammonia synthesis catalyst heterogeneous catalyst active site mechanism",
                "providers": ["openalex", "crossref", "europe_pmc"],
                "filters": {"max_results": 5},
                "consumer": "hypothesis-generate-literature",
            },
            provider_searchers=provider_searchers,
            verification_probes=[_verification_probe],
        )

        retrieval_results = retrieval_results_from_evidence_bundle(bundle)
        hypothesis = build_hypothesis(
            "hyp-001",
            1250.0,
            "island-001",
            passed=False,
            strategy="literature_exploration_generation",
        )
        origin = hypothesis.origin.model_copy(
            update={
                "retrieval_results": retrieval_results,
                "evidence_bundle_ids": evidence_bundle_ids(bundle),
                "literature_query_ids": literature_query_ids(bundle),
            }
        )
        full_review = hypothesis.review.full_review.model_copy(
            update={
                "retrieval_results": retrieval_results,
                "evidence_bundle_ids": evidence_bundle_ids(bundle),
                "literature_query_ids": literature_query_ids(bundle),
            }
        )
        review = hypothesis.review.model_copy(update={"full_review": full_review})
        ArtifactStore(run_dir).write_hypothesis(hypothesis.model_copy(update={"origin": origin, "review": review}))

        query_dir = run_dir / "literature" / "queries" / "q-smoke-ammonia"
        assert (query_dir / "REQUEST.json").exists()
        assert (query_dir / "PROVIDER_RECEIPTS.json").exists()
        assert (query_dir / "CANDIDATE_PAPERS.json").exists()
        assert (query_dir / "VERIFIED_PAPERS.json").exists()
        assert (query_dir / "EVIDENCE_BUNDLE.json").exists()
        assert (run_dir / "literature" / "bundles" / "bundle-q-smoke-ammonia.json").exists()

        assert bundle.retrieval_metadata.status == "succeeded"
        assert bundle.retrieval_metadata.providers_succeeded == ["openalex", "crossref", "europe_pmc"]
        assert bundle.retrieval_metadata.total_raw_results == 3
        assert bundle.retrieval_metadata.total_deduped_results == 2
        assert len(bundle.papers) == 2
        assert bundle.verified_papers[0].status == "verified"
        assert bundle.retrieval_metadata.pending_count == 1
        assert {"openalex", "crossref"}.issubset(set(bundle.papers[0].provider_sources))
        assert retrieval_results[0].query == bundle.request.query

        summary = validate_run_artifacts(run_dir, requested_skill="co-scientist-pipeline")
        assert summary.status == "valid"
        assert summary.errorCount == 0
