"""Host-agent project CLI for Co-Scientist entry skills."""

from __future__ import annotations

from collections.abc import Sequence

from .claude_project_cli import main as _main


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.host.project_cli`."""
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
