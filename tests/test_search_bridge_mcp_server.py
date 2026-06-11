from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.agent_contracts import (
    PaperCandidateContract,
    PaperVerificationContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
)
from packages.agent_mechanics.literature_providers.common import ProviderSearchResult


SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "search-bridge" / "server.py"
CODEX_CONFIG_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "codex" / "config.toml.example"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("co_scientist_search_bridge_mcp_server", SERVER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_provider(request: SearchRequestContract) -> ProviderSearchResult:
    return ProviderSearchResult(
        candidates=[
            PaperCandidateContract(
                paper_id="doi:10.1000/mcp",
                title="MCP bridge evidence",
                doi="10.1000/mcp",
                abstract="The MCP adapter writes the canonical evidence bundle.",
                provider_sources=["openalex"],
                relevance_score=0.9,
            )
        ],
        receipt=SearchProviderReceiptContract(
            provider="openalex",
            status="succeeded",
            result_count=1,
        ),
    )


def _verification_probe(candidate: PaperCandidateContract) -> PaperVerificationContract:
    return PaperVerificationContract(
        paper_id=candidate.paper_id,
        status="verified",
        method="crossref",
        confidence="high",
        reason="MCP smoke verifier resolved the DOI.",
    )


def test_mcp_search_bridge_handlers_call_canonical_tooling() -> None:
    module = _load_server_module()
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()

        response = module.handle_search_literature(
            str(run_dir),
            {
                "query_id": "q-mcp",
                "query": "mcp bridge evidence",
                "providers": ["openalex"],
                "filters": {"max_results": 3},
            },
            verify=False,
            provider_searchers={"openalex": _fake_provider},
        )

        assert response["bundle"]["bundle_id"] == "bundle-q-mcp"
        assert response["bundle"]["retrieval_metadata"]["status"] == "succeeded"
        assert Path(response["artifact_paths"]["evidence_bundle"]).exists()

        job = module.handle_search_start(
            str(run_dir),
            {
                "query_id": "q-mcp-job",
                "query": "mcp bridge evidence",
                "providers": ["openalex"],
            },
            verify=False,
            provider_searchers={"openalex": _fake_provider},
        )

        assert job["status"] == "completed"
        assert job["bundle_id"] == "bundle-q-mcp-job"
        assert module.handle_search_status(str(run_dir), job["job_id"])["bundle_id"] == "bundle-q-mcp-job"

        loaded = module.handle_get_evidence_bundle(str(run_dir), "bundle-q-mcp-job")
        assert loaded["bundle"]["query_id"] == "q-mcp-job"

        verification = module.handle_verify_literature_candidates(
            str(run_dir),
            "q-mcp-job",
            verification_probes=[_verification_probe],
        )
        assert verification["verified_papers"][0]["status"] == "verified"


def test_mcp_search_bridge_can_create_fastmcp_server_when_sdk_is_available() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    module = _load_server_module()

    server = module.create_server()

    assert server is not None


def test_codex_search_bridge_config_template_is_parseable() -> None:
    payload = tomllib.loads(CODEX_CONFIG_TEMPLATE.read_text(encoding="utf-8"))

    server = payload["mcp_servers"]["co_scientist_search_bridge"]
    assert server["command"] == "uv"
    assert "mcp-servers/search-bridge/server.py" in server["args"]
    assert server["enabled"] is True
    assert "OPENALEX_EMAIL" in server["env_vars"]
