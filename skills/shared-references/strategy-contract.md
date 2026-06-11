# Strategy Contract

Core constraints:

1. `state/STRATEGY_PLAN.json` is the current executable routing plan for the active phase.
2. `state/STRATEGY_DECISIONS.jsonl` is an append-only audit log of prior routing decisions.
3. `state/EVOLUTION_ROUNDS.jsonl` is an append-only completion receipt log for finished evolution rounds.
4. Strategy plans may select:
   - generation strategies
   - evolution strategy bundles
5. Strategy plans must honor `RUN_POLICY.yaml` and must not choose routes disallowed by the effective policy.
6. Strategy plans may use completion-advisory signals, but they must still materialize an explicit next action artifact.
7. Before each generation batch and before each individual evolution round, the host agent must refresh `state/STRATEGY_PLAN.json`.
8. `next_action = run_configuration` is the canonical routing action when `research_plan/RESEARCH_PLAN.json` is missing or invalid.
9. Generation must not start until configuration has produced a valid canonical research plan artifact.
10. Every evolved hypothesis persisted under `hypotheses/<id>/HYPOTHESIS.json` must have a corresponding append-only routing decision record in `state/STRATEGY_DECISIONS.jsonl`.
11. Every completed evolution round that persists a child hypothesis must have a corresponding append-only completion receipt in `state/EVOLUTION_ROUNDS.jsonl`.
12. `state/STRATEGY_DECISIONS.jsonl` decision indexes must be globally unique and allocated from the existing maximum `decision_index + 1`, not from the number of JSONL lines.
13. Repeated routing refreshes must not append multiple equivalent open `continue_evolution` decisions for the same unconsumed pre-round state. If the equivalent decision is already consumed by an `EVOLUTION_ROUNDS.jsonl` receipt, a later identical-looking route may be appended for a later round.
14. Every `continue_evolution` routing decision that is consumed by an evolution-round receipt must include router-level signals:
   - `hypothesis_count`
   - `viable_hypothesis_count`
   - `convergence_count`
   - `convergence_threshold`
   - `entered_top_k_last_round`
   - `top_hypothesis_ids`
   - `research_plan_status`
   - `selection_strategy`
   - `selected_parent_ids`
   - `selected_island_ids`
   These signals must describe the persisted state immediately before the child for that round is created.
15. `state/STRATEGY_DECISIONS.jsonl` must not contain round-result fields such as child hypothesis IDs, chosen concrete strategies, proximity statuses, tournament match IDs, top-k entry results, or convergence-count transitions. Those fields belong only in `state/EVOLUTION_ROUNDS.jsonl`.
16. In evolution, `selected_evolution_strategies` is only the candidate bundle. The active round must still choose exactly one concrete evolution strategy consistent with:
   - `signals.selection_strategy`
   - the selected parent set
   - the latest review findings
17. The active evolution round receipt must record:
   - the chosen parent IDs
   - the selected island strategy (`single_island` or `multi_island`)
   - the chosen concrete evolution strategy
   - the child hypothesis ID
   - placement and ranked match IDs produced by that child as the candidate/challenger
   - whether the new child entered the top-k frontier
18. `state/EVOLUTION_ROUNDS.jsonl` match IDs are closeout refs for the child created by that round, not lifetime refs. A round receipt must only include:
   - `placement_match_ids` whose tournament artifact has `match_strategy = placement_tournament` and `hypothesis_1_id = child_hypothesis_id`
   - `ranked_match_ids` whose tournament artifact has `match_strategy = ranked_tournament` and `hypothesis_1_id = child_hypothesis_id`
   - no duplicate match IDs
   Later matches where the child appears as `hypothesis_2_id` remain valid lifetime refs in `HYPOTHESIS.json`, but they must not be backfilled into the earlier round receipt.
19. A consumed `continue_evolution` decision must be replay-consistent with its round receipt:
   - `signals.hypothesis_count` equals the number of hypotheses available before the child is created.
   - `signals.viable_hypothesis_count` equals the number of viable hypotheses available before the child is created.
   - `signals.convergence_count` equals the round receipt's `convergence_count_before`.
   - For non-initial evolution rounds, `signals.convergence_count` equals the prior round's `convergence_count_after`.
   - For non-initial evolution rounds, `signals.entered_top_k_last_round` equals the prior round's `entered_top_k`.
   - `signals.top_hypothesis_ids` equals the consumed round receipt's `previous_top_k_ids`.
   - `signals.selected_parent_ids` only references viable hypotheses that existed before the child was created.
   - `signals.selected_island_ids` equals the selected parents' persisted `island_id` values in the same order.
   - `signals.entered_top_k_last_round = true` is invalid when `signals.convergence_count` is positive.
20. If `state/STRATEGY_PLAN.json` returns `next_action = inspect_state`, automatic routing must pause.
21. `inspect_state` is a blocked control-plane action, not a soft hint. The host agent must inspect or repair the persisted artifacts before resuming generation, review, or evolution.
22. `complete` is not a `state/STRATEGY_PLAN.json` action. Final completion must come from `tools.validation.verify_pipeline_completion` and the persisted completion decision artifact.
23. Resume-safe strategy rebuilds must preserve precise persisted execution stages when they are derivable from artifacts, including:
   - `Configuration`
   - `Reflection`
   - `Insights from Reviews`
   - `Proximity`
   - `Ranking`
24. When a run is resumed from one of those execution stages, `state/STRATEGY_PLAN.json` should emit the matching explicit action instead of collapsing immediately to generic `continue_evolution`.
