"""Export shared agent contract schemas for downstream consumers."""

from __future__ import annotations

import json
from pathlib import Path

from . import (
    CompletionDecisionContract,
    CoScientistStateContract,
    EvidenceBundleContract,
    EvolutionStateContract,
    HypothesisContract,
    HypothesisEmbeddingResultContract,
    HypothesisMatchupContract,
    IslandStateContract,
    MetaReviewContract,
    ProximityEmbeddingReceiptContract,
    ProximityGraphContract,
    ProximityStatusContract,
    RankingUpdateReceiptContract,
    ResearchPlanContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
    TournamentMatchContract,
)


SCHEMA_MODELS = {
    "co_scientist_state.schema.json": CoScientistStateContract,
    "completion_decision.schema.json": CompletionDecisionContract,
    "evidence_bundle.schema.json": EvidenceBundleContract,
    "evolution_state.schema.json": EvolutionStateContract,
    "hypothesis_embedding_result.schema.json": HypothesisEmbeddingResultContract,
    "hypothesis.schema.json": HypothesisContract,
    "hypothesis_matchup.schema.json": HypothesisMatchupContract,
    "island_state.schema.json": IslandStateContract,
    "meta_review.schema.json": MetaReviewContract,
    "proximity_embedding_receipt.schema.json": ProximityEmbeddingReceiptContract,
    "proximity_graph.schema.json": ProximityGraphContract,
    "proximity_status.schema.json": ProximityStatusContract,
    "ranking_update_receipt.schema.json": RankingUpdateReceiptContract,
    "research_plan.schema.json": ResearchPlanContract,
    "search_provider_receipt.schema.json": SearchProviderReceiptContract,
    "search_request.schema.json": SearchRequestContract,
    "tournament_match.schema.json": TournamentMatchContract,
}


def export_agent_contract_schemas(root: Path | None = None) -> list[Path]:
    """Write the current shared agent contracts as JSON schema files."""
    package_root = root or Path(__file__).resolve().parent
    schema_root = package_root / "schema"
    schema_root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, model in SCHEMA_MODELS.items():
        path = schema_root / filename
        path.write_text(
            json.dumps(model.model_json_schema(by_alias=True), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


if __name__ == "__main__":
    export_agent_contract_schemas()
