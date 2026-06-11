from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tools.host.host_agent_surface import bootstrap_host_agent_run
from tools.validation.contract_validation import validate_run_artifacts


def _write_config(run_dir: Path) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Policy Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "input_file: input.md",
                "",
                "policy:",
                "  exploration_mode: aggressive",
                "  budget_profile: high",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config_path


def test_validate_run_artifacts_accepts_bootstrapped_policy_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)

        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        summary = validate_run_artifacts(run_dir, requested_skill="co-scientist-pipeline")

        checked = {Path(path).name for path in summary.checkedArtifacts}
        assert summary.status == "valid"
        assert "RUN_POLICY.yaml" in checked
        assert "POLICY_DECISION.json" in checked
        run_policy = (run_dir / "RUN_POLICY.yaml").read_text(encoding="utf-8")
        assert "iteration_policy: completion_driven" in run_policy
