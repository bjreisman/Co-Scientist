"""Project-facing bootstrap helpers for host-agent and Claude Code flows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from packages.agent_contracts import StrategyPlanContract
from packages.agent_support import PIPELINE_STAGE_GENERATION, build_policy_decision, resolve_run_config
from packages.run_artifacts import ArtifactStore

from ..dashboard import DashboardSupervisor
from ..model_routing import freeze_policy, refresh_summary
from ..policy.plan_strategy import plan_strategy_for_run
from .host_agent import HostAgentHandoff, prepare_host_agent_handoff, write_host_agent_handoff
from .host_config import HostSettings


DashboardSupervisorFactory = Callable[[Path], DashboardSupervisor]


@dataclass(frozen=True)
class HostAgentBootstrapResult:
    """Stable result bundle for one host-agent bootstrap operation."""

    run_dir: Path
    handoff: HostAgentHandoff
    handoff_json_path: Path
    handoff_markdown_path: Path
    dashboard_links: dict[str, str]
    dashboard_runtime: dict[str, object]


@dataclass(frozen=True)
class DashboardLinksResult:
    """Stable dashboard availability result for one run."""

    runtime: dict[str, object]
    links: dict[str, str]


def bootstrap_host_agent_run(
    run_target: Path,
    *,
    requested_skill: str,
    resume: bool,
    ensure_dashboard: bool = True,
    dashboard_supervisor_factory: DashboardSupervisorFactory | None = None,
) -> HostAgentBootstrapResult:
    """Prepare one host-agent run bundle with artifacts and optional dashboard links."""
    settings = HostSettings.from_path(run_target)
    run_dir = Path(settings.run_dir).resolve()
    artifact_store = ArtifactStore(run_dir, top_k_limit=settings.ranking.tournament_top_k)
    bootstrap_notes = (
        _prepare_resumed_control_plane(artifact_store, settings)
        if resume
        else _bootstrap_fresh_control_plane(artifact_store, settings)
    )
    # Capture task model choices once; resume preserves the existing snapshot.
    if freeze_policy(run_dir) is not None:
        refresh_summary(run_dir)

    source_label = Path(settings.config_path).resolve() if settings.config_path else run_dir
    manifest_message = (
        f"Prepared host-agent bootstrap for `{requested_skill}` (resume={str(resume).lower()}) from `{source_label}`."
    )
    artifact_store.append_manifest_entry(manifest_message)
    for note in bootstrap_notes:
        artifact_store.append_manifest_entry(note)

    dashboard_links: dict[str, str] = {}
    dashboard_runtime: dict[str, object] = {"status": "disabled"}
    if ensure_dashboard:
        supervisor_factory = dashboard_supervisor_factory or (lambda runs_dir: DashboardSupervisor(runs_dir))
        supervisor = supervisor_factory(run_dir.parent)
        runtime = supervisor.ensure_started(wait_for_health=False)
        dashboard_runtime = runtime
        dashboard_links = supervisor.build_run_links(run_dir.name, runtime)
        artifact_store.write_dashboard_links(dashboard_links)
        artifact_store.append_manifest_entry("Ensured shared dashboard runtime and run-local links.")

    handoff = prepare_host_agent_handoff(
        run_dir,
        requested_skill=requested_skill,
        resume=resume,
    )
    json_path, markdown_path = write_host_agent_handoff(handoff)
    artifact_store.append_manifest_entry("Wrote host-agent handoff artifacts.")

    return HostAgentBootstrapResult(
        run_dir=run_dir,
        handoff=handoff,
        handoff_json_path=json_path,
        handoff_markdown_path=markdown_path,
        dashboard_links=dashboard_links or handoff.dashboardLinks,
        dashboard_runtime=dashboard_runtime,
    )


def _bootstrap_fresh_control_plane(artifact_store: ArtifactStore, settings: HostSettings) -> list[str]:
    """Create the initial control-plane artifacts for a fresh run."""
    artifact_store.bootstrap()
    artifact_store.write_run_policy(settings.run_policy)
    artifact_store.write_policy_decision(
        build_policy_decision(
            artifact_store.run_dir.name,
            settings.run_policy,
            source=settings.policy_source,
        )
    )
    artifact_store.write_resolved_run_config(resolve_run_config(settings.run_policy, settings.raw_config))
    plan_strategy_for_run(artifact_store.run_dir, current_phase=PIPELINE_STAGE_GENERATION)
    return [
        "Wrote run policy, policy decision, resolved config, and initial strategy plan artifacts.",
    ]


def _prepare_resumed_control_plane(artifact_store: ArtifactStore, settings: HostSettings) -> list[str]:
    """Prepare a resumed run without resetting persisted routing state."""
    artifact_store.prepare_resume_bootstrap()
    notes: list[str] = []

    if artifact_store.read_run_policy() is None:
        artifact_store.write_run_policy(settings.run_policy)
        notes.append("Materialized missing RUN_POLICY.yaml from the effective host settings.")
    if artifact_store.read_policy_decision() is None:
        artifact_store.write_policy_decision(
            build_policy_decision(
                artifact_store.run_dir.name,
                settings.run_policy,
                source=settings.policy_source,
            )
        )
        notes.append("Rebuilt missing POLICY_DECISION.json from the effective run policy.")
    if artifact_store.read_resolved_run_config() is None:
        artifact_store.write_resolved_run_config(resolve_run_config(settings.run_policy, settings.raw_config))
        notes.append("Rebuilt missing RESOLVED_RUN_CONFIG.json from the effective run policy and raw config.")
    if artifact_store.read_current_stage() is None and _restore_current_stage_from_persisted_state(artifact_store):
        notes.append("Reconstructed missing CURRENT_STAGE.json from persisted pipeline artifacts.")

    existing_plan = artifact_store.read_strategy_plan()
    if existing_plan is None:
        plan = plan_strategy_for_run(artifact_store.run_dir)
        notes.append(
            "Rebuilt missing STRATEGY_PLAN.json from persisted routing state "
            f"({plan.current_phase} -> {plan.next_action})."
        )
    else:
        preserved_plan = StrategyPlanContract.from_payload(existing_plan)
        notes.append(
            "Preserved existing control-plane artifacts for resume "
            f"({preserved_plan.current_phase} -> {preserved_plan.next_action})."
        )

    return notes


def _restore_current_stage_from_persisted_state(artifact_store: ArtifactStore) -> bool:
    """Recreate CURRENT_STAGE.json from persisted pipeline state when it is safely derivable."""
    pipeline_state = artifact_store.read_pipeline_state()
    if isinstance(pipeline_state, dict):
        stage = pipeline_state.get("currentPhase")
        stage_trail = pipeline_state.get("stageTrail", [])
        if isinstance(stage, str) and stage:
            artifact_store.write_current_stage(stage, stage_trail if isinstance(stage_trail, list) else [])
            return True

    strategy_plan = artifact_store.read_strategy_plan()
    if isinstance(strategy_plan, dict):
        current_phase = StrategyPlanContract.from_payload(strategy_plan).current_phase
        artifact_store.write_current_stage(current_phase, [current_phase])
        return True

    return False


def ensure_dashboard_links_for_run(
    run_dir: Path,
    *,
    top_k_limit: int = 10,
    dashboard_supervisor_factory: DashboardSupervisorFactory | None = None,
) -> dict[str, str]:
    """Ensure dashboard runtime exists and write deep links for one run directory."""
    return ensure_dashboard_for_run(
        run_dir,
        top_k_limit=top_k_limit,
        dashboard_supervisor_factory=dashboard_supervisor_factory,
    ).links


def ensure_dashboard_for_run(
    run_dir: Path,
    *,
    top_k_limit: int = 10,
    dashboard_supervisor_factory: DashboardSupervisorFactory | None = None,
    wait_for_health: bool = True,
) -> DashboardLinksResult:
    """Ensure dashboard runtime exists and return runtime metadata plus run links."""
    run_dir = run_dir.resolve()
    artifact_store = ArtifactStore(run_dir, top_k_limit=top_k_limit)
    artifact_store.ensure_layout()

    supervisor_factory = dashboard_supervisor_factory or (lambda runs_dir: DashboardSupervisor(runs_dir))
    supervisor = supervisor_factory(run_dir.parent)
    runtime = supervisor.ensure_started(wait_for_health=wait_for_health)
    links = supervisor.build_run_links(run_dir.name, runtime)
    artifact_store.write_dashboard_links(links)
    artifact_store.append_manifest_entry("Refreshed dashboard links through the shared dashboard supervisor.")
    return DashboardLinksResult(runtime=runtime, links=links)


__all__ = [
    "DashboardLinksResult",
    "HostAgentBootstrapResult",
    "bootstrap_host_agent_run",
    "ensure_dashboard_for_run",
    "ensure_dashboard_links_for_run",
]
