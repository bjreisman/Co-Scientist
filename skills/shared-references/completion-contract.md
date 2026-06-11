# Completion Contract

This contract defines when the pipeline may continue evolving, when it may move into overview generation, and how final completion decisions must be recorded.

## Phase completion

1. `research-config` is complete when:
   - `research_plan/RESEARCH_PLAN.json` exists
   - the artifact validates against `packages.agent_contracts.ResearchPlanContract`
2. `hypothesis-generation-pipeline` is complete when:
   - at least one hypothesis artifact exists under `hypotheses/<id>/HYPOTHESIS.json`
   - every generated hypothesis can be validated against `packages.agent_contracts.HypothesisContract`
3. `hypothesis-review-pipeline` is complete for one hypothesis when:
   - the embedded review payload validates
   - all canonical review stage artifacts exist:
     - `INITIAL_REVIEW.json`
     - `FULL_REVIEW.json`
     - `DEEP_VERIFICATION.json`
     - `OBSERVATION_REVIEW.json`
     - `SIMULATION_REVIEW.json`
     - `REVIEW_SUMMARY.json`
4. `hypothesis-evolution-loop` is complete when:
   - `state/EVOLUTION_STATE.json` exists
   - the artifact records `status: completed`
   - the evolved hypothesis chain is replayable from `state/STRATEGY_DECISIONS.jsonl` plus `state/EVOLUTION_ROUNDS.jsonl`
   - the artifact contains a valid stop reason or a valid operator override decision
5. `research-overview-pipeline` is complete when:
   - `meta/RESEARCH_OVERVIEW.json` exists
   - the artifact validates against `packages.agent_contracts.ResearchOverviewContract`

## Evolution stop reasons

The stable stop reason vocabulary for `state/EVOLUTION_STATE.json` is:

- `convergence_reached`
- `max_iterations_reached`
- `safety_iteration_limit_reached`
- `candidate_quality_plateau`
- `no_viable_candidates`
- `operator_stop`
- `validation_blocked`
- `budget_exhausted`
- `manual_override_complete`

The empty string is reserved for `not_started` or `running` evolution state.

Interpretation rules:

- `max_iterations_reached` means a user-visible capped iteration policy was reached.
- `safety_iteration_limit_reached` means an internal safety ceiling was reached for a completion-driven or unexpectedly long run.
- `convergence_reached` remains the canonical semantic stop signal when the active frontier no longer improves under the configured convergence rule.
- Research overview and completion-decision rationale may use "converged", "frontier converged", or "convergence reached" only when `EVOLUTION_STATE.stopReason` is exactly `convergence_reached`.
- For `safety_iteration_limit_reached`, describe the overview as a synthesis after the safety ceiling, not as scientific convergence.
- For an empty stop reason, the run is still active or paused; do not write a completed overview or completion decision unless an explicit override rationale is present and validated.
- If a completion rationale mentions a concrete safety iteration limit, that number must match `RESOLVED_RUN_CONFIG.convergence.safety_max_iterations`.

## Advisory completion verification

Completion advice must be generated through:

`python -m tools.validation.verify_pipeline_completion <run_dir> --skill <top-level-skill>`

The advisory verifier returns:

- `completionReadiness`
- `recommendedAction`
- `reasons`
- `signals`
- `overrideAllowed`

The verifier is advisory by default. It does not block execution by itself.
However, it must report `inspect_state` when the routing audit is inconsistent with the evolved hypothesis chain.
The verifier owns the final `complete` outcome; `state/STRATEGY_PLAN.json` should route to `generate_overview` or `inspect_state`, not emit `complete` directly.
It must also distinguish:

- capped-run completion
- completion-driven semantic completion
- safety-ceiling completion

## Completion decision recording

If the host agent accepts the advisory recommendation without changes, it may write:

`state/COMPLETION_DECISION.json`

If the host agent overrides the advisory recommendation, it must write:

- `state/COMPLETION_DECISION.json`
- at least one non-empty rationale entry

The completion decision artifact is the durable explanation of why the pipeline was completed, continued, or manually overridden.

## Pipeline completion

The top-level pipeline may be marked `completed` only when:

1. `research-overview-pipeline` has produced a valid overview artifact, and
2. a completion decision has been recorded, and
3. the decision is consistent with the current run artifacts or includes an explicit override rationale

The completion verifier should be run:

- after the evolution loop reports `status: completed`
- before the research overview is finalized
- before the top-level pipeline records `status: completed`
