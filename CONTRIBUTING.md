# Contributing

Thanks for considering a contribution to Co-Scientist. This project is early-stage research software, so small, well-tested changes are preferred over broad rewrites.

## Development Setup

Use the same setup path documented in `README.md`:

```powershell
uv sync --extra dev --extra mcp
pnpm --dir apps/dashboard install
pnpm --dir apps/dashboard build
```

Install the project-local agent surfaces only when you need to test Claude Code or Codex entry skills:

```powershell
powershell -File tools/install/install_co_scientist.ps1
powershell -File tools/install/install_co_scientist_codex.ps1
```

## Verification

Before opening a pull request, run:

```powershell
uv run python -m ruff check packages tools mcp-servers tests
uv run python -m ruff format --check packages tools mcp-servers tests
uv run pytest -q
uv pip check
pnpm --dir apps/dashboard build
uv run python -m tools.validation.verify_codex_integration_surface
```

When changing dashboard-facing contracts, regenerate and commit the generated frontend types:

```powershell
uv run python -m packages.dashboard_contracts.export_contract_artifacts
```

Generated `packages/*/schema/*.json` files are export artifacts and are intentionally not tracked.

## Pull Request Guidelines

- Keep code, comments, canonical technical documentation, tests, and skill-facing technical documentation in English. Translations such as `README.zh-CN.md` are allowed, but the English README remains the source of truth.
- Do not commit local run artifacts, `.venv`, dashboard caches, `.claude/`, `.agents/`, `.co-scientist/`, `CLAUDE.md`, or `AGENTS.md`.
- Do not commit API keys, provider credentials, private research notes, or unpublished manuscript content.
- Include focused tests for behavior changes and bug fixes.
- Keep host-agent calls out of automated tests unless the test uses deterministic local fakes.
