from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def resolve_ambiguous_outcome(
    outcome: dict[str, Any],
    *,
    tick_rows: list[dict[str, Any]] | None,
    resolution_source: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    original = outcome["original_m1_status"]
    if original != "same_bar_ambiguous":
        return outcome, _resolution_record(outcome, "not_required", None, None)
    if not tick_rows or resolution_source is None:
        return outcome, _resolution_record(outcome, "same_bar_ambiguous", None, None)
    entry_at = datetime.fromisoformat(outcome["entry_timestamp"])
    window_end = entry_at + timedelta(minutes=1)
    ticks = sorted(
        (
            (datetime.fromisoformat(str(row["timestamp"])), _tick_price(row))
            for row in tick_rows
            if row.get("timestamp") and _tick_price(row) is not None
        ),
        key=lambda item: item[0],
    )
    ticks = [row for row in ticks if entry_at <= row[0] < window_end]
    entry_index = next(
        (
            index
            for index, (_, price) in enumerate(ticks)
            if _entry_touched(outcome, price)
        ),
        None,
    )
    if entry_index is None:
        return outcome, _resolution_record(outcome, "same_bar_ambiguous", resolution_source, 0.0)
    target_index = next(
        (
            index
            for index, (_, price) in enumerate(ticks[entry_index:], start=entry_index)
            if _target_touched(outcome, price)
        ),
        None,
    )
    stop_index = next(
        (
            index
            for index, (_, price) in enumerate(ticks[entry_index:], start=entry_index)
            if _stop_touched(outcome, price)
        ),
        None,
    )
    if target_index is None and stop_index is None:
        return outcome, _resolution_record(outcome, "same_bar_ambiguous", resolution_source, 0.5)
    if target_index is not None and (stop_index is None or target_index < stop_index):
        status = "target_hit"
        exit_price = float(outcome["target_price"])
        exit_at = ticks[target_index][0]
    elif stop_index is not None and (target_index is None or stop_index < target_index):
        status = "stop_hit"
        exit_price = float(outcome["stop_price"])
        exit_at = ticks[stop_index][0]
    else:
        return outcome, _resolution_record(outcome, "same_bar_ambiguous", resolution_source, 0.0)
    direction = 1 if outcome["side"] == "long_reversion" else -1
    gross = direction * (exit_price - float(outcome["entry_price"]))
    resolved = {
        **outcome,
        "resolved_status": status,
        "resolution_source": resolution_source.resolve().as_posix(),
        "resolution_confidence": 1.0,
        "exit_timestamp": exit_at.isoformat(),
        "exit_price": exit_price,
        "gross_points": gross,
        "net_points": gross - float(outcome["total_cost_points"]),
    }
    return resolved, _resolution_record(resolved, status, resolution_source, 1.0)


def load_tick_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() in {".json", ".jsonl"}:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        payload = json.loads(text)
        return payload if isinstance(payload, list) else payload.get("ticks", [])
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _resolution_record(
    outcome: dict[str, Any],
    resolved_status: str,
    source: Path | None,
    confidence: float | None,
) -> dict[str, Any]:
    return {
        "resolution_id": f"{outcome['candidate_id']}:{outcome['episode_id']}:ambiguity",
        "session_date": outcome["session_date"],
        "candidate_id": outcome["candidate_id"],
        "episode_id": outcome["episode_id"],
        "original_m1_status": outcome["original_m1_status"],
        "resolved_status": resolved_status,
        "resolution_source": source.resolve().as_posix() if source else None,
        "resolution_source_sha256": (
            hashlib.sha256(source.read_bytes()).hexdigest() if source and source.exists() else None
        ),
        "resolution_confidence": confidence,
        "favorable_sequence_assumed": False,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _tick_price(row: dict[str, Any]) -> float | None:
    for field in ("bid", "price", "mid", "close"):
        if row.get(field) not in (None, ""):
            return float(row[field])
    return None


def _entry_touched(outcome: dict[str, Any], price: float) -> bool:
    entry = float(outcome["entry_price"])
    return price <= entry if outcome["side"] == "long_reversion" else price >= entry


def _target_touched(outcome: dict[str, Any], price: float) -> bool:
    target = float(outcome["target_price"])
    return price >= target if outcome["side"] == "long_reversion" else price <= target


def _stop_touched(outcome: dict[str, Any], price: float) -> bool:
    stop = float(outcome["stop_price"])
    return price <= stop if outcome["side"] == "long_reversion" else price >= stop
