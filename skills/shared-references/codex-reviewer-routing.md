# Codex Reviewer Routing

Purpose:

- Define the optional Codex reviewer subagent route without making the Co-Scientist pipeline depend on subagents.

Applicability:

- This reviewer route covers review, verification, and audit work. Configured scientific generation, ranking and refinement delegation is separately governed by `codex-model-routing.md`.
- It is not allowed for deterministic mechanics such as schema validation, literature search bridge execution, proximity embedding updates, Elo updates, island selection, dashboard projection, or artifact synchronization.

Routing Rules:

- If Codex subagents are available and the current task explicitly enters a review or verification stage, the host may ask a reviewer subagent to inspect the same canonical artifacts.
- When `state/MODEL_POLICY.json` exists, follow `codex-model-routing.md` to resolve, dispatch and audit the selected reviewer before execution. Its configured fallback governs unavailable agents.
- Without a model policy, or when its fallback explicitly permits local work, the main thread may execute the same review contract locally if subagents are unavailable, disabled, or too expensive. Disclose the route and host settings.
- The pipeline must remain valid when the reviewer route is `local_main_thread`.
- Subagent output is advisory until the parent thread validates it and writes the canonical artifact.
- A reviewer subagent must not fabricate literature evidence, embedding vectors, tournament results, validation summaries, or dashboard receipts.
- A reviewer subagent must not write canonical review artifacts unless the parent explicitly delegates that write and then validates the result.

Trace Rules:

- Record the selected reviewer route in:

  ```text
  runs/<run_id>/state/agent_traces/codex/<skill>/<timestamp>.json
  ```

- The trace should include:
  - `reviewerRoute`: `codex_subagent` or `local_main_thread`
  - `skill`
  - `hypothesisId`
  - `attemptedSubagent`
  - `subagentAvailable`
  - `canonicalArtifacts`
  - `findingsArtifact`
  - `validationCommand`
  - `status`

Completion Rule:

- Reviewer routing is complete only when the canonical review artifact exists and validates. The trace is audit evidence, not a substitute for the canonical artifact.
