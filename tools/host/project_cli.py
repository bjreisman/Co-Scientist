"""Host-agent project CLI for Co-Scientist entry skills."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from .claude_project_cli import main as _main


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m tools.host.project_cli`."""
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if arguments and arguments[0] == "models":
        from tools.model_routing import main as model_main

        return model_main(arguments[1:])
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
