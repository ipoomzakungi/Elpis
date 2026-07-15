from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Vol2VolCollectionStatus(StrEnum):
    COLLECTED = "collected"
    COLLECTED_INCOMPLETE = "collected_incomplete"
    SKIPPED_EXISTING = "skipped_existing"
    REJECTED_DATE_MISMATCH = "rejected_date_mismatch"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class Vol2VolCollectionRow(BaseModel):
    requested_session_date: date
    returned_session_date: date | None = None
    status: Vol2VolCollectionStatus
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    response_size_bytes: int = Field(default=0, ge=0)
    sha256: str | None = None
    snapshot_count: int = Field(default=0, ge=0)
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None
    series: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    output_path: str | None = None
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_guardrails(self) -> Vol2VolCollectionRow:
        if self.signal_allowed or not self.research_only:
            raise ValueError("Vol2Vol collection rows must remain research-only")
        return self


class Vol2VolCollectionManifest(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    advertised_session_count: int = Field(default=0, ge=0)
    included_session_count: int = Field(default=0, ge=0)
    rows: list[Vol2VolCollectionRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_guardrails(self) -> Vol2VolCollectionManifest:
        if self.signal_allowed or not self.research_only:
            raise ValueError("Vol2Vol collection manifests must remain research-only")
        return self


def inspect_payload(
    *,
    requested_session_date: date,
    body: str,
    output_path: Path | None,
) -> tuple[dict[str, Any], Vol2VolCollectionRow]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Vol2Vol response must be a JSON object")
    _reject_session_material(payload)
    returned = _parse_date(payload.get("sessionDate"))
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        snapshots = []
    observed = sorted(
        value
        for snapshot in snapshots
        if isinstance(snapshot, dict)
        if (value := _parse_datetime(snapshot.get("observedAt"))) is not None
    )
    series = sorted(
        {
            str(snapshot["series"])
            for snapshot in snapshots
            if isinstance(snapshot, dict) and snapshot.get("series") not in (None, "")
        }
    )
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    status = (
        Vol2VolCollectionStatus.COLLECTED
        if returned == requested_session_date
        else Vol2VolCollectionStatus.REJECTED_DATE_MISMATCH
    )
    warnings = []
    if status == Vol2VolCollectionStatus.REJECTED_DATE_MISMATCH:
        warnings.append("Requested and returned session dates differ; payload was not stored.")
    return payload, Vol2VolCollectionRow(
        requested_session_date=requested_session_date,
        returned_session_date=returned,
        status=status,
        response_size_bytes=len(body.encode("utf-8")),
        sha256=digest,
        snapshot_count=len(snapshots),
        first_observed_at=observed[0] if observed else None,
        last_observed_at=observed[-1] if observed else None,
        series=series,
        warnings=warnings,
        output_path=(
            output_path.as_posix()
            if output_path and status == Vol2VolCollectionStatus.COLLECTED
            else None
        ),
    )


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _reject_session_material(payload: Any) -> None:
    forbidden = {
        "authorization",
        "cf-clearance",
        "cookie",
        "cookies",
        "csrf",
        "headers",
        "set-cookie",
        "token",
        "tokens",
    }
    pending = [payload]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            keys = {str(key).lower().replace("_", "-") for key in current}
            if keys & forbidden or any(
                key.startswith("csrf") or key.endswith("token") or key.endswith("tokens")
                for key in keys
            ):
                raise ValueError("Vol2Vol response contains forbidden browser session material")
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
