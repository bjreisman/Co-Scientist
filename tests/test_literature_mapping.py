from __future__ import annotations

from packages.agent_contracts import EvidenceBundleContract, PaperCandidateContract, SearchRequestContract
from packages.agent_mechanics import (
    evidence_bundle_ids,
    literature_query_ids,
    retrieval_results_from_evidence_bundle,
)


def test_retrieval_results_from_evidence_bundle_maps_papers_to_legacy_contract() -> None:
    bundle = EvidenceBundleContract(
        bundle_id="bundle-q-001",
        query_id="q-001",
        request=SearchRequestContract(query_id="q-001", query="ammonia catalyst"),
        papers=[
            PaperCandidateContract(
                paper_id="doi:10.1000/example",
                title="Catalyst evidence",
                authors=["Ada Lovelace"],
                year=2024,
                venue="Journal of Catalysis",
                doi="10.1000/example",
                abstract="Evidence abstract.",
                relevance_score=0.7,
            )
        ],
    )

    retrieval_results = retrieval_results_from_evidence_bundle(bundle)

    assert retrieval_results[0].query == "ammonia catalyst"
    assert retrieval_results[0].score == 0.7
    assert retrieval_results[0].content == "Evidence abstract."
    assert retrieval_results[0].article.title == "Catalyst evidence"
    assert retrieval_results[0].article.authors == ["Ada Lovelace"]
    assert retrieval_results[0].article.journal == "Journal of Catalysis"
    assert evidence_bundle_ids(bundle) == ["bundle-q-001"]
    assert literature_query_ids(bundle) == ["q-001"]
