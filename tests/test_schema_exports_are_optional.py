from __future__ import annotations

from pathlib import Path

from packages.dashboard_contracts.export_contract_artifacts import render_frontend_types


RUNTIME_FILES = [
    Path("apps/dashboard/server/utils/dashboardArtifacts.ts"),
    Path("tools/host/host_agent_surface.py"),
    Path("tools/validation/contract_validation.py"),
]


def test_generated_dashboard_header_uses_flattened_source_path() -> None:
    rendered = render_frontend_types()
    assert "packages/dashboard_contracts/dashboard.py" in rendered
    assert "packages/dashboard_contracts/python/dashboard.py" not in rendered


def test_checked_in_dashboard_types_match_renderer() -> None:
    generated_path = Path("apps/dashboard/app/types/generated/dashboard.ts")
    generated = generated_path.read_text(encoding="utf-8")
    rendered = render_frontend_types()
    assert generated == rendered
    assert "ResearchOverview" not in generated
    assert "iteration_policy: 'completion_driven' | 'capped'" in generated
    assert "iteration_band?: '6_10' | '10_14' | '15_20' | '20_30' | null" in generated
    assert "safety_max_iterations: number" in generated
    assert "iteration_cap_source:" in generated
    assert "export type RunProgressSource" in generated
    assert "export type RunProgressConfidence" in generated
    assert "completedStages: PipelineStage[]" in generated
    assert "plannedNextStage?: PipelineStage | null" in generated
    assert "currentSkill: string" in generated
    assert "source: RunProgressSource" in generated
    assert "confidence: RunProgressConfidence" in generated


def test_runtime_paths_do_not_consume_schema_json_files() -> None:
    blocked = (
        "dashboard_snapshot.schema.json",
        "run_progress.schema.json",
        "run_summary.schema.json",
        "hypothesis.schema.json",
        "co_scientist_state.schema.json",
    )
    for path in RUNTIME_FILES:
        content = path.read_text(encoding="utf-8")
        for token in blocked:
            assert token not in content
