# co-scientist-start

Goal:

- Start one Co-Scientist run from Claude Code using a natural-language goal or an imported brief.

Expected input:

- either a natural-language research goal
- or a brief path such as `notes/drug_resistance_brief.md`
- or no explicit arguments, which should trigger a short guided intake

Guided intake:

- If the user only says `/co-scientist-start`, ask at most four short questions:
  1. What is the research goal?
  2. Should the run favor exploration or grounded progress?
  3. Should the run use a completion-driven search or a capped low-cost iteration budget?
  4. Is there an existing brief, paper note, or other file to import?
- Do not ask for low-level mechanics settings such as `num_debaters`, `elo_k_factor`, or `ucb_exploration_constant`.
- If the user explicitly asks for stricter or lighter review, capture that as a high-level `review` override for critique depth without replacing the iteration-strategy question or disabling any review stage.
- After collecting the answers, render a confirmation summary before you create any files.

Execution steps:

1. If the user supplied a natural-language goal, convert it into `--goal "<goal>"`.
2. If the user supplied a brief file, convert it into `--brief <path>`.
3. When the user also specified high-level controls such as exploration, iteration strategy, or review rigor, pass them through as:

   ```bash
   --exploration <value> --generation-bias <value> --review <value> --budget <value> --evolution <value> --stop-policy <value> --iteration-policy <value> --iteration-band <value> --human-checkpoint <value>
   ```

   Convert Claude-style `key: value` controls into real CLI flags before execution. For example:

   - `exploration: aggressive` -> `--exploration aggressive`
   - `review: strict` -> `--review strict`
   - `iteration policy: capped` -> `--iteration-policy capped`
   - `iteration band: 6 10` -> `--iteration-band 6_10`
   - `human checkpoint: before overview` -> `--human-checkpoint before_overview`

4. Before creating the run, render a summary with:

   ```bash
   python -m tools.host.claude_project_cli start --goal "<goal>" --skill co-scientist-pipeline --summary-only
   ```

   or the equivalent brief-based variant.

5. Show the returned summary to the user and wait for confirmation.
   - When you present the summary, also tell the user that the run-local dashboard receipt will be written to:
     - `runs/<run_id>/dashboard/LINKS.md`
     - `runs/<run_id>/dashboard/LINKS.json`
   - Tell the user that `/co-scientist-dashboard <run-dir>` is the ready-link follow-up when the background bootstrap has not finished yet.
6. After confirmation, run:

   ```bash
   python -m tools.host.claude_project_cli start --goal "<goal>" --skill co-scientist-pipeline
   ```

   or the equivalent brief-based variant.

7. Read the emitted handoff artifact:
   - `runs/<run_id>/state/HOST_AGENT_HANDOFF.json`
8. Read the CLI JSON result and the run-local dashboard receipt artifacts:
   - `runs/<run_id>/dashboard/LINKS.md`
   - `runs/<run_id>/dashboard/LINKS.json`
9. If the CLI JSON contains `dashboardLinks`:
   - If `dashboard.status` is `running`, return `dashboardLinks.dashboard` as the primary dashboard URL and include the deep links.
   - If `dashboard.status` is `starting`, immediately run:

   ```bash
   python -m tools.host.claude_project_cli dashboard <run-dir>
   ```

   - Read the refreshed CLI JSON result plus `runs/<run_id>/dashboard/LINKS.md`.
   - If `runtime.status` is now `running`, return the refreshed `links.dashboard` URL as the primary dashboard URL and include the deep links.
   - If `runtime.status` is still `starting`, tell the user that the dashboard is still booting, point them to `runs/<run_id>/dashboard/LINKS.md`, and include the retry command:

   ```text
   /co-scientist-dashboard <run-dir>
   ```

10. Open the canonical workflow and shared contracts:
   - `skills/co-scientist-pipeline/SKILL.md`
   - `skills/shared-references/artifact-contract.md`
   - `skills/shared-references/state-contract.md`
   - `skills/shared-references/integration-contract.md`
   - `skills/shared-references/execution-modes.md`
11. Continue execution from the canonical repository-local skills tree instead of inventing a parallel flow. If the first refreshed routing plan returns `run_configuration`, execute `research-config` before any generation work.
12. After each major phase write, run:

   ```bash
   python -m tools.validation.contract_validation runs/<run_id> --skill co-scientist-pipeline
   ```

Rules:

- Use `co-scientist-start` when the user wants the system to create the run directory, `input.md`, and the canonical start artifacts.
- If the user first asks what can be configured, route them to `co-scientist-params` or summarize `../../shared-references/start-parameters.md`.
- Use `co-scientist-run` only when the user already has a run directory or a compatibility `config.yaml`.
- Prefer `--interaction-mode guided` when the run came from a question-driven intake.
- Prefer `--interaction-mode brief_import` when the run is anchored by an imported brief without a separate free-form goal.
- Fresh runs normally pass through the explicit `Configuration` stage first so `research-config` can materialize `research_plan/RESEARCH_PLAN.json`.
- Once the user confirms the start summary, do not ask again after each evolution round when the effective policy is `iteration_policy = completion_driven` and `human_checkpoint = auto`.
- Under `completion_driven + auto`, keep running until the routing plan reaches overview or `inspect_state`, or a validator/safety stop requires intervention. Final `complete` comes from the completion verifier after overview work.
- If you must stop before convergence or a terminal route, tell the user the run is paused, current convergence has not been reached, persisted state is resumable, and the next recommended action is continue evolution through resume or an explicit continue request.
- Never pass Claude-style `key: value` text straight into `claude_project_cli`; convert it to explicit flags first.
- Read execution semantics from repository-local `SKILL.md` files and dynamic context from canonical artifacts.
- Treat `skills/` as canonical and `.claude/skills/` as the Claude Code entry surface.
- Treat `runs/<run_id>/dashboard/LINKS.md` as the human-readable dashboard receipt and `runs/<run_id>/dashboard/LINKS.json` as the machine-readable receipt.
