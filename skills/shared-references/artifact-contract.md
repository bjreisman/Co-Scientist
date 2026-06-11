# Artifact Contract

Core constraints:

1. The root directory of a run is the run directory itself; `config.yaml` is optional compatibility state.
2. Machine-consumable outputs must be written as JSON first.
3. Human-readable summaries must be written as companion Markdown files when needed.
4. The minimum stable artifact directories are:
   - `state/`
   - `research_plan/`
   - `hypotheses/`
   - `tournaments/`
   - `islands/`
   - `meta/`
   - `dashboard/`
   - `traces/`
5. The minimum stable artifact files are:
   - `state/START_REQUEST.json`
   - `RUN_POLICY.yaml`
   - `state/POLICY_DECISION.json`
   - `state/RESOLVED_RUN_CONFIG.json`
   - `state/STRATEGY_PLAN.json`
   - `state/STRATEGY_DECISIONS.jsonl`
   - `state/EVOLUTION_ROUNDS.jsonl`
   - `state/CURRENT_STAGE.json`
   - `state/PIPELINE_STATE.json`
   - `state/EVOLUTION_STATE.json`
   - `state/PROXIMITY_GRAPH.json` when similarity-assisted ranking is available
   - `state/COMPLETION_DECISION.json`
   - `state/HOST_AGENT_HANDOFF.json`
   - `research_plan/RESEARCH_PLAN.json`
   - `research_plan/RESEARCH_PLAN.md`
   - `hypotheses/<id>/HYPOTHESIS.json`
   - `hypotheses/<id>/HYPOTHESIS.md`
   - `hypotheses/<id>/ORIGIN.json`
   - `hypotheses/<id>/REVIEW/*.json`
   - `dashboard/SNAPSHOT.json`
   - `dashboard/LINKS.json`
   - `MANIFEST.md`
6. `hypotheses/<id>/HYPOTHESIS.json` must serialize the canonical shared hypothesis contract, including:
   - `id`
   - `timestamp`
   - `elo_rating`
   - `origin`
   - `review`
   - `island_id`
   - `parent_ids`
   - `placement_match_ids`
   - `ranked_match_ids`
7. `ORIGIN.json` may mirror the hypothesis origin payload, but it does not replace the canonical `HYPOTHESIS.json` contract.
8. The canonical hypothesis artifact must keep the nested content fields populated. The minimum acceptable shape is:
   - `origin.strategy`
   - `origin.content.statement`
   - `origin.content.mechanism`
   - `origin.content.experimental_design`
   - `origin.content.summary`
   - `origin.content.category`
9. Viable hypotheses must not keep `island_id` empty once the round has been finalized.
10. Evolved hypotheses must also persist:
   - non-empty `parent_ids`
   - a completed review bundle
   - round state updates in `state/EVOLUTION_STATE.json`
   - a completed round receipt in `state/EVOLUTION_ROUNDS.jsonl`
11. `hypotheses/<id>/HYPOTHESIS.json` match refs are lifetime participation refs and must not contain duplicates. They may include later matches where the hypothesis appears as an opponent.
12. `state/EVOLUTION_ROUNDS.jsonl` match refs are per-round closeout refs and must not contain duplicates. They must only include tournament matches where that round's child hypothesis is `hypothesis_1_id` for the recorded placement or ranked strategy.
