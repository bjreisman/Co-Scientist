# co-scientist-params

Goal:

- Show the user the available high-level start parameters for Co-Scientist.

When to use:

- The user asks what knobs or parameters are available.
- The user asks how `/co-scientist-start` can be configured.
- The user wants the expert-facing parameter table instead of the short guided intake.

Execution steps:

1. Run:

   ```bash
   python -m tools.host.claude_project_cli params
   ```

2. If the user explicitly wants machine-readable output, run:

   ```bash
   python -m tools.host.claude_project_cli params --format json
   ```

3. Present the parameter surface in this order:
   - core axes
   - advanced axes
   - utility flags only when relevant
4. Use `../../shared-references/start-parameters.md` as the canonical contract for names, defaults, and meanings.

Rules:

- Lead with the core axes and defaults rather than dumping every possible flag immediately.
- Do not expose low-level mechanics settings such as `num_debaters`, `elo_k_factor`, or `ucb_exploration_constant` as user-facing start parameters.
- If the user only wants to begin a run, route back to `/co-scientist-start` after answering the parameter question.
