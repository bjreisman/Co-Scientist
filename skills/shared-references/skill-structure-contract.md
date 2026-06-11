# Skill Structure Contract

This document defines the minimum structure for host-agent-facing `SKILL.md`
files in Co-Scientist.

The purpose is to make each skill self-sufficient for host-agent style execution surfaces:

- the host reads `SKILL.md`
- the host reads canonical run artifacts
- the host executes the declared workflow

Co-Scientist skills must not depend on implicit prompt-template injection.

## Required sections

Each migrated skill should include the following sections in order:

1. `Goal`
2. `Inputs`
3. `Outputs`
4. `Context Loading`
5. `Execution Prompt Contract`
6. `Execution Steps`
7. `Artifact Rules`
8. `Completion Rule`

Shorter helper skills may omit `Artifact Rules` only when they do not write any
artifacts directly, but the omission must be intentional.

## Section meanings

### `Goal`

State the single primary responsibility of the skill in one or two bullets.

### `Inputs`

List canonical artifact inputs explicitly. Avoid vague phrases such as
"research context" or "prior output" when concrete files are known.

Prefer file-oriented references such as:

- `research_plan/RESEARCH_PLAN.json`
- `state/STRATEGY_PLAN.json`
- `hypotheses/<id>/HYPOTHESIS.json`

### `Outputs`

List the stable artifacts that must exist when the skill completes.

If the skill also returns an in-memory object conceptually, still list the
artifact outputs because artifact persistence is the load-bearing contract.

### `Context Loading`

Describe which files must be opened before execution and which fields matter.

This section replaces hidden prompt-template variables. For example:

- read `research_goal` from `research_plan/RESEARCH_PLAN.json`
- treat `preferences` as evaluation axes
- treat `constraints` as hard boundaries

### `Execution Prompt Contract`

Describe the reasoning contract the host agent must follow while executing the
skill. This is where formerly external prompt semantics should live.

Recommended substructure:

- `System Intent`
- `Required Reasoning Focus`
- `Do Not Do`
- `Output Shape`

This section should define:

- what the model is trying to produce
- what it must pay attention to
- what failure modes are forbidden
- how the output must be shaped before writing artifacts

### `Execution Steps`

Provide an ordered list of execution steps.

These should be concrete enough that a host agent can follow them without
guessing hidden orchestration.

### `Artifact Rules`

State exactly which files must be written or updated, and clarify any
non-obvious serialization requirements.

Use this section to prevent partial writes, shadow artifacts, or informal
substitutes that do not satisfy the canonical contract.

### `Completion Rule`

Define when the skill may declare success.

This must be artifact-aware. A skill is not complete merely because a model
draft exists in memory; it is complete when required artifacts are written and
valid for downstream consumption.

## Dynamic context rules

Dynamic task context must come from one of these sources:

- host entry-skill arguments
- `input.md`
- canonical run artifacts under `state/`, `research_plan/`, `hypotheses/`,
  `tournaments/`, `islands/`, `meta/`, or `dashboard/`

Dynamic task context must not rely on unstated runtime substitution of external
prompt-template placeholders.

## Prompt asset migration rule

If a skill historically referenced:

- `prompts/system.md`
- `prompts/user_context.md`
- or other prompt snippets

their execution-critical semantics must be migrated into:

- `Context Loading`
- `Execution Prompt Contract`
- `Execution Steps`

Do not preserve a second hidden source of truth after migration.

## Style rules

- Keep imperative instructions explicit.
- Prefer artifact names over abstract nouns.
- Prefer stable file paths over "latest context" wording.
- Avoid references to implicit host behavior unless the repository actually
  enforces that behavior.
- Avoid `Prompt assets:` once a skill has been migrated.

## Relationship to other contracts

- `artifact-contract.md` defines what stable files exist.
- `state-contract.md` defines the state progression requirements.
- `strategy-contract.md` defines routing-plan and per-round strategy semantics.
- `completion-contract.md` defines when downstream completion claims are valid.

This document defines how one `SKILL.md` should expose those contracts to a
host agent.
