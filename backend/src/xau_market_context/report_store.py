from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_market_context import XauMarketContextSnapshot


class XauMarketContextReportStore:
    REPORT_ROOT_NAME = "xau_market_context"

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.report_root_path = self.reports_dir / self.REPORT_ROOT_NAME

    def report_root(self) -> Path:
        return self.report_root_path

    def report_dir(self, snapshot_id: str) -> Path:
        return self.report_root_path / _safe_id(snapshot_id)

    def persist_snapshot(
        self,
        snapshot: XauMarketContextSnapshot,
        *,
        overwrite: bool = False,
    ) -> XauMarketContextSnapshot:
        report_dir = self.report_dir(snapshot.snapshot_id)
        if report_dir.exists() and not overwrite:
            raise FileExistsError(snapshot.snapshot_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        context_path = report_dir / "context.json"
        metadata_path = report_dir / "metadata.json"
        markdown_path = report_dir / "context.md"
        _write_json(context_path, snapshot.model_dump(mode="json"))
        _write_json(metadata_path, _metadata(snapshot))
        markdown_path.write_text(_markdown(snapshot), encoding="utf-8")
        return snapshot

    def read_snapshot(self, snapshot_id: str) -> XauMarketContextSnapshot:
        path = self.report_dir(snapshot_id) / "context.json"
        if not path.exists():
            raise FileNotFoundError(snapshot_id)
        return XauMarketContextSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def new_market_context_snapshot_id(session_date: date | None = None) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    prefix_date = session_date.isoformat() if session_date else "unspecified"
    return f"xau_market_context_{prefix_date}_{stamp}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _metadata(snapshot: XauMarketContextSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "created_at": snapshot.created_at.isoformat(),
        "session_date": snapshot.session_date.isoformat(),
        "fusion_report_id": snapshot.fusion_report_id,
        "readiness": snapshot.readiness.value,
        "basis_status": snapshot.basis.status.value,
        "basis_points": snapshot.basis.basis_points,
        "active_session": (
            snapshot.active_session.session_name.value if snapshot.active_session else None
        ),
        "mapped_level_count": len(snapshot.mapped_levels),
        "candle_state_count": len(snapshot.candle_states),
        "missing_context": snapshot.missing_context,
        "research_only": snapshot.research_only,
        "signal_allowed": snapshot.signal_allowed,
    }


def _markdown(snapshot: XauMarketContextSnapshot) -> str:
    lines = [
        f"# XAU Market Context Snapshot {snapshot.snapshot_id}",
        "",
        "Research-only context report. No live trading, paper trading, broker execution, "
        "order placement, alerts, credentials, cookies, headers, HAR files, screenshots, "
        "private URLs, or session material are used or persisted.",
        "",
        f"- Readiness: `{snapshot.readiness.value}`",
        f"- Session date: `{snapshot.session_date}`",
        f"- Fusion report: `{snapshot.fusion_report_id}`",
        f"- Basis status: `{snapshot.basis.status.value}`",
        f"- Basis points: `{snapshot.basis.basis_points}`",
        f"- signal_allowed: `{str(snapshot.signal_allowed).lower()}`",
        f"- research_only: `{str(snapshot.research_only).lower()}`",
        "",
        "## Active Session",
    ]
    if snapshot.active_session is None:
        lines.append("- unavailable")
    else:
        lines.append(
            f"- `{snapshot.active_session.session_name.value}` open="
            f"`{snapshot.active_session.open_price}` at "
            f"`{snapshot.active_session.open_time.isoformat()}` "
            f"status=`{snapshot.active_session.status.value}`"
        )
    lines.extend(["", "## Nearest Mapped Wall"])
    if snapshot.nearest_mapped_wall is None:
        lines.append("- unavailable")
    else:
        lines.append(
            f"- futures=`{snapshot.nearest_mapped_wall.source_level}` "
            f"mapped=`{snapshot.nearest_mapped_wall.mapped_level}` "
            f"source=`{snapshot.nearest_mapped_wall.source}`"
        )
    lines.extend(["", "## Missing Context"])
    lines.extend(f"- {item}" for item in snapshot.missing_context)
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in snapshot.limitations)
    return "\n".join(lines) + "\n"


def _safe_id(value: str) -> str:
    normalized = "".join(char for char in value if char.isalnum() or char in "-_:.")
    if not normalized:
        raise ValueError("snapshot_id must not be blank")
    return normalized

