from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_walk_forward_research import (
    XauResearchOrderOutcome,
    XauResearchOrderPlan,
    XauWalkForwardRunResult,
    XauWalkForwardSnapshotRecord,
)


class XauWalkForwardReportStore:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.walk_forward_root = self.reports_dir / "xau_walk_forward"

    def report_root(self) -> Path:
        return self.walk_forward_root

    def report_dir(self, run_id: str) -> Path:
        return self.walk_forward_root / _safe_id(run_id)

    def latest_result(self) -> XauWalkForwardRunResult:
        candidates = sorted(
            self.walk_forward_root.glob("*/run_metadata.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError("No XAU walk-forward run exists")
        return XauWalkForwardRunResult.model_validate_json(
            candidates[0].read_text(encoding="utf-8")
        )

    def read_result(self, run_id: str) -> XauWalkForwardRunResult:
        path = self.report_dir(run_id) / "run_metadata.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        return XauWalkForwardRunResult.model_validate_json(path.read_text(encoding="utf-8"))

    def read_snapshots(self, run_id: str) -> list[XauWalkForwardSnapshotRecord]:
        path = self.report_dir(run_id) / "snapshots.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [XauWalkForwardSnapshotRecord.model_validate(item) for item in payload]

    def read_orders(self, run_id: str) -> list[XauResearchOrderPlan]:
        path = self.report_dir(run_id) / "research_orders.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [XauResearchOrderPlan.model_validate(item) for item in payload]

    def persist_run(
        self,
        *,
        result: XauWalkForwardRunResult,
        snapshots: list[XauWalkForwardSnapshotRecord],
        orders: list[XauResearchOrderPlan],
        outcomes: list[XauResearchOrderOutcome],
        overwrite_allowed: bool = False,
    ) -> XauWalkForwardRunResult:
        report_dir = self.report_dir(result.run_id)
        if report_dir.exists() and not overwrite_allowed:
            raise FileExistsError(result.run_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "run_metadata": report_dir / "run_metadata.json",
            "snapshots": report_dir / "snapshots.json",
            "range_desk_snapshots": report_dir / "range_desk_snapshots.json",
            "research_orders": report_dir / "research_orders.json",
            "simulated_outcomes": report_dir / "simulated_outcomes.json",
            "run_markdown": report_dir / "run.md",
            "order_history": report_dir / "order_history.md",
        }
        artifact_paths = [
            _project_relative(path, self.repo_root)
            for path in paths.values()
        ]
        result_with_paths = result.model_copy(update={"artifact_paths": artifact_paths})
        _write_json(paths["run_metadata"], result_with_paths.model_dump(mode="json"))
        _write_json(
            paths["snapshots"],
            [snapshot.model_dump(mode="json") for snapshot in snapshots],
        )
        _write_json(
            paths["range_desk_snapshots"],
            [
                snapshot.range_desk_plan.model_dump(mode="json")
                for snapshot in snapshots
                if snapshot.range_desk_plan is not None
            ],
        )
        _write_json(paths["research_orders"], [order.model_dump(mode="json") for order in orders])
        _write_json(
            paths["simulated_outcomes"],
            [outcome.model_dump(mode="json") for outcome in outcomes],
        )
        paths["run_markdown"].write_text(
            _run_markdown(result_with_paths, snapshots, orders, outcomes),
            encoding="utf-8",
        )
        paths["order_history"].write_text(_orders_markdown(orders, outcomes), encoding="utf-8")
        return result_with_paths


def new_run_id(session_date) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"xau_walk_forward_{session_date}_{stamp}"


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
    result: XauWalkForwardRunResult,
    snapshots: list[XauWalkForwardSnapshotRecord],
    orders: list[XauResearchOrderPlan],
    outcomes: list[XauResearchOrderOutcome],
) -> str:
    lines = [
        f"# XAU Walk-Forward Run {result.run_id}",
        "",
        (
            "Research-only Range Desk walk-forward record. No live orders, "
            "broker access, alerts, or real PnL."
        ),
        "",
        f"- Session date: `{result.session_date}`",
        f"- Readiness: `{result.readiness.value}`",
        f"- Snapshots: `{len(snapshots)}`",
        f"- Research orders: `{len(orders)}`",
        f"- Outcomes: `{len(outcomes)}`",
        f"- signal_allowed: `{str(result.signal_allowed).lower()}`",
        "",
        "## Snapshots",
    ]
    for snapshot in snapshots:
        price = snapshot.price_snapshot
        sd = snapshot.sd_snapshot
        dte = sd.dte if sd else None
        source = sd.sd_source.value if sd else None
        lines.append(
            f"- `{snapshot.timestamp.isoformat()}` {snapshot.schedule_tag.value}: "
            f"diff=`{price.diff_points}` dte=`{dte}` sd_source=`{source}`"
        )
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines) + "\n"


def _orders_markdown(
    orders: list[XauResearchOrderPlan],
    outcomes: list[XauResearchOrderOutcome],
) -> str:
    by_plan = {outcome.plan_id: outcome for outcome in outcomes}
    lines = [
        "# XAU Walk-Forward Research Orders",
        "",
        "Research-only simulated order history. Not live order management.",
        "",
    ]
    for order in orders:
        outcome = by_plan.get(order.plan_id)
        lines.append(
            "- `{plan}` {side} {stage}: entry=`{entry}` target=`{target}` stop=`{stop}` "
            "risk=`{risk}` outcome=`{outcome}` signal_allowed=`false`".format(
                plan=order.plan_id,
                side=order.side.value,
                stage=order.stage.value,
                entry=order.entry_level,
                target=order.target_level,
                stop=order.stop_level,
                risk=order.risk_status.value,
                outcome=outcome.status.value if outcome else "not_run",
            )
        )
    return "\n".join(lines) + "\n"


__all__ = ["XauWalkForwardReportStore", "new_run_id"]
