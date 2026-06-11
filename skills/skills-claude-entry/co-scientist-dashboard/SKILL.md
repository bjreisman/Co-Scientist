# co-scientist-dashboard

Goal:

- Resolve the ready dashboard runtime for one Co-Scientist run and return the current run links to the user.

Expected input:

- one run directory such as `runs/test1`

Execution steps:

1. Resolve the run directory and confirm that it contains the run-local dashboard/state artifacts.
2. Run:

   ```bash
   python -m tools.host.claude_project_cli dashboard <run-dir>
   ```

3. Read:
   - `runs/<run_id>/dashboard/LINKS.json`
   - `runs/<run_id>/dashboard/LINKS.md`
4. Read the CLI JSON result and use it as the canonical ready-link resolution surface for this run.
5. Return:
   - `links.dashboard` as the primary dashboard URL
   - the deep links under `links.*`
   - `runs/<run_id>/dashboard/LINKS.md` as the human-readable dashboard receipt
6. If `runtime.status` is still `starting`, explain that the dashboard is still booting, point the user to `runs/<run_id>/dashboard/LINKS.md`, and include the retry command:

   ```text
   /co-scientist-dashboard <run-dir>
   ```

Rules:

- Do not perform main pipeline reasoning in this entry skill.
- This skill is the ready-link follow-up when `start`, `run`, or `resume` only returned background bootstrap status.
- This skill only resolves dashboard runtime availability and exposes run-local links; it must not perform main pipeline reasoning.
