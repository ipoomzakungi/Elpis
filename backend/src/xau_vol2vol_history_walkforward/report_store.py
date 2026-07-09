from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_vol2vol_history_walkforward import (
    XauSdMeanReversionPlan,
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
    XauWalkforwardStats,
    XauWalkforwardTradeOutcome,
)
from src.xau_vol2vol_history_walkforward.ai_pack_builder import build_ai_pack_markdown
from src.xau_vol2vol_history_walkforward.history_normalizer import write_normalized_artifacts


class XauVol2VolHistoryWalkforwardReportStore:
    REPORT_ROOT_NAME = "xau_vol2vol_history_walkforward"

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.report_root_path = self.reports_dir / self.REPORT_ROOT_NAME

    def report_dir(self, run_id: str) -> Path:
        return self.report_root_path / _safe_id(run_id)

    def persist_run(
        self,
        *,
        stats: XauWalkforwardStats,
        range_snapshots: list[XauVol2VolRangeDeskSnapshot],
        strike_rows: list[XauVol2VolStrikeSnapshot],
        plans: list[XauSdMeanReversionPlan],
        outcomes: list[XauWalkforwardTradeOutcome],
        raw_manifest: dict[str, Any],
        overwrite: bool = False,
    ) -> Path:
        report_dir = self.report_dir(stats.run_id)
        if report_dir.exists() and not overwrite:
            raise FileExistsError(stats.run_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        _write_json(report_dir / "raw_manifest.json", raw_manifest)
        write_normalized_artifacts(
            output_dir=report_dir,
            strike_rows=strike_rows,
            range_rows=range_snapshots,
        )
        _write_json(report_dir / "plans.json", [item.model_dump(mode="json") for item in plans])
        _write_json(
            report_dir / "outcomes.json",
            [item.model_dump(mode="json") for item in outcomes],
        )
        _write_json(report_dir / "stats.json", stats.model_dump(mode="json"))
        markdown = build_ai_pack_markdown(
            stats=stats,
            range_snapshots=range_snapshots,
            strike_rows=strike_rows,
            plans=plans,
            outcomes=outcomes,
        )
        (report_dir / "ai_walkforward_pack.md").write_text(markdown, encoding="utf-8")
        _write_json(
            report_dir / "ai_walkforward_pack.json",
            {
                "stats": stats.model_dump(mode="json"),
                "plan_count": len(plans),
                "outcome_count": len(outcomes),
                "research_only": True,
                "signal_allowed": False,
            },
        )
        _write_json(
            report_dir / "metadata.json",
            {
                "run_id": stats.run_id,
                "created_at": datetime.now(UTC).isoformat(),
                "report_dir": _project_relative(report_dir, self.repo_root),
                "plan_count": len(plans),
                "outcome_count": len(outcomes),
                "signal_allowed": False,
                "research_only": True,
            },
        )
        return report_dir


def new_walkforward_run_id() -> str:
    return f"xau_vol2vol_history_walkforward_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_id(value: str) -> str:
    normalized = "".join(char for char in value if char.isalnum() or char in "-_:.")
    if not normalized:
        raise ValueError("run_id must not be blank")
    return normalized


def _project_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
