# Integration Contract

This repository exposes one execution surface:

1. Host-agent mode:
   - recommended natural-language entry: the host entry skill (`/co-scientist-start` in Claude Code or `$co-scientist-start` in Codex)
   - recommended CLI start: `python -m tools.host.project_cli start --goal "<goal>"`
   - entrypoint: `python -m tools.host.project_cli run <run-dir> --skill co-scientist-pipeline`
   - owner: `skills/`, `packages/agent_contracts/`, `tools/validation/contract_validation.py`, `tools/validation/verify_pipeline_completion.py`

Host-agent mode must assume the following:

- The run root is the run directory itself.
- `config.yaml` is optional and, when present, only serves as a compatibility bootstrap shell.
- Skill execution semantics live in `SKILL.md`; dynamic context must be loaded from canonical artifacts and host entry-skill inputs.
- Stable artifacts must be written into the run directory, not into transient in-memory state.
- Natural-language starts should be materialized into `input.md` plus `state/START_REQUEST.json` before the canonical pipeline begins.
- The effective high-level routing policy must be materialized into `RUN_POLICY.yaml` and `state/POLICY_DECISION.json`.
- Effective numeric execution settings must be materialized into `state/RESOLVED_RUN_CONFIG.json` before downstream skills consume run-level mechanics.
- Before a generation, review, or evolution bundle executes, the active routing plan should be materialized into `state/STRATEGY_PLAN.json`.
- Validation must happen after each major write through the mirrored contracts and the CLI/tool entrypoint in `tools/validation/contract_validation.py`.
- Completion advice must be generated through `tools/validation/verify_pipeline_completion.py` before the host agent declares the pipeline complete.
- Resume decisions must be driven by `state/PIPELINE_STATE.json` and `state/CURRENT_STAGE.json`.
- The host agent must not require repository-local orchestration code to execute the top-level skill flow.
- Migrated skills should follow `skills/shared-references/skill-structure-contract.md`.
- Shared implementation ownership should follow `skills/shared-references/code-structure-contract.md`.
- Deterministic mechanics invocation should follow `skills/shared-references/mechanics-integration-contract.md`.

Recommended validator commands:

- Fresh run: `python -m tools.validation.contract_validation <run_dir> --skill <top-level-skill>`
- Resume check: `python -m tools.validation.contract_validation <run_dir> --resume --skill <top-level-skill>`
- Completion advisory: `python -m tools.validation.verify_pipeline_completion <run_dir> --skill <top-level-skill>`

Recommended mechanics workflow:

- Use `tools` as the stable host-agent invocation surface for deterministic mechanics.
- Use `packages/agent_mechanics/*` as the internal implementation truth, not as an invitation to restate those mechanics in prompt prose.
- Omit `--phase` when refreshing strategy routing from persisted stage artifacts, and use explicit phase overrides only when intentionally forcing a new stage transition.

Top-level skills for direct host-agent consumption:

- `co-scientist-pipeline`
- `hypothesis-generation-pipeline`
- `hypothesis-review-pipeline`
- `hypothesis-evolution-loop`
- `research-overview-pipeline`

