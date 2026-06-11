"""Paper-existence verification for literature search candidates."""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from defusedxml import ElementTree as ET

from packages.agent_contracts import (
    EvidenceBundleContract,
    PaperCandidateContract,
    PaperVerificationContract,
)

from .literature_providers.common import (
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    build_url,
    clean_text,
    fetch_json,
    fetch_text,
)


VerificationProbe = Callable[[PaperCandidateContract], PaperVerificationContract | None]

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_API = "https://export.arxiv.org/api/query"
_CROSSREF_WORKS_API = "https://api.crossref.org/works"
_S2_SEARCH_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_OPENALEX_WORKS_API = "https://api.openalex.org/works"
_EUROPE_PMC_SEARCH_API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_TITLE_NORMALIZE_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_FUZZY_THRESHOLD = 0.6


def verify_paper_candidates(
    candidates: Sequence[PaperCandidateContract],
    *,
    probes: Sequence[VerificationProbe] | None = None,
) -> list[PaperVerificationContract]:
    """Verify a list of candidate papers with layered provider probes."""
    return [verify_paper_candidate(candidate, probes=probes) for candidate in candidates]


def verify_paper_candidate(
    candidate: PaperCandidateContract,
    *,
    probes: Sequence[VerificationProbe] | None = None,
) -> PaperVerificationContract:
    """Verify one candidate paper against public paper indexes."""
    if not any([candidate.arxiv_id, candidate.doi, candidate.title, candidate.pmid, candidate.pmcid]):
        return _verification(
            candidate,
            status="error",
            method="none",
            confidence="low",
            reason="Candidate has no arXiv ID, DOI, title, PMID, or PMCID.",
        )

    pending_reasons: list[str] = []
    for probe in probes or default_verification_probes():
        try:
            result = probe(candidate)
        except (ProviderRateLimitError, ProviderTimeoutError) as exc:
            pending_reasons.append(f"{probe.__name__}: {exc}")
            continue
        except ProviderError as exc:
            if _looks_transient_provider_error(exc):
                pending_reasons.append(f"{probe.__name__}: {exc}")
            continue
        if result is None:
            continue
        if result.status == "verified":
            return result
        if result.status == "verify_pending":
            pending_reasons.append(result.reason)

    if pending_reasons:
        return _verification(
            candidate,
            status="verify_pending",
            method="none",
            confidence="low",
            reason="; ".join(pending_reasons),
        )
    return _verification(
        candidate,
        status="unverified",
        method="none",
        confidence="low",
        reason="No verification probe confirmed this candidate.",
    )


def verify_evidence_bundle(
    bundle: EvidenceBundleContract,
    *,
    probes: Sequence[VerificationProbe] | None = None,
) -> EvidenceBundleContract:
    """Return a bundle with paper verification records and metadata counts."""
    verifications = verify_paper_candidates(bundle.papers, probes=probes)
    verified_count = sum(1 for item in verifications if item.status == "verified")
    unverified_count = sum(1 for item in verifications if item.status == "unverified")
    pending_count = sum(1 for item in verifications if item.status == "verify_pending")
    metadata = bundle.retrieval_metadata.model_copy(
        update={
            "verified_count": verified_count,
            "unverified_count": unverified_count,
            "pending_count": pending_count,
        }
    )
    return bundle.model_copy(
        update={
            "verified_papers": verifications,
            "retrieval_metadata": metadata,
        }
    )


def default_verification_probes() -> tuple[VerificationProbe, ...]:
    """Return the default layered verification probes."""
    return (
        verify_by_arxiv,
        verify_by_crossref,
        verify_by_semantic_scholar_title,
        verify_by_openalex_title,
        verify_by_europe_pmc_title,
    )


def verify_by_arxiv(candidate: PaperCandidateContract) -> PaperVerificationContract | None:
    """Verify a candidate by arXiv ID."""
    if not candidate.arxiv_id:
        return None
    arxiv_id = candidate.arxiv_id.split("v", 1)[0]
    text = fetch_text(build_url(_ARXIV_API, {"id_list": arxiv_id, "max_results": 1}))
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ProviderError("arXiv returned invalid Atom XML during verification.") from exc
    entries = root.findall(f"{{{_ATOM_NS}}}entry")
    if entries:
        return _verification(
            candidate,
            status="verified",
            method="arxiv",
            confidence="high",
            reason="arXiv API returned an entry for the candidate ID.",
        )
    return _verification(
        candidate,
        status="unverified",
        method="arxiv",
        confidence="low",
        reason="arXiv API returned no entry for the candidate ID.",
    )


def verify_by_crossref(candidate: PaperCandidateContract) -> PaperVerificationContract | None:
    """Verify a candidate by DOI through Crossref."""
    if not candidate.doi:
        return None
    doi_path = urllib.parse.quote(candidate.doi, safe="")
    fetch_json(f"{_CROSSREF_WORKS_API}/{doi_path}")
    return _verification(
        candidate,
        status="verified",
        method="crossref",
        confidence="high",
        reason="Crossref resolved the candidate DOI.",
    )


def verify_by_semantic_scholar_title(candidate: PaperCandidateContract) -> PaperVerificationContract | None:
    """Verify a candidate by fuzzy title match through Semantic Scholar."""
    if not candidate.title:
        return None
    payload = fetch_json(
        build_url(
            _S2_SEARCH_API,
            {"query": candidate.title, "limit": 1, "fields": "title,externalIds"},
        ),
        headers={"Accept": "application/json", "User-Agent": "co-scientist-literature/1.0"},
    )
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return _unverified_title(candidate, "semantic_scholar")
    title = clean_text(data[0].get("title") if isinstance(data[0], dict) else "")
    return _title_match_verification(candidate, title, method="semantic_scholar")


def verify_by_openalex_title(candidate: PaperCandidateContract) -> PaperVerificationContract | None:
    """Verify a candidate by fuzzy title match through OpenAlex."""
    if not candidate.title:
        return None
    payload = fetch_json(build_url(_OPENALEX_WORKS_API, {"search": candidate.title, "per-page": 1}))
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return _unverified_title(candidate, "openalex")
    title = clean_text(results[0].get("display_name") if isinstance(results[0], dict) else "")
    return _title_match_verification(candidate, title, method="openalex")


def verify_by_europe_pmc_title(candidate: PaperCandidateContract) -> PaperVerificationContract | None:
    """Verify a candidate by fuzzy title match through Europe PMC."""
    if not candidate.title:
        return None
    payload = fetch_json(
        build_url(
            _EUROPE_PMC_SEARCH_API,
            {
                "query": candidate.title,
                "format": "json",
                "pageSize": 1,
                "resultType": "core",
            },
        )
    )
    result_list = payload.get("resultList") if isinstance(payload.get("resultList"), dict) else {}
    results = result_list.get("result") if isinstance(result_list, dict) else []
    if not isinstance(results, list) or not results:
        return _unverified_title(candidate, "europe_pmc")
    title = clean_text(results[0].get("title") if isinstance(results[0], dict) else "")
    return _title_match_verification(candidate, title, method="europe_pmc")


def title_overlap(left: str, right: str) -> float:
    """Return normalized word-overlap score between two titles."""
    left_words = set(normalize_title(left).split())
    right_words = set(normalize_title(right).split())
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / max(len(left_words), len(right_words))


def normalize_title(value: str) -> str:
    """Normalize title text for fuzzy comparison."""
    value = _TITLE_NORMALIZE_RE.sub(" ", value.lower())
    return _WHITESPACE_RE.sub(" ", value).strip()


def _title_match_verification(
    candidate: PaperCandidateContract,
    matched_title: str,
    *,
    method: str,
) -> PaperVerificationContract:
    score = title_overlap(candidate.title, matched_title)
    if score >= _FUZZY_THRESHOLD:
        return _verification(
            candidate,
            status="verified",
            method=method,
            confidence="medium",
            reason=f"{method} returned a fuzzy title match with score {score:.2f}.",
        )
    return _verification(
        candidate,
        status="unverified",
        method=method,
        confidence="low",
        reason=f"{method} returned no sufficiently close title match.",
    )


def _unverified_title(candidate: PaperCandidateContract, method: str) -> PaperVerificationContract:
    return _verification(
        candidate,
        status="unverified",
        method=method,
        confidence="low",
        reason=f"{method} returned no title match.",
    )


def _verification(
    candidate: PaperCandidateContract,
    *,
    status: str,
    method: str,
    confidence: str,
    reason: str,
) -> PaperVerificationContract:
    return PaperVerificationContract(
        paper_id=candidate.paper_id,
        status=status,
        method=method,
        confidence=confidence,
        reason=reason,
        checked_at=datetime.now(UTC),
    )


def _looks_transient_provider_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "http 5" in message or "timeout" in message or "network" in message


__all__ = [
    "VerificationProbe",
    "default_verification_probes",
    "normalize_title",
    "title_overlap",
    "verify_by_arxiv",
    "verify_by_crossref",
    "verify_by_europe_pmc_title",
    "verify_by_openalex_title",
    "verify_by_semantic_scholar_title",
    "verify_evidence_bundle",
    "verify_paper_candidate",
    "verify_paper_candidates",
]
