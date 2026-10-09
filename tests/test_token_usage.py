from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.token_usage import attach_run, collect_usage


START = "2026-10-08T12:00:00+00:00"
BEFORE = "2026-10-08T11:59:00Z"
AFTER = "2026-10-08T12:01:00Z"


def _config(run: Path, sessions=None):
    (run / "state").mkdir(parents=True)
    (run / "state/TOKEN_USAGE_CONFIG.json").write_text(
        json.dumps(
            {
                "sessions": sessions or [{"thread_id": "root", "started_at": START}],
                "include_subagents": True,
            }
        )
    )


def _rollout(home: Path, thread: str, records: list, parent=None, directory="sessions"):
    path = home / directory / f"{thread}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"id": thread, "parent_thread_id": parent}
    path.write_text(
        json.dumps({"type": "session_meta", "payload": meta})
        + "\n"
        + "".join(json.dumps(record) + "\n" for record in records)
    )
    return path


def _usage(thread, response, stamp=AFTER, input_tokens=100, output_tokens=20):
    return {
        "type": "token_usage_record",
        "timestamp": stamp,
        "payload": {
            "thread_id": thread,
            "response_id": response,
            "usage": {
                "input_tokens": input_tokens,
                "cached_input_tokens": 70,
                "output_tokens": output_tokens,
                "reasoning_output_tokens": 5,
            },
        },
    }


def _event(input_tokens, stamp=AFTER):
    return {
        "type": "event_msg",
        "timestamp": stamp,
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": 10,
                    "cached_input_tokens": 0,
                    "reasoning_output_tokens": 0,
                },
            },
        },
    }


def test_collect_counts_root_and_nested_subagents_once_without_history_or_cache_double_count(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    records = [_usage("root", "old", BEFORE), _usage("root", "new"), _usage("root", "new"), _event(1000)]
    _rollout(home, "root", records)
    _rollout(home, "root", records, directory="archived_sessions")
    _rollout(home, "child", [_usage("child", "child-response")], parent="root")
    _rollout(home, "grandchild", [_usage("grandchild", "grandchild-response")], parent="child")
    _rollout(home, "unrelated", [_usage("unrelated", "unrelated-response")])
    report = collect_usage(run, codex_home=home)
    assert report["status"] == "available"
    assert report["sessionCount"] == 3
    assert report["totalTokens"] == 360
    assert report["inputTokens"] == 300
    assert report["cachedInputTokens"] == 210
    assert report["uncachedInputTokens"] == 90
    assert report["outputTokens"] == 60
    assert report["reasoningOutputTokens"] == 15


def test_older_cumulative_events_use_baseline_ignore_duplicates_and_handle_resets(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    _rollout(home, "root", [_event(100, BEFORE), _event(150), _event(150), _event(20, "2026-10-08T12:02:00Z")])
    report = collect_usage(run, codex_home=home)
    assert report["inputTokens"] == 70
    assert report["outputTokens"] == 10
    assert report["totalTokens"] == 80


def test_missing_sessions_are_unavailable_not_zero_and_partial_coverage_is_explicit(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run, [{"thread_id": "root", "started_at": START}, {"thread_id": "missing", "started_at": START}])
    report = collect_usage(run, codex_home=home)
    assert report["status"] == "unavailable"
    assert report["totalTokens"] is None
    _rollout(home, "root", [_usage("root", "r")])
    report = collect_usage(run, codex_home=home)
    assert report["status"] == "partial"
    assert report["missingSessionCount"] == 1
    assert report["totalTokens"] == 120


def test_inherited_responses_and_partial_json_lines_do_not_add_usage(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    path = _rollout(home, "root", [_usage("other", "inherited"), _usage("root", "real")])
    with path.open("a") as stream:
        stream.write('{"type":')
    assert collect_usage(run, codex_home=home)["totalTokens"] == 120


def test_reattach_preserves_start_and_budget_resume_adds_another_thread(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    first = attach_run(run, "root", budget_credits=500000)
    second = attach_run(run, "root")
    assert first == second
    assert len(attach_run(run, "resume")["sessions"]) == 2
    assert collect_usage(run, codex_home=tmp_path / "missing")["budgetCredits"] == 500000
    with pytest.raises(ValueError, match="positive"):
        attach_run(run, "root", budget_credits=-1)


def test_invalid_provider_counters_are_not_reported_as_measured_usage(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    bad = _usage("root", "bad", input_tokens=10)
    _rollout(home, "root", [bad])
    assert collect_usage(run, codex_home=home)["status"] == "unavailable"


def _context(turn, model="gpt-6.1-sol", speed=None):
    payload = {"turn_id": turn, "model": model}
    if speed is not None:
        payload["speed"] = speed
    return {"type": "turn_context", "timestamp": BEFORE, "payload": payload}


def _priced(thread, response, turn, cached=400000, cache_write=0):
    record = _usage(thread, response, input_tokens=500000, output_tokens=100000)
    record["payload"]["turn_id"] = turn
    record["payload"]["usage"].update(cached_input_tokens=cached, cache_write_input_tokens=cache_write)
    return record


def test_credit_estimate_uses_each_response_model_and_cached_subsets(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    _rollout(
        home,
        "root",
        [_context("t1"), _priced("root", "r1", "t1"), _context("t2", "gpt-6-astra"), _priced("root", "r2", "t2")],
    )
    report = collect_usage(run, codex_home=home)
    assert report["estimatedCredits"] == 31 + 160
    assert report["creditStatus"] == "available"
    assert report["assumedSpeedTokens"] == 1200000
    assert len(report["modelCredits"]) == 2


@pytest.mark.parametrize(("speed", "expected"), [("standard", 31), ("fast", 62), ("ultrafast", 186)])
def test_credit_speed_fallback_and_recorded_override(tmp_path, speed, expected):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    attach_run(run, "root", speed=speed)
    _rollout(home, "root", [_context("t1"), _priced("root", "r1", "t1")])
    assert collect_usage(run, codex_home=home)["estimatedCredits"] == expected
    _rollout(home, "root", [_context("t1", speed="standard"), _priced("root", "r1", "t1")])
    report = collect_usage(run, codex_home=home)
    assert report["estimatedCredits"] == 31
    assert report["assumedSpeedTokens"] == 0


def test_credit_cache_writes_and_guardian_safety_reviews_are_free(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    _rollout(home, "root", [_context("t1"), _priced("root", "r1", "t1", cache_write=100000)])
    path = _rollout(home, "safety", [_priced("safety", "free", "unknown")], parent="root")
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[0]["payload"]["source"] = {"subagent": {"other": "guardian"}}
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    report = collect_usage(run, codex_home=home)
    assert report["estimatedCredits"] == 26
    assert report["freeSafetyTokens"] == 600000
    assert report["unpricedTokens"] == 0
    assert report["totalTokens"] == 1200000


def test_unknown_models_are_unpriced_not_silently_free(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    _rollout(home, "root", [_context("t1", "unknown-model"), _priced("root", "r1", "t1")])
    report = collect_usage(run, codex_home=home)
    assert report["estimatedCredits"] is None
    assert report["creditStatus"] == "unavailable"
    assert report["unpricedTokens"] == 600000
    _rollout(home, "child", [_context("t2"), _priced("child", "r2", "t2")], parent="root")
    report = collect_usage(run, codex_home=home)
    assert report["estimatedCredits"] == 31
    assert report["creditStatus"] == "partial"


def test_legacy_tokens_are_priced_from_context_and_old_token_budgets_are_ignored(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    (run / "state/TOKEN_BUDGET.json").write_text('{"budgetTokens": 500000}')
    _rollout(home, "root", [_context("t1"), _event(100, BEFORE), _event(150)])
    report = collect_usage(run, codex_home=home)
    assert report["estimatedCredits"] == 0.0025
    assert report["budgetCredits"] is None
    attach_run(run, "root", budget_credits=1.5)
    assert collect_usage(run, codex_home=home)["budgetCredits"] == 1.5


def test_unsupported_speed_is_unknown_and_response_dedup_also_deduplicates_cost(tmp_path):
    run, home = tmp_path / "run", tmp_path / "codex"
    _config(run)
    records = [_context("t1"), _priced("root", "r1", "t1")]
    _rollout(home, "root", records)
    _rollout(home, "root", records, directory="archived_sessions")
    assert collect_usage(run, codex_home=home)["estimatedCredits"] == 31
    _rollout(home, "root", [_context("t1", speed="unknown"), _priced("root", "r1", "t1")])
    (home / "archived_sessions/root.jsonl").unlink()
    assert collect_usage(run, codex_home=home)["estimatedCredits"] is None
