"""Host-agent execution helpers for the top-level skills-first interface."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..validation.contract_validation import HostAgentValidationSummary, validate_run_artifacts
from .host_config import HostSettings


ExecutionModeName = Literal["host-agent"]

TOP_LEVEL_SKILLS = (
    "co-scientist-pipeline",
    "hypothesis-generation-pipeline",
    "hypothesis-review-pipeline",
    "hypothesis-evolution-loop",
    "research-overview-pipeline",
)


class ExecutionModeContract(BaseModel):
    """Stable description of one supported execution mode."""

    model_config = ConfigDict(extra="ignore")

    name: ExecutionModeName
    entrypoint: str
    description: str
    owns_llm_calls: bool
    repository_managed_runtime: bool
    primary_assets: list[str] = Field(default_factory=list)


class HostAgentValidationSnapshot(BaseModel):
    """Handoff-time validation snapshot metadata."""

    generatedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))
    command: str = Field(default="")
    status: Literal["valid", "invalid"] = Field(default="valid")
    errorCount: int = Field(default=0)
    warningCount: int = Field(default=0)
    resumeReady: bool = Field(default=False)
    note: str = Field(
        default="This is a handoff-time validation snapshot. Re-run contract validation for current artifact health."
    )


class HostAgentHandoff(BaseModel):
    """Stable handoff artifact for an external host agent."""

    model_config = ConfigDict(extra="ignore")

    mode: Literal["host-agent"] = Field(default="host-agent")
    runId: str
    runDir: str
    configPath: str
    inputFile: str
    requestedSkill: str
    resume: bool
    skillPath: str
    sharedReferences: dict[str, str]
    artifactPaths: dict[str, str]
    dashboardLinks: dict[str, str] = Field(default_factory=dict)
    validation: HostAgentValidationSummary
    validationSnapshot: HostAgentValidationSnapshot = Field(default_factory=HostAgentValidationSnapshot)
    nextActions: list[str] = Field(default_factory=list)


def get_execution_modes() -> list[ExecutionModeContract]:
    """Return the supported host-agent execution surface."""
    return [
        ExecutionModeContract(
            name="host-agent",
            entrypoint="python -m tools.host.project_cli run <run-dir> --skill co-scientist-pipeline",
            description="Host-agent-first path where an external host consumes skills and tools.",
            owns_llm_calls=False,
            repository_managed_runtime=False,
            primary_assets=["skills/", "packages/agent_contracts/", "runs/<run_id>"],
        ),
    ]


def prepare_host_agent_handoff(
    run_target: Path,
    *,
    requested_skill: str,
    resume: bool,
) -> HostAgentHandoff:
    """Build a handoff artifact for an external host agent."""
    if requested_skill not in TOP_LEVEL_SKILLS:
        raise ValueError(
            f"Unsupported host-agent skill: {requested_skill!r}. Supported top-level skills: "
            f"{', '.join(TOP_LEVEL_SKILLS)}"
        )

    settings = HostSettings.from_path(run_target)
    run_dir = Path(settings.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state").mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parents[2]
    skill_path = repo_root / "skills" / requested_skill / "SKILL.md"
    if not skill_path.is_file():
        raise FileNotFoundError(f"Top-level skill file not found: {skill_path}")

    dashboard_links = _read_dashboard_links(run_dir)
    validation = validate_run_artifacts(run_dir, resume=resume, requested_skill=requested_skill)

    return HostAgentHandoff(
        runId=run_dir.name,
        runDir=str(run_dir),
        configPath=str(Path(settings.config_path).resolve()) if settings.config_path else "",
        inputFile=str(Path(settings.input_file).resolve()),
        requestedSkill=requested_skill,
        resume=resume,
        skillPath=str(skill_path.resolve()),
        sharedReferences={
            "artifactContract": str((repo_root / "skills" / "shared-references" / "artifact-contract.md").resolve()),
            "completionContract": str(
                (repo_root / "skills" / "shared-references" / "completion-contract.md").resolve()
            ),
            "policyContract": str((repo_root / "skills" / "shared-references" / "policy-contract.md").resolve()),
            "resolvedConfigContract": str(
                (repo_root / "skills" / "shared-references" / "resolved-config-contract.md").resolve()
            ),
            "strategyContract": str((repo_root / "skills" / "shared-references" / "strategy-contract.md").resolve()),
            "stateContract": str((repo_root / "skills" / "shared-references" / "state-contract.md").resolve()),
            "codeStructureContract": str(
                (repo_root / "skills" / "shared-references" / "code-structure-contract.md").resolve()
            ),
            "integrationContract": str(
                (repo_root / "skills" / "shared-references" / "integration-contract.md").resolve()
            ),
            "mechanicsIntegrationContract": str(
                (repo_root / "skills" / "shared-references" / "mechanics-integration-contract.md").resolve()
            ),
            "executionModes": str((repo_root / "skills" / "shared-references" / "execution-modes.md").resolve()),
            "schemaIndex": str((repo_root / "skills" / "shared-references" / "schema-index.md").resolve()),
            "startRequestContractPy": str((repo_root / "packages" / "agent_contracts" / "start_request.py").resolve()),
            "runPolicyContractPy": str((repo_root / "packages" / "agent_contracts" / "policy.py").resolve()),
            "policyDecisionContractPy": str((repo_root / "packages" / "agent_contracts" / "policy.py").resolve()),
            "pipelineStateContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "pipeline_runtime.py").resolve()
            ),
            "currentStageContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "pipeline_runtime.py").resolve()
            ),
            "resolvedRunConfigContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "resolved_config.py").resolve()
            ),
            "researchPlanContractPy": str((repo_root / "packages" / "agent_contracts" / "research_plan.py").resolve()),
            "hypothesisContractPy": str((repo_root / "packages" / "agent_contracts" / "hypothesis.py").resolve()),
            "reviewContractPy": str((repo_root / "packages" / "agent_contracts" / "review.py").resolve()),
            "evolutionStateContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "pipeline_control.py").resolve()
            ),
            "evolutionRoundContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "evolution_round.py").resolve()
            ),
            "completionDecisionContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "pipeline_control.py").resolve()
            ),
            "insightsContractPy": str((repo_root / "packages" / "agent_contracts" / "meta_review.py").resolve()),
            "researchOverviewContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "meta_review.py").resolve()
            ),
            "proximityGraphContractPy": str((repo_root / "packages" / "agent_contracts" / "state.py").resolve()),
            "islandStateContractPy": str((repo_root / "packages" / "agent_contracts" / "state.py").resolve()),
            "tournamentMatchContractPy": str((repo_root / "packages" / "agent_contracts" / "ranking.py").resolve()),
            "rankingUpdateReceiptContractPy": str(
                (repo_root / "packages" / "agent_contracts" / "ranking.py").resolve()
            ),
            "strategyPlanContractPy": str((repo_root / "packages" / "agent_contracts" / "strategy_plan.py").resolve()),
        },
        artifactPaths={
            "manifest": str((run_dir / "MANIFEST.md").resolve()),
            "startRequest": str((run_dir / "state" / "START_REQUEST.json").resolve()),
            "runPolicy": str((run_dir / "RUN_POLICY.yaml").resolve()),
            "policyDecision": str((run_dir / "state" / "POLICY_DECISION.json").resolve()),
            "resolvedConfig": str((run_dir / "state" / "RESOLVED_RUN_CONFIG.json").resolve()),
            "strategyPlan": str((run_dir / "state" / "STRATEGY_PLAN.json").resolve()),
            "strategyDecisions": str((run_dir / "state" / "STRATEGY_DECISIONS.jsonl").resolve()),
            "evolutionRounds": str((run_dir / "state" / "EVOLUTION_ROUNDS.jsonl").resolve()),
            "pipelineState": str((run_dir / "state" / "PIPELINE_STATE.json").resolve()),
            "currentStage": str((run_dir / "state" / "CURRENT_STAGE.json").resolve()),
            "evolutionState": str((run_dir / "state" / "EVOLUTION_STATE.json").resolve()),
            "completionDecision": str((run_dir / "state" / "COMPLETION_DECISION.json").resolve()),
            "rankingUpdateReceipts": str((run_dir / "state" / "ranking_update_receipts").resolve()),
            "dashboardLinks": str((run_dir / "dashboard" / "LINKS.json").resolve()),
            "dashboardLinksMarkdown": str((run_dir / "dashboard" / "LINKS.md").resolve()),
        },
        dashboardLinks=dashboard_links,
        validation=validation,
        validationSnapshot=_build_validation_snapshot(
            validation,
            requested_skill=requested_skill,
            resume=resume,
        ),
        nextActions=_build_next_actions(requested_skill, resume, settings),
    )


def _build_validation_snapshot(
    validation: HostAgentValidationSummary,
    *,
    requested_skill: str,
    resume: bool,
) -> HostAgentValidationSnapshot:
    resume_flag = " --resume" if resume else ""
    return HostAgentValidationSnapshot(
        command=f"python -m tools.validation.contract_validation <run_dir>{resume_flag} --skill {requested_skill}",
        status=validation.status,
        errorCount=validation.errorCount,
        warningCount=validation.warningCount,
        resumeReady=validation.resumeReady,
    )


def write_host_agent_handoff(handoff: HostAgentHandoff) -> tuple[Path, Path]:
    """Write the host-agent handoff artifact bundle to the run directory."""
    run_dir = Path(handoff.runDir)
    state_dir = run_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    json_path = state_dir / "HOST_AGENT_HANDOFF.json"
    markdown_path = state_dir / "HOST_AGENT_HANDOFF.md"

    json_path.write_text(handoff.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_handoff_markdown(handoff), encoding="utf-8")
    return json_path, markdown_path


def _read_dashboard_links(run_dir: Path) -> dict[str, str]:
    links_path = run_dir / "dashboard" / "LINKS.json"
    if not links_path.exists():
        return {}
    payload = json.loads(links_path.read_text(encoding="utf-8"))
    links = payload.get("links", {})
    if not isinstance(links, dict):
        return {}
    return {str(key): str(value) for key, value in links.items()}


def _build_next_actions(requested_skill: str, resume: bool, settings: HostSettings) -> list[str]:
    run_policy = settings.run_policy.policy
    actions = [
        "Read the shared integration contract before executing any top-level skill.",
        f"Open the selected skill file for `{requested_skill}` and follow its artifact contract exactly.",
        (
            "Before writing any canonical JSON artifact, open `sharedReferences.schemaIndex` and then the matching "
            "exact Python contract file from `sharedReferences.*ContractPy`."
        ),
        (
            "If `state/STRATEGY_PLAN.json` returns `next_action = run_configuration`, first write the active stage as "
            "`Configuration` / `research-config`, run `research-config`, validate "
            "`research_plan/RESEARCH_PLAN.json`, and refresh routing before any generation work."
        ),
        (
            "Before performing deterministic mechanics work such as routing refresh, top-k selection, "
            "island selection, island reward updates, proximity updates, Elo updates, or convergence updates, open "
            "`sharedReferences.mechanicsIntegrationContract` and use the documented stable `tools.*` helper or CLI "
            "surface instead of reimplementing the logic manually."
        ),
        (
            "`islands/ISLANDS.json` is the only canonical persisted island artifact. Never read or write "
            "`state/ISLANDS.json`; if that file exists, stop, run contract validation, and repair canonical island "
            "state before continuing."
        ),
        (
            "During generation seeding or multi-island child creation, assign each viable hypothesis a non-empty "
            "`island_id`, call `tools.ensure_run_islands_for_hypotheses(...)`, and verify newly created islands "
            "must remain unvisited with `decayed_reward = 0.0`, `decayed_visits = 0.0`, and `visit_count = 0`. "
            "Do not put derived dashboard fields such as `hypothesis_ids`, `ucb_score`, or `strategy_label` into "
            "canonical island items."
        ),
        (
            "After `tools.update_run_single_island_reward(...)` closes a single-island round, reload "
            "`islands/ISLANDS.json` and confirm the selected island has nonzero `visit_count`, nonzero "
            "`decayed_visits`, and a `visit_count` covering the completed single-island round receipts that selected "
            "it. If this per-selected-island metrics validation fails, stop before the next routing refresh, run "
            "contract validation, and report a resumable blocked state."
        ),
        (
            "Use `from tools import sync_pipeline_stage_artifacts` when entering any active substage so "
            "`state/PIPELINE_STATE.json` and `state/CURRENT_STAGE.json` are updated together instead of drifting."
        ),
        (
            "For active runtime phases (`Generation`, `Evolution`, `Reflection`, `Insights from Reviews`, "
            "`Proximity`, `Ranking`, or `Research Overview`), do not leave `state/PIPELINE_STATE.json` with "
            "`status=not_started`; the paired stage-sync helper normalizes active work to `status=running`."
        ),
        (
            "Do not synthesize placeholder hypotheses, reviews, tournaments, proximity receipts, embeddings, or "
            "evolution-round receipts to make progress. If the required sub-skill or canonical tool cannot be "
            "executed, stop and report a resumable blocked state instead of writing low-information artifacts."
        ),
        (
            "A completed evolution round must be replayable from exactly one router decision, one evolved child, one "
            "review bundle, one proximity receipt, ranking artifacts, one convergence update, and one appended "
            "round receipt."
        ),
        (
            "For each newly viable hypothesis, call `tools.update_hypothesis_proximity(run_dir, hypothesis_id)` "
            "so the canonical embedding bridge generates a real embedding, updates `state/PROXIMITY_GRAPH.json`, "
            "and writes a proximity receipt. If the provider is unavailable or explicitly disabled, preserve the "
            "receipt and continue "
            "with the documented ranking fallback without inventing placeholder embeddings."
        ),
        (
            "Ranking hard order is mandatory for each viable ranking candidate: run the proximity bridge first, "
            "derive placement opponents through `tools.select_placement_opponents(...)` when a usable graph exists "
            "or `tools.select_fallback_placement_opponents(...)` only when a proximity receipt gates fallback, run "
            "`placement_tournament` artifacts, call `tools.apply_and_persist_elo_updates(...)` for the placement "
            "batch and verify the ranking update receipt, reload the post-placement frontier, then "
            "call `tools.should_run_ranked_tournament(...)` / `tools.select_ranked_opponents(...)`, run any "
            "`ranked_tournament` artifacts, and call `tools.apply_and_persist_elo_updates(...)` for the ranked "
            "batch when ranked matches exist. Do not use ranked tournament play as an implicit replacement for "
            "placement, and do not advance to convergence with completed tournament matches that lack ranking "
            "update receipt coverage."
        ),
        (
            "`state/STRATEGY_DECISIONS.jsonl` is router-planning audit only and must come from the canonical "
            "`python -m tools.policy.plan_strategy <run_dir>` surface with router signals such as hypothesis counts, "
            "viable counts, convergence state, top-k IDs, research-plan status, selected parents, and selected "
            "islands. Do not write child IDs, chosen concrete strategies, proximity statuses, tournament match IDs, "
            "top-k entry results, or convergence transitions into strategy decisions; write completed round metadata "
            "through `tools.append_evolution_round_record` to `artifactPaths.evolutionRounds`."
        ),
        (
            "After each major write, run "
            "`python -m tools.validation.contract_validation <run_dir> --skill "
            f"{requested_skill}` and inspect any reported warnings or errors."
        ),
        (
            "When dashboard links are present, prefer `artifactPaths.dashboardLinksMarkdown` for the human-readable "
            "receipt and `artifactPaths.dashboardLinks` for machine-readable follow-up."
        ),
        (
            "Before every generation batch and every individual evolution round, refresh the routing plan through "
            "`python -m tools.policy.plan_strategy <run_dir>` when restoring persisted state. Add "
            "`--phase <Configuration|Generation|Evolution|Insights from Reviews|Proximity|Ranking|"
            "Research Overview>` only when "
            "the top-level workflow is intentionally forcing a new stage transition, then follow the returned "
            "`next_action` plus any selected parent IDs."
        ),
        (
            "Do not dispatch `hypothesis-generation-pipeline` until `research_plan/RESEARCH_PLAN.json` exists and "
            "validates against the canonical research-plan contract."
        ),
        (
            "For every evolution round, choose one concrete strategy through `evolution-strategy-supervisor`, "
            "then run the matching `hypothesis-evolve-*` skill before review, proximity, and ranking updates."
        ),
        (
            "After every completed evolution round, use `tools.append_evolution_round_record` with "
            "`sharedReferences.evolutionRoundContractPy` and append the receipt to `artifactPaths.evolutionRounds` "
            "only after ranking update receipts cover the round's completed placement and ranked match IDs. The "
            "round receipt match IDs must be duplicate-free child-owned closeout refs where the child is "
            "`hypothesis_1_id`; do not copy later opponent-side lifetime refs into that earlier receipt."
        ),
        (
            "Before ending evolution or marking the pipeline complete, run "
            "`python -m tools.validation.verify_pipeline_completion <run_dir> --skill "
            f"{requested_skill}` and record any override rationale in "
            "`state/COMPLETION_DECISION.json`."
        ),
    ]
    if run_policy.iteration_policy == "completion_driven" and run_policy.human_checkpoint == "auto":
        actions.append(
            "The effective run policy is `completion_driven` with `human_checkpoint=auto`: while this host-agent "
            "turn still controls execution, do not ask the user whether to continue after each evolution round. Keep "
            "refreshing routing and continue evolution until the plan reaches `generate_overview` or `inspect_state`, "
            "or until validation or safety ceilings block further execution. Final `complete` comes from the "
            "completion verifier after overview work."
        )
        actions.append(
            "If you must return control to the user before a terminal route is reached, report that the run is "
            "paused, current convergence has not been reached, the persisted state is resumable, and the recommended "
            "next action is to continue evolution through `$co-scientist-resume <run-dir>` or an explicit continue "
            "request."
        )
    elif run_policy.human_checkpoint == "before_overview":
        actions.append(
            "The effective run policy requests a checkpoint before overview. Continue autonomously through evolution, "
            "then pause only when the routing plan is ready to enter `research-overview-pipeline`."
        )
    elif run_policy.human_checkpoint == "before_completion":
        actions.append(
            "The effective run policy requests a checkpoint before final completion. Continue autonomously through "
            "overview generation, then pause before recording the final completion decision."
        )
    elif run_policy.human_checkpoint == "every_major_stage":
        actions.append(
            "The effective run policy requests checkpoints at major stage transitions. Do not reinterpret this as "
            "permission to ask after every individual evolution child."
        )
    if resume:
        actions.append(
            "Before continuing resumed work, run "
            f"`python -m tools.validation.contract_validation <run_dir> --resume --skill {requested_skill}`."
        )
        actions.append(
            "Resume from the persisted pipeline state and current stage instead of restarting completed phases."
        )
        actions.append(
            "Obey the persisted route exactly during resume: `run_review` resumes only review, `run_insights` "
            "resumes only insights, `run_proximity` resumes only proximity, `run_ranking` resumes only ranking, and "
            "`continue_evolution` may create at most one child before closing that child through review, proximity, "
            "ranking with ranking update receipt coverage, convergence, and one appended round receipt."
        )
    else:
        actions.append("Treat the run as a fresh execution unless persisted artifacts explicitly indicate otherwise.")
    return actions


def _render_handoff_markdown(handoff: HostAgentHandoff) -> str:
    lines = [
        "# Host-Agent Handoff",
        "",
        f"- `runId`: `{handoff.runId}`",
        f"- `requestedSkill`: `{handoff.requestedSkill}`",
        f"- `resume`: `{str(handoff.resume).lower()}`",
        f"- `skillPath`: `{handoff.skillPath}`",
        "",
        "## Shared References",
        "",
    ]
    for label, path in handoff.sharedReferences.items():
        lines.append(f"- `{label}`: `{path}`")
    lines.extend(["", "## Artifact Paths", ""])
    for label, path in handoff.artifactPaths.items():
        lines.append(f"- `{label}`: `{path}`")
    if handoff.dashboardLinks:
        lines.extend(["", "## Dashboard Links", ""])
        for label, url in handoff.dashboardLinks.items():
            lines.append(f"- `{label}`: {url}")
    lines.extend(
        [
            "",
            "## Validation",
            "",
            "This is a handoff-time validation snapshot. Re-run contract validation for current artifact health.",
            "",
            f"- `snapshotGeneratedAt`: `{handoff.validationSnapshot.generatedAt.isoformat()}`",
            f"- `snapshotCommand`: `{handoff.validationSnapshot.command}`",
            f"- `status`: `{handoff.validation.status}`",
            f"- `errorCount`: `{handoff.validation.errorCount}`",
            f"- `warningCount`: `{handoff.validation.warningCount}`",
            f"- `resumeReady`: `{str(handoff.validation.resumeReady).lower()}`",
            "",
            "## Next Actions",
            "",
        ]
    )
    lines.extend(f"- {action}" for action in handoff.nextActions)
    lines.append("")
    return "\n".join(lines)
