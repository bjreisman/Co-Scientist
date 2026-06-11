from __future__ import annotations

import packages.agent_mechanics.literature_verification as literature_verification
from packages.agent_contracts import (
    EvidenceBundleContract,
    PaperCandidateContract,
    PaperVerificationContract,
    SearchRequestContract,
)
from packages.agent_mechanics import title_overlap, verify_evidence_bundle, verify_paper_candidate
from packages.agent_mechanics.literature_providers.common import ProviderRateLimitError


def test_title_overlap_handles_normalized_word_match() -> None:
    score = title_overlap(
        "Catalyst active sites for ammonia synthesis",
        "Ammonia synthesis catalyst active sites",
    )

    assert score >= 0.6


def test_verify_paper_candidate_confirms_crossref_doi(monkeypatch) -> None:
    def fake_fetch_json(url: str, headers=None):
        assert "api.crossref.org/works" in url
        return {"message": {"DOI": "10.1000/example"}}

    monkeypatch.setattr(literature_verification, "fetch_json", fake_fetch_json)

    result = verify_paper_candidate(
        PaperCandidateContract(
            paper_id="doi:10.1000/example",
            title="Catalyst paper",
            doi="10.1000/example",
        )
    )

    assert result.status == "verified"
    assert result.method == "crossref"
    assert result.confidence == "high"


def test_verify_paper_candidate_marks_transient_probe_failure_pending() -> None:
    def rate_limited_probe(candidate: PaperCandidateContract):
        raise ProviderRateLimitError("HTTP 429")

    result = verify_paper_candidate(
        PaperCandidateContract(paper_id="title:1", title="Catalyst paper"),
        probes=[rate_limited_probe],
    )

    assert result.status == "verify_pending"
    assert "HTTP 429" in result.reason


def test_verify_paper_candidate_confirms_arxiv_id(monkeypatch) -> None:
    atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>https://arxiv.org/abs/2401.12345v1</id></entry>
</feed>
"""

    monkeypatch.setattr(literature_verification, "fetch_text", lambda url, headers=None: atom)

    result = verify_paper_candidate(
        PaperCandidateContract(
            paper_id="arxiv:2401.12345",
            arxiv_id="2401.12345",
            title="arXiv paper",
        )
    )

    assert result.status == "verified"
    assert result.method == "arxiv"


def test_verify_evidence_bundle_updates_verification_counts() -> None:
    bundle = EvidenceBundleContract(
        bundle_id="bundle-q",
        query_id="q",
        request=SearchRequestContract(query_id="q", query="test"),
        papers=[
            PaperCandidateContract(paper_id="paper-v", title="verified"),
            PaperCandidateContract(paper_id="paper-u", title="unverified"),
            PaperCandidateContract(paper_id="paper-p", title="pending"),
        ],
    )

    def probe(candidate: PaperCandidateContract):
        if candidate.paper_id == "paper-v":
            return PaperVerificationContract(
                paper_id=candidate.paper_id,
                status="verified",
                method="title_fuzzy",
                confidence="medium",
            )
        if candidate.paper_id == "paper-u":
            return PaperVerificationContract(
                paper_id=candidate.paper_id,
                status="unverified",
                method="title_fuzzy",
                confidence="low",
            )
        return PaperVerificationContract(
            paper_id=candidate.paper_id,
            status="verify_pending",
            method="none",
            confidence="low",
            reason="rate limit",
        )

    verified_bundle = verify_evidence_bundle(bundle, probes=[probe])

    assert verified_bundle.retrieval_metadata.verified_count == 1
    assert verified_bundle.retrieval_metadata.unverified_count == 1
    assert verified_bundle.retrieval_metadata.pending_count == 1
    assert [item.status for item in verified_bundle.verified_papers] == [
        "verified",
        "unverified",
        "verify_pending",
    ]
