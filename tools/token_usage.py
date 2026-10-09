"""Collect numerical Codex usage into run artifacts without copying chat content."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.credit_usage import SPEED_MULTIPLIERS, CreditLedger


COUNTERS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError):
                # An active rollout may end in a partially written JSON line.
                continue
            if isinstance(record, dict):
                yield record


def _counts(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    result = {key: value.get(key, 0) for key in COUNTERS}
    if any(isinstance(number, bool) or not isinstance(number, int) or number < 0 for number in result.values()):
        return None
    if "input_tokens" not in value or "output_tokens" not in value:
        return None
    if result["cached_input_tokens"] + result["cache_write_input_tokens"] > result["input_tokens"]:
        return None
    if result["reasoning_output_tokens"] > result["output_tokens"]:
        return None
    return result


def attach_run(
    run_dir: Path, thread_id: str, *, budget_credits: float | None = None, speed: str | None = None
) -> dict[str, Any]:
    """Enroll a chat from this point forward; reattaching never resets its start."""
    if not run_dir.is_dir():
        raise ValueError("Create the run before attaching usage tracking.")
    if not thread_id or "/" in thread_id or "\\" in thread_id:
        raise ValueError("A valid Codex thread ID is required.")
    if budget_credits is not None and (
        isinstance(budget_credits, bool) or not math.isfinite(budget_credits) or budget_credits <= 0
    ):
        raise ValueError("Credit budget must be a positive finite number.")
    if speed is not None and speed not in SPEED_MULTIPLIERS:
        raise ValueError("Unknown credit speed.")
    path = run_dir / "state" / "TOKEN_USAGE_CONFIG.json"
    config = _read(path) or {"version": 1, "sessions": [], "include_subagents": True}
    if not any(session["thread_id"] == thread_id for session in config["sessions"]):
        config["sessions"].append({"thread_id": thread_id, "started_at": _now()})
    _write(path, config)
    if budget_credits is not None or speed is not None:
        budget_path = run_dir / "state" / "CREDIT_BUDGET.json"
        settings = _read(budget_path)
        if budget_credits is not None:
            settings["budgetCredits"] = budget_credits
        if speed is not None:
            settings["fallbackSpeed"] = speed
        _write(budget_path, settings)
    return config


def collect_usage(run_dir: Path, *, codex_home: Path | None = None) -> dict[str, Any]:  # noqa: C901
    """Sum distinct responses from enrolled chats and descendants since enrollment."""
    config = _read(run_dir / "state" / "TOKEN_USAGE_CONFIG.json")
    settings = _read(run_dir / "state" / "CREDIT_BUDGET.json")
    budget = settings.get("budgetCredits")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget <= 0:
        budget = None
    speed = settings.get("fallbackSpeed", "standard")
    ledger = CreditLedger(speed if speed in SPEED_MULTIPLIERS else "standard")
    report: dict[str, Any] = {
        "version": 1,
        "status": "unavailable",
        "updatedAt": _now(),
        "lastUsageAt": None,
        "startedAt": None,
        "totalTokens": None,
        "inputTokens": None,
        "cachedInputTokens": None,
        "uncachedInputTokens": None,
        "outputTokens": None,
        "reasoningOutputTokens": None,
        "budgetCredits": budget,
        "cacheWriteInputTokens": None,
        "sessionCount": 0,
        "missingSessionCount": 0,
        "source": "codex_rollout",
        "advisoryOnly": True,
    }
    sessions = config.get("sessions", [])
    if not sessions:
        report.update(ledger.report(available=False, missing=0))
        _write(run_dir / "state" / "TOKEN_USAGE.json", report)
        return report
    home = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    starts = {session["thread_id"]: _timestamp(session["started_at"]) for session in sessions}
    report["startedAt"] = min(starts.values()).isoformat()
    metadata: dict[str, dict[str, Any]] = {}
    files: dict[str, list[Path]] = {}
    for directory in (home / "sessions", home / "archived_sessions"):
        for path in directory.rglob("*.jsonl"):
            try:
                first = next(_records(path), {})
                meta = first.get("payload", {}) if first.get("type") == "session_meta" else {}
                thread = meta.get("id")
                if isinstance(thread, str):
                    metadata[thread] = meta
                    files.setdefault(thread, []).append(path)
            except (OSError, UnicodeError):
                continue
    if config.get("include_subagents", True):
        changed = True
        while changed:
            changed = False
            for thread, meta in metadata.items():
                parent = meta.get("parent_thread_id")
                if thread not in starts and parent in starts:
                    starts[thread] = starts[parent]
                    changed = True
    totals = dict.fromkeys(COUNTERS, 0)
    seen_responses: set[str] = set()
    observed: set[str] = set()
    last_usage_at: datetime | None = None
    for thread, start in starts.items():
        records: list[dict[str, Any]] = []
        contexts: dict[str, dict[str, Any]] = {}
        free = metadata.get(thread, {}).get("source", {}) == {"subagent": {"other": "guardian"}}
        try:
            for path in files.get(thread, []):
                records.extend(
                    record
                    for record in _records(path)
                    if record.get("type") == "token_usage_record"
                    or record.get("type") == "turn_context"
                    or (record.get("type") == "event_msg" and record.get("payload", {}).get("type") == "token_count")
                )
        except (OSError, UnicodeError):
            continue
        for record in records:
            if record.get("type") == "turn_context":
                context = record.get("payload", {})
                contexts[context.get("turn_id", "")] = {
                    key: context[key] for key in ("model", "speed", "service_tier") if key in context
                }
        direct = [
            record
            for record in records
            if record.get("type") == "token_usage_record" and record.get("payload", {}).get("thread_id") == thread
        ]
        if direct:
            for record in direct:
                payload = record["payload"]
                counts = _counts(payload.get("usage"))
                response_id = payload.get("response_id")
                if counts is None or not isinstance(response_id, str) or not response_id:
                    continue
                observed.add(thread)
                stamp = _timestamp(record["timestamp"])
                if stamp < start or response_id in seen_responses:
                    continue
                seen_responses.add(response_id)
                ledger.add(counts, contexts.get(payload.get("turn_id", ""), {}), free=free)
                for key in COUNTERS:
                    totals[key] += counts[key]
                last_usage_at = max(last_usage_at or stamp, stamp)
        else:
            # Older Codex versions expose cumulative token_count events only.
            previous = dict.fromkeys(COUNTERS, 0)
            context = {}
            for record in sorted(records, key=lambda item: item.get("timestamp", "")):
                payload = record.get("payload", {})
                if record.get("type") == "turn_context":
                    context = contexts.get(payload.get("turn_id", ""), {})
                    continue
                if payload.get("type") != "token_count":
                    continue
                counts = _counts((payload.get("info") or {}).get("total_token_usage"))
                if counts is None:
                    continue
                observed.add(thread)
                stamp = _timestamp(record["timestamp"])
                # A reset begins a new counter series; duplicate events add zero.
                reset = (
                    counts["input_tokens"] < previous["input_tokens"]
                    or counts["output_tokens"] < previous["output_tokens"]
                )
                if stamp >= start:
                    delta = {key: counts[key] if reset else max(counts[key] - previous[key], 0) for key in COUNTERS}
                    if _counts(delta) is not None:
                        ledger.add(delta, context, free=free)
                        for key in COUNTERS:
                            totals[key] += delta[key]
                    last_usage_at = max(last_usage_at or stamp, stamp)
                previous = counts
    missing = len(starts.keys() - observed)
    report.update({"sessionCount": len(observed), "missingSessionCount": missing})
    if observed:
        report.update(
            {
                "status": "partial" if missing else "available",
                "lastUsageAt": last_usage_at.isoformat() if last_usage_at else None,
                "totalTokens": totals["input_tokens"] + totals["output_tokens"],
                "inputTokens": totals["input_tokens"],
                "cachedInputTokens": totals["cached_input_tokens"],
                "uncachedInputTokens": totals["input_tokens"]
                - totals["cached_input_tokens"]
                - totals["cache_write_input_tokens"],
                "cacheWriteInputTokens": totals["cache_write_input_tokens"],
                "outputTokens": totals["output_tokens"],
                "reasoningOutputTokens": totals["reasoning_output_tokens"],
            }
        )
    report.update(ledger.report(available=bool(observed), missing=missing))
    _write(run_dir / "state" / "TOKEN_USAGE.json", report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Attach, collect once, or watch a run's measured token usage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("attach", "collect", "watch"))
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID"))
    parser.add_argument("--budget", type=float, help="Advisory budget in EDU credits.")
    parser.add_argument("--speed", choices=tuple(SPEED_MULTIPLIERS), help="Fallback when the rollout omits speed.")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args(argv)
    if not args.run_dir.is_dir():
        parser.error("Run directory does not exist.")
    if args.interval < 1:
        parser.error("Polling interval must be at least one second.")
    if args.command == "attach":
        attach_run(args.run_dir, args.thread_id, budget_credits=args.budget, speed=args.speed)
    elif args.budget is not None or args.speed is not None:
        parser.error("Use attach --budget/--speed to set credit settings.")
    try:
        while True:
            report = collect_usage(args.run_dir, codex_home=args.codex_home)
            print(json.dumps(report), flush=True)
            if args.command != "watch":
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
