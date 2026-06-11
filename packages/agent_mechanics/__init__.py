"""Host-neutral deterministic mechanics shared across host-agent tools and validators."""

from .convergence_check import ConvergenceCheckResult, did_enter_top_k, evaluate_convergence, update_convergence_count
from .elo_update import apply_elo_updates, compute_elo_delta
from .hypothesis_embedding import (
    generate_hypothesis_embedding,
    input_text_hash,
    resolve_embedding_provider_config,
    update_hypothesis_proximity,
)
from .hypothesis_embedding_text import format_hypothesis_for_embedding
from .island_reward_update import (
    apply_decayed_island_update,
    compute_single_island_reward,
    update_single_island_reward,
)
from .island_select import SelectionResult, sample_hypothesis, select_island_hypotheses, select_island_ucb
from .literature_bundle import build_evidence_bundle, dedupe_candidates, rank_candidates
from .literature_mapping import (
    evidence_bundle_ids,
    literature_query_ids,
    retrieval_results_from_evidence_bundle,
)
from .literature_search import resolve_provider_sequence, run_literature_search
from .literature_verification import (
    title_overlap,
    verify_evidence_bundle,
    verify_paper_candidate,
    verify_paper_candidates,
)
from .proximity_update import compute_cosine_similarities, update_proximity_graph
from .top_k_select import (
    get_top_k_hypotheses,
    select_fallback_placement_opponents,
    select_placement_opponents,
    select_ranked_opponents,
    should_run_ranked_tournament,
)


__all__ = [
    "ConvergenceCheckResult",
    "SelectionResult",
    "apply_decayed_island_update",
    "apply_elo_updates",
    "build_evidence_bundle",
    "compute_cosine_similarities",
    "compute_elo_delta",
    "compute_single_island_reward",
    "dedupe_candidates",
    "did_enter_top_k",
    "evaluate_convergence",
    "evidence_bundle_ids",
    "format_hypothesis_for_embedding",
    "generate_hypothesis_embedding",
    "get_top_k_hypotheses",
    "input_text_hash",
    "literature_query_ids",
    "rank_candidates",
    "resolve_embedding_provider_config",
    "resolve_provider_sequence",
    "retrieval_results_from_evidence_bundle",
    "run_literature_search",
    "sample_hypothesis",
    "select_fallback_placement_opponents",
    "select_island_hypotheses",
    "select_island_ucb",
    "select_placement_opponents",
    "select_ranked_opponents",
    "should_run_ranked_tournament",
    "title_overlap",
    "update_convergence_count",
    "update_hypothesis_proximity",
    "update_proximity_graph",
    "update_single_island_reward",
    "verify_evidence_bundle",
    "verify_paper_candidate",
    "verify_paper_candidates",
]
