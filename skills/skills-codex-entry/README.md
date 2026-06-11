# Codex Entry Skills

This directory contains the thin Codex-facing entry adapter for Co-Scientist.

The canonical workflow remains under `skills/<skill-name>/`. Codex entry skills must stay small: they translate Codex user intent into the neutral host CLI, require deterministic tool calls where appropriate, and then route execution back to the canonical repository-local skills and run artifacts.

Rules:

- Do not copy the full generation, review, evolution, ranking, proximity, or overview workflow into this directory.
- Use `python -m tools.host.project_cli` for host-agent bootstrap commands.
- Treat `.agents/skills/` as the Codex discovery surface after installation, not as the source of truth.
- Treat `skills/` as the canonical source of workflow semantics.
- Never fabricate validation, literature, embedding, ranking, or dashboard artifacts from prompt output.
