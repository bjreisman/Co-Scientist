from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tools.host.host_config import HostSettings


def test_host_settings_from_yaml_supports_minimal_host_agent_config() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("Investigate a host-agent-only run.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text("input_file: input.md\n", encoding="utf-8")

        settings = HostSettings.from_yaml(config_path)

        assert settings.input_file == str(input_path.resolve())
        assert settings.log_file == str((run_dir / "co_scientist.log").resolve())
        assert settings.ranking.tournament_top_k == 10
        assert settings.convergence.convergence_count_threshold == 3
        assert settings.convergence.max_iterations == 0
        assert settings.convergence.safety_max_iterations == 30
        assert settings.run_policy.policy.exploration_mode == "balanced"
        assert settings.run_policy.policy.iteration_policy == "completion_driven"
        assert settings.run_policy.policy.iteration_band is None
        assert settings.run_policy.policy.allowed_generation_strategies == [
            "literature_exploration_generation",
            "scientific_debates_generation",
            "assumptions_identification_generation",
        ]


def test_host_settings_builds_run_policy_from_config_sections() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("Investigate a host-agent-only run.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "input_file: input.md",
                    "",
                    "generation:",
                    "  literature_exploration_generation: true",
                    "  scientific_debates_generation:",
                    "    enabled: false",
                    "  assumptions_identification_generation: false",
                    "",
                    "reflection:",
                    "  full_review: true",
                    "  deep_verification_review: true",
                    "  observation_review: false",
                    "  simulation_review: false",
                    "",
                    "policy:",
                    "  stop_policy: strict",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        settings = HostSettings.from_yaml(config_path)

        assert settings.run_policy.policy.generation_bias == "literature_heavy"
        assert settings.run_policy.policy.review_rigor == "standard"
        assert settings.run_policy.policy.budget_profile == "medium"
        assert settings.run_policy.policy.allowed_generation_strategies == ["literature_exploration_generation"]
        assert settings.run_policy.policy.allowed_review_modes == [
            "full_review",
            "deep_verification_review",
            "observation_review",
            "simulation_review",
        ]
        assert settings.run_policy.policy.stop_policy == "strict"
        assert settings.run_policy.policy.iteration_policy == "completion_driven"


def test_host_settings_does_not_infer_low_budget_from_legacy_review_subset_hints() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("Investigate a host-agent-only run.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "input_file: input.md",
                    "",
                    "generation:",
                    "  literature_exploration_generation: true",
                    "  scientific_debates_generation:",
                    "    enabled: false",
                    "  assumptions_identification_generation: false",
                    "",
                    "reflection:",
                    "  full_review: true",
                    "  deep_verification_review: false",
                    "  observation_review: false",
                    "  simulation_review: false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        settings = HostSettings.from_yaml(config_path)

        assert settings.run_policy.policy.allowed_review_modes == [
            "full_review",
            "deep_verification_review",
            "observation_review",
            "simulation_review",
        ]
        assert settings.run_policy.policy.budget_profile == "medium"


def test_host_settings_normalizes_explicit_review_mode_subsets_to_full_stack() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("Investigate a host-agent-only run.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "input_file: input.md",
                    "",
                    "policy:",
                    "  review_rigor: light",
                    "  allowed_review_modes:",
                    "    - full_review",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        settings = HostSettings.from_yaml(config_path)

        assert settings.run_policy.policy.review_rigor == "light"
        assert settings.run_policy.policy.allowed_review_modes == [
            "full_review",
            "deep_verification_review",
            "observation_review",
            "simulation_review",
        ]


def test_host_settings_prefers_resolved_run_config_when_present() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        state_dir = run_dir / "state"
        state_dir.mkdir(parents=True)
        input_path = run_dir / "input.md"
        input_path.write_text("Investigate a host-agent-only run.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text("input_file: input.md\n", encoding="utf-8")
        (state_dir / "RESOLVED_RUN_CONFIG.json").write_text(
            """
{
  "profile": "aggressive",
  "generation": {
    "num_debaters": 4,
    "max_debate_turns": 6
  },
  "island": {
    "ucb_exploration_constant": 1.4,
    "decay_factor": 0.85,
    "softmax_temperature": 1.1,
    "stagnation_epsilon": 0.08
  },
  "ranking": {
    "placement_match_count": 12,
    "tournament_top_k": 10,
    "elo_k_factor": 32.0
  },
  "convergence": {
    "convergence_count_threshold": 4,
    "max_iterations": 8
  }
}
""".strip()
            + "\n",
            encoding="utf-8",
        )

        settings = HostSettings.from_yaml(config_path)

        assert settings.resolved_run_config is not None
        assert settings.ranking.tournament_top_k == 10
        assert settings.ranking.placement_match_count == 12
        assert settings.convergence.convergence_count_threshold == 4
        assert settings.convergence.max_iterations == 8
        assert settings.convergence.safety_max_iterations == 30


def test_host_settings_from_run_dir_supports_default_input_without_config_yaml() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("Investigate a host-agent-only run.\n", encoding="utf-8")

        settings = HostSettings.from_run_dir(run_dir)

        assert settings.input_file == str(input_path.resolve())
        assert settings.log_file == str((run_dir / "co_scientist.log").resolve())
        assert settings.config_path == ""
        assert settings.run_policy.policy.exploration_mode == "balanced"
        assert settings.run_policy.policy.iteration_policy == "completion_driven"
        assert settings.convergence.max_iterations == 0
        assert settings.convergence.safety_max_iterations == 30


def test_host_settings_infers_capped_iteration_policy_from_legacy_max_iterations() -> None:
    with TemporaryDirectory() as temp_dir:
        run_dir = Path(temp_dir) / "run"
        run_dir.mkdir()
        input_path = run_dir / "input.md"
        input_path.write_text("Investigate a host-agent-only run.\n", encoding="utf-8")
        config_path = run_dir / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "input_file: input.md",
                    "",
                    "convergence:",
                    "  max_iterations: 9",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        settings = HostSettings.from_yaml(config_path)

        assert settings.run_policy.policy.iteration_policy == "capped"
        assert settings.run_policy.policy.iteration_band == "6_10"
