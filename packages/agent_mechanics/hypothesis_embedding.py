"""Embedding bridge and artifact update helpers for hypothesis proximity."""

from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from packages.agent_contracts import (
    EmbeddingProviderConfigContract,
    HypothesisContract,
    HypothesisEmbeddingResultContract,
    ProximityEmbeddingMetadataContract,
    ProximityEmbeddingReceiptContract,
    ProximityGraphContract,
    ProximityStatusContract,
    ResolvedRunConfigContract,
    proximity_config_hash,
)
from packages.run_artifacts import ArtifactStore, sync_pipeline_stage_artifacts

from .hypothesis_embedding_text import format_hypothesis_for_embedding
from .proximity_update import update_proximity_graph


EmbeddingProvider = Callable[[str, EmbeddingProviderConfigContract], list[float]]

_FALSE_VALUES = {"0", "false", "no", "off"}
_DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"


def _default_proximity_model(provider: str) -> str:
    if provider == "gemini":
        return "gemini-embedding-2"
    if provider == "fake":
        return "fake-embedding"
    return "text-embedding-3-small"


def _default_proximity_dimensions(provider: str) -> int:
    if provider == "gemini":
        return 768
    return 1536


def _default_proximity_api_key_env(provider: str) -> str:
    if provider == "gemini":
        return "GEMINI_API_KEY"
    if provider == "fake":
        return ""
    return "OPENAI_API_KEY"


def _default_proximity_base_url_env(provider: str) -> str:
    if provider in {"gemini", "fake"}:
        return ""
    return "OPENAI_BASE_URL"


def resolve_embedding_provider_config(run_dir: str | Path | None = None) -> EmbeddingProviderConfigContract:
    """Resolve proximity embedding provider settings from run config or environment variables."""
    if run_dir is not None:
        resolved_config_path = Path(run_dir).resolve() / "state" / "RESOLVED_RUN_CONFIG.json"
        if resolved_config_path.exists():
            resolved = ResolvedRunConfigContract.from_json_file(resolved_config_path)
            return EmbeddingProviderConfigContract.model_validate(resolved.proximity.model_dump(mode="json"))
    provider = os.environ.get("CO_SCIENTIST_EMBEDDING_PROVIDER", "openai_compatible").strip() or "openai_compatible"
    enabled_raw = os.environ.get("CO_SCIENTIST_PROXIMITY_ENABLED", "true").strip().lower()
    dimensions_raw = os.environ.get(
        "CO_SCIENTIST_EMBEDDING_DIMENSIONS",
        str(_default_proximity_dimensions(provider)),
    ).strip()
    timeout_raw = os.environ.get("CO_SCIENTIST_EMBEDDING_TIMEOUT_SECONDS", "60").strip()
    try:
        dimensions = int(dimensions_raw)
    except ValueError:
        dimensions = _default_proximity_dimensions(provider)
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError:
        timeout_seconds = 60
    return EmbeddingProviderConfigContract(
        enabled=enabled_raw not in _FALSE_VALUES,
        provider=provider,
        model=os.environ.get("CO_SCIENTIST_EMBEDDING_MODEL", _default_proximity_model(provider)).strip()
        or _default_proximity_model(provider),
        dimensions=max(1, dimensions),
        base_url_env=os.environ.get(
            "CO_SCIENTIST_EMBEDDING_BASE_URL_ENV",
            _default_proximity_base_url_env(provider),
        ).strip()
        or _default_proximity_base_url_env(provider),
        api_key_env=os.environ.get(
            "CO_SCIENTIST_EMBEDDING_API_KEY_ENV",
            _default_proximity_api_key_env(provider),
        ).strip()
        or _default_proximity_api_key_env(provider),
        timeout_seconds=max(1, timeout_seconds),
    )


def input_text_hash(text: str) -> str:
    """Return the stable SHA-256 hash for one embedding input text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_hypothesis_embedding(
    run_dir: str | Path,
    hypothesis_id: str,
    *,
    config: EmbeddingProviderConfigContract | None = None,
    provider: EmbeddingProvider | None = None,
    write_receipt: bool = True,
) -> HypothesisEmbeddingResultContract:
    """Generate a canonical embedding for one hypothesis through the configured provider."""
    resolved_run_dir = Path(run_dir).resolve()
    resolved_config = config or resolve_embedding_provider_config(resolved_run_dir)
    hypothesis_path = resolved_run_dir / "hypotheses" / hypothesis_id / "HYPOTHESIS.json"
    hypothesis = HypothesisContract.from_json_file(hypothesis_path)
    embedding_text = format_hypothesis_for_embedding(hypothesis)
    text_hash = input_text_hash(embedding_text)

    if not resolved_config.enabled:
        result = _embedding_result(
            status="skipped_disabled",
            hypothesis_id=hypothesis_id,
            config=resolved_config,
            text_hash=text_hash,
            reason="Proximity embedding is disabled by configuration.",
        )
        if write_receipt:
            _write_receipt_and_status(resolved_run_dir, _receipt_from_result(result, graph_updated=False))
        return result

    try:
        embedding = _call_embedding_provider(embedding_text, resolved_config, provider=provider)
    except RuntimeError as exc:
        result = _embedding_result(
            status="skipped_provider_unavailable",
            hypothesis_id=hypothesis_id,
            config=resolved_config,
            text_hash=text_hash,
            reason=str(exc),
        )
        if write_receipt:
            _write_receipt_and_status(resolved_run_dir, _receipt_from_result(result, graph_updated=False))
        return result
    except Exception as exc:
        result = _embedding_result(
            status="failed_provider_error",
            hypothesis_id=hypothesis_id,
            config=resolved_config,
            text_hash=text_hash,
            reason=f"Embedding provider call failed: {exc}",
        )
        if write_receipt:
            _write_receipt_and_status(resolved_run_dir, _receipt_from_result(result, graph_updated=False))
        return result

    invalid_reason = _invalid_embedding_reason(embedding, resolved_config.dimensions)
    if invalid_reason:
        result = _embedding_result(
            status="failed_invalid_embedding",
            hypothesis_id=hypothesis_id,
            config=resolved_config,
            text_hash=text_hash,
            reason=invalid_reason,
        )
        if write_receipt:
            _write_receipt_and_status(resolved_run_dir, _receipt_from_result(result, graph_updated=False))
        return result

    result = _embedding_result(
        status="succeeded",
        hypothesis_id=hypothesis_id,
        config=resolved_config,
        text_hash=text_hash,
        embedding=[float(value) for value in embedding],
        reason="Embedding generated successfully.",
    )
    if write_receipt:
        _write_receipt_and_status(resolved_run_dir, _receipt_from_result(result, graph_updated=False))
    return result


def update_hypothesis_proximity(
    run_dir: str | Path,
    hypothesis_id: str,
    *,
    config: EmbeddingProviderConfigContract | None = None,
    provider: EmbeddingProvider | None = None,
) -> ProximityEmbeddingReceiptContract:
    """Generate one embedding, update the proximity graph, and write run-local receipts."""
    resolved_run_dir = Path(run_dir).resolve()
    sync_pipeline_stage_artifacts(
        resolved_run_dir,
        current_phase="Proximity",
        current_skill="hypothesis-proximity-update",
    )
    result = generate_hypothesis_embedding(
        resolved_run_dir,
        hypothesis_id,
        config=config,
        provider=provider,
        write_receipt=False,
    )
    if result.status != "succeeded":
        receipt = _receipt_from_result(result, graph_updated=False)
        _write_receipt_and_status(resolved_run_dir, receipt)
        return receipt

    artifact_store = ArtifactStore(resolved_run_dir)
    graph_payload = artifact_store.read_proximity_graph()
    graph = (
        ProximityGraphContract.from_payload(graph_payload)
        if isinstance(graph_payload, dict)
        else ProximityGraphContract()
    )
    existing_receipt = _receipt_for_existing_graph_embedding(
        graph,
        result,
        proximity_graph_path=str((resolved_run_dir / "state" / "PROXIMITY_GRAPH.json").resolve()),
    )
    if existing_receipt is not None:
        _write_receipt_and_status(resolved_run_dir, existing_receipt)
        return existing_receipt

    updated_graph = update_proximity_graph(graph, hypothesis_id, result.embedding)
    updated_graph.embedding_metadata[hypothesis_id] = ProximityEmbeddingMetadataContract(
        provider=result.provider,
        model=result.model,
        dimensions=result.dimensions,
        config_hash=result.config_hash,
        input_text_hash=result.input_text_hash,
    )
    artifact_store.write_proximity_graph(updated_graph)

    receipt = _receipt_from_result(
        result,
        graph_updated=True,
        proximity_graph_path=str((resolved_run_dir / "state" / "PROXIMITY_GRAPH.json").resolve()),
    )
    _write_receipt_and_status(resolved_run_dir, receipt)
    return receipt


def _receipt_for_existing_graph_embedding(
    graph: ProximityGraphContract,
    result: HypothesisEmbeddingResultContract,
    *,
    proximity_graph_path: str,
) -> ProximityEmbeddingReceiptContract | None:
    existing_embedding = graph.embeddings.get(result.hypothesis_id)
    if existing_embedding is None:
        return None

    existing_metadata = graph.embedding_metadata.get(result.hypothesis_id)
    if (
        existing_metadata is not None
        and existing_metadata.input_text_hash == result.input_text_hash
        and existing_metadata.config_hash == result.config_hash
    ):
        return _receipt_from_result(
            result.model_copy(update={"reason": "Proximity graph already contains the current embedding."}),
            graph_updated=False,
            proximity_graph_path=proximity_graph_path,
        )

    return _receipt_from_result(
        result.model_copy(
            update={
                "status": "failed_invalid_embedding",
                "embedding": [],
                "reason": (
                    "Existing proximity graph embedding was created with different or missing input/config metadata; "
                    "start a new run or rebuild the proximity graph."
                ),
            }
        ),
        graph_updated=False,
        proximity_graph_path=proximity_graph_path,
    )


def _call_embedding_provider(
    text: str,
    config: EmbeddingProviderConfigContract,
    *,
    provider: EmbeddingProvider | None,
) -> list[float]:
    if provider is not None:
        return provider(text, config)
    if config.provider == "fake":
        return _fake_embedding(text, config.dimensions)
    if config.provider == "gemini":
        return _gemini_embedding(text, config)
    if config.provider != "openai_compatible":
        raise RuntimeError(f"Unsupported embedding provider `{config.provider}`.")
    return _openai_compatible_embedding(text, config)


def _openai_compatible_embedding(text: str, config: EmbeddingProviderConfigContract) -> list[float]:
    api_key = os.environ.get(config.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Embedding provider is unavailable because `{config.api_key_env}` is not set.")
    base_url = os.environ.get(config.base_url_env, _DEFAULT_OPENAI_COMPATIBLE_BASE_URL).strip().rstrip("/")
    embeddings_url = f"{base_url}/embeddings"
    _require_http_url(embeddings_url)
    request = urllib.request.Request(  # noqa: S310 - URL scheme is validated before creating the request.
        embeddings_url,
        data=json.dumps({"model": config.model, "input": [text], "dimensions": config.dimensions}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - URL scheme is validated before opening the request.
            request,
            timeout=config.timeout_seconds,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Embedding provider request failed: {exc}") from exc
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError("Embedding provider response did not include `data[0].embedding`.")
    embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(embedding, list):
        raise RuntimeError("Embedding provider response did not include a list embedding.")
    return embedding


def _require_http_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"Embedding provider URL must use http or https, found `{parsed.scheme or 'empty'}`.")


def _gemini_embedding(text: str, config: EmbeddingProviderConfigContract) -> list[float]:
    api_key = os.environ.get(config.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Embedding provider is unavailable because `{config.api_key_env}` is not set.")

    client = _create_gemini_client(api_key=api_key, timeout_seconds=config.timeout_seconds)
    embed_config = _create_gemini_embed_config(config.dimensions)
    result = client.models.embed_content(
        model=config.model,
        contents=text,
        config=embed_config,
    )
    return _extract_gemini_embedding_values(result)


def _create_gemini_client(*, api_key: str, timeout_seconds: int):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Gemini embedding provider requires the `google-genai` package. "
            "Install it with `uv sync --extra gemini` or include `--extra gemini` in uv run."
        ) from exc

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_seconds * 1000))


def _create_gemini_embed_config(dimensions: int):
    try:
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Gemini embedding provider requires the `google-genai` package. "
            "Install it with `uv sync --extra gemini` or include `--extra gemini` in uv run."
        ) from exc

    return types.EmbedContentConfig(output_dimensionality=dimensions)


def _extract_gemini_embedding_values(result: object) -> list[float]:
    embeddings = getattr(result, "embeddings", None)
    if embeddings is None and isinstance(result, dict):
        embeddings = result.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise ValueError("Gemini embedding response did not include `embeddings[0].values`.")

    first_embedding = embeddings[0]
    values = getattr(first_embedding, "values", None)
    if values is None and isinstance(first_embedding, dict):
        values = first_embedding.get("values")
    if not isinstance(values, list):
        raise ValueError("Gemini embedding response did not include a list of values.")
    return values


def _fake_embedding(text: str, dimensions: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        byte = digest[index % len(digest)]
        values.append(round((byte / 255.0) * 2.0 - 1.0, 6))
    return values


def _invalid_embedding_reason(embedding: list[float], expected_dimensions: int) -> str:
    if not isinstance(embedding, list) or not embedding:
        return "Embedding provider returned an empty or non-list embedding."
    if len(embedding) != expected_dimensions:
        return f"Embedding dimensions mismatch: expected {expected_dimensions}, got {len(embedding)}."
    for value in embedding:
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(float(value)):
            return "Embedding provider returned a non-finite numeric value."
    return ""


def _embedding_result(
    *,
    status: str,
    hypothesis_id: str,
    config: EmbeddingProviderConfigContract,
    text_hash: str,
    embedding: list[float] | None = None,
    reason: str,
) -> HypothesisEmbeddingResultContract:
    return HypothesisEmbeddingResultContract(
        status=status,
        hypothesis_id=hypothesis_id,
        provider=config.provider,
        model=config.model,
        dimensions=config.dimensions,
        config_hash=config.config_hash or proximity_config_hash(config),
        input_text_hash=text_hash,
        embedding=embedding or [],
        reason=reason,
    )


def _receipt_from_result(
    result: HypothesisEmbeddingResultContract,
    *,
    graph_updated: bool,
    proximity_graph_path: str = "",
) -> ProximityEmbeddingReceiptContract:
    return ProximityEmbeddingReceiptContract(
        status=result.status,
        hypothesis_id=result.hypothesis_id,
        provider=result.provider,
        model=result.model,
        dimensions=result.dimensions,
        config_hash=result.config_hash,
        input_text_hash=result.input_text_hash,
        graph_updated=graph_updated,
        proximity_graph_path=proximity_graph_path,
        reason=result.reason,
    )


def _write_receipt_and_status(run_dir: Path, receipt: ProximityEmbeddingReceiptContract) -> None:
    receipt_path = run_dir / "state" / "proximity_receipts" / f"{receipt.hypothesis_id}.json"
    updated_receipt = receipt.model_copy(update={"receipt_path": str(receipt_path.resolve())})
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(updated_receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    status = ProximityStatusContract(
        status=updated_receipt.status,
        provider=updated_receipt.provider,
        model=updated_receipt.model,
        dimensions=updated_receipt.dimensions,
        config_hash=updated_receipt.config_hash,
        last_hypothesis_id=updated_receipt.hypothesis_id,
        last_receipt_path=str(receipt_path.resolve()),
        reason=updated_receipt.reason,
        updated_at=datetime.now(UTC),
    )
    status_path = run_dir / "state" / "PROXIMITY_STATUS.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(status.model_dump_json(indent=2) + "\n", encoding="utf-8")


__all__ = [
    "generate_hypothesis_embedding",
    "input_text_hash",
    "resolve_embedding_provider_config",
    "update_hypothesis_proximity",
]
