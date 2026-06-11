# Schema Index

Use this index before writing or editing any canonical artifact.

Core rule:

1. First identify the target artifact path.
2. Then open the exact Python contract file listed below.
3. Only after reading the contract fields, required keys, nested structures, and enum values should you emit JSON.
4. Run `python -m tools.validation.contract_validation <run_dir> --skill <top-level-skill>` after each major write.

Artifact to contract mapping:

- `RUN_POLICY.yaml`
  - `packages/agent_contracts/policy.py`
  - `RunPolicyContract`
- `state/START_REQUEST.json`
  - `packages/agent_contracts/start_request.py`
  - `StartRequestContract`
- `state/POLICY_DECISION.json`
  - `packages/agent_contracts/policy.py`
  - `PolicyDecisionContract`
- `state/PIPELINE_STATE.json`
  - `packages/agent_contracts/pipeline_runtime.py`
  - `PipelineStateContract`
- `state/CURRENT_STAGE.json`
  - `packages/agent_contracts/pipeline_runtime.py`
  - `CurrentStageContract`
- `state/RESOLVED_RUN_CONFIG.json`
  - `packages/agent_contracts/resolved_config.py`
  - `ResolvedRunConfigContract`
- `state/EVOLUTION_STATE.json`
  - `packages/agent_contracts/pipeline_control.py`
  - `EvolutionStateContract`
- `state/COMPLETION_DECISION.json`
  - `packages/agent_contracts/pipeline_control.py`
  - `CompletionDecisionContract`
- `state/STRATEGY_PLAN.json`
  - `packages/agent_contracts/strategy_plan.py`
  - `StrategyPlanContract`
- `state/STRATEGY_DECISIONS.jsonl`
  - `packages/agent_contracts/strategy_plan.py`
  - `StrategyDecisionRecordContract`
- `state/EVOLUTION_ROUNDS.jsonl`
  - `packages/agent_contracts/evolution_round.py`
  - `EvolutionRoundRecordContract`
- `research_plan/RESEARCH_PLAN.json`
  - `packages/agent_contracts/research_plan.py`
  - `ResearchPlanContract`
- `literature/queries/<query_id>/REQUEST.json`
  - `packages/agent_contracts/literature.py`
  - `SearchRequestContract`
- `literature/queries/<query_id>/PROVIDER_RECEIPTS.json`
  - `packages/agent_contracts/literature.py`
  - `SearchProviderReceiptContract`
  - This artifact serializes a list of provider receipt payloads.
- `literature/queries/<query_id>/EVIDENCE_BUNDLE.json`
  - `packages/agent_contracts/literature.py`
  - `EvidenceBundleContract`
- `literature/bundles/<bundle_id>.json`
  - `packages/agent_contracts/literature.py`
  - `EvidenceBundleContract`
- `meta/INSIGHTS_FROM_REVIEWS.json`
  - `packages/agent_contracts/meta_review.py`
  - `InsightsFromReviewsContract`
- `meta/RESEARCH_OVERVIEW.json`
  - `packages/agent_contracts/meta_review.py`
  - `ResearchOverviewContract`
- `hypotheses/<id>/HYPOTHESIS.json`
  - `packages/agent_contracts/hypothesis.py`
  - `HypothesisContract`
- `hypotheses/<id>/REVIEW/FULL_REVIEW.json`
  - `packages/agent_contracts/review.py`
  - `FullReviewContract`
- `hypotheses/<id>/REVIEW/INITIAL_REVIEW.json`
  - `packages/agent_contracts/review.py`
  - `InitialReviewContract`
- `hypotheses/<id>/REVIEW/DEEP_VERIFICATION.json`
  - `packages/agent_contracts/review.py`
  - `DeepVerificationReviewContract`
- `hypotheses/<id>/REVIEW/OBSERVATION_REVIEW.json`
  - `packages/agent_contracts/review.py`
  - `ObservationReviewContract`
- `hypotheses/<id>/REVIEW/SIMULATION_REVIEW.json`
  - `packages/agent_contracts/review.py`
  - `SimulationReviewContract`
- `hypotheses/<id>/REVIEW/REVIEW_SUMMARY.json`
  - `packages/agent_contracts/review.py`
  - `ReviewSummaryContract`
- `state/PROXIMITY_GRAPH.json`
  - `packages/agent_contracts/state.py`
  - `ProximityGraphContract`
- `islands/ISLANDS.json`
  - `packages/agent_contracts/state.py`
  - `IslandStateContract`
  - `items` must serialize a list of `IslandStateContract` payloads inside the run-level wrapper object.
- `tournaments/*.json`
  - `packages/agent_contracts/ranking.py`
  - `TournamentMatchContract`

Notes:

- `packages/agent_contracts/pipeline_runtime.py` is the canonical source for run-level pipeline summary artifacts. Stage labels and skill names must still remain consistent with `packages/agent_support/pipeline_semantics.py`.
- `packages/agent_contracts/hypothesis.py` also embeds the aggregate `ReviewContract`, so it is the final authority for the nested review payload stored inside `HYPOTHESIS.json`.
- `packages/agent_contracts/review.py` is the final authority for the standalone review artifacts written under `hypotheses/<id>/REVIEW/`.
- `packages/agent_contracts/literature.py` is the final authority for search bridge requests, provider receipts, paper candidates, paper verification records, and evidence bundles.
- `packages/agent_contracts/state.py` defines per-item state contracts. `islands/ISLANDS.json` adds a small run-level wrapper around the `items` list.
- `state/ISLANDS.json` is not a canonical artifact path. Do not read it as a fallback and do not write it during resume or repair.
- `packages/agent_contracts/ranking.py` is the canonical shape for each persisted tournament match artifact under `tournaments/`.
- If a skill writes both JSON and Markdown, the JSON contract is authoritative and the Markdown file must remain a faithful rendering of the same content.
