# Codex task model routing

Use this contract when a Co-Scientist scientific task is executed in Codex. Python helpers do not make model calls or change the running main chat's model.

## Configuration

- Project policy: `.co-scientist/model-policy.yaml`. Install or regenerate custom roles with `python -m tools.model_routing install --project <project-root>`. This validates settings, writes `.codex/agents/co_scientist_<role>.toml`, and creates `.codex/config.toml` only when absent. Existing project config is preserved.
- Bootstrap captures the policy in `state/MODEL_POLICY.json`. Resume retains that snapshot. Policy edits affect new runs; do not silently replace an existing run snapshot.
- Seven groups cover configuration, evidence extraction, generation, review, ranking, evolution and meta-review. `skill_overrides` selects a different role for one exact scientific skill. Models must be available in the host; configuration does not grant access.
- `fallback: stop` prevents silently running configured work with a different, potentially expensive parent model. `fallback: local` permits a disclosed local fallback; it cannot apply the role's model or reasoning to the main thread.
- Legacy runs without a configured policy retain host inheritance. No historical model dispatches are inferred from hypothetical routes.

## Dispatch

1. Before each eligible scientific subtask, run `python -m tools.model_routing begin <run-dir> --skill <exact-skill> --hypothesis-id <id>`. Omit the hypothesis flag for run-level tasks. Read the returned receipt, route and settings. Orchestration pipelines should dispatch their scientific leaves; the complete review bundle may be delegated once through `hypothesis-review-pipeline` instead of spawning six reviewers.
2. For `codex_subagent`, spawn the returned `agent_type` with its exact `model`, `reasoning_effort`, and `fork_turns: none`. If the custom role is not yet discovered but the host accepts explicit model settings, use `default` with those same settings and include the role instructions in the task. Give only the assigned skill contract, research plan, relevant canonical artifacts and bounded evidence packet. Do not inherit the entire conversation. Honor the lower of the policy concurrency limit and the user's active limit.
3. The child performs only the assigned scientific task and returns contract-shaped advisory findings. It must not recursively delegate, own the control plane, select opponents, call deterministic mechanics, or write canonical artifacts. Literature/embedding bridges remain parent-owned. The parent may retrieve additional evidence and redispatch the same task with a new receipt.
4. Record the result with `python -m tools.model_routing record <run-dir> --dispatch-id <id> --session-id <actual-child-session-id> --findings <advisory-path>`. For failure or unavailable agents, pass `--status failed` or `--status unavailable`. If the host exposes only an opaque agent handle, close as unavailable for verification instead of inventing a Codex session UUID.
5. `requested` is the policy choice. `observed` comes only from matching Codex rollout model/effort metadata after the dispatch began. Missing metadata is unverified; model-only metadata verifies only the model. A mismatch is a configuration failure: report it and stop that dispatch before canonical writeback. Do not label requested settings as actual use. Unverified results may be validated and used, but disclose the missing model audit.
6. Parent validates advisory results against the exact native contracts before canonical writes, syncs stage/review artifacts, and runs the required validation. A dispatch receipt is not scientific evidence or a completed stage.

For an allowed local fallback, begin with `--local` and record the actual parent session ID. The receipt explicitly says `local_main_thread`; neither configured role settings nor an order-swapped local judgment implies independence. If `fallback: stop`, preserve a resumable checkpoint when delegation cannot execute. Changing model policy is not authorization to resume a budget-paused campaign.

`evidence-extract` is only a bounded helper that extracts supported claims and caveats from supplied documents. It does not replace `literature-search` or create evidence bundles. Do not route validation, search bridges, embeddings, Elo, island selection, proximity, dashboard projection, routing or artifact synchronization to LLM agents.

## Inspect

`python -m tools.model_routing resolve <run-dir> --skill hypothesis-full-review` shows the request without creating a dispatch. `show <run-dir>` displays the policy and audit receipts. The dashboard displays requested task settings and observed dispatch metadata beside the credit meter. Codex may need a fresh chat/project configuration reload to discover newly installed custom agents.
