"""Contracts for proximity embedding bridge results and receipts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ProximityEmbeddingStatus = Literal[
    "succeeded",
    "skipped_disabled",
    "skipped_provider_unavailable",
    "failed_provider_error",
    "failed_invalid_embedding",
]


class EmbeddingProviderConfigContract(BaseModel):
    """Resolved provider settings for one proximity embedding call."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(default=True)
    provider: str = Field(default="openai_compatible")
    model: str = Field(default="text-embedding-3-small")
    dimensions: int = Field(default=1536)
    base_url_env: str = Field(default="OPENAI_BASE_URL")
    api_key_env: str = Field(default="OPENAI_API_KEY")
    timeout_seconds: int = Field(default=60)
    config_hash: str = Field(default="")


class HypothesisEmbeddingResultContract(BaseModel):
    """Result of generating one canonical hypothesis embedding."""

    model_config = ConfigDict(extra="ignore")

    status: ProximityEmbeddingStatus = Field(default="skipped_provider_unavailable")
    hypothesis_id: str = Field(default="")
    provider: str = Field(default="")
    model: str = Field(default="")
    dimensions: int = Field(default=0)
    config_hash: str = Field(default="")
    input_text_hash: str = Field(default="")
    embedding: list[float] = Field(default_factory=list)
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> HypothesisEmbeddingResultContract:
        """Validate a raw embedding result payload."""
        return cls.model_validate(payload)


class ProximityEmbeddingReceiptContract(BaseModel):
    """Run-local receipt for one hypothesis proximity update attempt."""

    model_config = ConfigDict(extra="ignore")

    status: ProximityEmbeddingStatus = Field(default="skipped_provider_unavailable")
    hypothesis_id: str = Field(default="")
    provider: str = Field(default="")
    model: str = Field(default="")
    dimensions: int = Field(default=0)
    config_hash: str = Field(default="")
    input_text_hash: str = Field(default="")
    graph_updated: bool = Field(default=False)
    receipt_path: str = Field(default="")
    proximity_graph_path: str = Field(default="")
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> ProximityEmbeddingReceiptContract:
        """Validate a raw receipt payload."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> ProximityEmbeddingReceiptContract:
        """Load and validate one receipt artifact."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class ProximityStatusContract(BaseModel):
    """Run-level proximity embedding bridge status summary."""

    model_config = ConfigDict(extra="ignore")

    status: ProximityEmbeddingStatus = Field(default="skipped_provider_unavailable")
    provider: str = Field(default="")
    model: str = Field(default="")
    dimensions: int = Field(default=0)
    config_hash: str = Field(default="")
    last_hypothesis_id: str = Field(default="")
    last_receipt_path: str = Field(default="")
    reason: str = Field(default="")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> ProximityStatusContract:
        """Validate a raw run-level proximity status payload."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> ProximityStatusContract:
        """Load and validate a run-level proximity status artifact."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


def proximity_config_hash(config: EmbeddingProviderConfigContract) -> str:
    """Return a stable hash for non-secret embedding provider settings."""
    payload = {
        "enabled": config.enabled,
        "provider": config.provider,
        "model": config.model,
        "dimensions": config.dimensions,
        "base_url_env": config.base_url_env,
        "api_key_env": config.api_key_env,
        "timeout_seconds": config.timeout_seconds,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "EmbeddingProviderConfigContract",
    "HypothesisEmbeddingResultContract",
    "ProximityEmbeddingReceiptContract",
    "ProximityEmbeddingStatus",
    "ProximityStatusContract",
    "proximity_config_hash",
]
