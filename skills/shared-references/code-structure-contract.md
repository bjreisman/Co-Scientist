# Code Structure Contract

This repository uses three structural layers:

1. `skills/`
   - Source of truth for agent behavior.
   - `SKILL.md` defines execution semantics.
   - `shared-references/` defines cross-skill contracts and repository-wide rules.

2. `packages/`
   - Source of truth for shared Python implementation.
   - Holds host-neutral contracts, mechanics, artifact IO, dashboard contracts, and policy/pipeline helpers.
   - Internal imports should target `packages.<domain>.*` directly.

3. `tools/`
   - Execution entrypoints and operational surfaces.
   - Holds CLI commands, bootstrap helpers, validation entrypoints, dashboard serving, and installer/doctor utilities.
   - `tools/` should not contain duplicate shared implementation layers.

## Import Rules

- Prefer direct imports from `packages/` for shared implementation.
- External host agents should prefer the stable `tools` helper or CLI surfaces documented by the relevant `SKILL.md` and shared references.
- Do not add new imports through compatibility wrappers such as:
  - `tools.contracts`
  - `tools.mechanics`
  - `tools.artifacts`
- Shared code should not reintroduce nested implementation namespaces such as `packages.<domain>.python.*`.

## Mechanics Rules

- Deterministic mechanics remain canonically implemented under `packages/agent_mechanics/`.
- Host-agent-facing invocation surfaces for those mechanics should be exposed through `tools`.
- Shared mechanics invocation rules should follow `skills/shared-references/mechanics-integration-contract.md`.

## Schema Rules

- Python models under `packages/` are the canonical runtime contracts.
- Generated `schema/*.json` files are export artifacts, not runtime dependencies.
- The `schema/` output directories may be absent until an exporter command regenerates them.
- The dashboard frontend consumes generated TypeScript under:
  - `apps/dashboard/app/types/generated/`
- It does not consume `schema/*.json` files at runtime.

## Design Goal

The target repository shape is:

```text
skills/    -> behavior and user-facing execution rules
packages/  -> shared implementation truth
tools/     -> executable entrypoints
apps/      -> product surfaces such as the dashboard
```

If this contract conflicts with legacy compatibility paths, the direct `packages/` path wins.
