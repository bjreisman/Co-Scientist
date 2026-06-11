#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON:-python}"

exec "$PYTHON_BIN" -m tools.install.codex_install --project "$REPO_ROOT" --repo-root "$REPO_ROOT" "$@"
