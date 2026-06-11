# Literature Search Contract

Use this shared reference whenever a skill needs external literature evidence.

Core rule:

- Formal external evidence must come from `tools.search_literature(...)` and the resulting `EvidenceBundleContract`.
- Do not invent papers, DOIs, arXiv IDs, venues, citation counts, or abstracts.
- Do not treat model memory as a substitute for search bridge artifacts.
- If the bridge is blocked or every provider fails, record the degraded state and do not claim that the result is literature-grounded.

Canonical tool surface:

```python
from tools import search_literature, load_evidence_bundle, verify_literature_candidates
```

Canonical contracts:

- `packages/agent_contracts/literature.py`
- `SearchRequestContract`
- `SearchProviderReceiptContract`
- `PaperCandidateContract`
- `PaperVerificationContract`
- `EvidenceBundleContract`

Canonical artifacts:

```text
literature/queries/<query_id>/REQUEST.json
literature/queries/<query_id>/PROVIDER_RECEIPTS.json
literature/queries/<query_id>/CANDIDATE_PAPERS.json
literature/queries/<query_id>/VERIFIED_PAPERS.json
literature/queries/<query_id>/EVIDENCE_BUNDLE.json
literature/queries/<query_id>/EVIDENCE_BUNDLE.md
literature/queries/<query_id>/SEARCH_TRACE.jsonl
literature/bundles/<bundle_id>.json
```

Recommended request shape:

```python
tools.search_literature(
    run_dir,
    {
        "query_id": "<stable-query-id>",
        "goal": "<why this evidence is needed>",
        "query": "<search query>",
        "query_type": "mechanism_support | novelty_scan | contradiction_scan | claim_verification | evidence_gathering",
        "keywords": ["..."],
        "providers": ["auto"],
        "filters": {"max_results": 10},
        "consumer": "<calling-skill-name>",
    },
)
```

Consumption rules:

- Use `EVIDENCE_BUNDLE.json` as the canonical input.
- `provider_receipts` prove which providers were actually attempted.
- `verified_papers` records existence checks; unverified papers must remain visible as uncertainty, not silently disappear.
- `synthesized_findings[].paper_refs` may only reference paper IDs present in `papers`.
- If `retrieval_metadata.status == "blocked"`, the caller must stop, retry with a broader provider list, or write a degraded artifact that explicitly says evidence retrieval was blocked.
- If `retrieval_metadata.status == "partial"`, the caller may continue but must preserve the partial-source limitation in the downstream artifact.

Validation:

Run:

```text
python -m tools.validation.contract_validation <run_dir> --skill <calling-skill>
```

The validator checks schema validity, provider receipt consistency, bundle copy consistency, paper reference closure, and verification count consistency.
