# co-scientist-doctor

Goal:

- Run the Co-Scientist environment diagnostics and explain any failing or warning checks to the user.

Expected input:

- no arguments for the default project-local doctor

Execution steps:

1. Run:

   ```bash
   python -m tools.host.claude_project_cli doctor
   ```

   or, when machine-readable output is needed:

   ```bash
   python -m tools.host.claude_project_cli doctor --format json
   ```

2. Read the emitted diagnostic output and summarize:
   - Python version health
   - Python dependency health
   - active environment / conda or virtualenv status
   - dashboard tooling (`node`, `pnpm`)
   - dashboard install/build readiness
   - project-local skill installation state
   - how `budget`, `iteration-policy`, `iteration-band`, `stop-policy`, and `human-checkpoint` divide responsibility
   - how dashboard ready URLs are resolved after a background bootstrap
   - what `inspect_state` or `validation blocked` means operationally

3. If the dashboard checks warn, recommend:

   ```bash
   pnpm --dir apps/dashboard install
   pnpm --dir apps/dashboard build
   ```

4. If the dashboard checks pass, remind the user:
   - fresh `start`, `run`, and `resume` commands try a background dashboard bootstrap
   - `python -m tools.host.claude_project_cli dashboard <run-dir>` resolves the ready dashboard URL
   - `runs/<run_id>/dashboard/LINKS.md` is the human-readable dashboard receipt
   - `budget` controls per-round intensity, while `iteration-policy` controls semantic vs capped stopping
   - `human-checkpoint=auto` means completion-driven runs should not pause after every evolution round
   - `inspect_state` means review/ranking/evolution artifacts disagree and need repair before resume or overview

5. If the project-local skills are not installed, recommend:

   ```powershell
   powershell -File tools/install/install_co_scientist.ps1
   ```

Rules:

- Prefer `conda run -n <env> python ...` over `conda activate` when the user is running commands through Claude Code shells.
- Treat doctor warnings as actionable guidance, not as fatal runtime errors unless the check status is `fail`.
