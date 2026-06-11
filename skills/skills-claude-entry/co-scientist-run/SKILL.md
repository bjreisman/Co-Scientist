# co-scientist-run

Goal:

- Start one Co-Scientist run from Claude Code and then continue with the canonical pipeline.

Expected input:

- one run directory such as `runs/test1`
- or one compatibility config path such as `runs/test1/config.yaml`

Execution steps:

1. Resolve the run directory or compatibility config path relative to the repository root when the user gives a relative path.
2. Run:

   ```bash
   python -m tools.host.claude_project_cli run <run-target> --skill co-scientist-pipeline
   ```

3. Read the emitted handoff artifact:
   - `runs/<run_id>/state/HOST_AGENT_HANDOFF.json`
4. Read the CLI JSON result and the run-local dashboard receipt artifacts:
   - `runs/<run_id>/dashboard/LINKS.md`
   - `runs/<run_id>/dashboard/LINKS.json`
5. If the CLI JSON contains `dashboardLinks`:
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

6. Open the canonical workflow and shared contracts:
   - `skills/co-scientist-pipeline/SKILL.md`
   - `skills/shared-references/artifact-contract.md`
   - `skills/shared-references/state-contract.md`
   - `skills/shared-references/integration-contract.md`
   - `skills/shared-references/execution-modes.md`
   - `skills/shared-references/schema-index.md`
7. Continue execution from the canonical repository-local skills tree instead of inventing a parallel flow. If the refreshed routing plan returns `run_configuration`, execute `research-config` and validate `research_plan/RESEARCH_PLAN.json` before any generation work.
8. After each major phase write, run:

   ```bash
   python -m tools.validation.contract_validation runs/<run_id> --skill co-scientist-pipeline
   ```

Rules:

- Read execution semantics from repository-local `SKILL.md` files and dynamic context from canonical artifacts.
- Use `runs/<run_id>/state/PIPELINE_STATE.json` and `CURRENT_STAGE.json` as the authoritative resume state.
- The first active stage may be `Configuration` rather than `Generation`; do not skip it when the routing plan requires `run_configuration`.
- If the effective run policy is `iteration_policy = completion_driven` and `human_checkpoint = auto`, do not ask whether to continue after each evolution round. Keep running until a real terminal route, checkpoint boundary, or blocking validator/safety state is reached.
- If you must stop before convergence or a terminal route, tell the user the run is paused, current convergence has not been reached, persisted state is resumable, and the next recommended action is continue evolution through resume or an explicit continue request.
- Treat `skills/` as canonical and `.claude/skills/` as the Claude Code entry surface.
- Treat `runs/<run_id>/dashboard/LINKS.md` as the human-readable dashboard receipt and `runs/<run_id>/dashboard/LINKS.json` as the machine-readable receipt.
