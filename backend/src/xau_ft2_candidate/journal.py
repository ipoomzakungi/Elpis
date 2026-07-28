from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

STREAMS = {
    "plans",
    "alerts",
    "acknowledgements",
    "events",
    "outcomes",
    "daily_summaries",
}


class Ft2CandidateJournal:
    def __init__(self, root: Path, candidate_hash: str) -> None:
        self.root = root
        self.candidate_hash = candidate_hash
        self.root.mkdir(parents=True, exist_ok=True)
        for stream in STREAMS:
            (self.root / f"{stream}.jsonl").touch(exist_ok=True)

    def append(
        self,
        stream: str,
        row: dict[str, Any],
        *,
        id_field: str,
    ) -> Path:
        if stream not in STREAMS:
            raise ValueError(f"Unsupported FT2 journal stream: {stream}")
        identifier = row.get(id_field)
        if not identifier:
            raise ValueError(f"Immutable row requires {id_field}")
        if any(item.get(id_field) == identifier for item in self.read(stream)):
            raise ValueError(f"Duplicate immutable {id_field}: {identifier}")
        supersedes = row.get("supersedes_id")
        if supersedes and not any(
            item.get(id_field) == supersedes for item in self.read(stream)
        ):
            raise ValueError(f"Superseded {id_field} does not exist: {supersedes}")
        payload = {
            **row,
            "candidate_hash": self.candidate_hash,
            "recorded_at": datetime.now(UTC).isoformat(),
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }
        path = self.root / f"{stream}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
        return path

    def read(self, stream: str) -> list[dict[str, Any]]:
        if stream not in STREAMS:
            raise ValueError(f"Unsupported FT2 journal stream: {stream}")
        path = self.root / f"{stream}.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def latest(self, stream: str) -> dict[str, Any] | None:
        rows = self.read(stream)
        return rows[-1] if rows else None

    def by_session(self, stream: str, session_date: date | str) -> list[dict[str, Any]]:
        value = session_date.isoformat() if isinstance(session_date, date) else session_date
        return [
            item for item in self.read(stream) if item.get("session_date") == value
        ]
