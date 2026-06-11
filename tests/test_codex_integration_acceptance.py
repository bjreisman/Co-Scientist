from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.validation.verify_codex_integration_surface import verify_codex_integration_surface


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_codex_integration_surface_acceptance_passes_without_running_codex() -> None:
    payload = verify_codex_integration_surface(REPO_ROOT)

    assert payload["status"] == "pass"
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["temporary_install_surface"]["status"] == "pass"
    assert checks["no_project_codex_directory"]["status"] == "pass"
    assert checks["search_bridge_config_output"]["status"] == "pass"


def test_codex_integration_surface_module_succeeds() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.validation.verify_codex_integration_surface",
            "--repo-root",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert "temporary_install_surface" in {check["name"] for check in payload["checks"]}
