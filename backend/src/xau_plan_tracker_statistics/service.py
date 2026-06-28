from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time
from pathlib import Path
from statistics import mean

from src.models.xau_plan_tracker_statistics import (
    XauPlanTrackerDteStats,
    XauPlanTrackerStatsRequest,
    XauPlanTrackerStatsResult,
    XauPlanTrackerStatsRunSummary,
)
from src.models.xau_price_plan_tracker import (
    XauPlanTrackerRunResult,
    XauResearchOrderSide,
    XauResearchPlanTrackerSnapshot,
    XauResearchTrackedOrder,
    XauTrackedOrderStatus,
)
from src.xau_price_plan_tracker.report_store import XauPlanTrackerReportStore


class XauPlanTrackerStatisticsService:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.store = XauPlanTrackerReportStore(reports_dir=reports_dir)

    def run(self, request: XauPlanTrackerStatsRequest) -> XauPlanTrackerStatsResult:
        runs = self._select_runs(request)
        if not runs:
            raise FileNotFoundError("No matching XAU plan tracker runs were found")

        return self._build_result(runs, request)

    def run_for_run(
        self,
        *,
        run_id: str,
        request: XauPlanTrackerStatsRequest,
    ) -> XauPlanTrackerStatsResult:
        run = self.store.read_result(run_id)
        return self._build_result([run], request)

    def _select_runs(self, request: XauPlanTrackerStatsRequest):
        runs = self.store.list_results()
        if request.session_date_from is not None:
            runs = [run for run in runs if run.session_date >= request.session_date_from]
        if request.session_date_to is not None:
            runs = [run for run in runs if run.session_date <= request.session_date_to]
        if request.max_runs is not None:
            runs = runs[: request.max_runs]
        return runs

    def _build_result(
        self,
        runs: list[XauPlanTrackerRunResult],
        request: XauPlanTrackerStatsRequest,
    ) -> XauPlanTrackerStatsResult:
        run_summaries: list[XauPlanTrackerStatsRunSummary] = []
        status_counts: dict[str, int] = defaultdict(int)
        side_counts: dict[str, int] = defaultdict(int)
        planning_time_counts: dict[str, int] = defaultdict(int)
        dte_values: list[float] = []
        total_near_miss = 0
        total_strict = 0
        recovery_count = 0
        current_pnl_values: list[float] = []
        drawdown_values: list[float] = []
        mfe_values: list[float] = []
        mae_values: list[float] = []
        total_snapshot_count = 0
        total_order_count = 0

        for run in runs:
            snapshots = self.store.read_snapshots(run.run_id)
            orders = self.store.read_orders(run.run_id)

            filtered_snapshots = _filter_snapshots(
                snapshots,
                planning_times=request.planning_times,
            )
            filtered_orders = _filter_orders(
                orders,
                planning_times=request.planning_times,
                sides=request.sides,
                statuses=request.statuses,
                include_unavailable=request.include_unavailable_orders,
            )

            total_snapshot_count += len(filtered_snapshots)
            total_order_count += len(filtered_orders)

            run_summary = _build_run_summary(
                run_id=run.run_id,
                session_date=run.session_date,
                snapshots=filtered_snapshots,
                orders=filtered_orders,
            )
            run_summaries.append(run_summary)

            for status, count in run_summary.status_counts.items():
                status_counts[status] += count
            for side, count in run_summary.side_counts.items():
                side_counts[side] += count
            for planning_time, count in run_summary.planning_time_counts.items():
                planning_time_counts[planning_time] += count

            for snapshot in filtered_snapshots:
                if snapshot.dte is not None:
                    dte_values.append(snapshot.dte)

            for order in filtered_orders:
                if order.status == XauTrackedOrderStatus.RECOVERY_TARGET_HIT:
                    recovery_count += 1
                if order.strict_triggered:
                    total_strict += 1
                if order.near_miss:
                    total_near_miss += 1
                if order.current_pnl_points is not None:
                    current_pnl_values.append(order.current_pnl_points)
                if order.drawdown_points is not None:
                    drawdown_values.append(order.drawdown_points)
                if order.max_favorable_excursion_points is not None:
                    mfe_values.append(order.max_favorable_excursion_points)
                if order.max_adverse_excursion_points is not None:
                    mae_values.append(order.max_adverse_excursion_points)

        return XauPlanTrackerStatsResult(
            generated_at=datetime.now(UTC),
            run_count=len(runs),
            snapshot_count=total_snapshot_count,
            order_count=total_order_count,
            run_ids=[summary.run_id for summary in run_summaries],
            planning_time_filter=request.planning_times,
            side_filter=request.sides,
            status_filter=request.statuses,
            include_unavailable_orders=request.include_unavailable_orders,
            status_counts=dict(status_counts),
            side_counts=dict(side_counts),
            planning_time_counts=dict(planning_time_counts),
            recovery_order_count=recovery_count,
            near_miss_count=total_near_miss,
            strict_triggered_count=total_strict,
            avg_current_pnl_points=_average(current_pnl_values),
            max_current_pnl_points=max(current_pnl_values) if current_pnl_values else None,
            min_current_pnl_points=min(current_pnl_values) if current_pnl_values else None,
            avg_drawdown_points=_average(drawdown_values),
            avg_mfe_points=_average(mfe_values),
            avg_mae_points=_average(mae_values),
            dte_summary=_dte_summary(dte_values),
            run_summaries=run_summaries,
            limitations=_accumulate_limitations(runs),
        )


def _filter_snapshots(
    snapshots: list[XauResearchPlanTrackerSnapshot],
    *,
    planning_times: list[time],
) -> list[XauResearchPlanTrackerSnapshot]:
    if not planning_times:
        return list(snapshots)
    planned = {value.strftime("%H:%M") for value in planning_times}
    return [
        snapshot
        for snapshot in snapshots
        if snapshot.planning_time.time().strftime("%H:%M") in planned
    ]


def _filter_orders(
    orders: list[XauResearchTrackedOrder],
    *,
    planning_times: list[time],
    sides: list[XauResearchOrderSide],
    statuses: list[XauTrackedOrderStatus],
    include_unavailable: bool,
) -> list[XauResearchTrackedOrder]:
    planned = {value.strftime("%H:%M") for value in planning_times} if planning_times else None
    output: list[XauResearchTrackedOrder] = []
    for order in orders:
        planning_time_key = order.planning_time.time().strftime("%H:%M")
        if planned is not None and planning_time_key not in planned:
            continue
        if not include_unavailable and order.status == XauTrackedOrderStatus.UNAVAILABLE:
            continue
        if sides and order.side not in sides:
            continue
        if statuses and order.status not in statuses:
            continue
        output.append(order)
    return output


def _build_run_summary(
    *,
    run_id: str,
    session_date: date,
    snapshots: list[XauResearchPlanTrackerSnapshot],
    orders: list[XauResearchTrackedOrder],
) -> XauPlanTrackerStatsRunSummary:
    side_counts: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    planning_time_counts: dict[str, int] = defaultdict(int)
    pnl_values: list[float] = []
    drawdown_values: list[float] = []
    near_miss = 0
    strict = 0

    for order in orders:
        status_counts[order.status.value] += 1
        side_counts[order.side.value] += 1
        planning_time_counts[order.planning_time.time().strftime("%H:%M")] += 1
        if order.near_miss:
            near_miss += 1
        if order.strict_triggered:
            strict += 1
        if order.current_pnl_points is not None:
            pnl_values.append(order.current_pnl_points)
        if order.drawdown_points is not None:
            drawdown_values.append(order.drawdown_points)

    return XauPlanTrackerStatsRunSummary(
        run_id=run_id,
        session_date=session_date,
        snapshot_count=len(snapshots),
        order_count=len(orders),
        status_counts=dict(status_counts),
        side_counts=dict(side_counts),
        planning_time_counts=dict(planning_time_counts),
        near_miss_count=near_miss,
        strict_triggered_count=strict,
        avg_current_pnl_points=_average(pnl_values),
        avg_drawdown_points=_average(drawdown_values),
    )


def _accumulate_limitations(runs: list[XauPlanTrackerRunResult]) -> list[str]:
    limitations: list[str] = []
    for run in runs:
        limitations.extend(run.limitations)
    if "Feature 028 aggregates only completed/persisted plan tracker runs." not in limitations:
        limitations.append("Feature 028 aggregates only completed/persisted plan tracker runs.")
    output: list[str] = []
    for item in limitations:
        normalized = str(item).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _average(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _dte_summary(values: list[float]) -> XauPlanTrackerDteStats:
    if not values:
        return XauPlanTrackerDteStats(sample_count=0)
    return XauPlanTrackerDteStats(
        sample_count=len(values),
        min=min(values),
        max=max(values),
        average=round(mean(values), 6),
    )


__all__ = ["XauPlanTrackerStatisticsService"]
