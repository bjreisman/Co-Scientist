"""Append-only evolution round replay artifact helpers."""

from __future__ import annotations

from pathlib import Path

from packages.agent_contracts import EvolutionRoundRecordContract
from packages.run_artifacts.artifact_io import ArtifactStore


def append_evolution_round_record(
    run_dir: str | Path,
    record: EvolutionRoundRecordContract | dict[str, object],
) -> EvolutionRoundRecordContract:
    """Append one validated evolution round record to `state/EVOLUTION_ROUNDS.jsonl`."""
    normalized = (
        record
        if isinstance(record, EvolutionRoundRecordContract)
        else EvolutionRoundRecordContract.from_payload(record)
    )
    return ArtifactStore(Path(run_dir)).append_evolution_round_record(normalized)


def load_evolution_round_records(run_dir: str | Path) -> list[EvolutionRoundRecordContract]:
    """Load validated evolution round records from `state/EVOLUTION_ROUNDS.jsonl`."""
    return ArtifactStore(Path(run_dir)).read_evolution_round_records()


__all__ = ["append_evolution_round_record", "load_evolution_round_records"]
