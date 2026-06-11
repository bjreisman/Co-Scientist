from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import RunPolicyContract
from tools.host.create_run import (
    build_run_policy_from_controls,
    create_run_artifacts,
    generate_run_id,
    render_input_markdown,
)
from tools.host.intake_request import build_start_request_contract, build_start_request_preview


def test_generate_run_id_uses_goal_slug_and_date_prefix() -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir)

        run_id = generate_run_id(runs_dir, goal="Investigate kinase selectivity drift")

        assert run_id.endswith("investigate-kinase-selectivity-drift")
        assert run_id.startswith("20")


def test_render_input_markdown_combines_goal_brief_and_notes() -> None:
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        brief_path = temp_path / "brief.md"
        notes_path = temp_path / "notes.md"
        brief_path.write_text("Imported brief content.", encoding="utf-8")
        notes_path.write_text("Imported notes content.", encoding="utf-8")

        rendered = render_input_markdown(
            goal="Investigate adaptive resistance.",
            brief_path=brief_path,
            notes_path=notes_path,
        )

        assert "# Research Brief" in rendered
        assert "## Goal" in rendered
        assert "Investigate adaptive resistance." in rendered
        assert "## Imported Brief" in rendered
        assert "Imported brief content." in rendered
        assert "## Imported Notes" in rendered
        assert "Imported notes content." in rendered


def test_create_run_artifacts_writes_minimal_shell_and_optional_run_policy() -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir)
        run_policy = build_run_policy_from_controls(exploration="aggressive", review="strict")
        preview = build_start_request_preview(
            goal="Find a plausible mechanism for resistance.",
            runs_dir=runs_dir,
            run_id="test-run",
            interaction_mode="direct",
            exploration="aggressive",
            review="strict",
        )

        created = create_run_artifacts(
            goal="Find a plausible mechanism for resistance.",
            runs_dir=runs_dir,
            run_id="test-run",
            run_policy=run_policy,
            start_request=build_start_request_contract(preview),
        )

        assert created.run_dir == runs_dir / "test-run"
        assert created.config_path is None
        assert created.input_path.exists()
        assert created.run_policy_path is not None
        assert created.run_policy_path.exists()
        assert (created.run_dir / "state" / "START_REQUEST.json").exists()
        assert "Find a plausible mechanism for resistance." in created.input_path.read_text(encoding="utf-8")
        loaded_policy = RunPolicyContract.from_yaml_file(created.run_policy_path)
        assert loaded_policy.policy.exploration_mode == "aggressive"
        assert loaded_policy.policy.review_rigor == "strict"
