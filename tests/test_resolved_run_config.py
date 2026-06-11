from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.host.host_agent_surface import bootstrap_host_agent_run
from tools.host.host_config import HostSettings
from tools.policy.resolve_run_config import resolve_run_config_for_path
from tools.policy.validate_resolved_config import validate_resolved_config_for_run


def _write_config(run_dir: Path, *, max_iterations: int = 6, num_debaters: int = 3) -> Path:
    input_path = run_dir / "input.md"
    input_path.write_text("# Resolved Config Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
    config_path = run_dir / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "input_file: input.md",
                "",
                "policy:",
                "  exploration_mode: aggressive",
                "",
                "generation:",
                "  scientific_debates_generation:",
                "    enabled: true",
                f"    num_debaters: {num_debaters}",
                "    max_debate_turns: 9",
                "",
                "ranking:",
                "  placement_match_count: 30",
                "  tournament_top_k: 18",
                "",
                "convergence:",
                "  convergence_count_threshold: 7",
                f"  max_iterations: {max_iterations}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return config_path


def test_bootstrap_host_agent_run_writes_resolved_run_config(monkeypatch) -> None:
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_MODEL", "frozen-embedding")
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_DIMENSIONS", "7")
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_TIMEOUT_SECONDS", "45")
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)

        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        payload = json.loads((run_dir / "state" / "RESOLVED_RUN_CONFIG.json").read_text(encoding="utf-8"))
        assert payload["profile"] == "aggressive"
        assert payload["generation"]["num_debaters"] == 3
        assert payload["generation"]["max_debate_turns"] == 8
        assert payload["ranking"]["placement_match_count"] == 20
        assert payload["ranking"]["tournament_top_k"] == 15
        assert payload["convergence"]["convergence_count_threshold"] == 6
        assert payload["convergence"]["max_iterations"] == 6
        assert payload["convergence"]["safety_max_iterations"] == 8
        assert payload["convergence"]["iteration_cap_source"] == "config_override"
        assert payload["proximity"]["enabled"] is True
        assert payload["proximity"]["provider"] == "fake"
        assert payload["proximity"]["model"] == "frozen-embedding"
        assert payload["proximity"]["dimensions"] == 7
        assert payload["proximity"]["timeout_seconds"] == 45


def test_resolve_run_config_cli_helpers_write_and_validate_resolved_config() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir, max_iterations=4, num_debaters=2)

        resolved = resolve_run_config_for_path(config_path)
        validated, issues = validate_resolved_config_for_run(run_dir)
        settings = HostSettings.from_yaml(config_path)

        assert resolved.profile == "aggressive"
        assert not issues
        assert validated.ranking.tournament_top_k == 15
        assert settings.ranking.tournament_top_k == 15
        assert settings.convergence.max_iterations == 4
        assert settings.convergence.safety_max_iterations == 8


def test_bootstrap_host_agent_run_defaults_to_completion_driven_iteration_semantics() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("# Resolved Config Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text("input_file: input.md\n", encoding="utf-8")

        bootstrap_host_agent_run(
            config_path,
            requested_skill="co-scientist-pipeline",
            resume=False,
            ensure_dashboard=False,
        )

        payload = json.loads((run_dir / "state" / "RESOLVED_RUN_CONFIG.json").read_text(encoding="utf-8"))
        assert payload["convergence"]["max_iterations"] == 0
        assert payload["convergence"]["safety_max_iterations"] == 30
        assert payload["convergence"]["iteration_cap_source"] == "completion_driven_default"


def test_resolve_run_config_allows_proximity_config_overrides(monkeypatch) -> None:
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_MODEL", "env-embedding")
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_DIMENSIONS", "1536")
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("# Resolved Config Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "input_file: input.md",
                    "",
                    "proximity:",
                    "  enabled: false",
                    "  provider: fake",
                    "  model: config-embedding",
                    "  dimensions: 5",
                    "  timeout_seconds: 12",
                    "  base_url_env: CONFIG_BASE_URL",
                    "  api_key_env: CONFIG_API_KEY",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        resolved = resolve_run_config_for_path(config_path)

        assert resolved.proximity.enabled is False
        assert resolved.proximity.provider == "fake"
        assert resolved.proximity.model == "config-embedding"
        assert resolved.proximity.dimensions == 5
        assert resolved.proximity.timeout_seconds == 12
        assert resolved.proximity.base_url_env == "CONFIG_BASE_URL"
        assert resolved.proximity.api_key_env == "CONFIG_API_KEY"


def test_resolve_run_config_uses_gemini_provider_defaults(monkeypatch) -> None:
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_PROVIDER", "gemini")
    monkeypatch.delenv("CO_SCIENTIST_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("CO_SCIENTIST_EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("CO_SCIENTIST_EMBEDDING_API_KEY_ENV", raising=False)
    monkeypatch.delenv("CO_SCIENTIST_EMBEDDING_BASE_URL_ENV", raising=False)
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        config_path = _write_config(run_dir)

        resolved = resolve_run_config_for_path(config_path)

        assert resolved.proximity.provider == "gemini"
        assert resolved.proximity.model == "gemini-embedding-2"
        assert resolved.proximity.dimensions == 768
        assert resolved.proximity.api_key_env == "GEMINI_API_KEY"
        assert resolved.proximity.base_url_env == ""
        assert resolved.proximity.config_hash


def test_resolve_run_config_allows_gemini_proximity_overrides(monkeypatch) -> None:
    monkeypatch.setenv("CO_SCIENTIST_EMBEDDING_PROVIDER", "openai_compatible")
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("# Gemini Config Run\n\nInvestigate adaptive response.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "input_file: input.md",
                    "",
                    "proximity:",
                    "  enabled: true",
                    "  provider: gemini",
                    "  model: gemini-embedding-2",
                    "  dimensions: 1536",
                    "  timeout_seconds: 45",
                    "  api_key_env: CUSTOM_GEMINI_API_KEY",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        resolved = resolve_run_config_for_path(config_path)

        assert resolved.proximity.provider == "gemini"
        assert resolved.proximity.model == "gemini-embedding-2"
        assert resolved.proximity.dimensions == 1536
        assert resolved.proximity.timeout_seconds == 45
        assert resolved.proximity.api_key_env == "CUSTOM_GEMINI_API_KEY"
        assert resolved.proximity.base_url_env == ""
