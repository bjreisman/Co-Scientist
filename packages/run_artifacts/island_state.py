"""Run-level helpers for canonical island state persistence."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from packages.agent_contracts import CoScientistStateContract, HypothesisContract, IslandStateContract

from .artifact_io import ArtifactStore


class RunIslandRewardUpdateResult(BaseModel):
    """Result of applying and persisting one single-island reward update."""

    model_config = ConfigDict(frozen=True)

    selected_island_id: str = Field(description="The island selected for the single-island update.")
    candidate_hypothesis_id: str = Field(description="The hypothesis used to compute the update reward.")
    reward: float = Field(description="The normalized reward returned by the canonical island helper.")
    decay_factor: float = Field(description="The decay factor applied to all persisted islands.")
    updated_islands: dict[str, IslandStateContract] = Field(description="Canonical island state after the update.")
    path: str = Field(description="Absolute path to the persisted islands/ISLANDS.json artifact.")


class RunIslandInitializationResult(BaseModel):
    """Result of ensuring canonical unvisited island state for hypotheses."""

    model_config = ConfigDict(frozen=True)

    initialized_island_ids: list[str] = Field(description="Island IDs created during this call.")
    preserved_island_ids: list[str] = Field(description="Island IDs already present before this call.")
    path: str = Field(description="Absolute path to the persisted islands/ISLANDS.json artifact.")


def load_run_hypotheses(run_dir: str | Path) -> dict[str, HypothesisContract]:
    """Load all canonical hypothesis artifacts for one run."""
    resolved_run_dir = Path(run_dir).resolve()
    hypotheses_root = resolved_run_dir / "hypotheses"
    if not hypotheses_root.exists():
        return {}

    hypotheses: dict[str, HypothesisContract] = {}
    for hypothesis_dir in sorted(path for path in hypotheses_root.iterdir() if path.is_dir()):
        hypothesis_path = hypothesis_dir / "HYPOTHESIS.json"
        if not hypothesis_path.exists():
            continue
        hypothesis = HypothesisContract.from_json_file(hypothesis_path)
        if hypothesis.id:
            hypotheses[hypothesis.id] = hypothesis
    return hypotheses


def load_run_islands(
    run_dir: str | Path,
    hypotheses: dict[str, HypothesisContract] | None = None,
) -> dict[str, IslandStateContract]:
    """Load canonical run island state and fill missing hypothesis islands with defaults."""
    resolved_run_dir = Path(run_dir).resolve()
    islands_path = resolved_run_dir / "islands" / "ISLANDS.json"
    islands: dict[str, IslandStateContract] = {}
    if islands_path.exists():
        payload = json.loads(islands_path.read_text(encoding="utf-8"))
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                island = IslandStateContract.from_payload(item)
                if island.id:
                    islands[island.id] = island

    for hypothesis in (hypotheses or {}).values():
        if hypothesis.island_id and hypothesis.island_id not in islands:
            islands[hypothesis.island_id] = IslandStateContract(id=hypothesis.island_id)
    return islands


def persist_run_islands(
    run_dir: str | Path,
    islands: dict[str, IslandStateContract],
    *,
    hypotheses: dict[str, HypothesisContract] | None = None,
    top_k_limit: int = 10,
) -> str:
    """Persist canonical island state to islands/ISLANDS.json."""
    resolved_run_dir = Path(run_dir).resolve()
    state = CoScientistStateContract(
        hypotheses=hypotheses or {},
        islands=islands,
    )
    store = ArtifactStore(resolved_run_dir, top_k_limit=top_k_limit)
    store.ensure_layout()
    store.write_islands(state)
    return str((resolved_run_dir / "islands" / "ISLANDS.json").resolve())


def ensure_run_islands_for_hypotheses(
    run_dir: str | Path,
    hypothesis_ids: list[str] | None = None,
    *,
    top_k_limit: int = 10,
) -> RunIslandInitializationResult:
    """Ensure selected viable hypotheses have canonical unvisited island items."""
    hypotheses = load_run_hypotheses(run_dir)
    if hypothesis_ids is None:
        target_hypotheses = [hypothesis for hypothesis in hypotheses.values() if hypothesis.is_viable]
    else:
        target_hypotheses = []
        for hypothesis_id in hypothesis_ids:
            hypothesis = hypotheses.get(hypothesis_id)
            if hypothesis is None:
                raise ValueError(f"Unknown hypothesis `{hypothesis_id}`.")
            target_hypotheses.append(hypothesis)

    islands = load_run_islands(run_dir)
    initialized_island_ids: list[str] = []
    preserved_island_ids: list[str] = []
    for hypothesis in target_hypotheses:
        if not hypothesis.is_viable:
            continue
        if not hypothesis.island_id:
            raise ValueError(f"Hypothesis `{hypothesis.id}` must have a non-empty island_id.")
        if hypothesis.island_id in islands:
            preserved_island_ids.append(hypothesis.island_id)
            continue
        islands[hypothesis.island_id] = IslandStateContract(id=hypothesis.island_id)
        initialized_island_ids.append(hypothesis.island_id)

    path = persist_run_islands(run_dir, islands, hypotheses=hypotheses, top_k_limit=top_k_limit)
    return RunIslandInitializationResult(
        initialized_island_ids=sorted(initialized_island_ids),
        preserved_island_ids=sorted(set(preserved_island_ids)),
        path=path,
    )


def update_run_single_island_reward(
    run_dir: str | Path,
    selected_island_id: str,
    candidate_hypothesis_id: str,
    decay_factor: float,
    *,
    top_k_limit: int = 10,
) -> RunIslandRewardUpdateResult:
    """Compute, apply, and persist one canonical single-island reward update."""
    if not selected_island_id:
        raise ValueError("selected_island_id must be non-empty.")
    if not candidate_hypothesis_id:
        raise ValueError("candidate_hypothesis_id must be non-empty.")

    hypotheses = load_run_hypotheses(run_dir)
    candidate = hypotheses.get(candidate_hypothesis_id)
    if candidate is None:
        raise ValueError(f"Unknown candidate hypothesis `{candidate_hypothesis_id}`.")

    islands = load_run_islands(run_dir, hypotheses)
    if selected_island_id not in islands:
        islands[selected_island_id] = IslandStateContract(id=selected_island_id)

    from packages.agent_mechanics.island_reward_update import update_single_island_reward

    reward = update_single_island_reward(
        islands,
        hypotheses,
        selected_island_id,
        candidate,
        decay_factor,
    )
    path = persist_run_islands(run_dir, islands, hypotheses=hypotheses, top_k_limit=top_k_limit)
    return RunIslandRewardUpdateResult(
        selected_island_id=selected_island_id,
        candidate_hypothesis_id=candidate_hypothesis_id,
        reward=reward,
        decay_factor=decay_factor,
        updated_islands=islands,
        path=path,
    )


__all__ = [
    "RunIslandInitializationResult",
    "RunIslandRewardUpdateResult",
    "ensure_run_islands_for_hypotheses",
    "load_run_hypotheses",
    "load_run_islands",
    "persist_run_islands",
    "update_run_single_island_reward",
]
