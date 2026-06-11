from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_REFERENCES_ROOT = REPO_ROOT / "skills" / "shared-references"


def test_mechanics_integration_contract_covers_load_bearing_helper_surfaces() -> None:
    mechanics_contract = (SHARED_REFERENCES_ROOT / "mechanics-integration-contract.md").read_text(encoding="utf-8")

    required_references = (
        "python -m tools.policy.plan_strategy <run_dir> [--phase <...>]",
        "from tools import select_island_hypotheses",
        "from tools import ensure_run_islands_for_hypotheses",
        "from tools import update_run_single_island_reward",
        "from tools import update_single_island_reward",
        "from tools import compute_single_island_reward",
        "from tools import apply_decayed_island_update",
        "packages/run_artifacts/island_state.py",
        "from tools import update_hypothesis_proximity",
        "from tools import update_proximity_graph",
        "from tools import get_top_k_hypotheses",
        "from tools import select_placement_opponents",
        "from tools import select_fallback_placement_opponents",
        "from tools import should_run_ranked_tournament",
        "from tools import select_ranked_opponents",
        "from tools import apply_and_persist_elo_updates",
        "packages/run_artifacts/ranking_writeback.py",
        "from tools import evaluate_convergence",
        "Policy A: Hard Requirement",
        "Policy B: Artifact-Missing Fallback",
        "Policy C: No Manual Reimplementation",
    )

    for reference in required_references:
        assert reference in mechanics_contract

    assert "host agents must call `tools.update_hypothesis_proximity(run_dir, hypothesis_id)`" in mechanics_contract
    assert "newly created islands must be unvisited" in mechanics_contract
    assert "`hypothesis_ids`, `ucb_score`, or `strategy_label`" in mechanics_contract
    assert "load-bearing single-island round closeout write" in mechanics_contract
    assert "nonzero `visit_count` and nonzero `decayed_visits`" in mechanics_contract
    assert "number of completed single-island round receipts" in mechanics_contract
    assert "do not write `state/ISLANDS.json`" in mechanics_contract
    assert "lower-level surfaces are not the host-agent persistence path" in mechanics_contract
    assert "do not fabricate placeholder embeddings" in mechanics_contract
    assert "proximity graph updates may be skipped only by the canonical embedding bridge" in mechanics_contract


def test_shared_reference_indexes_point_to_mechanics_contract() -> None:
    mechanics_reference = "skills/shared-references/mechanics-integration-contract.md"
    code_structure_contract = (SHARED_REFERENCES_ROOT / "code-structure-contract.md").read_text(encoding="utf-8")
    integration_contract = (SHARED_REFERENCES_ROOT / "integration-contract.md").read_text(encoding="utf-8")

    assert mechanics_reference in code_structure_contract
    assert mechanics_reference in integration_contract
