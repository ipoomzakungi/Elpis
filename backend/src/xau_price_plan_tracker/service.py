from __future__ import annotations

from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau_price_plan_tracker import (
    XauDukasCliCaptureRequest,
    XauDukasPriceBar,
    XauPlanLevels,
    XauPlanTrackerReadiness,
    XauPlanTrackerRequest,
    XauPlanTrackerRunResult,
    XauResearchPlanTrackerSnapshot,
    XauResearchTrackedOrder,
    XauTrackedOrderStatus,
)
from src.models.xau_walk_forward_research import (
    XauResearchOrderPlan,
    XauResearchOrderPlanConfig,
    XauResearchOrderSide,
    XauResearchOrderStage,
    XauResearchRiskConfig,
    XauWalkForwardAlignmentStatus,
    XauWalkForwardPriceSnapshot,
    XauWalkForwardPriceSource,
    XauWalkForwardSdSource,
    XauWalkForwardSourceQuality,
)
from src.xau_price_plan_tracker.dukas_cli import load_price_bars, run_dukas_cli_capture
from src.xau_price_plan_tracker.order_tracker import track_research_order
from src.xau_price_plan_tracker.reference_price import extract_reference_price_at
from src.xau_price_plan_tracker.report_store import (
    XauPlanTrackerReportStore,
    new_plan_tracker_run_id,
)
from src.xau_walk_forward.order_planner import generate_research_order_plans
from src.xau_walk_forward.sd_source import resolve_sd_snapshot


class XauPlanTrackerService:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir
        self.store = XauPlanTrackerReportStore(reports_dir=reports_dir)

    def run(self, request: XauPlanTrackerRequest) -> XauPlanTrackerRunResult:
        run_id = new_plan_tracker_run_id(request.session_date)
        planning_datetimes = [
            _combine(request.session_date, planning_time, request.timezone)
            for planning_time in request.planning_times
        ]
        run_until = _combine(request.session_date, request.run_until_time, request.timezone)
        bars, price_limitations = self._load_or_capture_bars(request, planning_datetimes, run_until)
        snapshots: list[XauResearchPlanTrackerSnapshot] = []
        tracked_orders: list[XauResearchTrackedOrder] = []
        missing_inputs: list[str] = []
        limitations = [
            "Feature 026 tracks research plans only; it does not place live or paper orders.",
            "Dukascopy bars are traded-side research price data, not an execution feed.",
            *price_limitations,
        ]

        for index, planning_time in enumerate(planning_datetimes):
            snapshot_id = f"{run_id}_{index:03d}"
            reference = extract_reference_price_at(bars, planning_time)
            sd_snapshot = resolve_sd_snapshot(
                timestamp=planning_time,
                cme_source=request.cme_source,
                reports_dir=self.reports_dir,
            )
            snapshot_missing: list[str] = []
            snapshot_limitations = [*reference.limitations, *sd_snapshot.limitations]
            if reference.reference_price is None:
                snapshot_missing.append("traded_reference_price")
            if sd_snapshot.sd_source == XauWalkForwardSdSource.UNAVAILABLE:
                snapshot_missing.append("native_sd")
            if sd_snapshot.future_reference_price is None:
                snapshot_missing.append("future_reference_price")

            plans: list[XauResearchOrderPlan] = []
            if not snapshot_missing:
                price_snapshot = XauWalkForwardPriceSnapshot(
                    timestamp=planning_time,
                    future_reference_price=sd_snapshot.future_reference_price,
                    traded_reference_price=reference.reference_price,
                    future_price_source=XauWalkForwardPriceSource.MANUAL,
                    traded_price_source=XauWalkForwardPriceSource.MANUAL,
                    source_quality=XauWalkForwardSourceQuality.MANUAL,
                    alignment_status=XauWalkForwardAlignmentStatus.ALIGNED,
                    limitations=reference.limitations,
                )
                plans = generate_research_order_plans(
                    snapshot_id=snapshot_id,
                    timestamp=planning_time,
                    price_snapshot=price_snapshot,
                    sd_snapshot=sd_snapshot,
                    config=_order_config(request),
                    risk_config=XauResearchRiskConfig(
                        recovery_enabled=True,
                        recovery_multiplier=request.recovery_multiplier,
                        point_value_per_size_unit=1.0,
                    ),
                )
                tracked_orders.extend(
                    _track_initial_orders(
                        plans=plans,
                        bars=bars,
                        planning_time=planning_time,
                        run_until=run_until,
                        near_miss_threshold_points=request.near_miss_threshold_points,
                    )
                )
            long_plan, short_plan = _plan_levels(plans)
            snapshot = XauResearchPlanTrackerSnapshot(
                snapshot_id=snapshot_id,
                planning_time=planning_time,
                future_reference_price=sd_snapshot.future_reference_price,
                traded_reference_price=reference.reference_price,
                diff_points=(
                    sd_snapshot.future_reference_price - reference.reference_price
                    if sd_snapshot.future_reference_price is not None
                    and reference.reference_price is not None
                    else None
                ),
                dte=sd_snapshot.dte,
                native_1sd=sd_snapshot.native_1sd,
                native_2sd=sd_snapshot.native_2sd,
                native_3sd=sd_snapshot.native_3sd,
                reference_alignment=reference.alignment_status,
                long_plan=long_plan,
                short_plan=short_plan,
                missing_inputs=snapshot_missing,
                limitations=snapshot_limitations,
            )
            snapshots.append(snapshot)
            missing_inputs.extend(snapshot_missing)

        result = XauPlanTrackerRunResult(
            run_id=run_id,
            created_at=datetime.now(UTC),
            session_date=request.session_date,
            snapshot_count=len(snapshots),
            tracked_order_count=len(tracked_orders),
            open_order_count=sum(
                1
                for order in tracked_orders
                if order.status
                in {
                    XauTrackedOrderStatus.OPEN,
                    XauTrackedOrderStatus.PLANNED,
                    XauTrackedOrderStatus.RECOVERY_TRIGGERED,
                }
            ),
            completed_order_count=sum(
                1
                for order in tracked_orders
                if order.status
                in {
                    XauTrackedOrderStatus.TARGET_HIT,
                    XauTrackedOrderStatus.STOP_HIT,
                    XauTrackedOrderStatus.RECOVERY_TARGET_HIT,
                    XauTrackedOrderStatus.EXPIRED,
                    XauTrackedOrderStatus.AMBIGUOUS,
                }
            ),
            readiness=_readiness(snapshots, tracked_orders, missing_inputs),
            missing_inputs=_dedupe(missing_inputs),
            limitations=_dedupe(limitations),
        )
        output_store = (
            XauPlanTrackerReportStore(reports_dir=request.output_root)
            if request.output_root is not None
            else self.store
        )
        return output_store.persist_run(
            result=result,
            snapshots=snapshots,
            tracked_orders=tracked_orders,
            overwrite=request.overwrite,
        )

    def latest(self) -> XauPlanTrackerRunResult:
        return self.store.latest_result()

    def get_run(self, run_id: str) -> XauPlanTrackerRunResult:
        return self.store.read_result(run_id)

    def get_snapshots(self, run_id: str) -> list[XauResearchPlanTrackerSnapshot]:
        return self.store.read_snapshots(run_id)

    def get_orders(self, run_id: str) -> list[XauResearchTrackedOrder]:
        return self.store.read_orders(run_id)

    def _load_or_capture_bars(
        self,
        request: XauPlanTrackerRequest,
        planning_datetimes: list[datetime],
        run_until: datetime,
    ) -> tuple[list[XauDukasPriceBar], list[str]]:
        if request.price_bars_path is not None:
            return (
                _normalize_bar_times(
                    load_price_bars(
                        request.price_bars_path,
                        symbol=request.symbol,
                        timeframe=request.timeframe,
                    ),
                    request.timezone,
                ),
                [],
            )
        capture_request = XauDukasCliCaptureRequest(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_time=min(planning_datetimes),
            end_time=run_until,
            timezone=request.timezone,
            dukas_cli_path=request.dukas_cli_path,
            command_template=request.command_template,
            output_dir=request.output_root,
            research_only_acknowledged=True,
        )
        capture = run_dukas_cli_capture(capture_request)
        if capture.bars_path is None or capture.status.value not in {"completed", "partial"}:
            return [], capture.limitations
        return (
            _normalize_bar_times(
                load_price_bars(
                    capture.bars_path,
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                ),
                request.timezone,
            ),
            capture.limitations,
        )


def _track_initial_orders(
    *,
    plans: list[XauResearchOrderPlan],
    bars: list[XauDukasPriceBar],
    planning_time: datetime,
    run_until: datetime,
    near_miss_threshold_points: float,
) -> list[XauResearchTrackedOrder]:
    recovery_by_side = {
        plan.side: plan for plan in plans if plan.stage == XauResearchOrderStage.RECOVERY_1
    }
    tracked: list[XauResearchTrackedOrder] = []
    for plan in plans:
        if plan.stage != XauResearchOrderStage.INITIAL:
            continue
        tracked.append(
            track_research_order(
                plan,
                bars,
                planning_time=planning_time,
                run_until=run_until,
                near_miss_threshold_points=near_miss_threshold_points,
                recovery_plan=recovery_by_side.get(plan.side),
            )
        )
    return tracked


def _plan_levels(
    plans: list[XauResearchOrderPlan],
) -> tuple[XauPlanLevels | None, XauPlanLevels | None]:
    recovery_by_side = {
        plan.side: plan for plan in plans if plan.stage == XauResearchOrderStage.RECOVERY_1
    }
    long_plan = None
    short_plan = None
    for plan in plans:
        if plan.stage != XauResearchOrderStage.INITIAL:
            continue
        recovery = recovery_by_side.get(plan.side)
        levels = XauPlanLevels(
            side=plan.side,
            entry_level=plan.entry_level,
            target_level=plan.target_level,
            stop_level=plan.stop_level,
            recovery_entry_level=recovery.entry_level if recovery else None,
            recovery_target_level=recovery.target_level if recovery else None,
        )
        if plan.side == XauResearchOrderSide.LONG_REVERSION:
            long_plan = levels
        elif plan.side == XauResearchOrderSide.SHORT_REVERSION:
            short_plan = levels
    return long_plan, short_plan


def _order_config(request: XauPlanTrackerRequest) -> XauResearchOrderPlanConfig:
    return XauResearchOrderPlanConfig(
        entry_sd_abs=request.entry_sd,
        target_sd_abs=request.target_sd,
        stop_sd_abs=request.stop_sd,
        recovery_entry_sd_abs=request.recovery_entry_sd,
        recovery_target_sd_abs=request.recovery_target_sd,
        max_recovery_steps=request.max_recovery_steps,
        expire_time=request.run_until_time,
    )


def _combine(session_date, value: time, timezone: str) -> datetime:
    return datetime.combine(session_date, value, tzinfo=ZoneInfo(timezone))


def _normalize_bar_times(
    bars: list[XauDukasPriceBar],
    timezone: str,
) -> list[XauDukasPriceBar]:
    zone = ZoneInfo(timezone)
    normalized = []
    for bar in bars:
        timestamp = bar.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=zone)
        else:
            timestamp = timestamp.astimezone(zone)
        normalized.append(bar.model_copy(update={"timestamp": timestamp}))
    return sorted(normalized, key=lambda item: item.timestamp)


def _readiness(
    snapshots: list[XauResearchPlanTrackerSnapshot],
    tracked_orders: list[XauResearchTrackedOrder],
    missing_inputs: list[str],
) -> XauPlanTrackerReadiness:
    if not snapshots:
        return XauPlanTrackerReadiness.BLOCKED
    if missing_inputs or not tracked_orders:
        return XauPlanTrackerReadiness.PARTIAL
    return XauPlanTrackerReadiness.COMPLETE


def _dedupe(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


__all__ = ["XauPlanTrackerService"]
