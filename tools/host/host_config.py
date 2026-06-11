"""Minimal host-agent settings loaded from run-local artifacts or compatibility YAML."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.agent_contracts import ResolvedRunConfigContract, RunPolicyContract
from packages.agent_support import build_run_policy_from_config


__all__ = ["HostConvergenceConfig", "HostRankingConfig", "HostSettings"]


class HostRankingConfig(BaseModel):
    """Host-agent-visible ranking configuration."""

    model_config = ConfigDict(extra="ignore")

    tournament_top_k: int = Field(default=10, description="Top-ranked frontier size used by host-agent artifacts.")
    placement_match_count: int = Field(default=10, description="Placement match count used by ranking workflows.")
    elo_k_factor: float = Field(default=32.0, description="Elo update factor used by ranking workflows.")


class HostConvergenceConfig(BaseModel):
    """Host-agent-visible convergence configuration."""

    model_config = ConfigDict(extra="ignore")

    convergence_count_threshold: int = Field(default=3, description="Consecutive no-entry threshold for convergence.")
    max_iterations: int = Field(
        default=0,
        description="Primary semantic iteration cap. `0` means completion-driven mode with no small hard cap.",
    )
    safety_max_iterations: int = Field(
        default=30,
        description="Safety-only iteration ceiling used to prevent non-terminating evolution loops.",
    )


class HostSettings(BaseModel):
    """Top-level host-agent settings loaded from YAML."""

    model_config = ConfigDict(extra="ignore")

    input_file: str = Field(default="input.md", description="Path to the research brief file for the host-agent run.")
    log_file: str = Field(default="co_scientist.log", description="Run-local log file path.")
    config_path: str = Field(default="", exclude=True, description="Resolved path to the YAML config file.")
    run_dir: str = Field(default="", exclude=True, description="Resolved directory containing the YAML config file.")
    raw_config: dict[str, Any] = Field(default_factory=dict, exclude=True, description="Raw YAML payload.")
    run_policy: RunPolicyContract = Field(default_factory=RunPolicyContract, exclude=True)
    policy_source: str = Field(default="", exclude=True, description="Source used to derive the effective run policy.")
    resolved_run_config: ResolvedRunConfigContract | None = Field(default=None, exclude=True)
    ranking: HostRankingConfig = Field(default_factory=HostRankingConfig)
    convergence: HostConvergenceConfig = Field(default_factory=HostConvergenceConfig)

    @field_validator("input_file")
    @classmethod
    def _validate_input_file(cls, value: str) -> str:
        path = Path(value)
        if not path.exists():
            raise ValueError(f"input_file does not exist: {value}")
        if not path.is_file():
            raise ValueError(f"input_file is not a regular file: {value}")
        return value

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """Load host-agent settings from a compatibility YAML configuration file."""
        with open(path, encoding="utf-8") as handle:
            try:
                data: dict[str, Any] = yaml.safe_load(handle) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML in config file: {path}") from exc

        return cls._from_run_dir_payload(path.resolve().parent, data, config_path=path.resolve())

    @classmethod
    def from_run_dir(cls, run_dir: Path) -> Self:
        """Load host-agent settings directly from one run directory."""
        run_dir = run_dir.resolve()
        config_path = run_dir / "config.yaml"
        if config_path.exists():
            return cls.from_yaml(config_path)
        return cls._from_run_dir_payload(run_dir, {}, config_path=None)

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Load host-agent settings from either a run directory or a config path."""
        resolved_path = path.resolve()
        if resolved_path.is_dir():
            return cls.from_run_dir(resolved_path)
        return cls.from_yaml(resolved_path)

    @classmethod
    def _from_run_dir_payload(
        cls,
        run_dir: Path,
        payload: dict[str, Any],
        *,
        config_path: Path | None,
    ) -> Self:
        data = deepcopy(payload)
        raw_config = deepcopy(payload)

        if "input_file" not in data:
            data["input_file"] = "input.md"
        if "log_file" not in data:
            data["log_file"] = "co_scientist.log"

        for key in ("input_file", "log_file"):
            if key in data and not Path(data[key]).is_absolute():
                data[key] = str((run_dir / data[key]).resolve())

        data["config_path"] = str(config_path.resolve()) if config_path is not None else ""
        data["run_dir"] = str(run_dir)
        resolved_run_config_path = run_dir / "state" / "RESOLVED_RUN_CONFIG.json"
        resolved_run_config = (
            ResolvedRunConfigContract.from_json_file(resolved_run_config_path)
            if resolved_run_config_path.exists()
            else None
        )
        run_policy_path = run_dir / "RUN_POLICY.yaml"
        if run_policy_path.exists():
            run_policy = RunPolicyContract.from_yaml_file(run_policy_path)
            policy_source = str(run_policy_path.resolve())
        else:
            run_policy = build_run_policy_from_config(
                raw_config,
                run_dir=run_dir,
                input_file=str(data.get("input_file", "")),
                log_file=str(data.get("log_file", "co_scientist.log")),
            )
            policy_source = str(config_path.resolve()) if config_path is not None else "<run-defaults>"

        if resolved_run_config is not None:
            ranking_payload = dict(data.get("ranking", {})) if isinstance(data.get("ranking"), dict) else {}
            ranking_payload["tournament_top_k"] = resolved_run_config.ranking.tournament_top_k
            ranking_payload["placement_match_count"] = resolved_run_config.ranking.placement_match_count
            ranking_payload["elo_k_factor"] = resolved_run_config.ranking.elo_k_factor
            data["ranking"] = ranking_payload

            convergence_payload = (
                dict(data.get("convergence", {})) if isinstance(data.get("convergence"), dict) else {}
            )
            convergence_payload["convergence_count_threshold"] = (
                resolved_run_config.convergence.convergence_count_threshold
            )
            convergence_payload["max_iterations"] = resolved_run_config.convergence.max_iterations
            convergence_payload["safety_max_iterations"] = resolved_run_config.convergence.safety_max_iterations
            data["convergence"] = convergence_payload

        data["raw_config"] = raw_config
        data["run_policy"] = run_policy
        data["policy_source"] = policy_source
        data["resolved_run_config"] = resolved_run_config
        return cls(**data)
