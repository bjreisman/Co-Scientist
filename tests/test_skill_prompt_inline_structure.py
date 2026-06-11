from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"


MIGRATED_SKILLS = [
    "research-config",
    "hypothesis-generate-literature",
    "hypothesis-generate-assumptions",
    "hypothesis-generate-debate",
    "hypothesis-evolve-grounding",
    "hypothesis-evolve-coherence",
    "hypothesis-evolve-feasibility",
    "hypothesis-evolve-inspiration",
    "hypothesis-evolve-combination",
    "hypothesis-evolve-simplification",
    "hypothesis-evolve-out-of-box",
    "hypothesis-initial-review",
    "hypothesis-full-review",
    "hypothesis-deep-verification",
    "hypothesis-observation-review",
    "hypothesis-simulation-review",
    "hypothesis-review-summary",
    "evolution-strategy-supervisor",
    "hypothesis-placement-tournament",
    "hypothesis-ranked-tournament",
    "insights-from-reviews",
    "research-overview-pipeline",
]


REQUIRED_SECTION_HEADINGS = [
    "Goal:",
    "Inputs:",
    "Outputs:",
    "Context Loading:",
    "Execution Prompt Contract:",
    "Execution Steps:",
    "Completion Rule:",
]

REQUIRED_SCHEMA_REFERENCES = {
    "run-policy-router": ("packages/agent_contracts/policy.py",),
    "research-config": ("packages/agent_contracts/research_plan.py",),
    "hypothesis-generate-literature": (
        "packages/agent_contracts/hypothesis.py",
        "packages/agent_contracts/literature.py",
    ),
    "hypothesis-generate-assumptions": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-generate-debate": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-evolve-grounding": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-evolve-coherence": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-evolve-feasibility": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-evolve-inspiration": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-evolve-combination": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-evolve-simplification": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-evolve-out-of-box": ("packages/agent_contracts/hypothesis.py",),
    "hypothesis-placement-tournament": ("packages/agent_contracts/ranking.py",),
    "hypothesis-ranked-tournament": ("packages/agent_contracts/ranking.py",),
    "hypothesis-initial-review": ("packages/agent_contracts/review.py",),
    "hypothesis-full-review": (
        "packages/agent_contracts/review.py",
        "packages/agent_contracts/literature.py",
    ),
    "hypothesis-deep-verification": (
        "packages/agent_contracts/review.py",
        "packages/agent_contracts/literature.py",
    ),
    "hypothesis-observation-review": ("packages/agent_contracts/review.py",),
    "hypothesis-simulation-review": ("packages/agent_contracts/review.py",),
    "hypothesis-review-summary": ("packages/agent_contracts/review.py",),
    "insights-from-reviews": ("packages/agent_contracts/meta_review.py",),
    "research-overview-pipeline": (
        "packages/agent_contracts/meta_review.py",
        "packages/agent_contracts/pipeline_runtime.py",
    ),
}

DETERMINISTIC_SKILL_REFERENCES = {
    "hypothesis-proximity-update": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/state.py",
        "packages/agent_contracts/proximity.py",
        "from tools import update_hypothesis_proximity",
        "packages/agent_mechanics/hypothesis_embedding.py",
        "packages/agent_mechanics/hypothesis_embedding_text.py",
    ),
    "ranking-elo-update": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/ranking.py",
        "packages/agent_contracts/hypothesis.py",
        "from tools import apply_and_persist_elo_updates",
        "packages/run_artifacts/ranking_writeback.py",
        "RankingUpdateReceiptContract",
    ),
    "island-select": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/state.py",
        "packages/agent_contracts/hypothesis.py",
        "packages/agent_contracts/resolved_config.py",
        "from tools import select_island_hypotheses",
        "packages/agent_mechanics/island_select.py",
        "Do not read, repair from, or write `state/ISLANDS.json`.",
        "Deprecated aliases are not accepted as selection inputs.",
    ),
    "convergence-check": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/pipeline_control.py",
        "from tools import evaluate_convergence",
        "packages/agent_mechanics/convergence_check.py",
    ),
    "literature-search": (
        "skills/shared-references/schema-index.md",
        "skills/shared-references/literature-search-contract.md",
        "packages/agent_contracts/literature.py",
        "from tools import search_literature",
        "tools/literature_search_client.py",
    ),
    "strategy-router": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/strategy_plan.py",
        "python -m tools.policy.plan_strategy",
        "tools/policy/plan_strategy.py",
    ),
}

DETERMINISTIC_REQUIRED_SECTION_HEADINGS = [
    "Goal:",
    "Inputs:",
    "Outputs:",
    "Context Loading:",
    "Execution Contract:",
    "Execution Steps:",
    "Completion Rule:",
]

PIPELINE_MECHANICS_REFERENCES = {
    "hypothesis-ranking-pipeline": (
        "Goal:",
        "Inputs:",
        "Outputs:",
        "Context Loading:",
        "Execution Contract:",
        "Execution Steps:",
        "Completion Rule:",
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/hypothesis.py",
        "packages/agent_contracts/ranking.py",
        "packages/agent_contracts/resolved_config.py",
        "from tools import select_placement_opponents",
        "from tools import select_fallback_placement_opponents",
        "from tools import get_top_k_hypotheses",
        "from tools import should_run_ranked_tournament",
        "from tools import select_ranked_opponents",
        "packages/agent_mechanics/top_k_select.py",
    ),
    "hypothesis-evolution-loop": (
        "from tools import ensure_run_islands_for_hypotheses",
        "from tools import update_run_single_island_reward",
        "tools.ensure_run_islands_for_hypotheses(run_dir, [candidate_hypothesis.id])",
        "tools.update_run_single_island_reward(run_dir, selected_island_id, candidate_hypothesis.id, decay_factor)",
        "packages/run_artifacts/island_state.py",
        "Do not hand-edit `islands/ISLANDS.json`, and never write `state/ISLANDS.json`.",
        "`decayed_reward = 0.0`, `decayed_visits = 0.0`, and `visit_count = 0`",
        "`hypothesis_ids`, `ucb_score`, or `strategy_label`",
        "nonzero `visit_count` and nonzero `decayed_visits`",
        "stop before the next routing refresh",
        "tools.update_single_island_reward(...)",
        "tools.compute_single_island_reward(...)",
        "tools.apply_decayed_island_update(...)",
        "packages/agent_mechanics/island_reward_update.py",
        "from tools import evaluate_convergence",
        "packages/agent_mechanics/convergence_check.py",
        "signals.selection_strategy == single_island",
        "signals.selection_strategy == multi_island",
        "from tools import append_evolution_round_record",
        "packages/agent_contracts/evolution_round.py",
        "state/EVOLUTION_ROUNDS.jsonl",
        "copy `proximity_receipt_status` from the persisted per-child receipt",
        "do not leave pre-round router signals as the current plan",
    ),
}

DIRECT_ENTRY_PIPELINE_REQUIRED_SECTION_HEADINGS = [
    "Goal:",
    "Inputs:",
    "Outputs:",
    "Context Loading:",
    "Execution Contract:",
    "Execution Steps:",
    "Completion Rule:",
]

DIRECT_ENTRY_PIPELINE_REFERENCES = {
    "co-scientist-pipeline": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/policy.py",
        "packages/agent_contracts/research_plan.py",
        "packages/agent_contracts/resolved_config.py",
        "packages/agent_contracts/strategy_plan.py",
        "packages/agent_contracts/pipeline_runtime.py",
        "packages/agent_contracts/pipeline_control.py",
    ),
    "hypothesis-generation-pipeline": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/research_plan.py",
        "packages/agent_contracts/strategy_plan.py",
        "packages/agent_contracts/hypothesis.py",
        "packages/agent_contracts/literature.py",
        "packages/agent_contracts/state.py",
        "packages/agent_contracts/pipeline_runtime.py",
        "tools.ensure_run_islands_for_hypotheses(run_dir)",
        "`decayed_reward = 0.0`, `decayed_visits = 0.0`, and `visit_count = 0`",
        "`hypothesis_ids`, `ucb_score`, or `strategy_label`",
    ),
    "hypothesis-review-pipeline": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/review.py",
        "packages/agent_contracts/hypothesis.py",
        "packages/agent_contracts/literature.py",
        "from tools import sync_hypothesis_review",
        "packages/run_artifacts/review_sync.py",
    ),
    "hypothesis-evolution-loop": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/pipeline_control.py",
        "packages/agent_contracts/pipeline_runtime.py",
        "packages/agent_contracts/hypothesis.py",
        "packages/agent_contracts/state.py",
        "packages/agent_contracts/ranking.py",
        "packages/agent_contracts/evolution_round.py",
    ),
}

REMAINING_ACTIVE_SKILL_REQUIRED_SECTION_HEADINGS = [
    "Goal:",
    "Inputs:",
    "Outputs:",
    "Context Loading:",
    "Execution Contract:",
    "Execution Steps:",
    "Completion Rule:",
]

REMAINING_ACTIVE_SKILL_REFERENCES = {
    "run-policy-router": (
        "skills/shared-references/schema-index.md",
        "packages/agent_contracts/policy.py",
    ),
    "dashboard-snapshot": (
        "skills/shared-references/artifact-contract.md",
        "packages/dashboard_contracts/snapshot_projection.py",
        "from tools import build_dashboard_snapshot",
    ),
}

ACTIVE_SUBSTAGE_RUNTIME_REFERENCES = {
    "co-scientist-pipeline": (
        "currentPhase",
        "currentSkill",
        "CURRENT_STAGE",
        "run_configuration",
        "sync_pipeline_stage_artifacts",
        'current_phase="Configuration"',
        'current_skill="research-config"',
        "run_review",
        "run_insights",
        "run_proximity",
        "run_ranking",
    ),
    "hypothesis-evolution-loop": (
        "sync_pipeline_stage_artifacts",
        'current_phase="Evolution"',
        'current_skill="hypothesis-evolution-loop"',
        "Reflection",
        "Insights from Reviews",
        "Proximity",
        "Ranking",
    ),
    "hypothesis-review-pipeline": (
        "packages/agent_contracts/pipeline_runtime.py",
        "sync_pipeline_stage_artifacts",
        'current_phase="Reflection"',
        'current_skill="hypothesis-review-pipeline"',
    ),
    "insights-from-reviews": (
        "packages/agent_contracts/pipeline_runtime.py",
        "sync_pipeline_stage_artifacts",
        'current_phase="Insights from Reviews"',
        'current_skill="insights-from-reviews"',
    ),
    "hypothesis-proximity-update": (
        "packages/agent_contracts/pipeline_runtime.py",
        "sync_pipeline_stage_artifacts",
        'current_phase="Proximity"',
        'current_skill="hypothesis-proximity-update"',
    ),
    "hypothesis-ranking-pipeline": (
        "packages/agent_contracts/pipeline_runtime.py",
        "sync_pipeline_stage_artifacts",
        'current_phase="Ranking"',
        'current_skill="hypothesis-ranking-pipeline"',
    ),
    "research-overview-pipeline": (
        "packages/agent_contracts/pipeline_runtime.py",
        "sync_pipeline_stage_artifacts",
        'current_phase="Research Overview"',
        'current_skill="research-overview-pipeline"',
    ),
}

CLAUDE_ENTRY_DASHBOARD_REFERENCES = {
    "co-scientist-start": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "python -m tools.host.claude_project_cli dashboard <run-dir>",
        "dashboardLinks.dashboard",
        "/co-scientist-dashboard <run-dir>",
    ),
    "co-scientist-run": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "python -m tools.host.claude_project_cli dashboard <run-dir>",
        "dashboardLinks.dashboard",
        "/co-scientist-dashboard <run-dir>",
    ),
    "co-scientist-resume": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "python -m tools.host.claude_project_cli dashboard <run-dir>",
        "dashboardLinks.dashboard",
        "/co-scientist-dashboard <run-dir>",
    ),
    "co-scientist-dashboard": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "links.dashboard",
        "human-readable dashboard receipt",
        "ready-link follow-up",
    ),
}


CODEX_ENTRY_DASHBOARD_REFERENCES = {
    "co-scientist-start": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "python -m tools.host.project_cli dashboard <run-dir>",
        "dashboard.status",
        "runtime.status",
        "dashboardLinks.dashboard",
        "$co-scientist-dashboard <run-dir>",
    ),
    "co-scientist-run": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "python -m tools.host.project_cli dashboard <run-dir>",
        "dashboard.status",
        "runtime.status",
        "dashboardLinks.dashboard",
        "$co-scientist-dashboard <run-dir>",
    ),
    "co-scientist-resume": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "python -m tools.host.project_cli dashboard <run-dir>",
        "dashboard.status",
        "runtime.status",
        "dashboardLinks.dashboard",
        "$co-scientist-dashboard <run-dir>",
    ),
    "co-scientist-dashboard": (
        "runs/<run_id>/dashboard/LINKS.md",
        "runs/<run_id>/dashboard/LINKS.json",
        "links.dashboard",
        "runtime.status",
        "ready-link follow-up",
    ),
}


def test_stage_restore_prompts_prefer_persisted_state_refresh_over_forced_evolution_override() -> None:
    top_level_skill = (SKILLS_ROOT / "co-scientist-pipeline" / "SKILL.md").read_text(encoding="utf-8")
    evolution_loop_skill = (SKILLS_ROOT / "hypothesis-evolution-loop" / "SKILL.md").read_text(encoding="utf-8")
    strategy_router_skill = (SKILLS_ROOT / "strategy-router" / "SKILL.md").read_text(encoding="utf-8")

    assert "python -m tools.policy.plan_strategy <run_dir>` when resuming persisted routing state" in top_level_skill
    assert "--phase Evolution`." not in top_level_skill
    assert (
        "python -m tools.policy.plan_strategy <run_dir>` before every evolution round that is resuming "
        "from persisted state" in evolution_loop_skill
    )
    assert "--phase Evolution` before every evolution round." not in evolution_loop_skill
    assert (
        "[--phase <Configuration|Generation|Evolution|Insights from Reviews|Proximity|Ranking|Research Overview>]"
        in strategy_router_skill
    )
    assert (
        "Omit `--phase` when refreshing routing from persisted `state/PIPELINE_STATE.json` or "
        "`state/CURRENT_STAGE.json`." in strategy_router_skill
    )


def test_migrated_canonical_skills_no_longer_have_prompt_directories() -> None:
    for skill_name in MIGRATED_SKILLS:
        prompts_dir = SKILLS_ROOT / skill_name / "prompts"
        assert not prompts_dir.exists(), f"{skill_name} should not keep a prompts/ directory after migration"


def test_migrated_skill_markdown_files_expose_required_execution_sections() -> None:
    for skill_name in MIGRATED_SKILLS:
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for heading in REQUIRED_SECTION_HEADINGS:
            assert heading in skill_md, f"{skill_name} is missing required section {heading!r}"


def test_migrated_skills_no_longer_use_prompt_assets_marker() -> None:
    for skill_name in MIGRATED_SKILLS:
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "Prompt assets:" not in skill_md


def test_core_schema_writing_skills_reference_exact_python_contracts() -> None:
    for skill_name, contract_paths in REQUIRED_SCHEMA_REFERENCES.items():
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "schema-index.md" in skill_md
        for contract_path in contract_paths:
            assert contract_path in skill_md


def test_deterministic_skills_expose_canonical_invocation_surfaces() -> None:
    for skill_name, required_references in DETERMINISTIC_SKILL_REFERENCES.items():
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for heading in DETERMINISTIC_REQUIRED_SECTION_HEADINGS:
            assert heading in skill_md, f"{skill_name} is missing required section {heading!r}"
        for reference in required_references:
            assert reference in skill_md, f"{skill_name} is missing deterministic reference {reference!r}"


def test_pipeline_skills_bind_load_bearing_mechanics_helpers() -> None:
    for skill_name, required_references in PIPELINE_MECHANICS_REFERENCES.items():
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for reference in required_references:
            assert reference in skill_md, f"{skill_name} is missing pipeline-mechanics reference {reference!r}"


def test_direct_entry_pipeline_skills_expose_structured_contract_sections() -> None:
    for skill_name in DIRECT_ENTRY_PIPELINE_REFERENCES:
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for heading in DIRECT_ENTRY_PIPELINE_REQUIRED_SECTION_HEADINGS:
            assert heading in skill_md, f"{skill_name} is missing direct-entry section {heading!r}"


def test_direct_entry_pipeline_skills_reference_exact_control_plane_contracts() -> None:
    for skill_name, required_references in DIRECT_ENTRY_PIPELINE_REFERENCES.items():
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for reference in required_references:
            assert reference in skill_md, f"{skill_name} is missing direct-entry reference {reference!r}"


def test_generation_pipeline_does_not_claim_routing_audit_artifact_ownership() -> None:
    skill_md = (SKILLS_ROOT / "hypothesis-generation-pipeline" / "SKILL.md").read_text(encoding="utf-8")

    assert "research_plan/RESEARCH_PLAN.json` is a required canonical input" in skill_md
    assert "If the research plan artifact is missing or invalid, stop immediately." in skill_md
    assert "packages/agent_contracts/strategy_plan.py" in skill_md
    assert "- updated `state/STRATEGY_DECISIONS.jsonl`" not in skill_md
    assert "Do not append or rewrite `state/STRATEGY_DECISIONS.jsonl` from this skill." in skill_md


def test_evolution_loop_requires_round_replay_receipts() -> None:
    skill_md = (SKILLS_ROOT / "hypothesis-evolution-loop" / "SKILL.md").read_text(encoding="utf-8")
    strategy_contract = (SKILLS_ROOT / "shared-references" / "strategy-contract.md").read_text(encoding="utf-8")
    schema_index = (SKILLS_ROOT / "shared-references" / "schema-index.md").read_text(encoding="utf-8")

    assert "state/EVOLUTION_ROUNDS.jsonl" in skill_md
    assert "from tools import append_evolution_round_record" in skill_md
    assert "tools.append_evolution_round_record(run_dir, record)" in skill_md
    assert "EvolutionRoundRecordContract" in skill_md
    assert "child hypothesis ID" in skill_md
    assert "chosen concrete evolution strategy" in skill_md
    assert "state/EVOLUTION_ROUNDS.jsonl" in strategy_contract
    assert "EvolutionRoundRecordContract" in schema_index


def test_literature_grounded_skills_require_search_bridge_tools() -> None:
    for skill_name in (
        "literature-search",
        "hypothesis-generate-literature",
        "hypothesis-full-review",
        "hypothesis-deep-verification",
    ):
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "tools.search_literature" in skill_md or "from tools import search_literature" in skill_md
        assert "EvidenceBundleContract" in skill_md
        assert "packages/agent_contracts/literature.py" in skill_md

    for skill_name in (
        "hypothesis-generate-literature",
        "hypothesis-full-review",
        "hypothesis-deep-verification",
    ):
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "Do not invent papers" in skill_md
        assert "model memory as a substitute" in skill_md
        assert "Search for or recall" not in skill_md


def test_remaining_active_skills_expose_structured_contract_sections() -> None:
    for skill_name in REMAINING_ACTIVE_SKILL_REFERENCES:
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for heading in REMAINING_ACTIVE_SKILL_REQUIRED_SECTION_HEADINGS:
            assert heading in skill_md, f"{skill_name} is missing remaining-active section {heading!r}"
        assert "Execution notes:" not in skill_md, f"{skill_name} should not retain legacy execution notes headings"


def test_remaining_active_skills_reference_canonical_surfaces() -> None:
    for skill_name, required_references in REMAINING_ACTIVE_SKILL_REFERENCES.items():
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for reference in required_references:
            assert reference in skill_md, f"{skill_name} is missing remaining-active reference {reference!r}"


def test_pipeline_and_substage_skills_require_explicit_active_stage_writeback() -> None:
    for skill_name, required_references in ACTIVE_SUBSTAGE_RUNTIME_REFERENCES.items():
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for reference in required_references:
            assert reference in skill_md, f"{skill_name} is missing active-stage runtime reference {reference!r}"


def test_active_stage_prompts_reference_the_canonical_stage_sync_helper() -> None:
    for skill_name in (
        "co-scientist-pipeline",
        "hypothesis-evolution-loop",
        "hypothesis-review-pipeline",
        "insights-from-reviews",
        "hypothesis-proximity-update",
        "hypothesis-ranking-pipeline",
        "research-overview-pipeline",
    ):
        skill_dir = SKILLS_ROOT / skill_name if skill_name != "co-scientist-pipeline" else SKILLS_ROOT / skill_name
        skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "from tools import sync_pipeline_stage_artifacts" in skill_md
        assert "packages/run_artifacts/stage_sync.py" in skill_md or "tools.sync_pipeline_stage_artifacts" in skill_md


def test_claude_entry_skills_expose_dashboard_follow_up_contracts() -> None:
    entry_root = SKILLS_ROOT / "skills-claude-entry"
    for skill_name, required_references in CLAUDE_ENTRY_DASHBOARD_REFERENCES.items():
        skill_md = (entry_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for reference in required_references:
            assert reference in skill_md, f"{skill_name} is missing Claude-entry dashboard reference {reference!r}"


def test_codex_entry_skills_expose_dashboard_follow_up_contracts() -> None:
    entry_root = SKILLS_ROOT / "skills-codex-entry"
    for skill_name, required_references in CODEX_ENTRY_DASHBOARD_REFERENCES.items():
        skill_md = (entry_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for reference in required_references:
            assert reference in skill_md, f"{skill_name} is missing Codex-entry dashboard reference {reference!r}"


def test_claude_entry_run_resume_skills_explain_configuration_stage() -> None:
    entry_root = SKILLS_ROOT / "skills-claude-entry"
    for skill_name in ("co-scientist-start", "co-scientist-run", "co-scientist-resume"):
        skill_md = (entry_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "run_configuration" in skill_md or "Configuration" in skill_md
        assert "research-config" in skill_md
        assert "research_plan/RESEARCH_PLAN.json" in skill_md


def test_codex_entry_run_resume_skills_explain_configuration_stage() -> None:
    entry_root = SKILLS_ROOT / "skills-codex-entry"
    for skill_name in ("co-scientist-start", "co-scientist-run", "co-scientist-resume"):
        skill_md = (entry_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "run_configuration" in skill_md or "Configuration" in skill_md
        assert "research-config" in skill_md
        assert "research_plan/RESEARCH_PLAN.json" in skill_md


def test_codex_start_run_skills_require_major_phase_validation() -> None:
    entry_root = SKILLS_ROOT / "skills-codex-entry"
    for skill_name in ("co-scientist-start", "co-scientist-run"):
        skill_md = (entry_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "After major phase writes" in skill_md
        assert "python -m tools.validation.contract_validation runs/<run_id> --skill co-scientist-pipeline" in skill_md


def test_co_scientist_doctor_prompt_explains_iteration_control_model() -> None:
    skill_md = (SKILLS_ROOT / "skills-claude-entry" / "co-scientist-doctor" / "SKILL.md").read_text(encoding="utf-8")

    assert (
        "how `budget`, `iteration-policy`, `iteration-band`, `stop-policy`, and "
        "`human-checkpoint` divide responsibility" in skill_md
    )
    assert (
        "budget` controls per-round intensity, while `iteration-policy` controls semantic vs capped stopping"
        in skill_md
    )
    assert "human-checkpoint" in skill_md
    assert "inspect_state" in skill_md


def test_completion_driven_prompt_surfaces_forbid_per_round_confirmation_in_auto_mode() -> None:
    for relative_path in (
        SKILLS_ROOT / "co-scientist-pipeline" / "SKILL.md",
        SKILLS_ROOT / "hypothesis-evolution-loop" / "SKILL.md",
        SKILLS_ROOT / "skills-claude-entry" / "co-scientist-start" / "SKILL.md",
        SKILLS_ROOT / "skills-claude-entry" / "co-scientist-run" / "SKILL.md",
        SKILLS_ROOT / "skills-claude-entry" / "co-scientist-resume" / "SKILL.md",
    ):
        skill_md = relative_path.read_text(encoding="utf-8")
        normalized = skill_md.lower()
        assert "completion_driven" in normalized
        assert "human_checkpoint" in normalized
        assert "do not ask" in normalized or "do not stop" in normalized
        assert "convergence has not been reached" in normalized
        assert "continue evolution" in normalized
        assert "will continue until convergence" not in normalized


def test_codex_entry_prompts_surface_paused_continue_handoff_semantics() -> None:
    for relative_path in (
        SKILLS_ROOT / "skills-codex-entry" / "co-scientist-start" / "SKILL.md",
        SKILLS_ROOT / "skills-codex-entry" / "co-scientist-run" / "SKILL.md",
        SKILLS_ROOT / "skills-codex-entry" / "co-scientist-resume" / "SKILL.md",
    ):
        skill_md = relative_path.read_text(encoding="utf-8")
        normalized = skill_md.lower()
        assert "completion_driven" in normalized
        assert "current convergence has not been reached" in normalized
        assert "continue evolution" in normalized
        assert "$co-scientist-resume" in skill_md
        assert "will continue until convergence" not in normalized


def test_resume_execution_boundaries_forbid_placeholder_artifacts() -> None:
    for relative_path in (
        SKILLS_ROOT / "co-scientist-pipeline" / "SKILL.md",
        SKILLS_ROOT / "hypothesis-evolution-loop" / "SKILL.md",
        SKILLS_ROOT / "skills-codex-entry" / "co-scientist-resume" / "SKILL.md",
        SKILLS_ROOT / "skills-claude-entry" / "co-scientist-resume" / "SKILL.md",
    ):
        skill_md = relative_path.read_text(encoding="utf-8")
        assert "Do not synthesize placeholder hypotheses" in skill_md
        assert "resumable blocked state" in skill_md
        assert "exactly one router decision" in skill_md
        assert "one evolved child" in skill_md
        assert "one proximity receipt" in skill_md


def test_evolve_prompts_forbid_generic_refinement_placeholders() -> None:
    for skill_name in (
        "hypothesis-evolve-grounding",
        "hypothesis-evolve-coherence",
        "hypothesis-evolve-feasibility",
        "hypothesis-evolve-simplification",
        "hypothesis-evolve-inspiration",
        "hypothesis-evolve-combination",
        "hypothesis-evolve-out-of-box",
    ):
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "Quality Floor:" in skill_md
        assert "parent review bundle" in skill_md
        assert "mechanistic variables" in skill_md
        assert "measurable readouts" in skill_md
        assert "Apply targeted improvement" in skill_md
        assert "stop and report the missing artifact" in skill_md


def test_review_prompts_forbid_empty_completed_review_artifacts() -> None:
    review_skill_names = (
        "hypothesis-review-pipeline",
        "hypothesis-initial-review",
        "hypothesis-full-review",
        "hypothesis-deep-verification",
        "hypothesis-observation-review",
        "hypothesis-simulation-review",
        "hypothesis-review-summary",
    )
    for skill_name in review_skill_names:
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "placeholder" in skill_md
        assert "substantive" in skill_md
    for skill_name in review_skill_names[1:]:
        skill_md = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "Review Quality Floor:" in skill_md
    review_pipeline = (SKILLS_ROOT / "hypothesis-review-pipeline" / "SKILL.md").read_text(encoding="utf-8")
    assert "must not accept empty completed review artifacts" in review_pipeline


def test_review_prompt_contracts_lock_scalar_list_fields() -> None:
    simulation_skill = (SKILLS_ROOT / "hypothesis-simulation-review" / "SKILL.md").read_text(encoding="utf-8")
    review_summary_skill = (SKILLS_ROOT / "hypothesis-review-summary" / "SKILL.md").read_text(encoding="utf-8")

    assert "Each item in `steps` must be a plain string" in simulation_skill
    assert "Each item in `failure_scenarios` must be a plain string" in simulation_skill
    assert "Each item in `summaries` must be a plain string" in review_summary_skill


def test_proximity_prompt_contracts_require_bridge_call_and_receipt_gated_fallback() -> None:
    proximity_skill = (SKILLS_ROOT / "hypothesis-proximity-update" / "SKILL.md").read_text(encoding="utf-8")
    generation_skill = (SKILLS_ROOT / "hypothesis-generation-pipeline" / "SKILL.md").read_text(encoding="utf-8")
    evolution_skill = (SKILLS_ROOT / "hypothesis-evolution-loop" / "SKILL.md").read_text(encoding="utf-8")
    ranking_skill = (SKILLS_ROOT / "hypothesis-ranking-pipeline" / "SKILL.md").read_text(encoding="utf-8")

    assert "tools.update_hypothesis_proximity(run_dir, hypothesis_id)" in proximity_skill
    assert "This skill must not hand-write embeddings" in proximity_skill
    assert "Do not skip this skill merely because no embedding vector is already present" in proximity_skill
    assert "receipt status is `updated`" not in proximity_skill
    assert "after an `updated` receipt" not in proximity_skill
    assert "receipt status is `succeeded`" in proximity_skill
    assert "`skipped_disabled`" in proximity_skill
    assert "`skipped_provider_unavailable`" in proximity_skill
    assert "`failed_provider_error`" in proximity_skill
    assert "`failed_invalid_embedding`" in proximity_skill
    assert "embedding config hash" in proximity_skill
    assert "graph_updated=false" in proximity_skill
    assert "hypothesis-proximity-update` for each viable hypothesis" in generation_skill
    assert "receipt-gated fallback path only after `hypothesis-proximity-update` has recorded" in generation_skill
    assert "non-updated receipt/status" not in generation_skill
    assert "hypothesis-proximity-update` for each viable child hypothesis" in evolution_skill
    assert (
        "receipt-gated missing-graph fallback only after `hypothesis-proximity-update` has recorded" in evolution_skill
    )
    assert "non-updated receipt/status" not in evolution_skill
    assert "return to `hypothesis-proximity-update` instead of choosing opponents manually" in ranking_skill


def test_hypothesis_emission_prompt_contracts_lock_multiline_string_experimental_design() -> None:
    for relative_path in (
        SKILLS_ROOT / "hypothesis-generate-literature" / "SKILL.md",
        SKILLS_ROOT / "hypothesis-generate-debate" / "SKILL.md",
        SKILLS_ROOT / "hypothesis-generate-assumptions" / "SKILL.md",
        SKILLS_ROOT / "hypothesis-evolve-grounding" / "SKILL.md",
    ):
        skill_md = relative_path.read_text(encoding="utf-8")
        assert "must remain one string field containing embedded line breaks" in skill_md
        assert "do not emit it as a list, array, or nested object" in skill_md


def test_review_pipeline_prompt_treats_sync_and_validation_as_hard_gates() -> None:
    skill_md = (SKILLS_ROOT / "hypothesis-review-pipeline" / "SKILL.md").read_text(encoding="utf-8")

    assert "Treat `tools.sync_hypothesis_review(run_dir, hypothesis_id)` as a hard gate." in skill_md
    assert "If it fails, stop the review sequence immediately" in skill_md
    assert "If validation fails, stop and repair the review bundle" in skill_md
    assert "python -m tools.validation.contract_validation <run_dir> --skill hypothesis-review-pipeline" in skill_md
