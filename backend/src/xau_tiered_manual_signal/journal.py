from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STREAMS = {
    "plans",
    "signals",
    "acknowledgements",
    "outcomes",
    "daily_summary",
}


class ManualSignalJournal:
    def __init__(self, root: Path, policy_hash: str) -> None:
        self.root = root
        self.policy_hash = policy_hash
        self.root.mkdir(parents=True, exist_ok=True)
        for stream in STREAMS:
            (self.root / f"{stream}.jsonl").touch(exist_ok=True)

    def append(
        self,
        stream: str,
        row: dict[str, Any],
        *,
        id_field: str | None = None,
    ) -> Path:
        if stream not in STREAMS:
            raise ValueError(f"Unsupported manual-signal stream: {stream}")
        if id_field and any(
            item.get(id_field) == row.get(id_field) for item in self.read(stream)
        ):
            raise ValueError(f"Duplicate immutable {id_field}: {row.get(id_field)}")
        payload = {
            **row,
            "policy_hash": self.policy_hash,
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
            raise ValueError(f"Unsupported manual-signal stream: {stream}")
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
