from __future__ import annotations

import tools


def test_tools_dir_lists_lazy_helper_exports() -> None:
    exported_names = dir(tools)

    assert "update_proximity_graph" in exported_names
    assert "sync_pipeline_stage_artifacts" in exported_names
    assert "generate_hypothesis_embedding" in exported_names
    assert "update_hypothesis_proximity" in exported_names
    assert "search_literature" in exported_names
    assert "verify_literature_candidates" in exported_names
    assert "build_evidence_bundle" in exported_names
    assert "load_evidence_bundle" in exported_names
    assert "retrieval_results_from_evidence_bundle" in exported_names
    assert "append_evolution_round_record" in exported_names
    assert "load_evolution_round_records" in exported_names
    assert "select_fallback_placement_opponents" in exported_names
    assert "update_run_single_island_reward" in exported_names


def test_tools_lazy_exports_remain_importable_from_the_stable_surface() -> None:
    from tools import (
        append_evolution_round_record,
        build_evidence_bundle,
        generate_hypothesis_embedding,
        load_evidence_bundle,
        load_evolution_round_records,
        retrieval_results_from_evidence_bundle,
        search_literature,
        select_fallback_placement_opponents,
        sync_pipeline_stage_artifacts,
        update_hypothesis_proximity,
        update_proximity_graph,
        update_run_single_island_reward,
        verify_literature_candidates,
    )

    assert callable(append_evolution_round_record)
    assert callable(build_evidence_bundle)
    assert callable(generate_hypothesis_embedding)
    assert callable(load_evidence_bundle)
    assert callable(load_evolution_round_records)
    assert callable(retrieval_results_from_evidence_bundle)
    assert callable(search_literature)
    assert callable(select_fallback_placement_opponents)
    assert callable(sync_pipeline_stage_artifacts)
    assert callable(update_hypothesis_proximity)
    assert callable(update_proximity_graph)
    assert callable(update_run_single_island_reward)
    assert callable(verify_literature_candidates)
