# Policy Contract

Core constraints:

1. `RUN_POLICY.yaml` is the human-readable, run-local source of truth for high-level routing intent.
2. `state/POLICY_DECISION.json` records the effective high-level policy that the host agent should execute against.
3. High-level policy must stay bounded to enumerated routing axes such as exploration mode, generation bias, review rigor, evolution style, budget profile, stop policy, iteration policy, and optional iteration band.
4. Allowed generation strategies must be chosen from:
   - `literature_exploration_generation`
   - `scientific_debates_generation`
   - `assumptions_identification_generation`
5. Allowed review modes must be chosen from:
   - `full_review`
   - `deep_verification_review`
   - `observation_review`
   - `simulation_review`
6. Policy artifacts must remain host-neutral and must not depend on repository-local orchestration state.
7. `review_rigor` controls review depth, critique density, and evidence detail. It does not disable review stages:
   - `strict`: run all review kinds with maximal scrutiny and detailed rationale.
   - `standard`: run all review kinds with normal depth and balanced critique density.
   - `light`: run all review kinds with concise but still explicit reasoning.
8. `allowed_review_modes` remains a compatibility mirror of the canonical review surface and must keep all four review kinds enabled. Host agents must not use it to prune the review stack.
9. `budget_profile` controls per-round intensity; it must not be treated as the only source of truth for total iteration depth.
10. `iteration_policy` selects whether the run should stop through semantic completion signals (`completion_driven`) or through a user-chosen iteration cap (`capped`).
11. `iteration_band` may be set only when `iteration_policy` is `capped`.
12. `human_checkpoint` controls where explicit user confirmation is required; it is independent from `iteration_policy`.
13. `human_checkpoint: auto` means the host agent should continue autonomously between individual evolution rounds and only stop when:
   - the routing plan changes away from automatic continuation
   - validation blocks execution
   - a configured safety or capped-run stop reason is reached
14. If the host-agent turn returns control to the user before a terminal route, the response must say the run is paused, current convergence has not been reached, persisted state is resumable, and the next recommended action is continue evolution through resume or an explicit continue request.
15. `human_checkpoint: before_overview` means autonomous execution may continue through generation, review, ranking, and evolution work, but must pause before `research-overview-pipeline`.
16. `human_checkpoint: before_completion` means autonomous execution may continue through overview generation, but must pause before the final completion confirmation/writeback.
17. `human_checkpoint: every_major_stage` means the host agent may pause between major stage transitions, but still must not reinterpret `completion_driven` as "ask after every evolution child by default."
