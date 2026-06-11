# Mechanics Integration Contract

This contract defines how host agents must consume load-bearing deterministic mechanics in `Co-Scientist`.

Core rule:

1. Shared Python implementation remains canonical under `packages/`.
2. External host agents must invoke deterministic mechanics through the stable `tools` surface or the explicitly documented CLI entrypoint.
3. If a skill says one helper is canonical for a given mechanics step, do not restate the algorithm in prompt prose and reimplement it manually.
4. When a required helper is available and the required artifacts exist, using the helper is mandatory rather than optional.

## Invocation Surfaces

- Repository-internal shared implementation:
  - import from `packages.*`
- Host-agent deterministic helper surface:
  - import from `tools`
- Host-agent deterministic router CLI:
  - `python -m tools.policy.plan_strategy <run_dir> [--phase <...>]`

## Load-Bearing Mechanics

These mechanics define pipeline semantics and must not be forked ad hoc in prompts.

### Routing and Stage Recovery

- Canonical surface:
  - `python -m tools.policy.plan_strategy <run_dir> [--phase <...>]`
  - or `plan_strategy_for_run(...)` from `tools/policy/plan_strategy.py`
- Persisted-state refresh:
  - omit `--phase`
- Explicit stage override:
  - pass `--phase <...>` only when intentionally forcing a new stage transition

### Island Selection

- Canonical surface:
  - `from tools import select_island_hypotheses`
- Implementation:
  - `packages/agent_mechanics/island_select.py`
- Required artifacts:
  - `islands/ISLANDS.json`
  - viable `hypotheses/<id>/HYPOTHESIS.json`
  - `state/RESOLVED_RUN_CONFIG.json`

### Island Initialization

- Canonical surface:
  - `from tools import ensure_run_islands_for_hypotheses`
- Implementation:
  - `packages/run_artifacts/island_state.py`
- Rule:
  - generation seeding and multi-island child creation must use the run-level initialization helper rather than hand-writing island records
  - newly created islands must be unvisited: verify `decayed_reward = 0.0`, `decayed_visits = 0.0`, and `visit_count = 0`
  - only a completed single-island round closeout may increment visits or decayed reward metrics
  - canonical island items must not contain derived dashboard or router fields such as `hypothesis_ids`, `ucb_score`, or `strategy_label`

### Island Reward and Decay Update

- Canonical surface:
  - `from tools import update_run_single_island_reward`
- Implementation:
  - `packages/run_artifacts/island_state.py`
- Lower-level internal/testing surfaces:
  - `from tools import update_single_island_reward`
  - `from tools import compute_single_island_reward`
  - `from tools import apply_decayed_island_update`
- Lower-level implementation:
  - `packages/agent_mechanics/island_reward_update.py`
- Rule:
  - single-island child updates must use the run-level helper rather than direct manual edits to island reward / visit statistics
  - host-agent evolution loops must call `tools.update_run_single_island_reward(run_dir, selected_island_id, candidate_hypothesis_id, decay_factor)` after the child has final review, viability, and Elo state
  - this helper call is a load-bearing single-island round closeout write, not an optional dashboard refresh
  - after the helper returns, the caller must reload canonical `islands/ISLANDS.json` and confirm the selected island has nonzero `visit_count` and nonzero `decayed_visits`
  - the selected island `visit_count` must be at least the number of completed single-island round receipts that selected that island
  - if selected-island metrics do not validate, stop before the next routing refresh, run contract validation, and report a resumable blocked state rather than continuing with stale UCB selection state
  - do not write `state/ISLANDS.json`; `islands/ISLANDS.json` is the only canonical persisted island artifact
  - the lower-level surfaces are not the host-agent persistence path because they do not load run artifacts or write the canonical island artifact

### Proximity Embedding Bridge

- Canonical surface:
  - `from tools import update_hypothesis_proximity`
- Implementation:
  - `packages/agent_mechanics/hypothesis_embedding.py`
  - `packages/agent_mechanics/hypothesis_embedding_text.py`
- Required input:
  - run directory
  - target `hypothesis_id`
  - run-frozen embedding provider settings from `state/RESOLVED_RUN_CONFIG.json`; the bridge uses the configured environment variable names only to read provider endpoint and API key values at call time
- Rule:
  - host agents must call `tools.update_hypothesis_proximity(run_dir, hypothesis_id)` for each newly viable hypothesis instead of hand-generating embeddings
  - the bridge records `state/proximity_receipts/<hypothesis_id>.json` and `state/PROXIMITY_STATUS.json`
  - the bridge records embedding metadata in `state/PROXIMITY_GRAPH.json` and must not overwrite an existing embedding when input/config metadata has drifted
  - do not fabricate placeholder embeddings, manual feature vectors, or prose-derived pseudo-embeddings in order to force a graph update

### Proximity Graph Update

- Lower-level canonical surface:
  - `from tools import update_proximity_graph`
- Implementation:
  - `packages/agent_mechanics/proximity_update.py`
- Required input:
  - an embedding vector returned by the canonical embedding bridge or another explicit provider integration
- Rule:
  - do not call this lower-level helper with prompt-fabricated vectors

### Ranking Frontier and Opponent Selection

- Canonical surfaces:
  - `from tools import get_top_k_hypotheses`
  - `from tools import select_placement_opponents`
  - `from tools import select_fallback_placement_opponents`
  - `from tools import should_run_ranked_tournament`
  - `from tools import select_ranked_opponents`
- Implementation:
  - `packages/agent_mechanics/top_k_select.py`
- Rule:
  - top-k frontier selection, placement-opponent choice, and ranked-opponent choice are deterministic mechanics, not freeform narrative judgment

### Elo Updates

- Canonical surface:
  - `from tools import apply_and_persist_elo_updates`
- Implementation:
  - `packages/run_artifacts/ranking_writeback.py`
  - `packages/agent_mechanics/elo_update.py`
- Rule:
  - host-agent ranking closeout must use the receipt-writing helper; lower-level Elo updates are not sufficient without canonical hypothesis persistence and a ranking update receipt

### Convergence Updates

- Canonical surface:
  - `from tools import evaluate_convergence`
- Implementation:
  - `packages/agent_mechanics/convergence_check.py`

## Failure Policies

Use the following policy classes when writing or maintaining skills.

### Policy A: Hard Requirement

The helper must be used when:

- the helper is available through `tools`
- the canonical input artifacts required by that helper exist and validate

Examples:

- island selection
- island reward update and canonical persistence after a single-island evolution round
- top-k frontier and ranked-entry selection when the current frontier artifacts exist
- convergence update

### Policy B: Artifact-Missing Fallback

The skill may fall back only when the canonical helper cannot run because a required upstream artifact is genuinely missing or invalid.

Requirements:

1. Record an explicit fallback rationale in the trace.
2. Limit the fallback to the missing-artifact scenario only.
3. Return to canonical helper execution as soon as the artifact exists again.

Example:

- placement-opponent selection may fall back only when `state/PROXIMITY_GRAPH.json` is absent, invalid, or candidate-incomplete and a proximity receipt/status records a skipped, disabled, failed, or provider-unavailable outcome for the candidate
- receipt-gated placement fallback must call `tools.select_fallback_placement_opponents(...)`; ranked tournament play must not be used as an implicit substitute for the placement stage
- proximity graph updates may be skipped only by the canonical embedding bridge, with a persisted proximity receipt/status explaining the provider outcome

### Policy C: No Manual Reimplementation

The following are forbidden when the canonical helper and artifacts are available:

1. manually rewriting top-k selection logic in prompt prose
2. manually recomputing island reward and decay updates in prompt prose or hand-writing `islands/ISLANDS.json`
3. manually restating convergence counter rules and editing artifacts without helper output
4. manually inventing placeholder embeddings or similarity matrices in order to mimic `tools.update_hypothesis_proximity(...)` or `tools.update_proximity_graph(...)`

## Skill Authoring Rule

If a skill owns or orchestrates a load-bearing mechanics step, its `SKILL.md` must explicitly state:

1. which helper surface is canonical
2. where the implementation lives under `packages/agent_mechanics/` or `tools/`
3. what artifacts are required before the helper is called
4. whether fallback is allowed, and under what exact condition

## Host-Agent Rule

Before performing deterministic mechanics work, a host agent should:

1. open this contract
2. open `skills/shared-references/schema-index.md`
3. open the exact Python contract for any artifact it will write
4. invoke the documented `tools.*` helper or CLI surface
