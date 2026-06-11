"""Root-level helper modules for the skill-first Co-Scientist pipeline.

This package intentionally keeps imports light so host-agent mode can load
contract and validation helpers without pulling in extra runtime layers.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
for candidate in (_REPO_ROOT,):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.append(candidate_str)


_LAZY_EXPORTS = {
    "ArtifactStore": ("packages.run_artifacts", "ArtifactStore"),
    "ConvergenceCheckResult": ("packages.agent_mechanics.convergence_check", "ConvergenceCheckResult"),
    "DashboardSupervisor": ("tools.dashboard.serve", "DashboardSupervisor"),
    "ExecutionModeContract": ("tools.host.host_agent", "ExecutionModeContract"),
    "HostAgentHandoff": ("tools.host.host_agent", "HostAgentHandoff"),
    "HostAgentBootstrapResult": ("tools.host.host_agent_surface", "HostAgentBootstrapResult"),
    "HostAgentValidationSummary": ("tools.validation.contract_validation", "HostAgentValidationSummary"),
    "RunIslandInitializationResult": ("packages.run_artifacts", "RunIslandInitializationResult"),
    "RunIslandRewardUpdateResult": ("packages.run_artifacts", "RunIslandRewardUpdateResult"),
    "SelectionResult": ("packages.agent_mechanics.island_select", "SelectionResult"),
    "apply_decayed_island_update": ("packages.agent_mechanics.island_reward_update", "apply_decayed_island_update"),
    "apply_and_persist_elo_updates": ("packages.run_artifacts", "apply_and_persist_elo_updates"),
    "apply_elo_updates": ("packages.agent_mechanics.elo_update", "apply_elo_updates"),
    "append_evolution_round_record": ("packages.run_artifacts", "append_evolution_round_record"),
    "build_evidence_bundle": ("tools.literature_search_client", "build_evidence_bundle"),
    "build_dashboard_snapshot": ("packages.dashboard_contracts", "build_dashboard_snapshot"),
    "build_empty_dashboard_snapshot": ("packages.dashboard_contracts", "build_empty_dashboard_snapshot"),
    "compute_cosine_similarities": ("packages.agent_mechanics.proximity_update", "compute_cosine_similarities"),
    "compute_elo_delta": ("packages.agent_mechanics.elo_update", "compute_elo_delta"),
    "compute_single_island_reward": ("packages.agent_mechanics.island_reward_update", "compute_single_island_reward"),
    "ensure_run_islands_for_hypotheses": ("packages.run_artifacts", "ensure_run_islands_for_hypotheses"),
    "evaluate_convergence": ("packages.agent_mechanics.convergence_check", "evaluate_convergence"),
    "generate_hypothesis_embedding": (
        "packages.agent_mechanics.hypothesis_embedding",
        "generate_hypothesis_embedding",
    ),
    "get_execution_modes": ("tools.host.host_agent", "get_execution_modes"),
    "get_top_k_hypotheses": ("packages.agent_mechanics.top_k_select", "get_top_k_hypotheses"),
    "load_evidence_bundle": ("tools.literature_search_client", "load_evidence_bundle"),
    "load_evolution_round_records": ("packages.run_artifacts", "load_evolution_round_records"),
    "load_run_hypotheses": ("packages.run_artifacts", "load_run_hypotheses"),
    "load_run_islands": ("packages.run_artifacts", "load_run_islands"),
    "prepare_host_agent_handoff": ("tools.host.host_agent", "prepare_host_agent_handoff"),
    "persist_run_islands": ("packages.run_artifacts", "persist_run_islands"),
    "persist_hypotheses": ("packages.run_artifacts", "persist_hypotheses"),
    "retrieval_results_from_evidence_bundle": (
        "packages.agent_mechanics.literature_mapping",
        "retrieval_results_from_evidence_bundle",
    ),
    "bootstrap_host_agent_run": ("tools.host.host_agent_surface", "bootstrap_host_agent_run"),
    "sample_hypothesis": ("packages.agent_mechanics.island_select", "sample_hypothesis"),
    "search_literature": ("tools.literature_search_client", "search_literature"),
    "select_island_hypotheses": ("packages.agent_mechanics.island_select", "select_island_hypotheses"),
    "select_island_ucb": ("packages.agent_mechanics.island_select", "select_island_ucb"),
    "select_fallback_placement_opponents": (
        "packages.agent_mechanics.top_k_select",
        "select_fallback_placement_opponents",
    ),
    "select_placement_opponents": ("packages.agent_mechanics.top_k_select", "select_placement_opponents"),
    "select_ranked_opponents": ("packages.agent_mechanics.top_k_select", "select_ranked_opponents"),
    "should_run_ranked_tournament": ("packages.agent_mechanics.top_k_select", "should_run_ranked_tournament"),
    "sync_hypothesis_review": ("packages.run_artifacts", "sync_hypothesis_review"),
    "sync_pipeline_stage_artifacts": ("packages.run_artifacts", "sync_pipeline_stage_artifacts"),
    "update_hypothesis_proximity": ("packages.agent_mechanics.hypothesis_embedding", "update_hypothesis_proximity"),
    "update_proximity_graph": ("packages.agent_mechanics.proximity_update", "update_proximity_graph"),
    "update_run_single_island_reward": ("packages.run_artifacts", "update_run_single_island_reward"),
    "update_single_island_reward": ("packages.agent_mechanics.island_reward_update", "update_single_island_reward"),
    "validate_resume_state": ("tools.validation.contract_validation", "validate_resume_state"),
    "validate_run_artifacts": ("tools.validation.contract_validation", "validate_run_artifacts"),
    "verify_literature_candidates": ("tools.literature_search_client", "verify_literature_candidates"),
    "write_host_agent_handoff": ("tools.host.host_agent", "write_host_agent_handoff"),
    "ensure_dashboard_for_run": ("tools.host.host_agent_surface", "ensure_dashboard_for_run"),
    "ensure_dashboard_links_for_run": ("tools.host.host_agent_surface", "ensure_dashboard_links_for_run"),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str):
    """Lazily import selected helper symbols on first access."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = importlib.import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy helper names to host-agent introspection such as `dir(tools)`."""
    return sorted(set(globals()) | set(__all__))
