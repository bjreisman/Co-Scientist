from __future__ import annotations

from packages.dashboard_contracts import build_dashboard_snapshot, build_empty_dashboard_snapshot


def test_build_dashboard_snapshot_from_state(sample_state) -> None:
    snapshot = build_dashboard_snapshot(
        "demo-run",
        "2026-05-24T00:00:00Z",
        sample_state,
    )

    assert snapshot.runId == "demo-run"
    assert snapshot.hasData is True
    assert snapshot.state.iteration_count == 2
    assert snapshot.metrics[0].label == "Hypotheses"
    assert snapshot.ranking[0].id == "hyp-001"
    assert snapshot.graphSeed.crossEdges[0].id == "hyp-001->hyp-002"
    assert snapshot.model_dump(mode="json", by_alias=True)["graphSeed"]["crossEdges"][0]["from"] == "hyp-001"
    assert snapshot.insightSections[0].items
    assert any(section.title == "Iteration Strategy" for section in snapshot.insightSections)
    assert snapshot.routing.strategy_decision_count == 0


def test_build_empty_dashboard_snapshot() -> None:
    snapshot = build_empty_dashboard_snapshot("empty-run", "2026-05-24T00:00:00Z")

    assert snapshot.runId == "empty-run"
    assert snapshot.hasData is False
    assert snapshot.metrics[0].value == 0
    assert any(section.title == "Iteration Strategy" for section in snapshot.insightSections)
    assert snapshot.routing.policy_decision is None
