# Start Parameters

This reference defines the user-facing parameter surface for natural-language Co-Scientist starts.

## Entry Surfaces

- Entry skill: `/co-scientist-start` in Claude Code or `$co-scientist-start` in Codex
- Parameter help: `/co-scientist-params` in Claude Code or `$co-scientist-params` in Codex
- CLI: `python -m tools.host.project_cli start`
- CLI parameter help: `python -m tools.host.project_cli params`

## Interaction Rules

1. Default to a short guided intake when the user invokes the host entry skill without arguments.
2. Ask at most four short questions in guided mode:
   - research goal
   - exploration preference
   - iteration strategy
   - optional brief import
3. Do not ask for low-level mechanics knobs such as `num_debaters`, `elo_k_factor`, or `ucb_exploration_constant`.
4. When the user asks what can be configured, show the high-level axes first and only show utility flags when relevant.
5. When converting an entry-skill request into a CLI command, map `key: value` controls to explicit flags and do not pass the colon form directly into `project_cli`.

## Core Axes

### `exploration`

- CLI flag: `--exploration`
- Values: `conservative | balanced | aggressive`
- Default: `balanced`
- Meaning: controls how strongly the run favors novelty, diversity, and broad search.

### `review`

- CLI flag: `--review`
- Values: `light | standard | strict`
- Default: `standard`
- Meaning: controls review depth and critique strictness without disabling any required review stage.

### `budget`

- CLI flag: `--budget`
- Values: `low | medium | high`
- Default: `medium`
- Meaning: controls per-round run intensity and how expensive each generation, review, and ranking pass may become.

### `iteration-policy`

- CLI flag: `--iteration-policy`
- Values: `completion_driven | capped`
- Default: `completion_driven`
- Meaning: controls whether the run stops through semantic completion signals or through a user-chosen iteration cap.

### `human-checkpoint`

- CLI flag: `--human-checkpoint`
- Values: `auto | before_overview | before_completion | every_major_stage`
- Default: `auto`
- Meaning: controls where the run should pause for explicit human confirmation.
- `auto` means the host agent should not ask whether to continue after each individual evolution round; in `completion_driven` mode it should keep going until a real stop, block, or configured checkpoint boundary is reached.
- If an interactive host-agent turn stops before convergence or a terminal route, the handoff must say the run is paused, current convergence has not been reached, persisted state is resumable, and the next recommended action is continue evolution through resume or an explicit continue request.
- `before_overview` means pause only when the run is ready to hand off to the overview stage.
- `before_completion` means pause only after overview work is done and the system is ready to record final completion.
- `every_major_stage` means pause at major stage transitions, not at every child hypothesis by default.

## Advanced Axes

### `generation-bias`

- CLI flag: `--generation-bias`
- Values: `literature_heavy | debate_heavy | assumptions_heavy | mixed`
- Default: `mixed`
- Meaning: biases generation toward one family of idea creation strategies.

### `evolution`

- CLI flag: `--evolution`
- Values: `exploit | balanced | diversify`
- Default: `balanced`
- Meaning: controls whether later iterations exploit current winners or diversify the search.

### `stop-policy`

- CLI flag: `--stop-policy`
- Values: `exploratory | standard | strict`
- Default: `standard`
- Meaning: controls how readily the run accepts that semantic stop conditions are sufficient to move toward the overview or final synthesis.

### `iteration-band`

- CLI flag: `--iteration-band`
- Values: `6_10 | 10_14 | 15_20 | 20_30`
- Default: none
- Meaning: optional capped-run iteration range. Use only with `--iteration-policy capped`.

## Utility Flags

- `--goal`: primary natural-language research goal
- `--brief`: import one existing Markdown or text brief into `input.md`
- `--notes`: append one notes file to the generated brief
- `--run-id`: explicitly set the run directory name
- `--runs-dir`: explicitly set the parent runs directory
- `--summary-only`: render the start summary without creating files

## Examples

```text
/co-scientist-start
/co-scientist-start "Investigate a plausible resistance mechanism." -- exploration: aggressive, iteration policy: completion_driven
$co-scientist-start
$co-scientist-start "Investigate a plausible resistance mechanism." -- exploration: aggressive, iteration policy: completion_driven
python -m tools.host.project_cli start --goal "Investigate a plausible resistance mechanism." --budget low --iteration-policy capped --iteration-band 6_10
python -m tools.host.project_cli params
```
