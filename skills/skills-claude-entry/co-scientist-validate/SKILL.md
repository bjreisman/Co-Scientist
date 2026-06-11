# co-scientist-validate

Goal:

- Validate one Co-Scientist run directory from Claude Code.

Expected input:

- one run directory such as `runs/test1`

Execution steps:

1. Resolve the run directory.
2. Decide whether the user wants a fresh-run validation or a resume validation.
3. Run one of:

   ```bash
   python -m tools.validation.contract_validation <run-dir> --skill co-scientist-pipeline
   ```

   or

   ```bash
   python -m tools.validation.contract_validation <run-dir> --resume --skill co-scientist-pipeline
   ```

4. Read and summarize the validation result without rewriting the run artifacts unless the user asked for a fix.

Rules:

- This entry skill is a thin Claude Code surface over `tools.validation.contract_validation`.
- Keep the validator as the source of truth for run readiness.
