from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class XauVol2VolDataLakeLoadResult:
    payloads: list[Any] = field(default_factory=list)
    source_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class XauVol2VolSessionEligibility:
    source_session_status: str
    forward_plan_eligible: bool
    backtest_eligible: bool
    payload_sha256: str | None = None
    collection_history_count: int = 0
    reasons: list[str] = field(default_factory=list)


def daily_raw_path(root: Path, session_date: date) -> Path:
    return root / "daily" / session_date.isoformat() / "raw.json"


def daily_metadata_path(root: Path, session_date: date) -> Path:
    return root / "daily" / session_date.isoformat() / "collection_meta.json"


def monthly_raw_path(root: Path, target_month: str) -> Path:
    return root / "monthly" / target_month / "raw.json"


def evaluate_daily_session_eligibility(
    *,
    root: Path,
    session_date: date,
    current_date: date,
) -> XauVol2VolSessionEligibility:
    raw_path = daily_raw_path(root, session_date)
    if not raw_path.exists():
        return XauVol2VolSessionEligibility(
            source_session_status="missing",
            forward_plan_eligible=False,
            backtest_eligible=False,
            reasons=["Vol2Vol daily payload is missing."],
        )
    try:
        body = raw_path.read_text(encoding="utf-8")
        payload = json.loads(body)
    except (OSError, json.JSONDecodeError):
        return XauVol2VolSessionEligibility(
            source_session_status="invalid",
            forward_plan_eligible=False,
            backtest_eligible=False,
            reasons=["Vol2Vol daily payload is unreadable or invalid JSON."],
        )
    returned_date = str(payload.get("sessionDate") or "")[:10]
    if returned_date != session_date.isoformat():
        return XauVol2VolSessionEligibility(
            source_session_status="date_mismatch",
            forward_plan_eligible=False,
            backtest_eligible=False,
            reasons=["Requested and stored Vol2Vol session dates differ."],
        )
    payload_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    metadata_path = daily_metadata_path(root, session_date)
    if not metadata_path.exists():
        if session_date >= current_date:
            return XauVol2VolSessionEligibility(
                source_session_status="metadata_missing",
                forward_plan_eligible=False,
                backtest_eligible=False,
                payload_sha256=payload_sha256,
                reasons=["Current-session completion metadata is missing."],
            )
        return XauVol2VolSessionEligibility(
            source_session_status="legacy_complete",
            forward_plan_eligible=False,
            backtest_eligible=True,
            payload_sha256=payload_sha256,
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return XauVol2VolSessionEligibility(
            source_session_status="metadata_invalid",
            forward_plan_eligible=False,
            backtest_eligible=False,
            payload_sha256=payload_sha256,
            reasons=["Vol2Vol collection metadata is invalid."],
        )
    history = metadata.get("collection_history")
    history_count = len(history) if isinstance(history, list) else 0
    if metadata.get("complete") is False:
        is_current = session_date == current_date
        return XauVol2VolSessionEligibility(
            source_session_status=("current_incomplete" if is_current else "incomplete"),
            forward_plan_eligible=is_current,
            backtest_eligible=False,
            payload_sha256=payload_sha256,
            collection_history_count=history_count,
            reasons=(
                ["Current incomplete session is eligible only for true-forward planning."]
                if is_current
                else ["Incomplete historical session is ineligible."]
            ),
        )
    return XauVol2VolSessionEligibility(
        source_session_status="complete",
        forward_plan_eligible=True,
        backtest_eligible=True,
        payload_sha256=payload_sha256,
        collection_history_count=history_count,
    )


def session_is_eligible_for_observation(
    eligibility: XauVol2VolSessionEligibility,
    observation_mode: str,
) -> bool:
    if observation_mode == "true_forward":
        return eligibility.forward_plan_eligible or eligibility.backtest_eligible
    return eligibility.backtest_eligible


def load_vol2vol_data_lake(
    *,
    root: Path,
    session_date_from: date,
    session_date_to: date,
    monthly_target: str | None = None,
) -> XauVol2VolDataLakeLoadResult:
    payloads: list[Any] = []
    source_paths: list[Path] = []
    warnings: list[str] = []
    current = session_date_from
    while current <= session_date_to:
        path = daily_raw_path(root, current)
        if path.exists():
            metadata_path = daily_metadata_path(root, current)
            if _is_incomplete(metadata_path):
                warnings.append(f"Incomplete Vol2Vol daily data-lake file excluded: {path}")
            else:
                _append_payload(path, payloads, source_paths, warnings)
        else:
            warnings.append(f"Missing Vol2Vol daily data-lake file: {path}")
        current += timedelta(days=1)
    if monthly_target:
        path = monthly_raw_path(root, monthly_target)
        if path.exists():
            _append_payload(path, payloads, source_paths, warnings)
        else:
            warnings.append(f"Missing Vol2Vol monthly data-lake file: {path}")
    return XauVol2VolDataLakeLoadResult(
        payloads=payloads,
        source_paths=source_paths,
        warnings=warnings,
    )


def _is_incomplete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return payload.get("complete") is False


def _append_payload(
    path: Path,
    payloads: list[Any],
    source_paths: list[Path],
    warnings: list[str],
) -> None:
    try:
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
        source_paths.append(path)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"Could not load {path}: {exc}")
