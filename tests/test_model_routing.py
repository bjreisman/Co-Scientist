from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from tools.model_routing import (
    POLICY_NAME,
    begin_dispatch,
    finish_dispatch,
    freeze_policy,
    install_policy,
    load_policy,
    resolve_task,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    install_policy(tmp_path)
    return tmp_path


def make_run(project: Path) -> Path:
    run = project / "runs/demo"
    run.mkdir(parents=True)
    return run


def test_task_settings_and_exact_override(project: Path) -> None:
    path = project / POLICY_NAME
    policy = yaml.safe_load(path.read_text())
    policy["skill_overrides"] = {"hypothesis-initial-review": "evidence"}
    path.write_text(yaml.safe_dump(policy))
    install_policy(project)
    run = make_run(project)
    assert resolve_task(run, "hypothesis-generate-debate")["requested"] == {
        "model": "gpt-6.1-sol",
        "reasoningEffort": "medium",
    }
    assert resolve_task(run, "hypothesis-initial-review")["spawn"]["model"] == "gpt-6-luna"
    assert resolve_task(run, "hypothesis-full-review")["requested"]["reasoningEffort"] == "high"
    for skill in ("ranking-elo-update", "literature-search", "hypothesis-proximity-update", "island-select"):
        with pytest.raises(ValueError, match="not a delegated"):
            resolve_task(run, skill)


def test_resume_retains_frozen_choices_despite_reinstalled_roles(project: Path) -> None:
    run = make_run(project)
    before = freeze_policy(run)
    policy_path = project / POLICY_NAME
    policy = yaml.safe_load(policy_path.read_text())
    policy["roles"]["reviewer"]["model"] = "gpt-6-luna"
    policy_path.write_text(yaml.safe_dump(policy))
    install_policy(project)
    assert freeze_policy(run) == before
    resolved = resolve_task(run, "hypothesis-full-review")
    assert resolved["requested"]["model"] == "gpt-6.1-sol"
    assert resolved["spawn"]["agent_type"] == "default"  # Role config cannot override frozen settings.


def test_local_fallback_is_explicit_and_cannot_claim_role_model(project: Path) -> None:
    run = make_run(project)
    with pytest.raises(ValueError, match="fallback=stop"):
        resolve_task(run, "hypothesis-full-review", local=True)
    path = project / POLICY_NAME
    policy = yaml.safe_load(path.read_text())
    policy["fallback"] = "local"
    path.write_text(yaml.safe_dump(policy))
    other = project / "runs/other"
    other.mkdir()
    resolved = resolve_task(other, "hypothesis-full-review", local=True)
    assert resolved["route"] == "local_main_thread" and resolved["spawn"] is None


def test_legacy_run_retains_host_inheritance(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    route = resolve_task(run, "hypothesis-full-review")
    assert route["route"] == "local_main_thread" and route["requested"] is None
    assert not (run / "state/MODEL_POLICY.json").exists()


def test_installer_preserves_unrelated_config_and_refuses_unmanaged_roles(project: Path) -> None:
    config = project / ".codex/config.toml"
    original = '# user comment\nmodel = "gpt-6-astra"\n'
    config.write_text(original)
    install_policy(project)
    assert config.read_text() == original
    role = project / ".codex/agents/co_scientist_reviewer.toml"
    assert tomllib.loads(role.read_text())["model"] == "gpt-6.1-sol"
    role.write_text('name = "user_agent"\n')
    with pytest.raises(ValueError, match="unmanaged agent"):
        install_policy(project)
    assert role.read_text() == 'name = "user_agent"\n'


@pytest.mark.parametrize("change", ["undefined_role", "invalid_effort", "mechanics_override", "unknown_field"])
def test_invalid_policies_fail_before_install_writes(project: Path, change: str) -> None:
    source = project / "invalid.yaml"
    data = yaml.safe_load((project / POLICY_NAME).read_text())
    if change == "undefined_role":
        data["tasks"]["review"] = "missing"
    elif change == "invalid_effort":
        data["roles"]["reviewer"]["reasoning_effort"] = "none"
    elif change == "mechanics_override":
        data["skill_overrides"] = {"ranking-elo-update": "judge"}
    else:
        data["rolse"] = {}
    source.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_policy(source)
    with pytest.raises(ValueError):
        install_policy(project / "untouched", policy_path=source)
    assert not (project / "untouched").exists()


def rollout(home: Path, *, model: str, effort: str | None) -> None:
    path = home / "sessions/child.jsonl"
    path.parent.mkdir(parents=True)
    records = [
        {"type": "session_meta", "payload": {"id": "child", "parent_thread_id": "parent"}},
        {
            "type": "turn_context",
            "timestamp": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
            "payload": {"model": model, "effort": effort, "private_text": "never copy this"},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


@pytest.mark.parametrize(
    ("model", "effort", "expected"),
    [
        ("gpt-6.1-sol", "high", "verified"),
        ("gpt-6-luna", "high", "mismatch"),
        ("gpt-6.1-sol", "low", "mismatch"),
        ("gpt-6.1-sol", None, "model_only"),
    ],
)
def test_audit_uses_actual_session_metadata(project: Path, model: str, effort: str | None, expected: str) -> None:
    run = make_run(project)
    receipt = begin_dispatch(run, "hypothesis-full-review")
    home = project / "fake_home"
    rollout(home, model=model, effort=effort)
    result = finish_dispatch(run, receipt["id"], session_id="child", codex_home=home)
    assert result["verification"] == expected
    assert result["observed"][0]["model"] == model
    summary = (run / "state/MODEL_ROUTING.json").read_text()
    assert "never copy this" not in summary and "private_text" not in summary
    with pytest.raises(ValueError, match="already closed"):
        finish_dispatch(run, receipt["id"], session_id="child", codex_home=home)


def test_missing_metadata_and_parent_session_cannot_verify_child(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "parent")
    run = make_run(project)
    receipt = begin_dispatch(run, "hypothesis-full-review")
    with pytest.raises(ValueError, match="not the parent"):
        finish_dispatch(run, receipt["id"], session_id="parent")
    result = finish_dispatch(run, receipt["id"], session_id="absent", codex_home=project / "missing")
    assert result["verification"] == "unverified" and result["observed"] == []


def test_only_contexts_after_dispatch_can_verify(project: Path) -> None:
    run = make_run(project)
    receipt = begin_dispatch(run, "hypothesis-full-review")
    home = project / "home"
    path = home / "sessions/old.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": "old"}})
        + "\n"
        + json.dumps(
            {
                "type": "turn_context",
                "timestamp": "2000-01-01T00:00:00Z",
                "payload": {"model": "gpt-6.1-sol", "effort": "high"},
            }
        )
        + "\n"
    )
    result = finish_dispatch(run, receipt["id"], session_id="old", codex_home=home)
    assert result["verification"] == "unverified"
