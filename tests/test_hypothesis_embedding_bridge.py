from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from packages.agent_contracts import (
    CoScientistStateContract,
    EmbeddingProviderConfigContract,
    ResearchPlanContract,
    ResolvedRunConfigContract,
)
from packages.agent_mechanics import generate_hypothesis_embedding, update_hypothesis_proximity
from packages.run_artifacts import ArtifactStore
from tests.conftest import build_hypothesis


class _FakeGeminiEmbedding:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class _FakeGeminiResult:
    def __init__(self, values: list[float]) -> None:
        self.embeddings = [_FakeGeminiEmbedding(values)]


class _FakeGeminiModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def embed_content(self, **kwargs: object) -> _FakeGeminiResult:
        self.calls.append(kwargs)
        return _FakeGeminiResult([0.1, 0.2, 0.3])


class _FakeGeminiClient:
    latest: _FakeGeminiClient | None = None

    def __init__(self, *, api_key: str, timeout_seconds: int) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.models = _FakeGeminiModels()
        _FakeGeminiClient.latest = self


def _prepare_run(run_dir: Path) -> None:
    store = ArtifactStore(run_dir, top_k_limit=2)
    store.bootstrap()
    hypothesis = build_hypothesis("hyp-001", 1230.0, "island-001")
    state = CoScientistStateContract(
        research_plan=ResearchPlanContract(status="completed", research_goal="Test proximity embeddings."),
        hypotheses={hypothesis.id: hypothesis},
    )
    store.write_research_plan(state.research_plan)
    store.write_hypothesis(hypothesis)
    store.write_pipeline_state(
        state,
        mode="host-agent",
        status="running",
        current_phase="Generation",
        current_skill="hypothesis-generation-pipeline",
        stage_trail=["Generation"],
    )


def test_generate_hypothesis_embedding_uses_fake_provider_and_writes_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        result = generate_hypothesis_embedding(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )

        receipt_path = run_dir / "state" / "proximity_receipts" / "hyp-001.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        status = json.loads((run_dir / "state" / "PROXIMITY_STATUS.json").read_text(encoding="utf-8"))

        assert result.status == "succeeded"
        assert len(result.embedding) == 3
        assert receipt["status"] == "succeeded"
        assert receipt["graph_updated"] is False
        assert status["last_hypothesis_id"] == "hyp-001"
        assert receipt["config_hash"]
        assert status["config_hash"] == receipt["config_hash"]


def test_generate_hypothesis_embedding_records_provider_unavailable_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        result = generate_hypothesis_embedding(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(provider="openai_compatible", dimensions=3),
        )

        receipt = json.loads((run_dir / "state" / "proximity_receipts" / "hyp-001.json").read_text(encoding="utf-8"))
        assert result.status == "skipped_provider_unavailable"
        assert result.embedding == []
        assert receipt["graph_updated"] is False
        assert "OPENAI_API_KEY" in receipt["reason"]


def test_generate_hypothesis_embedding_prefers_run_resolved_config(monkeypatch) -> None:
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_MODEL", "env-embedding")
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_DIMENSIONS", "9")
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)
        ArtifactStore(run_dir).write_resolved_run_config(
            ResolvedRunConfigContract.from_payload(
                {
                    "proximity": {
                        "provider": "fake",
                        "model": "frozen-embedding",
                        "dimensions": 4,
                        "timeout_seconds": 15,
                    }
                }
            )
        )

        result = generate_hypothesis_embedding(run_dir, "hyp-001")

        receipt = json.loads((run_dir / "state" / "proximity_receipts" / "hyp-001.json").read_text(encoding="utf-8"))
        assert result.status == "succeeded"
        assert result.provider == "fake"
        assert result.model == "frozen-embedding"
        assert len(result.embedding) == 4
        assert receipt["model"] == "frozen-embedding"
        assert receipt["dimensions"] == 4


def test_update_hypothesis_proximity_updates_graph_stage_and_receipt() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        receipt = update_hypothesis_proximity(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )

        graph = json.loads((run_dir / "state" / "PROXIMITY_GRAPH.json").read_text(encoding="utf-8"))
        pipeline_state = json.loads((run_dir / "state" / "PIPELINE_STATE.json").read_text(encoding="utf-8"))
        current_stage = json.loads((run_dir / "state" / "CURRENT_STAGE.json").read_text(encoding="utf-8"))
        persisted_receipt = json.loads(
            (run_dir / "state" / "proximity_receipts" / "hyp-001.json").read_text(encoding="utf-8")
        )

        assert receipt.status == "succeeded"
        assert receipt.graph_updated is True
        assert len(graph["embeddings"]["hyp-001"]) == 3
        assert graph["embedding_metadata"]["hyp-001"]["input_text_hash"] == persisted_receipt["input_text_hash"]
        assert graph["embedding_metadata"]["hyp-001"]["config_hash"] == persisted_receipt["config_hash"]
        assert pipeline_state["currentPhase"] == "Proximity"
        assert current_stage["stage"] == "Proximity"
        assert persisted_receipt["graph_updated"] is True
        assert persisted_receipt["input_text_hash"]


def test_update_hypothesis_proximity_is_idempotent_for_current_graph_embedding() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)
        config = EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3)

        first_receipt = update_hypothesis_proximity(run_dir, "hyp-001", config=config)
        second_receipt = update_hypothesis_proximity(run_dir, "hyp-001", config=config)

        graph = json.loads((run_dir / "state" / "PROXIMITY_GRAPH.json").read_text(encoding="utf-8"))
        assert first_receipt.status == "succeeded"
        assert first_receipt.graph_updated is True
        assert second_receipt.status == "succeeded"
        assert second_receipt.graph_updated is False
        assert "already contains the current embedding" in second_receipt.reason
        assert len(graph["embeddings"]["hyp-001"]) == 3


def test_update_hypothesis_proximity_rejects_config_drift_for_existing_embedding() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        first_receipt = update_hypothesis_proximity(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(provider="fake", model="fake-embedding", dimensions=3),
        )
        drift_receipt = update_hypothesis_proximity(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(provider="fake", model="other-embedding", dimensions=4),
        )

        graph = json.loads((run_dir / "state" / "PROXIMITY_GRAPH.json").read_text(encoding="utf-8"))
        assert first_receipt.status == "succeeded"
        assert drift_receipt.status == "failed_invalid_embedding"
        assert drift_receipt.graph_updated is False
        assert "different or missing input/config metadata" in drift_receipt.reason
        assert len(graph["embeddings"]["hyp-001"]) == 3
        assert graph["embedding_metadata"]["hyp-001"]["model"] == "fake-embedding"


def test_generate_hypothesis_embedding_uses_gemini_provider(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "packages.agent_mechanics.hypothesis_embedding._create_gemini_client",
        _FakeGeminiClient,
        raising=False,
    )
    monkeypatch.setattr(
        "packages.agent_mechanics.hypothesis_embedding._create_gemini_embed_config",
        lambda dimensions: {"output_dimensionality": dimensions},
        raising=False,
    )
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        result = generate_hypothesis_embedding(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=3,
                api_key_env="GEMINI_API_KEY",
            ),
        )

        assert result.status == "succeeded"
        assert result.provider == "gemini"
        assert result.model == "gemini-embedding-2"
        assert result.embedding == [0.1, 0.2, 0.3]
        assert _FakeGeminiClient.latest is not None
        assert _FakeGeminiClient.latest.api_key == "test-key"
        assert _FakeGeminiClient.latest.timeout_seconds == 60
        call = _FakeGeminiClient.latest.models.calls[0]
        assert call["model"] == "gemini-embedding-2"
        assert call["config"] == {"output_dimensionality": 3}
        assert isinstance(call["contents"], str)
        assert "Hypothesis ID: hyp-001" in call["contents"]


def test_generate_hypothesis_embedding_records_gemini_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        result = generate_hypothesis_embedding(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=3,
                api_key_env="GEMINI_API_KEY",
            ),
        )

        assert result.status == "skipped_provider_unavailable"
        assert result.embedding == []
        assert "GEMINI_API_KEY" in result.reason


def test_generate_hypothesis_embedding_records_gemini_sdk_unavailable(monkeypatch) -> None:
    def unavailable_client(*, api_key: str, timeout_seconds: int) -> object:
        raise RuntimeError("Gemini embedding provider requires the `google-genai` package.")

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "packages.agent_mechanics.hypothesis_embedding._create_gemini_client",
        unavailable_client,
        raising=False,
    )
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        result = generate_hypothesis_embedding(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=3,
                api_key_env="GEMINI_API_KEY",
            ),
        )

        assert result.status == "skipped_provider_unavailable"
        assert "google-genai" in result.reason


def test_generate_hypothesis_embedding_records_invalid_gemini_response(monkeypatch) -> None:
    class BadClient:
        def __init__(self, *, api_key: str, timeout_seconds: int) -> None:
            self.models = self

        def embed_content(self, **kwargs: object) -> object:
            return object()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "packages.agent_mechanics.hypothesis_embedding._create_gemini_client",
        BadClient,
        raising=False,
    )
    monkeypatch.setattr(
        "packages.agent_mechanics.hypothesis_embedding._create_gemini_embed_config",
        lambda dimensions: {"output_dimensionality": dimensions},
        raising=False,
    )
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        result = generate_hypothesis_embedding(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=3,
                api_key_env="GEMINI_API_KEY",
            ),
        )

        assert result.status == "failed_provider_error"
        assert "Embedding provider call failed" in result.reason


def test_generate_hypothesis_embedding_rejects_gemini_dimension_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "packages.agent_mechanics.hypothesis_embedding._create_gemini_client",
        _FakeGeminiClient,
        raising=False,
    )
    monkeypatch.setattr(
        "packages.agent_mechanics.hypothesis_embedding._create_gemini_embed_config",
        lambda dimensions: {"output_dimensionality": dimensions},
        raising=False,
    )
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        _prepare_run(run_dir)

        result = generate_hypothesis_embedding(
            run_dir,
            "hyp-001",
            config=EmbeddingProviderConfigContract(
                provider="gemini",
                model="gemini-embedding-2",
                dimensions=4,
                api_key_env="GEMINI_API_KEY",
            ),
        )

        assert result.status == "failed_invalid_embedding"
        assert "expected 4, got 3" in result.reason
