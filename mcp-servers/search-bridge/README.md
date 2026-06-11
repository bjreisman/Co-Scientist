# Co-Scientist Search Bridge MCP Server

This directory contains the optional MCP transport for the Co-Scientist literature search bridge.

The server is intentionally thin. It does not implement provider search, deduplication, verification, evidence bundle construction, or artifact validation. Those responsibilities stay in:

- `packages/agent_mechanics/literature_*.py`
- `packages/agent_mechanics/literature_providers/*.py`
- `tools/literature_search_client.py`
- `tools/validation/contract_validation.py`

## Install

The project can run without this server. Install the optional MCP dependency only when an external MCP host needs to call the bridge:

```powershell
conda activate cos
pip install -e .[mcp]
```

## Run

From the repository root:

```powershell
python mcp-servers/search-bridge/server.py
```

The server runs over stdio by default through FastMCP.

## Tools

The transport exposes:

- `search_literature(run_dir, request, verify=True)`
- `search_start(run_dir, request, verify=True)`
- `search_status(run_dir, job_id)`
- `get_evidence_bundle(run_dir, bundle_id)`
- `verify_literature_candidates(run_dir, query_id)`

`search_literature` and `search_start` both call the canonical Python bridge and write run-local artifacts. The first transport version executes `search_start` synchronously, then persists a job record under:

```text
literature/mcp_jobs/<job_id>.json
```

This keeps the transport observable without introducing a second background job system.

## Request Shape

Example request payload:

```json
{
  "query_id": "q-ammonia-catalyst",
  "goal": "optimize ammonia synthesis catalysts",
  "query": "ammonia synthesis catalyst heterogeneous catalyst active site mechanism",
  "providers": ["openalex", "crossref", "europe_pmc"],
  "filters": {"max_results": 5},
  "consumer": "literature-search"
}
```

The response includes the serialized `EvidenceBundleContract` and absolute artifact paths.

## Reliability Boundary

The MCP server can only expose the bridge to MCP-capable hosts. It cannot guarantee provider uptime, paid full-text access, or that a candidate paper supports a fine-grained scientific claim. Reliability comes from the canonical bridge artifacts:

- `PROVIDER_RECEIPTS.json` proves which providers were attempted.
- `EVIDENCE_BUNDLE.json` records `succeeded`, `partial`, or `blocked` status.
- `VERIFIED_PAPERS.json` records paper-existence verification.
- `tools.validation.contract_validation` checks artifact consistency and retrieval-result linkage.
