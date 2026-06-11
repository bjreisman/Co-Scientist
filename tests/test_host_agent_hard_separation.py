from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def test_host_agent_cli_run_works_when_repository_runtime_imports_are_blocked() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        (run_dir / "input.md").write_text("# Host-Agent Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
        (run_dir / "config.yaml").write_text("input_file: input.md\n", encoding="utf-8")

        command = [
            sys.executable,
            "-c",
            "\n".join(
                [
                    "import sys",
                    "class _Guard:",
                    "    def find_spec(self, fullname, path=None, target=None):",
                    "        blocked = ('back' + 'end', 'lega' + 'cy')",
                    "        if any(fullname == root or fullname.startswith(root + '.') for root in blocked):",
                    "            raise ImportError(f'import blocked: {fullname}')",
                    "        return None",
                    "sys.meta_path.insert(0, _Guard())",
                    "from tools.host.claude_project_cli import main",
                    f"raise SystemExit(main(['run', r'{run_dir}', '--no-dashboard']))",
                ]
            ),
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root)

        result = subprocess.run(
            command,
            cwd=repo_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["requestedSkill"] == "co-scientist-pipeline"
        assert Path(payload["handoffJson"]).exists()
