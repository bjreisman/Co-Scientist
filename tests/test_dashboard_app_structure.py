from __future__ import annotations

from pathlib import Path


def test_dashboard_app_is_artifact_only_and_runtime_free() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    dashboard_root = repo_root / "apps" / "dashboard"
    artifact_reader = dashboard_root / "server" / "utils" / "dashboardArtifacts.ts"
    snapshot_route = dashboard_root / "server" / "api" / "runs" / "[runId]" / "snapshot.get.ts"
    progress_route = dashboard_root / "server" / "api" / "runs" / "[runId]" / "progress.get.ts"
    runs_route = dashboard_root / "server" / "api" / "runs" / "index.get.ts"
    health_route = dashboard_root / "server" / "api" / "health.get.ts"

    forbidden_runtime_root = repo_root / ("lega" + "cy")

    assert dashboard_root.exists()
    assert not forbidden_runtime_root.exists()
    assert not (repo_root / "src" / "frontend").exists()
    assert not (repo_root / "src" / "backend").exists()
    assert artifact_reader.exists()
    assert snapshot_route.exists()
    assert progress_route.exists()
    assert runs_route.exists()
    assert health_route.exists()

    artifact_reader_text = artifact_reader.read_text(encoding="utf-8")
    assert ("back" + "end.") not in artifact_reader_text
    assert ("lega" + "cy") not in artifact_reader_text
    assert "StatePersistence" not in artifact_reader_text
    assert "create_async_engine" not in artifact_reader_text
    assert "db_url" not in artifact_reader_text
    assert "POLICY_DECISION.json" in artifact_reader_text
    assert "RESOLVED_RUN_CONFIG.json" in artifact_reader_text
    assert "STRATEGY_PLAN.json" in artifact_reader_text
    assert "research_plan" in artifact_reader_text
    assert "RESEARCH_PLAN.json" in artifact_reader_text
    assert "HYPOTHESIS.json" in artifact_reader_text
    assert "ISLANDS.json" in artifact_reader_text
    assert "DEEP_VERIFICATION.json" in artifact_reader_text
    assert "OBSERVATION_REVIEW.json" in artifact_reader_text
    assert "SIMULATION_REVIEW.json" in artifact_reader_text
    assert "REVIEW_SUMMARY.json" in artifact_reader_text
    assert "TOURNAMENT.json" in artifact_reader_text
    assert "iterationCount" in artifact_reader_text
    assert "convergenceCount" in artifact_reader_text
    assert "Latest routing mode is" in artifact_reader_text
    assert "island metrics remain uninitialized" in artifact_reader_text
    assert "enteredTopKLastRound" in artifact_reader_text
    assert "hypothesis-review-pipeline" in artifact_reader_text
    assert "run_ranking" in artifact_reader_text
    assert "INITIAL_REVIEW.json" in artifact_reader_text
    assert "PROXIMITY_GRAPH.json" in artifact_reader_text
    assert "topHypothesisIds" in artifact_reader_text
    assert "completedStages" in artifact_reader_text
    assert "plannedNextStage" in artifact_reader_text
    assert "currentSkill" in artifact_reader_text

    insight_card = dashboard_root / "app" / "components" / "InsightCard.vue"
    markdown_renderer = dashboard_root / "app" / "utils" / "renderMarkdown.ts"
    hypothesis_detail = dashboard_root / "app" / "components" / "HypothesisDetailPanel.vue"
    meta_reviews_page = dashboard_root / "app" / "pages" / "meta-reviews.vue"
    ranking_page = dashboard_root / "app" / "pages" / "ranking.vue"
    state_card = dashboard_root / "app" / "components" / "DashboardStateCard.vue"
    flowchart = dashboard_root / "app" / "components" / "PipelineFlowchart.vue"
    css_path = dashboard_root / "app" / "assets" / "css" / "main.css"

    insight_card_text = insight_card.read_text(encoding="utf-8")
    markdown_renderer_text = markdown_renderer.read_text(encoding="utf-8")
    hypothesis_detail_text = hypothesis_detail.read_text(encoding="utf-8")
    meta_reviews_page_text = meta_reviews_page.read_text(encoding="utf-8")
    ranking_page_text = ranking_page.read_text(encoding="utf-8")
    state_card_text = state_card.read_text(encoding="utf-8")
    flowchart_text = flowchart.read_text(encoding="utf-8")
    css_text = css_path.read_text(encoding="utf-8")

    assert "renderMarkdownToHtml" in insight_card_text
    assert "v-html" in insight_card_text
    assert "sectionClass" in insight_card_text
    assert "insight-dot" not in insight_card_text
    assert "renderInlineMarkdown" in markdown_renderer_text
    assert "<code>$1</code>" in markdown_renderer_text
    assert "experimentalDesignSteps" in hypothesis_detail_text
    assert "detail-ordered-list" in hypothesis_detail_text
    assert "meta-reviews-grid" in meta_reviews_page_text
    assert "fullWidth?: boolean" in state_card_text
    assert "'full-width': fullWidth" in state_card_text
    assert "full-width" in ranking_page_text
    assert ':completed-stages="completedStages"' not in ranking_page_text
    assert ':planned-next-stage="plannedNextStage"' not in ranking_page_text
    assert ':current-skill="currentSkill"' not in ranking_page_text
    assert "ranking-overview" not in flowchart_text
    assert "nodeStateClass('supervisor')" in flowchart_text
    assert "completedStages" not in flowchart_text
    assert "currentSkill" not in flowchart_text
    assert "plannedNextStage" not in flowchart_text
    assert "agent-flow-arrow-active" not in flowchart_text
    assert "agent-flow-arrow-planned" not in flowchart_text
    assert "agent-flow-arrow-completed" not in flowchart_text
    assert ".detail-ordered-list" in css_text
    assert ".insight-copy code" in css_text
    assert ".meta-reviews-grid" in css_text
    assert "--meta-review-card-height" in css_text
    assert ".meta-reviews-grid .insight-card" in css_text
    assert ".meta-reviews-grid .insight-content" in css_text
    assert ".status-card.full-width" in css_text
    assert ".agent-node.planned" not in css_text
    assert ".agent-node.control" not in css_text
    assert ".agent-node.completed" not in css_text
    assert ".agent-flow-line.active" not in css_text
    assert ".agent-flow-line.planned" not in css_text
    assert ".agent-flow-line.completed" not in css_text
    assert ".agent-flow-arrowhead.active" not in css_text
