# State Contract

Core constraints:

1. `packages/agent_contracts/*` is the canonical host-neutral schema layer for shared artifacts and deterministic helpers.
2. Artifact JSON must round-trip into the shared contracts or well-defined field subsets of those contracts.
3. Run-local artifacts are the persistence layer for bootstrap, resume, inspection, and dashboard reads.
4. `PIPELINE_STATE.json` is a run-level summary artifact and does not replace the full canonical state.
5. Validation and resume checks must be possible from artifact JSON alone through `python -m tools.validation.contract_validation`.
6. Evolution control state must be serializable through `state/EVOLUTION_STATE.json`.
7. Completion decisions must be serializable through `state/COMPLETION_DECISION.json`.
8. Advisory completion checks must be possible from artifact JSON alone through `python -m tools.validation.verify_pipeline_completion`.
9. High-level routing intent must be serializable through `RUN_POLICY.yaml` and `state/POLICY_DECISION.json`.
10. Natural-language run starts must be auditable through `state/START_REQUEST.json`.
11. Deterministic numeric execution settings must be serializable through `state/RESOLVED_RUN_CONFIG.json`.
12. Per-phase routing plans and routing audit history must be serializable through `state/STRATEGY_PLAN.json` and `state/STRATEGY_DECISIONS.jsonl`.
13. Completed evolution rounds must be serializable through `state/EVOLUTION_ROUNDS.jsonl` and must preserve the child hypothesis ID, concrete evolution strategy, parent IDs, top-k entry result, and convergence-count transition.
14. Host agents should use `skills/shared-references/schema-index.md` to map each artifact path to its exact Python contract before writing JSON.
15. When a run enters an active substage such as `Configuration`, `Generation`, `Evolution`, `Reflection`, `Insights from Reviews`, `Proximity`, `Ranking`, or `Research Overview`, update both `state/PIPELINE_STATE.json` and `state/CURRENT_STAGE.json` immediately so `currentPhase`, `currentSkill`, `stage`, and `stageTrail` reflect that active substage consistently.
16. `state/PIPELINE_STATE.json status = not_started` is valid for bootstrap and fresh configuration setup only. For active runtime phases (`Generation`, `Evolution`, `Reflection`, `Insights from Reviews`, `Proximity`, `Ranking`, or `Research Overview`), the paired writer must persist `status = running` unless the run is already terminal.
17. Prefer `from tools import sync_pipeline_stage_artifacts` as the canonical paired write surface for active-substage stage synchronization instead of hand-editing only one of those artifacts.
