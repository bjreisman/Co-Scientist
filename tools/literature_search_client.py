"""Host-agent callable literature search bridge entry points."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from packages.agent_contracts import (
    EvidenceBundleContract,
    PaperCandidateContract,
    PaperVerificationContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
)
from packages.agent_mechanics.literature_bundle import (
    build_evidence_bundle as build_mechanics_evidence_bundle,
)
from packages.agent_mechanics.literature_bundle import stable_query_id
from packages.agent_mechanics.literature_providers import ProviderSearchFunction
from packages.agent_mechanics.literature_search import run_literature_search
from packages.agent_mechanics.literature_verification import (
    VerificationProbe,
    verify_evidence_bundle,
    verify_paper_candidates,
)


def search_literature(
    run_dir: str | Path,
    request: SearchRequestContract | Mapping[str, Any],
    *,
    provider_searchers: Mapping[str, ProviderSearchFunction] | None = None,
    verify: bool = True,
    verification_probes: Sequence[VerificationProbe] | None = None,
) -> EvidenceBundleContract:
    """Run literature search, optionally verify papers, and persist artifacts."""
    resolved_run_dir = Path(run_dir).resolve()
    search_request = _normalize_request(request, resolved_run_dir)
    bundle = run_literature_search(search_request, provider_searchers=provider_searchers)
    if verify:
        bundle = verify_evidence_bundle(bundle, probes=verification_probes)
    _write_query_artifacts(resolved_run_dir, bundle)
    return bundle


def verify_literature_candidates(
    run_dir: str | Path,
    query_id: str,
    *,
    verification_probes: Sequence[VerificationProbe] | None = None,
) -> list[PaperVerificationContract]:
    """Verify persisted candidate papers for a query and update bundle artifacts when present."""
    resolved_run_dir = Path(run_dir).resolve()
    query_dir = _query_dir(resolved_run_dir, query_id)
    candidates = [
        PaperCandidateContract.from_payload(item)
        for item in _read_json(query_dir / "CANDIDATE_PAPERS.json", default=[])
    ]
    verifications = verify_paper_candidates(candidates, probes=verification_probes)
    _write_json(query_dir / "VERIFIED_PAPERS.json", [item.model_dump(mode="json") for item in verifications])

    bundle_path = query_dir / "EVIDENCE_BUNDLE.json"
    if bundle_path.exists():
        bundle = EvidenceBundleContract.from_json_file(bundle_path)
        metadata = bundle.retrieval_metadata.model_copy(
            update={
                "verified_count": sum(1 for item in verifications if item.status == "verified"),
                "unverified_count": sum(1 for item in verifications if item.status == "unverified"),
                "pending_count": sum(1 for item in verifications if item.status == "verify_pending"),
            }
        )
        updated_bundle = bundle.model_copy(update={"verified_papers": verifications, "retrieval_metadata": metadata})
        _write_query_artifacts(resolved_run_dir, updated_bundle)
    return verifications


def build_evidence_bundle(run_dir: str | Path, query_id: str) -> EvidenceBundleContract:
    """Build and persist an evidence bundle from existing query artifacts."""
    resolved_run_dir = Path(run_dir).resolve()
    query_dir = _query_dir(resolved_run_dir, query_id)
    request = SearchRequestContract.from_json_file(query_dir / "REQUEST.json")
    receipts = [
        SearchProviderReceiptContract.from_payload(item)
        for item in _read_json(query_dir / "PROVIDER_RECEIPTS.json", default=[])
    ]
    candidates = [
        PaperCandidateContract.from_payload(item)
        for item in _read_json(query_dir / "CANDIDATE_PAPERS.json", default=[])
    ]
    bundle = build_mechanics_evidence_bundle(request, candidates, receipts)
    verifications = [
        PaperVerificationContract.from_payload(item)
        for item in _read_json(query_dir / "VERIFIED_PAPERS.json", default=[])
    ]
    if verifications:
        metadata = bundle.retrieval_metadata.model_copy(
            update={
                "verified_count": sum(1 for item in verifications if item.status == "verified"),
                "unverified_count": sum(1 for item in verifications if item.status == "unverified"),
                "pending_count": sum(1 for item in verifications if item.status == "verify_pending"),
            }
        )
        bundle = bundle.model_copy(update={"verified_papers": verifications, "retrieval_metadata": metadata})
    _write_query_artifacts(resolved_run_dir, bundle)
    return bundle


def load_evidence_bundle(run_dir: str | Path, bundle_id: str) -> EvidenceBundleContract:
    """Load one persisted evidence bundle by bundle id."""
    resolved_run_dir = Path(run_dir).resolve()
    bundle_path = resolved_run_dir / "literature" / "bundles" / f"{bundle_id}.json"
    if not bundle_path.exists():
        raise FileNotFoundError(f"Evidence bundle not found: {bundle_path}")
    return EvidenceBundleContract.from_json_file(bundle_path)


def _normalize_request(
    request: SearchRequestContract | Mapping[str, Any],
    run_dir: Path,
) -> SearchRequestContract:
    search_request = (
        request if isinstance(request, SearchRequestContract) else SearchRequestContract.from_payload(dict(request))
    )
    query_id = search_request.query_id or stable_query_id(search_request)
    run_id = search_request.run_id or run_dir.name
    return search_request.model_copy(update={"query_id": query_id, "run_id": run_id})


def _write_query_artifacts(run_dir: Path, bundle: EvidenceBundleContract) -> None:
    query_dir = _query_dir(run_dir, bundle.query_id)
    bundle_dir = run_dir / "literature" / "bundles"
    query_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    _write_json(query_dir / "REQUEST.json", bundle.request.model_dump(mode="json"))
    _write_json(
        query_dir / "PROVIDER_RECEIPTS.json",
        [receipt.model_dump(mode="json") for receipt in bundle.provider_receipts],
    )
    _write_json(
        query_dir / "CANDIDATE_PAPERS.json",
        [paper.model_dump(mode="json") for paper in bundle.papers],
    )
    _write_json(
        query_dir / "VERIFIED_PAPERS.json",
        [verification.model_dump(mode="json") for verification in bundle.verified_papers],
    )
    _write_json(query_dir / "EVIDENCE_BUNDLE.json", bundle.model_dump(mode="json"))
    _write_text(query_dir / "EVIDENCE_BUNDLE.md", render_evidence_bundle_markdown(bundle))
    _write_text(
        query_dir / "SEARCH_TRACE.jsonl",
        "".join(
            json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for receipt in bundle.provider_receipts
        ),
    )
    _write_json(bundle_dir / f"{bundle.bundle_id}.json", bundle.model_dump(mode="json"))


def render_evidence_bundle_markdown(bundle: EvidenceBundleContract) -> str:
    """Render a compact human-readable view of one evidence bundle."""
    lines = [
        f"# Evidence Bundle {bundle.bundle_id}",
        "",
        f"- Query ID: `{bundle.query_id}`",
        f"- Status: `{bundle.retrieval_metadata.status}`",
        f"- Providers attempted: {', '.join(bundle.retrieval_metadata.providers_attempted) or 'none'}",
        f"- Providers succeeded: {', '.join(bundle.retrieval_metadata.providers_succeeded) or 'none'}",
        f"- Papers: {len(bundle.papers)}",
        f"- Verified: {bundle.retrieval_metadata.verified_count}",
        f"- Unverified: {bundle.retrieval_metadata.unverified_count}",
        f"- Pending: {bundle.retrieval_metadata.pending_count}",
        "",
        "## Papers",
        "",
    ]
    for paper in bundle.papers:
        identifiers = ", ".join(
            item
            for item in [
                f"DOI {paper.doi}" if paper.doi else "",
                f"arXiv {paper.arxiv_id}" if paper.arxiv_id else "",
                f"PMID {paper.pmid}" if paper.pmid else "",
            ]
            if item
        )
        lines.append(f"- `{paper.paper_id}` {paper.title or '(untitled)'}")
        lines.append(f"  - Year: {paper.year or 'unknown'}")
        lines.append(f"  - Venue: {paper.venue or 'unknown'}")
        lines.append(f"  - Identifiers: {identifiers or 'none'}")
    return "\n".join(lines).rstrip() + "\n"


def _query_dir(run_dir: Path, query_id: str) -> Path:
    return run_dir / "literature" / "queries" / query_id


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    temp_path.replace(path)


__all__ = [
    "build_evidence_bundle",
    "load_evidence_bundle",
    "render_evidence_bundle_markdown",
    "search_literature",
    "verify_literature_candidates",
]
