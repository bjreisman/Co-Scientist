from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tools.host.intake_request import (
    GUIDED_INTAKE_QUESTIONS,
    build_start_request_contract,
    build_start_request_preview,
    infer_interaction_mode,
    render_start_summary,
)


def test_guided_intake_questions_stay_short_and_bounded() -> None:
    assert 2 <= len(GUIDED_INTAKE_QUESTIONS) <= 4
    assert "research goal" in GUIDED_INTAKE_QUESTIONS[0].lower()


def test_infer_interaction_mode_prefers_brief_import_when_only_brief_is_supplied() -> None:
    with TemporaryDirectory() as temp_dir:
        brief_path = Path(temp_dir) / "brief.md"
        brief_path.write_text("Imported brief", encoding="utf-8")

        mode = infer_interaction_mode(goal=None, brief_path=brief_path)

        assert mode == "brief_import"


def test_build_start_request_preview_renders_summary_and_effective_controls() -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        preview = build_start_request_preview(
            goal="Investigate adaptive resistance.",
            runs_dir=runs_dir,
            interaction_mode="guided",
            exploration="aggressive",
            review="strict",
        )

        summary = render_start_summary(preview)

        assert preview.interaction_mode == "guided"
        assert preview.explicit_controls == {"exploration": "aggressive", "review": "strict"}
        assert preview.effective_controls["exploration"] == "aggressive"
        assert preview.effective_controls["review"] == "strict"
        assert "Planned Co-Scientist run:" in summary
        assert "- interaction mode: guided" in summary
        assert "state/STRATEGY_PLAN.json" in summary


def test_build_start_request_contract_tracks_explicit_and_inferred_controls() -> None:
    with TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        preview = build_start_request_preview(
            goal="Investigate adaptive resistance.",
            runs_dir=runs_dir,
            run_id="guided-run",
            interaction_mode="guided",
            exploration="aggressive",
        )

        contract = build_start_request_contract(preview)

        assert contract.runId == "guided-run"
        assert contract.requestText == "Investigate adaptive resistance."
        assert contract.interactionMode == "guided"
        assert contract.explicitControls == {"exploration": "aggressive"}
        assert contract.inferredControls["review"] == "standard"
