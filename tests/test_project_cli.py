from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.host.project_cli import main


def test_project_cli_params_matches_host_surface(capsys) -> None:
    exit_code = main(["params", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entrySkill"] == "/co-scientist-start"
    assert any(axis["name"] == "iteration-policy" for axis in payload["coreAxes"])


def test_project_cli_doctor_json_reports_status(capsys) -> None:
    exit_code = main(["doctor", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] in {"pass", "warn", "fail"}
    assert any(check["name"] == "python" for check in payload["checks"])


def test_project_cli_module_help_succeeds() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.host.project_cli",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "{init,start,run,resume,validate,dashboard,doctor,params}" in result.stdout
    assert "RuntimeWarning" not in result.stderr


def test_project_cli_module_start_summary_only_succeeds() -> None:
    with TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.host.project_cli",
                "start",
                "--runs-dir",
                str(Path(temp_dir) / "runs"),
                "--goal",
                "Optimize ammonia synthesis conditions.",
                "--summary-only",
            ],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["command"] == "start"
        assert payload["summaryOnly"] is True
