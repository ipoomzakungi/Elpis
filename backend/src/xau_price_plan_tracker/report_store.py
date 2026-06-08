from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_price_plan_tracker import (
    XauPlanTrackerRunResult,
    XauResearchPlanTrackerSnapshot,
    XauResearchTrackedOrder,
)


class XauPlanTrackerReportStore:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.plan_tracker_root = self.reports_dir / "xau_plan_tracker"

    def report_root(self) -> Path:
        return self.plan_tracker_root

    def report_dir(self, run_id: str) -> Path:
        return self.plan_tracker_root / _safe_id(run_id)

    def latest_result(self) -> XauPlanTrackerRunResult:
        candidates = sorted(
            self.plan_tracker_root.glob("*/plan_tracker_metadata.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError("No XAU plan tracker run exists")
        return XauPlanTrackerRunResult.model_validate_json(
            candidates[0].read_text(encoding="utf-8")
        )

    def read_result(self, run_id: str) -> XauPlanTrackerRunResult:
        path = self.report_dir(run_id) / "plan_tracker_metadata.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        return XauPlanTrackerRunResult.model_validate_json(path.read_text(encoding="utf-8"))

    def read_snapshots(self, run_id: str) -> list[XauResearchPlanTrackerSnapshot]:
        path = self.report_dir(run_id) / "snapshots.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [XauResearchPlanTrackerSnapshot.model_validate(item) for item in payload]

    def read_orders(self, run_id: str) -> list[XauResearchTrackedOrder]:
        path = self.report_dir(run_id) / "tracked_orders.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [XauResearchTrackedOrder.model_validate(item) for item in payload]

    def persist_run(
        self,
        *,
        result: XauPlanTrackerRunResult,
        snapshots: list[XauResearchPlanTrackerSnapshot],
        tracked_orders: list[XauResearchTrackedOrder],
        overwrite: bool = False,
    ) -> XauPlanTrackerRunResult:
        report_dir = self.report_dir(result.run_id)
        if report_dir.exists() and not overwrite:
            raise FileExistsError(result.run_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "metadata": report_dir / "plan_tracker_metadata.json",
            "snapshots": report_dir / "snapshots.json",
            "tracked_orders": report_dir / "tracked_orders.json",
            "run_markdown": report_dir / "run.md",
            "order_history": report_dir / "order_history.md",
        }
        artifact_paths = [_project_relative(path, self.repo_root) for path in paths.values()]
        result_with_paths = result.model_copy(update={"artifact_paths": artifact_paths})
        _write_json(paths["metadata"], result_with_paths.model_dump(mode="json"))
        _write_json(
            paths["snapshots"],
            [snapshot.model_dump(mode="json") for snapshot in snapshots],
        )
        _write_json(
            paths["tracked_orders"],
            [order.model_dump(mode="json") for order in tracked_orders],
        )
        paths["run_markdown"].write_text(
            _run_markdown(result_with_paths, snapshots, tracked_orders),
            encoding="utf-8",
        )
        paths["order_history"].write_text(
            _orders_markdown(tracked_orders),
            encoding="utf-8",
        )
        return result_with_paths


def new_plan_tracker_run_id(session_date) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"xau_plan_tracker_{session_date}_{stamp}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _project_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _safe_id(value: str) -> str:
    normalized = "".join(char for char in value if char.isalnum() or char in "-_:.")
    if not normalized:
        raise ValueError("run_id must not be blank")
    return normalized


def _run_markdown(
    result: XauPlanTrackerRunResult,
    snapshots: list[XauResearchPlanTrackerSnapshot],
    orders: list[XauResearchTrackedOrder],
) -> str:
    lines = [
        f"# XAU Plan Tracker Run {result.run_id}",
        "",
        (
            "Research-only simulated plan tracking. No live orders, broker access, "
            "alerts, or real PnL."
        ),
        "",
        f"- Session date: `{result.session_date}`",
        f"- Readiness: `{result.readiness.value}`",
        f"- Snapshots: `{len(snapshots)}`",
        f"- Tracked orders: `{len(orders)}`",
        f"- signal_allowed: `{str(result.signal_allowed).lower()}`",
        "",
        "## Snapshots",
    ]
    for snapshot in snapshots:
        lines.append(
            f"- `{snapshot.planning_time.isoformat()}` future=`{snapshot.future_reference_price}` "
            f"traded=`{snapshot.traded_reference_price}` diff=`{snapshot.diff_points}` "
            f"1SD=`{snapshot.native_1sd}` 2SD=`{snapshot.native_2sd}` 3SD=`{snapshot.native_3sd}`"
        )
    lines.extend(["", "## Orders"])
    for order in orders:
        lines.append(
            f"- `{order.order_id}` {order.side.value}: entry=`{order.entry_level}` "
            f"target=`{order.target_level}` stop=`{order.stop_level}` "
            f"status=`{order.status.value}` "
            f"pnl_points=`{order.current_pnl_points}` drawdown_points=`{order.drawdown_points}`"
        )
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines) + "\n"


def _orders_markdown(orders: list[XauResearchTrackedOrder]) -> str:
    lines = [
        "# XAU Plan Tracker Simulated Orders",
        "",
        "Research-only simulated order history. Not live order management.",
        "",
    ]
    for order in orders:
        trigger = order.trigger_time.isoformat() if order.trigger_time else None
        exit_time = order.exit_time.isoformat() if order.exit_time else None
        closest = (
            f"{order.closest_price_to_entry}@{order.closest_time_to_entry.isoformat()}"
            if order.closest_price_to_entry is not None
            and order.closest_time_to_entry is not None
            else None
        )
        lines.append(
            f"- `{order.order_id}` {order.side.value}: status=`{order.status.value}` "
            f"trigger=`{trigger}` exit=`{exit_time}` current=`{order.current_price}` "
            f"pnl_points=`{order.current_pnl_points}` "
            f"strict_triggered=`{order.strict_triggered}` "
            f"near_miss=`{order.near_miss}` "
            f"near_miss_distance=`{order.near_miss_distance_points}` "
            f"near_miss_threshold=`{order.near_miss_threshold_points}` "
            f"closest_entry=`{closest}` "
            f"mae_points=`{order.max_adverse_excursion_points}` signal_allowed=`false`"
        )
    return "\n".join(lines) + "\n"


__all__ = ["XauPlanTrackerReportStore", "new_plan_tracker_run_id"]
