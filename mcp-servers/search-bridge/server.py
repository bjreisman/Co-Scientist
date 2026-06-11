"""MCP transport adapter for the Co-Scientist literature search bridge."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.agent_contracts import EvidenceBundleContract
from packages.agent_mechanics.literature_providers import ProviderSearchFunction
from packages.agent_mechanics.literature_verification import VerificationProbe
from tools.literature_search_client import (
    load_evidence_bundle,
    search_literature,
    verify_literature_candidates,
)


SERVER_NAME = "co-scientist-search-bridge"


def handle_search_literature(
    run_dir: str,
    request: Mapping[str, Any],
    *,
    verify: bool = True,
    provider_searchers: Mapping[str, ProviderSearchFunction] | None = None,
    verification_probes: Sequence[VerificationProbe] | None = None,
) -> dict[str, Any]:
    """Run the canonical literature search bridge and return JSON-compatible output."""
    bundle = search_literature(
        run_dir,
        request,
        provider_searchers=provider_searchers,
        verify=verify,
        verification_probes=verification_probes,
    )
    return _bundle_response(Path(run_dir), bundle)


def handle_search_start(
    run_dir: str,
    request: Mapping[str, Any],
    *,
    verify: bool = True,
    provider_searchers: Mapping[str, ProviderSearchFunction] | None = None,
    verification_probes: Sequence[VerificationProbe] | None = None,
) -> dict[str, Any]:
    """Start a search job and persist a small MCP job record.

    The first transport version executes synchronously because the canonical Python
    bridge already owns retries, provider receipts, and blocked-state semantics.
    """
    job_id = _job_id(request)
    _write_job_record(
        run_dir,
        {
            "job_id": job_id,
            "status": "running",
            "bundle_id": "",
            "query_id": str(request.get("query_id", "")),
            "error": "",
        },
    )
    try:
        response = handle_search_literature(
            run_dir,
            request,
            verify=verify,
            provider_searchers=provider_searchers,
            verification_probes=verification_probes,
        )
    except Exception as exc:
        record = {
            "job_id": job_id,
            "status": "failed",
            "bundle_id": "",
            "query_id": str(request.get("query_id", "")),
            "error": f"{exc.__class__.__name__}: {exc}",
        }
        _write_job_record(run_dir, record)
        raise

    bundle_payload = response["bundle"]
    retrieval_status = bundle_payload["retrieval_metadata"]["status"]
    record = {
        "job_id": job_id,
        "status": "blocked" if retrieval_status == "blocked" else "completed",
        "bundle_id": bundle_payload["bundle_id"],
        "query_id": bundle_payload["query_id"],
        "artifact_paths": response["artifact_paths"],
        "error": "",
    }
    _write_job_record(run_dir, record)
    return record


def handle_search_status(run_dir: str, job_id: str) -> dict[str, Any]:
    """Return the persisted status for a search job."""
    job_path = _job_path(run_dir, job_id)
    if not job_path.exists():
        raise FileNotFoundError(f"Search bridge job not found: {job_path}")
    return json.loads(job_path.read_text(encoding="utf-8"))


def handle_get_evidence_bundle(run_dir: str, bundle_id: str) -> dict[str, Any]:
    """Load one persisted evidence bundle."""
    bundle = load_evidence_bundle(run_dir, bundle_id)
    return _bundle_response(Path(run_dir), bundle)


def handle_verify_literature_candidates(
    run_dir: str,
    query_id: str,
    *,
    verification_probes: Sequence[VerificationProbe] | None = None,
) -> dict[str, Any]:
    """Verify persisted literature candidates for a query."""
    verifications = verify_literature_candidates(
        run_dir,
        query_id,
        verification_probes=verification_probes,
    )
    return {
        "query_id": query_id,
        "verified_papers": [item.model_dump(mode="json") for item in verifications],
        "artifact_paths": {
            "verified_papers": str(
                (Path(run_dir) / "literature" / "queries" / query_id / "VERIFIED_PAPERS.json").resolve()
            )
        },
    }


def create_server() -> Any:
    """Create the FastMCP server instance."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install the optional `mcp` package to run the search bridge MCP server.") from exc

    server = FastMCP(
        SERVER_NAME,
        instructions=(
            "Transport adapter for Co-Scientist literature search. "
            "All tools call tools.literature_search_client and write run-local artifacts."
        ),
    )

    @server.tool(
        name="search_literature",
        description="Run literature search and return an EvidenceBundleContract plus artifact paths.",
    )
    def search_literature_tool(run_dir: str, request: dict[str, Any], verify: bool = True) -> dict[str, Any]:
        return handle_search_literature(run_dir, request, verify=verify)

    @server.tool(
        name="search_start",
        description="Run a literature search and persist a search job status record.",
    )
    def search_start_tool(run_dir: str, request: dict[str, Any], verify: bool = True) -> dict[str, Any]:
        return handle_search_start(run_dir, request, verify=verify)

    @server.tool(
        name="search_status",
        description="Read a persisted search job status record.",
    )
    def search_status_tool(run_dir: str, job_id: str) -> dict[str, Any]:
        return handle_search_status(run_dir, job_id)

    @server.tool(
        name="get_evidence_bundle",
        description="Load one persisted EvidenceBundleContract by bundle id.",
    )
    def get_evidence_bundle_tool(run_dir: str, bundle_id: str) -> dict[str, Any]:
        return handle_get_evidence_bundle(run_dir, bundle_id)

    @server.tool(
        name="verify_literature_candidates",
        description="Verify persisted candidate papers for one query and update bundle artifacts.",
    )
    def verify_literature_candidates_tool(run_dir: str, query_id: str) -> dict[str, Any]:
        return handle_verify_literature_candidates(run_dir, query_id)

    return server


def main() -> None:
    """Run the MCP server over stdio."""
    create_server().run("stdio")


def _bundle_response(run_dir: Path, bundle: EvidenceBundleContract) -> dict[str, Any]:
    return {
        "bundle": bundle.model_dump(mode="json"),
        "artifact_paths": _artifact_paths(run_dir, bundle),
    }


def _artifact_paths(run_dir: Path, bundle: EvidenceBundleContract) -> dict[str, str]:
    query_dir = run_dir / "literature" / "queries" / bundle.query_id
    return {
        "request": str((query_dir / "REQUEST.json").resolve()),
        "provider_receipts": str((query_dir / "PROVIDER_RECEIPTS.json").resolve()),
        "candidate_papers": str((query_dir / "CANDIDATE_PAPERS.json").resolve()),
        "verified_papers": str((query_dir / "VERIFIED_PAPERS.json").resolve()),
        "evidence_bundle": str((query_dir / "EVIDENCE_BUNDLE.json").resolve()),
        "evidence_bundle_markdown": str((query_dir / "EVIDENCE_BUNDLE.md").resolve()),
        "search_trace": str((query_dir / "SEARCH_TRACE.jsonl").resolve()),
        "bundle_copy": str((run_dir / "literature" / "bundles" / f"{bundle.bundle_id}.json").resolve()),
    }


def _job_id(request: Mapping[str, Any]) -> str:
    query_id = str(request.get("query_id", "")).strip()
    if query_id:
        return f"search-{query_id}"
    return f"search-{uuid.uuid4().hex[:12]}"


def _job_path(run_dir: str, job_id: str) -> Path:
    return Path(run_dir) / "literature" / "mcp_jobs" / f"{job_id}.json"


def _write_job_record(run_dir: str, record: Mapping[str, Any]) -> None:
    job_path = _job_path(run_dir, str(record["job_id"]))
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
