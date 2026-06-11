from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tools.host.claude_project_cli import main
from tools.host.host_agent import HostAgentHandoff
from tools.host.host_agent_surface import DashboardLinksResult, HostAgentBootstrapResult
from tools.validation.contract_validation import HostAgentValidationSummary


def _write_config(run_dir: Path) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Host-Agent Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text("input_file: input.md\n", encoding="utf-8")
    return config_path


def test_claude_project_cli_run_writes_handoff(capsys) -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)

        exit_code = main(["run", str(config_path), "--no-dashboard"])

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["requestedSkill"] == "co-scientist-pipeline"
        assert Path(payload["handoffJson"]).exists()
        assert Path(payload["handoffMarkdown"]).exists()


def test_claude_project_cli_resume_uses_run_dir_and_sets_resume_flag(capsys) -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        exit_code = main(["resume", str(run_dir), "--no-dashboard"])

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["resume"] is True
        assert payload["runDir"] == str(run_dir.resolve())


def test_claude_project_cli_init_creates_run_from_goal(capsys) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"

        exit_code = main(
            [
                "init",
                "--runs-dir",
                str(runs_dir),
                "--run-id",
                "goal-run",
                "--goal",
                "Investigate a resistance mechanism.",
                "--exploration",
                "aggressive",
            ]
        )

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "init"
        assert payload["runDir"] == str((runs_dir / "goal-run").resolve())
        assert "configPath" not in payload
        assert Path(payload["inputPath"]).exists()
        assert Path(payload["runPolicyPath"]).exists()
        assert (Path(payload["runDir"]) / "state" / "START_REQUEST.json").exists()


def test_claude_project_cli_start_bootstraps_created_run(capsys) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"

        exit_code = main(
            [
                "start",
                "--runs-dir",
                str(runs_dir),
                "--run-id",
                "start-run",
                "--goal",
                "Investigate a kinase selectivity mechanism.",
                "--no-dashboard",
            ]
        )

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "start"
        assert payload["requestedSkill"] == "co-scientist-pipeline"
        assert payload["runDir"] == str((runs_dir / "start-run").resolve())
        assert "configPath" not in payload
        assert payload["dashboard"]["status"] == "disabled"
        assert Path(payload["handoffJson"]).exists()
        assert Path(payload["handoffMarkdown"]).exists()
        assert (Path(payload["runDir"]) / "state" / "START_REQUEST.json").exists()


def test_claude_project_cli_start_returns_dashboard_links_when_enabled(capsys, monkeypatch) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"

        def fake_bootstrap_host_agent_run(
            run_target: Path,
            *,
            requested_skill: str,
            resume: bool,
            ensure_dashboard: bool = True,
            dashboard_supervisor_factory=None,
        ) -> HostAgentBootstrapResult:
            run_dir = run_target.resolve()
            state_dir = run_dir / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            handoff = HostAgentHandoff(
                runId=run_dir.name,
                runDir=str(run_dir),
                configPath="",
                inputFile=str((run_dir / "input.md").resolve()),
                requestedSkill=requested_skill,
                resume=resume,
                skillPath=str((Path.cwd() / "skills" / "co-scientist-pipeline" / "SKILL.md").resolve()),
                sharedReferences={},
                artifactPaths={},
                dashboardLinks={
                    "dashboard": "http://127.0.0.1:3000/?run=start-run",
                    "ranking": "http://127.0.0.1:3000/ranking?run=start-run",
                },
                validation=HostAgentValidationSummary(
                    status="valid",
                    checkedArtifacts=[],
                    issues=[],
                    errorCount=0,
                    warningCount=0,
                    resumeReady=False,
                    requestedSkill=requested_skill,
                ),
                nextActions=[],
            )
            return HostAgentBootstrapResult(
                run_dir=run_dir,
                handoff=handoff,
                handoff_json_path=state_dir / "HOST_AGENT_HANDOFF.json",
                handoff_markdown_path=state_dir / "HOST_AGENT_HANDOFF.md",
                dashboard_links=handoff.dashboardLinks,
                dashboard_runtime={"status": "running"},
            )

        monkeypatch.setattr("tools.host.claude_project_cli.bootstrap_host_agent_run", fake_bootstrap_host_agent_run)

        exit_code = main(
            [
                "start",
                "--runs-dir",
                str(runs_dir),
                "--run-id",
                "start-run",
                "--goal",
                "Investigate a dashboard startup contract.",
            ]
        )

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["dashboard"]["status"] == "running"
        assert payload["dashboardLinks"]["dashboard"].endswith("/?run=start-run")
        assert payload["dashboardLinks"]["ranking"].endswith("/ranking?run=start-run")


def test_claude_project_cli_start_summary_only_does_not_create_files(capsys) -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"

        exit_code = main(
            [
                "start",
                "--runs-dir",
                str(runs_dir),
                "--goal",
                "Investigate a literature-grounded resistance mechanism.",
                "--interaction-mode",
                "guided",
                "--summary-only",
            ]
        )

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "start"
        assert payload["summaryOnly"] is True
        assert payload["interactionMode"] == "guided"
        assert "Planned Co-Scientist run:" in payload["summary"]
        assert not Path(payload["runDir"]).exists()


def test_claude_project_cli_params_text_lists_core_axes(capsys) -> None:
    exit_code = main(["params"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Co-Scientist start parameters" in output
    assert "Core axes:" in output
    assert "exploration (--exploration)" in output
    assert "review (--review)" in output
    assert "iteration-policy (--iteration-policy)" in output


def test_claude_project_cli_params_json_exposes_advanced_axes(capsys) -> None:
    exit_code = main(["params", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entrySkill"] == "/co-scientist-start"
    assert any(axis["name"] == "iteration-policy" for axis in payload["coreAxes"])
    assert any(axis["name"] == "iteration-band" for axis in payload["advancedAxes"])
    assert any(axis["name"] == "generation-bias" for axis in payload["advancedAxes"])
    assert any(axis["name"] == "summary-only" for axis in payload["utilityFlags"])


def test_claude_project_cli_doctor_json_reports_status(capsys) -> None:
    exit_code = main(["doctor", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] in {"pass", "warn", "fail"}
    assert any(check["name"] == "python" for check in payload["checks"])


def test_claude_project_cli_start_accepts_colon_style_controls_in_summary_mode(capsys) -> None:
    exit_code = main(
        [
            "start",
            "--goal",
            "Investigate a plausible resistance mechanism.",
            "exploration:",
            "aggressive,",
            "review:",
            "strict,",
            "iteration policy:",
            "capped,",
            "iteration band:",
            "6 10,",
            "human checkpoint:",
            "before overview",
            "--summary-only",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["effectiveControls"]["exploration"] == "aggressive"
    assert payload["effectiveControls"]["review"] == "strict"
    assert payload["effectiveControls"]["iteration_policy"] == "capped"
    assert payload["effectiveControls"]["iteration_band"] == "6_10"
    assert payload["effectiveControls"]["human_checkpoint"] == "before_overview"


def test_claude_project_cli_start_requires_iteration_band_for_capped_runs() -> None:
    with pytest.raises(
        ValueError, match="`--iteration-band` is required when `--iteration-policy capped` is selected."
    ):
        main(
            [
                "start",
                "--goal",
                "Investigate a plausible resistance mechanism.",
                "--iteration-policy",
                "capped",
                "--summary-only",
            ]
        )


def test_claude_project_cli_module_help_succeeds() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.host.claude_project_cli",
            "--help",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "{init,start,run,resume,validate,dashboard,doctor,params}" in result.stdout


def test_claude_project_cli_module_start_summary_only_succeeds() -> None:
    with TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.host.claude_project_cli",
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


def test_tools_policy_module_entrypoints_do_not_emit_runpy_warning() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    for module_name in (
        "tools.policy.plan_strategy",
        "tools.policy.resolve_run_config",
        "tools.policy.validate_resolved_config",
    ):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                module_name,
                "--help",
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "RuntimeWarning" not in result.stderr
        assert "found in sys.modules after import of package 'tools.policy'" not in result.stderr


def test_claude_project_cli_dashboard_returns_runtime_and_links(capsys, monkeypatch) -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        monkeypatch.setattr(
            "tools.host.claude_project_cli.ensure_dashboard_for_run",
            lambda *args, **kwargs: DashboardLinksResult(
                runtime={
                    "status": "starting",
                    "frontend": {"baseUrl": "http://127.0.0.1:3000"},
                    "api": {"baseUrl": "http://127.0.0.1:3000/api"},
                },
                links={
                    "dashboard": "http://127.0.0.1:3000/?run=run",
                    "ranking": "http://127.0.0.1:3000/ranking?run=run",
                    "evolution": "http://127.0.0.1:3000/evolution?run=run",
                    "metaReviews": "http://127.0.0.1:3000/meta-reviews?run=run",
                },
            ),
        )

        exit_code = main(["dashboard", str(run_dir)])

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["runtime"]["status"] == "starting"
        assert payload["links"]["dashboard"].endswith("/?run=run")
        assert payload["links"]["ranking"].endswith("/ranking?run=run")
