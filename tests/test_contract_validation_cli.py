from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    CoScientistStateContract,
    DeepVerificationReviewContract,
    EmbeddingProviderConfigContract,
    EvidenceBundleContract,
    EvolutionRoundRecordContract,
    FullReviewContract,
    HypothesisMatchupContract,
    InitialReviewContract,
    IslandStateContract,
    ObservationReviewContract,
    PaperCandidateContract,
    ResearchOverviewContract,
    ResearchPlanContract,
    ResolvedRunConfigContract,
    ReviewContract,
    ReviewSummaryContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
    SimulationReviewContract,
    TournamentMatchContract,
)
from packages.agent_mechanics import (
    evidence_bundle_ids,
    literature_query_ids,
    retrieval_results_from_evidence_bundle,
    update_hypothesis_proximity,
)
from packages.agent_mechanics.literature_providers.common import ProviderSearchResult
from packages.run_artifacts import ArtifactStore, apply_and_persist_elo_updates
from tests.conftest import build_hypothesis
from tools.literature_search_client import search_literature


def _write_config(run_dir: Path) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Validator CLI Run\n\nInvestigate response drift.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "input_file: input.md",
                "",
                "persistence:",
                '  db_url: "sqlite+aiosqlite:///co_scientist.db"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _fake_literature_provider(request: SearchRequestContract) -> ProviderSearchResult:
    return ProviderSearchResult(
        candidates=[
            PaperCandidateContract(
                paper_id="doi:10.1000/example",
                title="Search bridge evidence",
                doi="10.1000/example",
                provider_sources=["openalex"],
            )
        ],
        receipt=SearchProviderReceiptContract(
            provider="openalex",
            status="succeeded",
            result_count=1,
        ),
    )


def _build_literature_linked_hypothesis(bundle: EvidenceBundleContract):
    retrieval_results = retrieval_results_from_evidence_bundle(bundle)
    hypothesis = build_hypothesis(
        "hyp-001",
        1250.0,
        "island-001",
        passed=False,
        strategy="literature_exploration_generation",
    )
    linked_origin = hypothesis.origin.model_copy(
        update={
            "retrieval_results": retrieval_results,
            "evidence_bundle_ids": evidence_bundle_ids(bundle),
            "literature_query_ids": literature_query_ids(bundle),
        }
    )
    linked_full_review = hypothesis.review.full_review.model_copy(
        update={
            "retrieval_results": retrieval_results,
            "evidence_bundle_ids": evidence_bundle_ids(bundle),
            "literature_query_ids": literature_query_ids(bundle),
        }
    )
    linked_review = hypothesis.review.model_copy(update={"full_review": linked_full_review})
    return hypothesis.model_copy(update={"origin": linked_origin, "review": linked_review})


def _continue_evolution_router_signals(
    *,
    selected_parent_ids: list[str],
    selected_island_ids: list[str],
    selection_strategy: str = "single_island",
    hypothesis_count: int = 2,
    viable_hypothesis_count: int = 2,
    convergence_count: int = 1,
    convergence_threshold: int = 3,
    entered_top_k_last_round: bool | None = True,
    top_hypothesis_ids: list[str] | None = None,
    research_plan_status: str = "valid",
) -> dict[str, object]:
    return {
        "hypothesis_count": hypothesis_count,
        "viable_hypothesis_count": viable_hypothesis_count,
        "convergence_count": convergence_count,
        "convergence_threshold": convergence_threshold,
        "entered_top_k_last_round": entered_top_k_last_round,
        "top_hypothesis_ids": top_hypothesis_ids or selected_parent_ids,
        "research_plan_status": research_plan_status,
        "selection_strategy": selection_strategy,
        "selected_parent_ids": selected_parent_ids,
        "selected_island_ids": selected_island_ids,
    }


def _write_strategy_decision_records_for_evolution_round(run_dir: Path) -> None:
    (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "decision_index": 1,
                "current_phase": "Generation",
                "next_action": "run_generation",
                "selected_generation_strategies": ["literature_exploration_generation"],
                "selected_evolution_strategies": [],
                "max_new_hypotheses": 1,
                "reasoning": ["Seed the initial frontier."],
                "advisory_recommendation": "inspect_state",
                "signals": {},
                "status": "planned",
            }
        )
        + "\n"
        + json.dumps(
            {
                "run_id": run_dir.name,
                "decision_index": 2,
                "current_phase": "Evolution",
                "next_action": "continue_evolution",
                "selected_generation_strategies": [],
                "selected_evolution_strategies": ["grounding_evolution", "coherence_evolution"],
                "max_new_hypotheses": 0,
                "reasoning": ["Continue evolving."],
                "advisory_recommendation": "continue_evolution",
                "signals": _continue_evolution_router_signals(
                    selected_parent_ids=["hyp-001"],
                    selected_island_ids=["island-001"],
                    hypothesis_count=1,
                    viable_hypothesis_count=1,
                    entered_top_k_last_round=None,
                ),
                "status": "planned",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _append_continue_evolution_decision(
    run_dir: Path,
    *,
    decision_index: int,
    selected_parent_ids: list[str] | None = None,
    selected_island_ids: list[str] | None = None,
    hypothesis_count: int = 2,
    viable_hypothesis_count: int = 2,
    convergence_count: int = 0,
    entered_top_k_last_round: bool | None = True,
    top_hypothesis_ids: list[str] | None = None,
) -> None:
    decision = {
        "run_id": run_dir.name,
        "decision_index": decision_index,
        "current_phase": "Evolution",
        "next_action": "continue_evolution",
        "selected_generation_strategies": [],
        "selected_evolution_strategies": ["grounding_evolution", "coherence_evolution"],
        "max_new_hypotheses": 0,
        "reasoning": ["Continue evolving."],
        "advisory_recommendation": "continue_evolution",
        "signals": _continue_evolution_router_signals(
            selected_parent_ids=selected_parent_ids or ["hyp-001"],
            selected_island_ids=selected_island_ids or ["island-001"],
            hypothesis_count=hypothesis_count,
            viable_hypothesis_count=viable_hypothesis_count,
            convergence_count=convergence_count,
            entered_top_k_last_round=entered_top_k_last_round,
            top_hypothesis_ids=top_hypothesis_ids or ["hyp-001", "hyp-002"],
        ),
        "status": "planned",
    }
    with (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision) + "\n")


def _prepare_evolution_round_run(
    run_dir: Path,
    *,
    append_round_record: bool,
    round_record_updates: dict[str, object] | None = None,
    include_ranking_artifacts: bool = True,
) -> None:
    _write_config(run_dir)
    store = ArtifactStore(run_dir, top_k_limit=3)
    store.bootstrap()
    parent = build_hypothesis("hyp-001", 1200.0, "island-001")
    child = build_hypothesis(
        "hyp-002",
        1200.0,
        "island-001",
        parent_ids=["hyp-001"],
        strategy="grounding_evolution",
    )
    tournament_matches: dict[str, TournamentMatchContract] = {}
    if include_ranking_artifacts:
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=child.id,
            hypothesis_2_id=parent.id,
            match_strategy="placement_tournament",
            reasoning="The evolved child is more specific and testable than its parent.",
            winner_id=child.id,
        )
        apply_and_persist_elo_updates(
            run_dir,
            [match],
            [HypothesisMatchupContract(hypothesis_1=child, hypothesis_2=parent)],
            "placement_tournament",
            top_k_limit=3,
        )
        tournament_matches[match.id] = match
    state = CoScientistStateContract(
        research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
        hypotheses={parent.id: parent, child.id: child},
        tournament_matches=tournament_matches,
        islands={
            "island-001": IslandStateContract(id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5)
        },
        iteration_count=1,
        convergence_count=0,
    )
    store.write_research_plan(state.research_plan)
    store.write_hypothesis(parent)
    store.write_hypothesis(child)
    if include_ranking_artifacts:
        update_hypothesis_proximity(
            run_dir,
            child.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
    store.write_islands(state)
    store.write_pipeline_state(
        state,
        mode="host-agent",
        status="running",
        current_phase="Evolution",
        current_skill="hypothesis-evolution-loop",
        stage_trail=["Generation", "Evolution"],
    )
    store.write_evolution_state(
        state,
        convergence_threshold=3,
        max_iterations=6,
        safety_max_iterations=12,
        effective_top_k=2,
        status="running",
        entered_top_k_last_round=True,
        last_selected_strategy="grounding_evolution",
        last_selected_island="island-001",
    )
    _write_strategy_decision_records_for_evolution_round(run_dir)
    if append_round_record:
        record_payload = {
            "run_id": run_dir.name,
            "round_index": 1,
            "decision_index": 2,
            "selection_strategy": "single_island",
            "selected_island_ids": ["island-001"],
            "parent_hypothesis_ids": ["hyp-001"],
            "chosen_evolution_strategy": "grounding_evolution",
            "child_hypothesis_id": "hyp-002",
            "child_island_id": "island-001",
            "review_passed": True,
            "placement_match_ids": ["match-001"] if include_ranking_artifacts else [],
            "previous_top_k_ids": ["hyp-001"],
            "current_top_k_ids": ["hyp-001", "hyp-002"],
            "entered_top_k": True,
            "convergence_count_before": 1,
            "convergence_count_after": 0,
        }
        record_payload.update(round_record_updates or {})
        store.append_evolution_round_record(EvolutionRoundRecordContract.from_payload(record_payload))


def _prepare_safety_stopped_overview_run(run_dir: Path) -> ArtifactStore:
    _write_config(run_dir)
    store = ArtifactStore(run_dir, top_k_limit=3)
    store.bootstrap()
    store.write_resolved_run_config(
        ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
    )
    hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
    state = CoScientistStateContract(
        research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
        hypotheses={hypothesis.id: hypothesis},
        islands={
            "island-001": IslandStateContract(id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5)
        },
        iteration_count=30,
        convergence_count=1,
    )
    store.write_research_plan(state.research_plan)
    store.write_hypothesis(hypothesis)
    store.write_islands(state)
    store.write_pipeline_state(
        state,
        mode="host-agent",
        status="running",
        current_phase="Research Overview",
        current_skill="research-overview-pipeline",
        stage_trail=["Generation", "Evolution", "Research Overview"],
    )
    store.write_evolution_state(
        state,
        convergence_threshold=3,
        max_iterations=0,
        safety_max_iterations=30,
        effective_top_k=1,
        status="completed",
        entered_top_k_last_round=False,
        stop_policy="standard",
        iteration_policy="completion_driven",
        safety_limit_hit=True,
        stop_reason="safety_iteration_limit_reached",
        overview_eligible=True,
    )
    return store


def _run_contract_validation(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.validation.contract_validation",
            str(run_dir),
            "--skill",
            "co-scientist-pipeline",
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def test_contract_validation_cli_succeeds_for_fresh_run_and_writes_json() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        json_out = run_dir / "validation" / "summary.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
                "--json-out",
                str(json_out),
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"
        assert payload["requestedSkill"] == "co-scientist-pipeline"
        assert json_out.exists()
        written = json.loads(json_out.read_text(encoding="utf-8"))
        assert written["status"] == "valid"


def test_contract_validation_cli_accepts_valid_literature_bridge_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        search_literature(
            run_dir,
            {"query_id": "q-001", "query": "ammonia catalyst", "providers": ["openalex"]},
            provider_searchers={"openalex": _fake_literature_provider},
            verify=False,
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"


def test_contract_validation_cli_accepts_literature_linked_retrieval_results() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        bundle = search_literature(
            run_dir,
            {"query_id": "q-001", "query": "ammonia catalyst", "providers": ["openalex"]},
            provider_searchers={"openalex": _fake_literature_provider},
            verify=False,
        )
        hypothesis = _build_literature_linked_hypothesis(bundle)
        ArtifactStore(run_dir).write_hypothesis(hypothesis)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"


def test_contract_validation_cli_fails_when_literature_generation_omits_bridge_linkage() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        ArtifactStore(run_dir).write_hypothesis(
            build_hypothesis(
                "hyp-001",
                1250.0,
                "island-001",
                passed=False,
                strategy="literature_exploration_generation",
            )
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-generate-literature",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("origin.evidence_bundle_ids" in issue["message"] for issue in payload["issues"])
        assert any("origin.literature_query_ids" in issue["message"] for issue in payload["issues"])
        assert any("origin.retrieval_results" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_literature_generation_refs_unknown_bridge_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        bundle = EvidenceBundleContract(
            bundle_id="bundle-q-missing",
            query_id="q-missing",
            request=SearchRequestContract(query_id="q-missing", query="missing evidence"),
            papers=[],
            provider_receipts=[],
        )
        retrieval_results = retrieval_results_from_evidence_bundle(bundle)
        hypothesis = build_hypothesis(
            "hyp-001",
            1250.0,
            "island-001",
            passed=False,
            strategy="literature_exploration_generation",
        )
        origin = hypothesis.origin.model_copy(
            update={
                "retrieval_results": retrieval_results,
                "evidence_bundle_ids": ["bundle-q-missing"],
                "literature_query_ids": ["q-missing"],
            }
        )
        ArtifactStore(run_dir).write_hypothesis(hypothesis.model_copy(update={"origin": origin}))

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-generate-literature",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("unknown evidence bundle IDs" in issue["message"] for issue in payload["issues"])
        assert any("unknown literature query IDs" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_retrieval_results_lack_literature_linkage() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        bundle = search_literature(
            run_dir,
            {"query_id": "q-001", "query": "ammonia catalyst", "providers": ["openalex"]},
            provider_searchers={"openalex": _fake_literature_provider},
            verify=False,
        )
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001", passed=False)
        origin = hypothesis.origin.model_copy(
            update={"retrieval_results": retrieval_results_from_evidence_bundle(bundle)}
        )
        ArtifactStore(run_dir).write_hypothesis(hypothesis.model_copy(update={"origin": origin}))

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("no `evidence_bundle_ids` linkage" in issue["message"] for issue in payload["issues"])
        assert any("no `literature_query_ids` linkage" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_literature_finding_refs_unknown_paper() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        search_literature(
            run_dir,
            {"query_id": "q-001", "query": "ammonia catalyst", "providers": ["openalex"]},
            provider_searchers={"openalex": _fake_literature_provider},
            verify=False,
        )
        bundle_paths = [
            run_dir / "literature" / "queries" / "q-001" / "EVIDENCE_BUNDLE.json",
            run_dir / "literature" / "bundles" / "bundle-q-001.json",
        ]
        for bundle_path in bundle_paths:
            bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle_payload["synthesized_findings"] = [
                {
                    "finding_id": "finding-001",
                    "type": "support",
                    "statement": "This unsupported finding references a missing paper.",
                    "paper_refs": ["missing-paper"],
                    "confidence": "low",
                }
            ]
            bundle_path.write_text(json.dumps(bundle_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("references unknown paper IDs" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_resume_fails_when_resume_artifacts_are_missing() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        result = subprocess.run(
            [
                sys.executable,
                "tools/validation/contract_validation.py",
                str(run_dir),
                "--resume",
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert payload["resumeReady"] is False
        assert any("PIPELINE_STATE.json" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_strategy_audit_cannot_replay_evolution() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        parent = build_hypothesis("hyp-001", 1250.0, "island-001")
        child = build_hypothesis("hyp-002", 1310.0, "island-001", parent_ids=["hyp-001"])
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={parent.id: parent, child.id: child},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(parent)
        store.write_hypothesis(child)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").write_text(
            json.dumps(
                {
                    "run_id": run_dir.name,
                    "decision_index": 1,
                    "current_phase": "Generation",
                    "next_action": "run_generation",
                    "selected_generation_strategies": ["literature_exploration_generation"],
                    "selected_evolution_strategies": [],
                    "max_new_hypotheses": 1,
                    "reasoning": ["Seed the initial frontier."],
                    "advisory_recommendation": "inspect_state",
                    "signals": {},
                    "status": "planned",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("strategy decision audit log is shorter" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_warns_when_evolution_round_receipts_are_missing_for_legacy_run() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=False)

        result = _run_contract_validation(run_dir)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"
        assert any("EVOLUTION_ROUNDS.jsonl is missing" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_accepts_matching_evolution_round_receipts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        result = _run_contract_validation(run_dir)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"
        assert any(path.endswith("EVOLUTION_ROUNDS.jsonl") for path in payload["checkedArtifacts"])


def test_contract_validation_cli_fails_when_evolution_state_is_stale_after_latest_round() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["enteredTopKLastRound"] = False
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "EVOLUTION_STATE.json `enteredTopKLastRound` must match" in issue["message"] for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_strategy_plan_signals_are_stale_after_latest_round() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        (run_dir / "state" / "STRATEGY_PLAN.json").write_text(
            json.dumps(
                {
                    "status": "planned",
                    "current_phase": "Evolution",
                    "next_action": "continue_evolution",
                    "selected_generation_strategies": [],
                    "selected_evolution_strategies": ["grounding_evolution"],
                    "max_new_hypotheses": 0,
                    "reasoning": ["Continue from stale pre-round signals."],
                    "advisory_recommendation": "continue_evolution",
                    "signals": {"hypothesis_count": 1},
                    "updated_at": "2026-06-01T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "STRATEGY_PLAN.json `signals.hypothesis_count` is stale" in issue["message"] for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_round_records_proximity_status_without_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(
            run_dir,
            append_round_record=True,
            include_ranking_artifacts=False,
            round_record_updates={
                "proximity_receipt_status": "skipped_disabled",
                "current_top_k_ids": ["hyp-001"],
                "entered_top_k": False,
                "convergence_count_after": 2,
            },
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "matching per-child proximity receipt artifact is missing" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_evolution_round_reuses_strategy_decision_index() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        _append_continue_evolution_decision(run_dir, decision_index=3)

        store = ArtifactStore(run_dir, top_k_limit=3)
        second_child = build_hypothesis(
            "hyp-003",
            1295.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="grounding_evolution",
        )
        store.write_hypothesis(second_child)
        store.append_evolution_round_record(
            EvolutionRoundRecordContract.from_payload(
                {
                    "run_id": run_dir.name,
                    "round_index": 2,
                    "decision_index": 2,
                    "selection_strategy": "single_island",
                    "selected_island_ids": ["island-001"],
                    "parent_hypothesis_ids": ["hyp-001"],
                    "chosen_evolution_strategy": "grounding_evolution",
                    "child_hypothesis_id": "hyp-003",
                    "child_island_id": "island-001",
                    "review_passed": True,
                    "previous_top_k_ids": ["hyp-001", "hyp-002"],
                    "current_top_k_ids": ["hyp-001", "hyp-002", "hyp-003"],
                    "entered_top_k": True,
                    "convergence_count_before": 0,
                    "convergence_count_after": 0,
                }
            )
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("reuses strategy decision index" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_equivalent_continue_evolution_decisions_remain_open() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=False)
        _append_continue_evolution_decision(
            run_dir,
            decision_index=3,
            hypothesis_count=1,
            viable_hypothesis_count=1,
            convergence_count=1,
            entered_top_k_last_round=None,
            top_hypothesis_ids=["hyp-001"],
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "equivalent open continue_evolution strategy decisions" in issue["message"] for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_same_pre_round_continue_evolution_decisions_remain_open() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=False)
        _append_continue_evolution_decision(
            run_dir,
            decision_index=3,
            selected_parent_ids=["hyp-002"],
            selected_island_ids=["island-001"],
            hypothesis_count=1,
            viable_hypothesis_count=1,
            convergence_count=1,
            entered_top_k_last_round=None,
            top_hypothesis_ids=["hyp-001"],
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("same pre-round state" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_ignores_consumed_decisions_for_open_pre_round_duplicates() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        _append_continue_evolution_decision(
            run_dir,
            decision_index=3,
            selected_parent_ids=["hyp-002"],
            selected_island_ids=["island-001"],
            hypothesis_count=1,
            viable_hypothesis_count=1,
            convergence_count=1,
            entered_top_k_last_round=None,
            top_hypothesis_ids=["hyp-001"],
        )

        result = _run_contract_validation(run_dir)
        payload = json.loads(result.stdout)

        assert not any("same pre-round state" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_evolution_round_refs_opponent_owned_ranked_match() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        store = ArtifactStore(run_dir, top_k_limit=3)
        child_path = run_dir / "hypotheses" / "hyp-002" / "HYPOTHESIS.json"
        child = build_hypothesis(
            "hyp-002",
            1200.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="grounding_evolution",
        )
        challenger = build_hypothesis("hyp-003", 1180.0, "island-002", passed=False)
        opponent_owned_match = TournamentMatchContract(
            id="match-002",
            status="completed",
            hypothesis_1_id=challenger.id,
            hypothesis_2_id=child.id,
            match_strategy="ranked_tournament",
            reasoning="The later challenger is less mature than the evolved child.",
            winner_id=child.id,
        )
        child_payload = json.loads(child_path.read_text(encoding="utf-8"))
        child_payload["ranked_match_ids"] = ["match-002"]
        child_path.write_text(json.dumps(child_payload, indent=2) + "\n", encoding="utf-8")
        challenger = challenger.model_copy(update={"ranked_match_ids": ["match-002"]})
        store.write_hypothesis(challenger)
        store.write_tournaments(
            CoScientistStateContract(
                research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
                hypotheses={child.id: child, challenger.id: challenger},
                tournament_matches={opponent_owned_match.id: opponent_owned_match},
            )
        )
        rounds_path = run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
        round_payload = json.loads(rounds_path.read_text(encoding="utf-8").splitlines()[0])
        round_payload["ranked_match_ids"] = ["match-002"]
        rounds_path.write_text(json.dumps(round_payload) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "ranked match IDs must be child-owned ranked_tournament matches" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_hypothesis_match_refs_contain_duplicates() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        hypothesis_path = run_dir / "hypotheses" / "hyp-002" / "HYPOTHESIS.json"
        hypothesis_payload = json.loads(hypothesis_path.read_text(encoding="utf-8"))
        hypothesis_payload["placement_match_ids"] = ["match-001", "match-001"]
        hypothesis_path.write_text(json.dumps(hypothesis_payload, indent=2) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "HYPOTHESIS.json `placement_match_ids` must not contain duplicates" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_evolution_round_match_refs_contain_duplicates() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        rounds_path = run_dir / "state" / "EVOLUTION_ROUNDS.jsonl"
        round_payload = json.loads(rounds_path.read_text(encoding="utf-8").splitlines()[0])
        round_payload["placement_match_ids"] = ["match-001", "match-001"]
        rounds_path.write_text(json.dumps(round_payload) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "EVOLUTION_ROUNDS.jsonl `placement_match_ids` must not contain duplicates" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_evolution_top_k_replay_is_discontinuous() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        _append_continue_evolution_decision(run_dir, decision_index=3)

        store = ArtifactStore(run_dir, top_k_limit=3)
        second_child = build_hypothesis(
            "hyp-003",
            1295.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="grounding_evolution",
        )
        store.write_hypothesis(second_child)
        store.append_evolution_round_record(
            EvolutionRoundRecordContract.from_payload(
                {
                    "run_id": run_dir.name,
                    "round_index": 2,
                    "decision_index": 3,
                    "selection_strategy": "single_island",
                    "selected_island_ids": ["island-001"],
                    "parent_hypothesis_ids": ["hyp-001"],
                    "chosen_evolution_strategy": "grounding_evolution",
                    "child_hypothesis_id": "hyp-003",
                    "child_island_id": "island-001",
                    "review_passed": True,
                    "previous_top_k_ids": ["hyp-001"],
                    "current_top_k_ids": ["hyp-001", "hyp-002", "hyp-003"],
                    "entered_top_k": True,
                    "convergence_count_before": 0,
                    "convergence_count_after": 0,
                }
            )
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "previous_top_k_ids must match the prior round current_top_k_ids" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_frontier_evolved_child_lacks_placement_provenance() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(
            run_dir,
            append_round_record=True,
            include_ranking_artifacts=False,
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("without placement tournament provenance" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_strategy_signal_counts_drift_from_replay() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        records = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines()]
        records[1]["signals"]["hypothesis_count"] = 2
        records[1]["signals"]["viable_hypothesis_count"] = 2
        decisions_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("signal `hypothesis_count` must equal" in issue["message"] for issue in payload["issues"])
        assert any("signal `viable_hypothesis_count` must equal" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_strategy_frontier_signal_drifts_from_round_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        records = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines()]
        records[1]["signals"]["top_hypothesis_ids"] = ["hyp-999"]
        decisions_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("signal `top_hypothesis_ids` must match" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_strategy_selects_unavailable_parent() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        records = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines()]
        records[1]["signals"]["selected_parent_ids"] = ["hyp-002"]
        records[1]["signals"]["selected_island_ids"] = ["island-001"]
        decisions_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "selected parents that were not available before" in issue["message"] for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_strategy_entered_top_k_signal_conflicts_with_prior_round() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        _append_continue_evolution_decision(run_dir, decision_index=3, entered_top_k_last_round=False)

        store = ArtifactStore(run_dir, top_k_limit=3)
        second_child = build_hypothesis(
            "hyp-003",
            1295.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="grounding_evolution",
        )
        store.write_hypothesis(second_child)
        store.append_evolution_round_record(
            EvolutionRoundRecordContract.from_payload(
                {
                    "run_id": run_dir.name,
                    "round_index": 2,
                    "decision_index": 3,
                    "selection_strategy": "single_island",
                    "selected_island_ids": ["island-001"],
                    "parent_hypothesis_ids": ["hyp-001"],
                    "chosen_evolution_strategy": "grounding_evolution",
                    "child_hypothesis_id": "hyp-003",
                    "child_island_id": "island-001",
                    "review_passed": True,
                    "previous_top_k_ids": ["hyp-001", "hyp-002"],
                    "current_top_k_ids": ["hyp-001", "hyp-002", "hyp-003"],
                    "entered_top_k": True,
                    "convergence_count_before": 0,
                    "convergence_count_after": 0,
                }
            )
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "signal `entered_top_k_last_round` must match the prior round entered_top_k result" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_round_decision_lacks_router_signals() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        records = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines()]
        records[1]["signals"].pop("hypothesis_count")
        decisions_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("missing router signal `hypothesis_count`" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_strategy_decision_contains_round_result_fields() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)

        decisions_path = run_dir / "state" / "STRATEGY_DECISIONS.jsonl"
        records = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines()]
        records[1]["child_hypothesis_id"] = "hyp-002"
        records[1]["signals"]["chosen_evolution_strategy"] = "grounding_evolution"
        decisions_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "must not contain round-result fields at the top level" in issue["message"] for issue in payload["issues"]
        )
        assert any("`signals` must not contain round-result fields" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_evolution_round_parent_linkage_drifts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(
            run_dir,
            append_round_record=True,
            round_record_updates={"parent_hypothesis_ids": ["hyp-999"]},
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("parent IDs do not match" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_evolution_round_strategy_drifts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(
            run_dir,
            append_round_record=True,
            round_record_updates={"chosen_evolution_strategy": "coherence_evolution"},
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "chosen strategy does not match the child hypothesis origin strategy" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_current_skill_conflicts_with_current_phase() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-review-pipeline",
            stage_trail=["Generation", "Evolution"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("currentSkill" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_active_pipeline_phase_remains_not_started() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        store = ArtifactStore(run_dir, top_k_limit=3)
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
        )
        store.write_research_plan(state.research_plan)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="not_started",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
            stage_trail=["Evolution"],
        )
        pipeline_state_path = run_dir / "state" / "PIPELINE_STATE.json"
        pipeline_state_payload = json.loads(pipeline_state_path.read_text(encoding="utf-8"))
        pipeline_state_payload["status"] = "not_started"
        pipeline_state_path.write_text(json.dumps(pipeline_state_payload, indent=2) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("PIPELINE_STATE.json `status` must be `running`" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_current_stage_phase_drifts_from_pipeline_state() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Insights from Reviews",
            current_skill="insights-from-reviews",
            stage_trail=["Generation", "Reflection", "Insights from Reviews"],
        )
        (run_dir / "state" / "CURRENT_STAGE.json").write_text(
            json.dumps(
                {
                    "runId": run_dir.name,
                    "stage": "Proximity",
                    "stageTrail": ["Generation", "Reflection", "Insights from Reviews", "Proximity"],
                    "updatedAt": "2026-06-01T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "currentPhase" in issue["message"] and "CURRENT_STAGE.json `stage`" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_current_stage_trail_drifts_from_pipeline_state() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Ranking"],
        )
        (run_dir / "state" / "CURRENT_STAGE.json").write_text(
            json.dumps(
                {
                    "runId": run_dir.name,
                    "stage": "Ranking",
                    "stageTrail": ["Generation", "Reflection", "Insights from Reviews", "Ranking"],
                    "updatedAt": "2026-06-01T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "stageTrail" in issue["message"] and "CURRENT_STAGE.json" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_completed_skills_have_duplicates() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        pipeline_state_path = run_dir / "state" / "PIPELINE_STATE.json"
        pipeline_state_payload = json.loads(pipeline_state_path.read_text(encoding="utf-8"))
        pipeline_state_payload["completedSkills"] = ["research-config", "research-config"]
        pipeline_state_path.write_text(json.dumps(pipeline_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "completedSkills" in issue["message"] and "duplicate" in issue["message"] for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_pipeline_summary_counts_drift_from_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        pipeline_state_path = run_dir / "state" / "PIPELINE_STATE.json"
        pipeline_state_payload = json.loads(pipeline_state_path.read_text(encoding="utf-8"))
        pipeline_state_payload["tournamentMatchCount"] = 1
        pipeline_state_path.write_text(json.dumps(pipeline_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "tournamentMatchCount" in issue["message"] and "artifact tree count" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_generation_phase_has_no_research_plan() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        state = CoScientistStateContract()
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Generation",
            current_skill="hypothesis-generation-pipeline",
            stage_trail=["Generation"],
        )
        (run_dir / "state" / "STRATEGY_PLAN.json").write_text(
            json.dumps(
                {
                    "status": "planned",
                    "current_phase": "Generation",
                    "next_action": "run_generation",
                    "selected_generation_strategies": ["literature_exploration_generation"],
                    "selected_evolution_strategies": [],
                    "max_new_hypotheses": 1,
                    "reasoning": ["Begin generation."],
                    "advisory_recommendation": "",
                    "signals": {},
                    "updated_at": "2026-06-01T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "valid research_plan/RESEARCH_PLAN.json is required" in issue["message"] for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_hypothesis_artifact_is_not_canonical() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        malformed_hypothesis_dir = run_dir / "hypotheses" / "H1"
        (malformed_hypothesis_dir / "REVIEW").mkdir(parents=True)
        (malformed_hypothesis_dir / "HYPOTHESIS.json").write_text(
            json.dumps({"id": "H1", "content": {"statement": "Malformed"}}) + "\n",
            encoding="utf-8",
        )
        (malformed_hypothesis_dir / "REVIEW" / "REVIEW_SUMMARY.json").write_text(
            json.dumps({"status": "completed", "summaries": ["ok"]}) + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("HYPOTHESIS.json is missing canonical keys" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_hypothesis_content_fields_are_blank() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        malformed_hypothesis_dir = run_dir / "hypotheses" / "H1"
        (malformed_hypothesis_dir / "REVIEW").mkdir(parents=True)
        (malformed_hypothesis_dir / "HYPOTHESIS.json").write_text(
            json.dumps(
                {
                    "id": "H1",
                    "timestamp": "2026-05-28T00:00:00+00:00",
                    "elo_rating": 1200.0,
                    "origin": {
                        "status": "completed",
                        "strategy": "grounding_evolution",
                        "content": {
                            "statement": "A statement.",
                            "mechanism": "",
                            "experimental_design": "1. Test it.",
                            "summary": "",
                            "category": "",
                        },
                    },
                    "review": {"initial_review": {"status": "completed", "passed": True}},
                    "island_id": "",
                    "parent_ids": ["H0"],
                    "placement_match_ids": [],
                    "ranked_match_ids": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (malformed_hypothesis_dir / "REVIEW" / "REVIEW_SUMMARY.json").write_text(
            json.dumps({"status": "completed", "summaries": ["ok"]}) + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("required origin content fields" in issue["message"] for issue in payload["issues"])
        assert any("island_id" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_evolved_hypotheses_have_no_evolution_state() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        parent = build_hypothesis("hyp-001", 1250.0, "island-001")
        child = build_hypothesis("hyp-002", 1310.0, "island-001", parent_ids=["hyp-001"])
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={parent.id: parent, child.id: child},
            islands={"island-001": IslandStateContract(id="island-001")},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(parent)
        store.write_hypothesis(child)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").write_text(
            json.dumps(
                {
                    "run_id": run_dir.name,
                    "decision_index": 1,
                    "current_phase": "Generation",
                    "next_action": "run_generation",
                    "selected_generation_strategies": ["literature_exploration_generation"],
                    "selected_evolution_strategies": [],
                    "max_new_hypotheses": 1,
                    "reasoning": ["Seed the initial frontier."],
                    "advisory_recommendation": "inspect_state",
                    "signals": {},
                    "status": "planned",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "run_id": run_dir.name,
                    "decision_index": 2,
                    "current_phase": "Evolution",
                    "next_action": "continue_evolution",
                    "selected_generation_strategies": [],
                    "selected_evolution_strategies": ["grounding_evolution"],
                    "max_new_hypotheses": 0,
                    "reasoning": ["Continue evolving."],
                    "advisory_recommendation": "continue_evolution",
                    "signals": {
                        "selection_strategy": "single_island",
                        "selected_parent_ids": ["hyp-001"],
                        "selected_island_ids": ["island-001"],
                    },
                    "status": "planned",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("EVOLUTION_STATE.json is missing" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_allows_open_selection_before_first_evolution_child() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        parent = build_hypothesis("hyp-001", 1200.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={parent.id: parent},
            islands={"island-001": IslandStateContract(id="island-001")},
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(parent)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        _append_continue_evolution_decision(
            run_dir,
            decision_index=1,
            hypothesis_count=1,
            viable_hypothesis_count=1,
            entered_top_k_last_round=None,
            top_hypothesis_ids=[parent.id],
        )
        result = _run_contract_validation(run_dir)
        payload = json.loads(result.stdout)
        assert not any("every island still has" in issue["message"] for issue in payload["issues"])
        assert result.returncode == 0, payload


def test_contract_validation_cli_fails_when_single_island_rounds_never_update_island_metrics() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        parent = build_hypothesis("hyp-001", 1250.0, "island-001")
        child = build_hypothesis("hyp-002", 1310.0, "island-001", parent_ids=["hyp-001"])
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={parent.id: parent, child.id: child},
            islands={"island-001": IslandStateContract(id="island-001")},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(parent)
        store.write_hypothesis(child)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=6,
            safety_max_iterations=12,
            effective_top_k=2,
            status="running",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            last_selected_island="island-001",
        )
        (run_dir / "state" / "STRATEGY_DECISIONS.jsonl").write_text(
            json.dumps(
                {
                    "run_id": run_dir.name,
                    "decision_index": 1,
                    "current_phase": "Generation",
                    "next_action": "run_generation",
                    "selected_generation_strategies": ["literature_exploration_generation"],
                    "selected_evolution_strategies": [],
                    "max_new_hypotheses": 1,
                    "reasoning": ["Seed the initial frontier."],
                    "advisory_recommendation": "inspect_state",
                    "signals": {},
                    "status": "planned",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "run_id": run_dir.name,
                    "decision_index": 2,
                    "current_phase": "Evolution",
                    "next_action": "continue_evolution",
                    "selected_generation_strategies": [],
                    "selected_evolution_strategies": ["grounding_evolution", "coherence_evolution"],
                    "max_new_hypotheses": 0,
                    "reasoning": ["Continue evolving."],
                    "advisory_recommendation": "continue_evolution",
                    "signals": {
                        "selection_strategy": "single_island",
                        "selected_parent_ids": ["hyp-001"],
                        "selected_island_ids": ["island-001"],
                    },
                    "status": "planned",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("visit_count = 0" in issue["message"] for issue in payload["issues"])
        assert any("decayed_visits = 0" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_selected_island_metrics_are_partially_unpersisted() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        (run_dir / "islands" / "ISLANDS.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "island-001",
                            "decayed_reward": 0.0,
                            "decayed_visits": 0.0,
                            "visit_count": 0,
                        },
                        {
                            "id": "island-002",
                            "decayed_reward": 0.5,
                            "decayed_visits": 1.0,
                            "visit_count": 1,
                        },
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        pipeline_state_path = run_dir / "state" / "PIPELINE_STATE.json"
        pipeline_state_payload = json.loads(pipeline_state_path.read_text(encoding="utf-8"))
        pipeline_state_payload["islandCount"] = 2
        pipeline_state_path.write_text(json.dumps(pipeline_state_payload) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "Island `island-001` was selected by completed single-island evolution rounds" in issue["message"]
            and "`visit_count = 0`" in issue["message"]
            for issue in payload["issues"]
        )
        assert any(
            "Island `island-001` was selected by completed single-island evolution rounds" in issue["message"]
            and "`decayed_visits = 0`" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_selected_island_visit_count_is_under_persisted() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        _append_continue_evolution_decision(run_dir, decision_index=3)

        store = ArtifactStore(run_dir, top_k_limit=3)
        second_child = build_hypothesis(
            "hyp-003",
            1295.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="grounding_evolution",
        )
        store.write_hypothesis(second_child)
        store.append_evolution_round_record(
            EvolutionRoundRecordContract.from_payload(
                {
                    "run_id": run_dir.name,
                    "round_index": 2,
                    "decision_index": 3,
                    "selection_strategy": "single_island",
                    "selected_island_ids": ["island-001"],
                    "parent_hypothesis_ids": ["hyp-001"],
                    "chosen_evolution_strategy": "grounding_evolution",
                    "child_hypothesis_id": "hyp-003",
                    "child_island_id": "island-001",
                    "review_passed": True,
                    "previous_top_k_ids": ["hyp-001", "hyp-002"],
                    "current_top_k_ids": ["hyp-001", "hyp-002", "hyp-003"],
                    "entered_top_k": True,
                    "convergence_count_before": 0,
                    "convergence_count_after": 0,
                }
            )
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "Island `island-001` was selected by completed single-island evolution rounds `2` times "
            "but has `visit_count = 1`." in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_allows_unselected_island_metrics_to_remain_zero() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _prepare_evolution_round_run(run_dir, append_round_record=True)
        (run_dir / "islands" / "ISLANDS.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "island-001",
                            "decayed_reward": 0.5,
                            "decayed_visits": 1.0,
                            "visit_count": 1,
                        },
                        {
                            "id": "island-002",
                            "decayed_reward": 0.0,
                            "decayed_visits": 0.0,
                            "visit_count": 0,
                        },
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        pipeline_state_path = run_dir / "state" / "PIPELINE_STATE.json"
        pipeline_state_payload = json.loads(pipeline_state_path.read_text(encoding="utf-8"))
        pipeline_state_payload["islandCount"] = 2
        pipeline_state_path.write_text(json.dumps(pipeline_state_payload) + "\n", encoding="utf-8")

        result = _run_contract_validation(run_dir)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"
        assert payload["errorCount"] == 0


def test_contract_validation_cli_fails_when_island_artifact_uses_deprecated_fields() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-001": IslandStateContract(id="island-001")},
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Generation",
            current_skill="hypothesis-generation-pipeline",
        )
        (run_dir / "islands" / "ISLANDS.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "island_id": "island-001",
                            "reward": 0.5,
                            "decayed_visits": 1.0,
                            "visit_count": 1,
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("deprecated non-canonical keys" in issue["message"] for issue in payload["issues"])
        assert any("missing canonical keys" in issue["message"] for issue in payload["issues"])
        assert any("must keep `id` non-empty" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_island_items_contain_non_canonical_keys() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-001": IslandStateContract(id="island-001")},
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Generation",
            current_skill="hypothesis-generation-pipeline",
        )
        (run_dir / "islands" / "ISLANDS.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "island-001",
                            "decayed_reward": 0.0,
                            "decayed_visits": 0.0,
                            "visit_count": 0,
                            "hypothesis_ids": ["hyp-001"],
                            "ucb_score": 0.0,
                            "strategy_label": "manual",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stdout
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("non-canonical keys" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_deprecated_state_islands_artifact_exists() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)
        state_dir = run_dir / "state"
        state_dir.mkdir()
        (state_dir / "ISLANDS.json").write_text(
            json.dumps(
                {"items": [{"id": "island-001", "decayed_reward": 0.0, "decayed_visits": 0.0, "visit_count": 0}]}
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("`state/ISLANDS.json` is deprecated" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_viable_hypothesis_island_is_missing_from_islands() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-001": IslandStateContract(id="island-001")},
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Generation",
            current_skill="hypothesis-generation-pipeline",
        )
        (run_dir / "islands" / "ISLANDS.json").write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "id": "island-other",
                            "decayed_reward": 0.5,
                            "decayed_visits": 1.0,
                            "visit_count": 1,
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("missing canonical island items" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_convergence_signals_conflict() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            iteration_count=3,
            convergence_count=3,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=12,
            effective_top_k=1,
            status="completed",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            last_selected_island="island-001",
            stop_reason="convergence_reached",
            overview_eligible=True,
        )
        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["enteredTopKLastRound"] = True
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("enteredTopKLastRound" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_terminal_stop_reason_remains_running() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-001": IslandStateContract(id="island-001", visit_count=1)},
            iteration_count=3,
            convergence_count=3,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=12,
            effective_top_k=1,
            status="completed",
            entered_top_k_last_round=False,
            stop_reason="convergence_reached",
            overview_eligible=True,
        )
        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["status"] = "running"
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("terminal `stopReason`" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_top_k_signal_is_missing_after_iterations() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-001": IslandStateContract(id="island-001", visit_count=1)},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Evolution",
            current_skill="hypothesis-evolution-loop",
        )
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=12,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=True,
        )
        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["enteredTopKLastRound"] = None
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("enteredTopKLastRound" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_completed_pipeline_has_running_evolution_state() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        hypothesis = build_hypothesis("hyp-001", 1250.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={"island-001": IslandStateContract(id="island-001", visit_count=1)},
            iteration_count=1,
            convergence_count=0,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="completed",
            current_phase="Completed",
            current_skill="",
            stage_trail=[],
        )
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=12,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=True,
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("PIPELINE_STATE.json is already `completed`" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_embedded_review_drifts_from_stage_artifacts() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        hypothesis = build_hypothesis("hyp-001", 1200.0, "island-001").model_copy(update={"review": ReviewContract()})
        store.write_hypothesis(hypothesis)

        review_dir = run_dir / "hypotheses" / "hyp-001" / "REVIEW"
        (review_dir / "INITIAL_REVIEW.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "passed": True,
                    "preferences": ["Mechanistically plausible"],
                    "constraints": ["Needs experimental confirmation"],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("REVIEW/INITIAL_REVIEW.json" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_completed_review_summary_has_no_content() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        hypothesis = build_hypothesis("hyp-001", 1200.0, "island-001").model_copy(update={"review": ReviewContract()})
        store.write_hypothesis(hypothesis)

        review_dir = run_dir / "hypotheses" / "hyp-001" / "REVIEW"
        (review_dir / "REVIEW_SUMMARY.json").write_text(
            json.dumps({"status": "completed", "summaries": []}) + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "Completed review summary artifacts must include at least one summary item." in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_completed_simulation_review_has_no_steps() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        hypothesis = build_hypothesis("hyp-001", 1200.0, "island-001").model_copy(update={"review": ReviewContract()})
        store.write_hypothesis(hypothesis)

        review_dir = run_dir / "hypotheses" / "hyp-001" / "REVIEW"
        (review_dir / "SIMULATION_REVIEW.json").write_text(
            json.dumps({"status": "completed", "steps": [], "failure_scenarios": ["One failure mode."]}) + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "Completed simulation review artifacts must include at least one step." in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_evolved_hypothesis_uses_placeholder_content() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        parent = build_hypothesis("hyp-001", 1250.0, "island-001")
        child = build_hypothesis(
            "hyp-002",
            1210.0,
            "island-001",
            parent_ids=["hyp-001"],
            strategy="coherence_evolution",
        )
        placeholder_content = child.origin.content.model_copy(
            update={
                "statement": (
                    "Evolved from Li-mediated electrochemical (round 5): refined mechanism with improved "
                    "experimental controls and quantitative benchmarks."
                ),
                "mechanism": (
                    "Refinement of Li-mediated electrochemical addressing review-identified weaknesses through "
                    "targeted mechanistic and design improvements."
                ),
                "experimental_design": (
                    "1. Apply targeted improvement to Li-mediated electrochemical.\n"
                    "2. Characterize with standard techniques.\n"
                    "3. Benchmark against parent under identical conditions.\n"
                    "4. Validate improvement quantitatively."
                ),
                "summary": (
                    "Refined Li-mediated electrochemical with improved performance and experimental validation."
                ),
                "category": "Evolved Hypothesis",
            }
        )
        child = child.model_copy(update={"origin": child.origin.model_copy(update={"content": placeholder_content})})
        store.write_hypothesis(parent)
        store.write_hypothesis(child)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("placeholder `statement` content" in issue["message"] for issue in payload["issues"])
        assert any(
            "specific experimental design rather than placeholder steps" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_completed_review_bundle_is_placeholder_only() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        placeholder_review = ReviewContract(
            initial_review=InitialReviewContract(
                status="completed",
                passed=True,
                preferences=["Refined from parent."],
                constraints=["Must outperform parent."],
            ),
            full_review=FullReviewContract(status="completed"),
            deep_verification_review=DeepVerificationReviewContract(status="completed"),
            observation_review=ObservationReviewContract(status="completed"),
            simulation_review=SimulationReviewContract(
                status="completed",
                steps=["Synthesize evolved catalyst.", "Characterize structure.", "Test activity."],
                failure_scenarios=["Synthesis reproducibility.", "Stability under reaction conditions."],
            ),
            review_summary=ReviewSummaryContract(status="completed", summaries=["Viable evolved hypothesis."]),
        )
        hypothesis = build_hypothesis("hyp-001", 1200.0, "island-001").model_copy(
            update={"review": placeholder_review}
        )
        store.write_hypothesis(hypothesis)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "specific non-placeholder preferences or constraints" in issue["message"] for issue in payload["issues"]
        )
        assert any("Completed full review artifacts must include" in issue["message"] for issue in payload["issues"])
        assert any(
            "Completed deep verification review artifacts must include" in issue["message"]
            for issue in payload["issues"]
        )
        assert any("non-placeholder summary content" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_placement_ranking_has_no_proximity_bridge_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        candidate = build_hypothesis("hyp-001", 1200.0, "island-001")
        candidate_origin = candidate.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        candidate = candidate.model_copy(update={"origin": candidate_origin})
        opponent = build_hypothesis("hyp-002", 1200.0, "island-002")
        opponent_origin = opponent.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        opponent = opponent.model_copy(update={"origin": opponent_origin})
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="placement_tournament",
            reasoning="The candidate is more directly testable.",
            winner_id=candidate.id,
        )
        apply_and_persist_elo_updates(
            run_dir,
            [match],
            [HypothesisMatchupContract(hypothesis_1=candidate, hypothesis_2=opponent)],
            "placement_tournament",
            top_k_limit=3,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={candidate.id: candidate, opponent.id: opponent},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-ranking-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("requires a proximity embedding bridge receipt" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_completed_tournament_has_no_ranking_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        candidate = build_hypothesis("hyp-001", 1216.0, "island-001")
        candidate_origin = candidate.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        candidate = candidate.model_copy(update={"origin": candidate_origin, "placement_match_ids": ["match-001"]})
        opponent = build_hypothesis("hyp-002", 1184.0, "island-002")
        opponent_origin = opponent.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        opponent = opponent.model_copy(update={"origin": opponent_origin, "ranked_match_ids": ["match-001"]})
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="placement_tournament",
            reasoning="The candidate is more directly testable.",
            winner_id=candidate.id,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={candidate.id: candidate, opponent.id: opponent},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        update_hypothesis_proximity(
            run_dir,
            candidate.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-ranking-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "completed tournament match" in issue["message"]
            and "ranking update receipt" in issue["message"]
            and "match-001" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_accepts_placement_ranking_after_proximity_bridge_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        candidate = build_hypothesis("hyp-001", 1200.0, "island-001")
        candidate_origin = candidate.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        candidate = candidate.model_copy(update={"origin": candidate_origin})
        opponent = build_hypothesis("hyp-002", 1200.0, "island-002")
        opponent_origin = opponent.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        opponent = opponent.model_copy(update={"origin": opponent_origin})
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="placement_tournament",
            reasoning="The candidate is more directly testable.",
            winner_id=candidate.id,
        )
        apply_and_persist_elo_updates(
            run_dir,
            [match],
            [HypothesisMatchupContract(hypothesis_1=candidate, hypothesis_2=opponent)],
            "placement_tournament",
            top_k_limit=3,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={candidate.id: candidate, opponent.id: opponent},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        update_hypothesis_proximity(
            run_dir,
            candidate.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-ranking-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"


def test_contract_validation_cli_accepts_placement_and_ranked_receipts_for_same_candidate() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        candidate = build_hypothesis("hyp-001", 1200.0, "island-001")
        opponent = build_hypothesis("hyp-002", 1200.0, "island-002")
        champion = build_hypothesis("hyp-003", 1200.0, "island-003")
        placement_match = TournamentMatchContract(
            id="match-placement",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="placement_tournament",
            reasoning="The candidate is more directly testable.",
            winner_id=candidate.id,
        )
        apply_and_persist_elo_updates(
            run_dir,
            [placement_match],
            [HypothesisMatchupContract(hypothesis_1=candidate, hypothesis_2=opponent)],
            "placement_tournament",
            top_k_limit=3,
        )
        ranked_match = TournamentMatchContract(
            id="match-ranked",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=champion.id,
            match_strategy="ranked_tournament",
            reasoning="The champion remains stronger overall.",
            winner_id=champion.id,
        )
        apply_and_persist_elo_updates(
            run_dir,
            [ranked_match],
            [HypothesisMatchupContract(hypothesis_1=candidate, hypothesis_2=champion)],
            "ranked_tournament",
            top_k_limit=3,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={candidate.id: candidate, opponent.id: opponent, champion.id: champion},
            tournament_matches={placement_match.id: placement_match, ranked_match.id: ranked_match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
                "island-003": IslandStateContract(
                    id="island-003", visit_count=1, decayed_visits=1.0, decayed_reward=0.8
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        store.write_hypothesis(champion)
        update_hypothesis_proximity(
            run_dir,
            candidate.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-ranking-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"


def test_contract_validation_cli_fails_when_completed_tournament_elo_is_not_persisted() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        candidate = build_hypothesis("hyp-001", 1200.0, "island-001")
        candidate_origin = candidate.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        candidate = candidate.model_copy(update={"origin": candidate_origin, "placement_match_ids": ["match-001"]})
        opponent = build_hypothesis("hyp-002", 1200.0, "island-002")
        opponent_origin = opponent.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        opponent = opponent.model_copy(update={"origin": opponent_origin, "ranked_match_ids": ["match-001"]})
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="placement_tournament",
            reasoning="The candidate is more directly testable.",
            winner_id=candidate.id,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={candidate.id: candidate, opponent.id: opponent},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        update_hypothesis_proximity(
            run_dir,
            candidate.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-ranking-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "Elo rating" in issue["message"]
            and "match-001" in issue["message"]
            and "ranking-elo-update" in issue["message"]
            and "tools.apply_and_persist_elo_updates" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_ranked_challenger_skips_placement_stage() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        candidate = build_hypothesis("hyp-001", 1320.0, "island-001")
        candidate_origin = candidate.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        candidate = candidate.model_copy(update={"origin": candidate_origin, "ranked_match_ids": ["match-001"]})
        opponent = build_hypothesis("hyp-002", 1280.0, "island-002")
        opponent_origin = opponent.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        opponent = opponent.model_copy(update={"origin": opponent_origin, "ranked_match_ids": ["match-001"]})
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="ranked_tournament",
            reasoning="The candidate is better grounded.",
            winner_id=candidate.id,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={candidate.id: candidate, opponent.id: opponent},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        update_hypothesis_proximity(
            run_dir,
            candidate.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-ranking-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any(
            "has ranked_tournament match refs but no placement_tournament match refs" in issue["message"]
            for issue in payload["issues"]
        )


def test_contract_validation_cli_fails_when_top_k_candidate_skips_ranked_tournament() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        store.write_resolved_run_config(ResolvedRunConfigContract.from_payload({"ranking": {"tournament_top_k": 3}}))
        candidate = build_hypothesis("hyp-001", 1320.0, "island-001")
        candidate_origin = candidate.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        candidate = candidate.model_copy(update={"origin": candidate_origin, "placement_match_ids": ["match-001"]})
        opponent = build_hypothesis("hyp-002", 1184.0, "island-002")
        opponent_origin = opponent.origin.model_copy(update={"strategy": "assumptions_identification_generation"})
        opponent = opponent.model_copy(update={"origin": opponent_origin, "ranked_match_ids": ["match-001"]})
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=candidate.id,
            hypothesis_2_id=opponent.id,
            match_strategy="placement_tournament",
            reasoning="The candidate is more directly testable.",
            winner_id=candidate.id,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={candidate.id: candidate, opponent.id: opponent},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(candidate)
        store.write_hypothesis(opponent)
        update_hypothesis_proximity(
            run_dir,
            candidate.id,
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        store.write_tournaments(state)
        store.write_islands(state)
        store.write_pipeline_state(
            state,
            mode="host-agent",
            status="running",
            current_phase="Ranking",
            current_skill="hypothesis-ranking-pipeline",
            stage_trail=["Generation", "Reflection", "Insights from Reviews", "Proximity", "Ranking"],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "hypothesis-ranking-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("has no ranked_tournament match refs" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_tournament_artifacts_are_not_referenced_by_hypotheses() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        hypothesis_one = build_hypothesis("hyp-001", 1216.0, "island-001")
        hypothesis_two = build_hypothesis("hyp-002", 1184.0, "island-002")
        match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id=hypothesis_one.id,
            hypothesis_2_id=hypothesis_two.id,
            match_strategy="ranked_tournament",
            reasoning="Hypothesis one is better grounded.",
            winner_id=hypothesis_one.id,
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis_one.id: hypothesis_one, hypothesis_two.id: hypothesis_two},
            tournament_matches={match.id: match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis_one)
        store.write_hypothesis(hypothesis_two)
        store.write_tournaments(state)
        store.write_islands(state)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("ranked tournament match refs" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_hypothesis_contains_extra_ranked_match_refs() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        placement_match = TournamentMatchContract(
            id="match-001",
            status="completed",
            hypothesis_1_id="hyp-001",
            hypothesis_2_id="hyp-002",
            match_strategy="placement_tournament",
            reasoning="Hypothesis one is the placement challenger.",
            winner_id="hyp-001",
        )
        hypothesis_one = build_hypothesis("hyp-001", 1216.0, "island-001").model_copy(
            update={
                "placement_match_ids": ["match-001"],
                "ranked_match_ids": ["match-001"],
            }
        )
        hypothesis_two = build_hypothesis("hyp-002", 1184.0, "island-002").model_copy(
            update={"ranked_match_ids": ["match-001"]}
        )
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis_one.id: hypothesis_one, hypothesis_two.id: hypothesis_two},
            tournament_matches={placement_match.id: placement_match},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.2
                ),
            },
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis_one)
        store.write_hypothesis(hypothesis_two)
        store.write_tournaments(state)
        store.write_islands(state)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("extra ranked tournament match refs" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_evolution_state_lists_more_frontier_items_than_effective_top_k() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=1)
        hypothesis_one = build_hypothesis("hyp-001", 1320.0, "island-001")
        hypothesis_two = build_hypothesis("hyp-002", 1280.0, "island-002")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis_one.id: hypothesis_one, hypothesis_two.id: hypothesis_two},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.4
                ),
            },
            iteration_count=2,
            convergence_count=1,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis_one)
        store.write_hypothesis(hypothesis_two)
        store.write_islands(state)
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=12,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            last_selected_island="island-001",
        )

        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["topHypothesisIds"] = ["hyp-001", "hyp-002"]
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("more `topHypothesisIds` than `effectiveTopK`" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_effective_top_k_drifts_from_resolved_config() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        store.write_resolved_run_config(ResolvedRunConfigContract.from_payload({"ranking": {"tournament_top_k": 3}}))
        hypothesis_one = build_hypothesis("hyp-001", 1320.0, "island-001")
        hypothesis_two = build_hypothesis("hyp-002", 1280.0, "island-002")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis_one.id: hypothesis_one, hypothesis_two.id: hypothesis_two},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                ),
                "island-002": IslandStateContract(
                    id="island-002", visit_count=1, decayed_visits=1.0, decayed_reward=0.4
                ),
            },
            iteration_count=2,
            convergence_count=1,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis_one)
        store.write_hypothesis(hypothesis_two)
        store.write_islands(state)
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=30,
            effective_top_k=3,
            status="running",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            last_selected_island="island-001",
        )

        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["effectiveTopK"] = 3
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("effectiveTopK` must equal" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_safety_max_iterations_drifts_from_resolved_config() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                )
            },
            iteration_count=20,
            convergence_count=1,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=30,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            last_selected_island="island-001",
        )

        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload["safetyMaxIterations"] = 20
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("safetyMaxIterations` must equal" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_safety_stop_precedes_resolved_ceiling() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                )
            },
            iteration_count=20,
            convergence_count=1,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=30,
            effective_top_k=1,
            status="running",
            entered_top_k_last_round=False,
            last_selected_strategy="grounding_evolution",
            last_selected_island="island-001",
        )

        evolution_state_path = run_dir / "state" / "EVOLUTION_STATE.json"
        evolution_state_payload = json.loads(evolution_state_path.read_text(encoding="utf-8"))
        evolution_state_payload.update(
            {
                "status": "completed",
                "safetyLimitHit": True,
                "stopReason": "safety_iteration_limit_reached",
                "overviewEligible": True,
            }
        )
        evolution_state_path.write_text(json.dumps(evolution_state_payload) + "\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("before the resolved safety ceiling was met" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_completion_rationale_uses_wrong_top_k_text() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=8)
        store.bootstrap()
        store.write_resolved_run_config(ResolvedRunConfigContract.from_payload({"ranking": {"tournament_top_k": 8}}))
        store.write_completion_decision(
            decision="complete",
            verifier_recommendation="complete",
            requested_skill="co-scientist-pipeline",
            override=False,
            rationale=["The run stopped after three consecutive rounds without new top-5 entries."],
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.validation.contract_validation",
                str(run_dir),
                "--skill",
                "co-scientist-pipeline",
            ],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("rationale references top-k values" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_overview_claims_convergence_after_safety_stop() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                )
            },
            iteration_count=30,
            convergence_count=1,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=30,
            effective_top_k=1,
            status="completed",
            entered_top_k_last_round=False,
            stop_policy="standard",
            iteration_policy="completion_driven",
            safety_limit_hit=True,
            stop_reason="safety_iteration_limit_reached",
            overview_eligible=True,
        )
        store.write_json(
            run_dir / "meta" / "RESEARCH_OVERVIEW.json",
            ResearchOverviewContract(
                status="completed",
                content="After 30 evolution rounds, the frontier converged on one leading direction.",
            ),
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("must not claim convergence" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_overview_claims_full_literature_coverage_after_partial_search() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_safety_stopped_overview_run(run_dir)
        search_literature(
            run_dir,
            {"query_id": "q-001", "query": "ammonia catalyst", "providers": ["openalex", "crossref"]},
            provider_searchers={"openalex": _fake_literature_provider},
            verify=False,
        )
        store.write_json(
            run_dir / "meta" / "RESEARCH_OVERVIEW.json",
            ResearchOverviewContract(
                status="completed",
                content="The recommendations are based on comprehensive literature coverage across the field.",
            ),
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("comprehensive literature coverage" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_overview_omits_partial_literature_limitation() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_safety_stopped_overview_run(run_dir)
        search_literature(
            run_dir,
            {"query_id": "q-001", "query": "ammonia catalyst", "providers": ["openalex", "crossref"]},
            provider_searchers={"openalex": _fake_literature_provider},
            verify=False,
        )
        store.write_json(
            run_dir / "meta" / "RESEARCH_OVERVIEW.json",
            ResearchOverviewContract(
                status="completed",
                content="The final recommendations prioritize the most experimentally useful catalyst directions.",
            ),
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("literature retrieval limitation note" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_accepts_overview_with_partial_literature_limitation() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_safety_stopped_overview_run(run_dir)
        search_literature(
            run_dir,
            {"query_id": "q-001", "query": "ammonia catalyst", "providers": ["openalex", "crossref"]},
            provider_searchers={"openalex": _fake_literature_provider},
            verify=False,
        )
        store.write_json(
            run_dir / "meta" / "RESEARCH_OVERVIEW.json",
            ResearchOverviewContract(
                status="completed",
                content=(
                    "The final recommendations prioritize useful catalyst directions. Literature retrieval was "
                    "partial, so external evidence coverage is limited and should be expanded before final claims."
                ),
            ),
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"


def test_contract_validation_cli_fails_when_overview_claims_embedding_ranking_after_proximity_fallback() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_safety_stopped_overview_run(run_dir)
        store.write_json(
            run_dir / "state" / "PROXIMITY_STATUS.json",
            {
                "status": "skipped_provider_unavailable",
                "reason": "OPENAI_API_KEY is not configured.",
            },
        )
        store.write_json(
            run_dir / "meta" / "RESEARCH_OVERVIEW.json",
            ResearchOverviewContract(
                status="completed",
                content="The final priorities use embedding-informed ranking across the frontier.",
            ),
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("must not describe ranking as embedding-" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_overview_omits_proximity_fallback_limitation() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_safety_stopped_overview_run(run_dir)
        store.write_json(
            run_dir / "state" / "PROXIMITY_STATUS.json",
            {
                "status": "skipped_provider_unavailable",
                "reason": "OPENAI_API_KEY is not configured.",
            },
        )
        store.write_json(
            run_dir / "meta" / "RESEARCH_OVERVIEW.json",
            ResearchOverviewContract(
                status="completed",
                content="The final priorities are based on the reviewed frontier and tournament ordering.",
            ),
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("proximity embedding fallback limitation note" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_accepts_overview_with_proximity_fallback_limitation() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        store = _prepare_safety_stopped_overview_run(run_dir)
        store.write_json(
            run_dir / "state" / "PROXIMITY_STATUS.json",
            {
                "status": "skipped_provider_unavailable",
                "reason": "OPENAI_API_KEY is not configured.",
            },
        )
        store.write_json(
            run_dir / "meta" / "RESEARCH_OVERVIEW.json",
            ResearchOverviewContract(
                status="completed",
                content=(
                    "The final priorities are based on the reviewed frontier and tournament ordering. Proximity "
                    "embedding was skipped because the provider was unavailable, so ranking used documented fallback "
                    "rather than placement based on a proximity graph."
                ),
            ),
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "valid"


def test_contract_validation_cli_fails_when_completion_rationale_claims_convergence_after_safety_stop() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        hypothesis = build_hypothesis("hyp-001", 1320.0, "island-001")
        state = CoScientistStateContract(
            research_plan=ResearchPlanContract(status="completed", research_goal="Investigate response drift."),
            hypotheses={hypothesis.id: hypothesis},
            islands={
                "island-001": IslandStateContract(
                    id="island-001", visit_count=1, decayed_visits=1.0, decayed_reward=0.5
                )
            },
            iteration_count=30,
            convergence_count=1,
        )
        store.write_research_plan(state.research_plan)
        store.write_hypothesis(hypothesis)
        store.write_islands(state)
        store.write_evolution_state(
            state,
            convergence_threshold=3,
            max_iterations=0,
            safety_max_iterations=30,
            effective_top_k=1,
            status="completed",
            entered_top_k_last_round=False,
            stop_policy="standard",
            iteration_policy="completion_driven",
            safety_limit_hit=True,
            stop_reason="safety_iteration_limit_reached",
            overview_eligible=True,
        )
        store.write_completion_decision(
            decision="complete",
            verifier_recommendation="complete",
            requested_skill="co-scientist-pipeline",
            override=False,
            rationale=["The frontier converged after additional review."],
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("rationale must not claim convergence" in issue["message"] for issue in payload["issues"])


def test_contract_validation_cli_fails_when_completion_rationale_uses_wrong_safety_limit_text() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        _write_config(run_dir)

        store = ArtifactStore(run_dir, top_k_limit=3)
        store.bootstrap()
        store.write_resolved_run_config(
            ResolvedRunConfigContract.from_payload({"convergence": {"safety_max_iterations": 30}})
        )
        store.write_completion_decision(
            decision="generate_overview",
            verifier_recommendation="generate_overview",
            requested_skill="co-scientist-pipeline",
            override=False,
            rationale=["Safety iteration limit (20) reached."],
        )

        result = _run_contract_validation(run_dir)

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == "invalid"
        assert any("rationale references safety limit values" in issue["message"] for issue in payload["issues"])
