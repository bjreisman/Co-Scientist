# Execution Surface

## host-agent

- Recommended user-facing entry: the host entry skill (`/co-scientist-start` in Claude Code or `$co-scientist-start` in Codex) or `python -m tools.host.project_cli start --goal "<goal>"`
- Entrypoint: `python -m tools.host.project_cli run <run-dir> --skill co-scientist-pipeline`
- Runtime owner: an external host agent consumes top-level `SKILL.md` files after bootstrap
- LLM calls: owned by the external host agent, not by repository-local Python runtime
- Main purpose: portable host-agent execution surface

Host-agent mode expects:

- a run root directory that contains `input.md` and the canonical artifact tree
- an optional compatibility `config.yaml` only when older scripts still rely on it
- a canonical research brief in `input.md`
- migrated skills whose execution semantics are expressed directly in `SKILL.md`
- canonical runtime contracts under `packages/agent_contracts/`
- validator-first checks through `python -m tools.validation.contract_validation`
- advisory completion checks through `python -m tools.validation.verify_pipeline_completion`
- resume metadata in `state/PIPELINE_STATE.json` and `state/CURRENT_STAGE.json`
- evolution control state in `state/EVOLUTION_STATE.json`
- completion decisions in `state/COMPLETION_DECISION.json`
- the shared skill structure rules in `skills/shared-references/skill-structure-contract.md`
