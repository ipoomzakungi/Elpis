from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STREAMS = {
    "sessions",
    "opportunities",
    "outcomes",
    "ambiguity_resolutions",
    "daily_summaries",
    "review_checkpoints",
}


class DuplicateValidationSessionError(ValueError):
    pass


class CandidateValidationStore:
    def __init__(self, root: Path, manifest_hash: str) -> None:
        self.root = root
        self.manifest_hash = manifest_hash
        root.mkdir(parents=True, exist_ok=True)

    def append_session_bundle(
        self,
        *,
        session: dict[str, Any],
        opportunities: list[dict[str, Any]],
        outcomes: list[dict[str, Any]],
        resolutions: list[dict[str, Any]],
        daily_summary: dict[str, Any],
    ) -> None:
        session_date = session["session_date"]
        if any(row.get("session_date") == session_date for row in self.read("sessions")):
            raise DuplicateValidationSessionError(f"Session already ingested: {session_date}")
        self._assert_unique(
            "opportunities",
            "opportunity_id",
            [row["opportunity_id"] for row in opportunities],
        )
        self._assert_unique(
            "outcomes",
            "outcome_id",
            [row["outcome_id"] for row in outcomes],
        )
        self._assert_unique(
            "ambiguity_resolutions",
            "resolution_id",
            [row["resolution_id"] for row in resolutions],
        )
        self.append("sessions", session)
        for row in opportunities:
            self.append("opportunities", row)
        for row in outcomes:
            self.append("outcomes", row)
        for row in resolutions:
            self.append("ambiguity_resolutions", row)
        self.append("daily_summaries", daily_summary)

    def append(self, stream: str, row: dict[str, Any]) -> Path:
        if stream not in STREAMS:
            raise ValueError(f"Unsupported validation stream: {stream}")
        payload = {
            **row,
            "candidate_manifest_hash": self.manifest_hash,
            "recorded_at": datetime.now(UTC).isoformat(),
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }
        path = self.root / f"{stream}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return path

    def read(self, stream: str) -> list[dict[str, Any]]:
        if stream not in STREAMS:
            raise ValueError(f"Unsupported validation stream: {stream}")
        path = self.root / f"{stream}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def has_review_checkpoint(self, session_count: int) -> bool:
        return any(
            row.get("session_count") == session_count for row in self.read("review_checkpoints")
        )

    def append_superseding(
        self,
        stream: str,
        row: dict[str, Any],
        *,
        id_field: str,
        supersedes_id: str,
    ) -> Path:
        existing = self.read(stream)
        if not any(item.get(id_field) == supersedes_id for item in existing):
            raise ValueError(f"Cannot supersede missing record: {supersedes_id}")
        if row.get(id_field) == supersedes_id:
            raise ValueError("A correction must have a new immutable record ID")
        self._assert_unique(stream, id_field, [row[id_field]])
        return self.append(stream, {**row, "supersedes_id": supersedes_id})

    def _assert_unique(self, stream: str, field: str, values: list[str]) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {field} in append bundle")
        existing = {row.get(field) for row in self.read(stream)}
        duplicate = existing.intersection(values)
        if duplicate:
            raise ValueError(f"Duplicate immutable records: {sorted(duplicate)}")
