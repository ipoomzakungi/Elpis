from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauEntryType,
    XauPlanReadiness,
    XauSdMeanReversionPlan,
    XauTradeSide,
    XauWalkforwardTradeOutcome,
    XauWalkforwardTradeStatus,
    XauWindowAlignmentStatus,
)
from src.xau_market_context.price_loader import load_price_bars


@dataclass(frozen=True)
class XauPriceBarFolderLoadResult:
    bars: list[XauPriceBar] = field(default_factory=list)
    source_paths: list[Path] = field(default_factory=list)
    duplicate_timestamp_count: int = 0
    warnings: list[str] = field(default_factory=list)


def load_traded_bars(path: Path, *, timezone: str = "Asia/Bangkok") -> list[XauPriceBar]:
    return load_price_bars(path, default_symbol="XAUUSD", default_timezone=timezone)


def load_traded_bars_folder(
    folder: Path,
    *,
    timezone: str = "Asia/Bangkok",
) -> XauPriceBarFolderLoadResult:
    source_paths = sorted(
        path
        for pattern in ("*.csv", "*.json")
        for path in folder.rglob(pattern)
        if path.is_file()
    )
    by_timestamp: dict[datetime, XauPriceBar] = {}
    duplicate_count = 0
    warnings: list[str] = []
    loaded_paths: list[Path] = []
    for path in source_paths:
        try:
            file_bars = load_traded_bars(path, timezone=timezone)
        except (OSError, ValueError) as exc:
            warnings.append(f"Could not load price bars from {path}: {exc}")
            continue
        loaded_paths.append(path)
        for bar in file_bars:
            if bar.timestamp in by_timestamp:
                duplicate_count += 1
            by_timestamp[bar.timestamp] = bar
    return XauPriceBarFolderLoadResult(
        bars=[by_timestamp[key] for key in sorted(by_timestamp)],
        source_paths=loaded_paths,
        duplicate_timestamp_count=duplicate_count,
        warnings=warnings,
    )


def simulate_plans(
    plans: list[XauSdMeanReversionPlan],
    bars: list[XauPriceBar],
    *,
    simulation_start: datetime | None = None,
    simulation_end: datetime | None = None,
    planning_time: time = time(0, 0),
    session_end_time: time = time(23, 0),
    entry_touch_policy: str = "touch",
    same_bar_policy: str = "ambiguous",
    cost_points: float = 0.0,
) -> list[XauWalkforwardTradeOutcome]:
    sorted_bars = sorted(bars, key=lambda item: item.timestamp)
    return [
        simulate_plan(
            plan,
            sorted_bars,
            simulation_start=simulation_start,
            simulation_end=simulation_end,
            planning_time=planning_time,
            session_end_time=session_end_time,
            entry_touch_policy=entry_touch_policy,
            same_bar_policy=same_bar_policy,
            cost_points=cost_points,
        )
        for plan in plans
    ]


def simulate_plan(
    plan: XauSdMeanReversionPlan,
    bars: list[XauPriceBar],
    *,
    simulation_start: datetime | None = None,
    simulation_end: datetime | None = None,
    planning_time: time = time(0, 0),
    session_end_time: time = time(23, 0),
    entry_touch_policy: str = "touch",
    same_bar_policy: str = "ambiguous",
    cost_points: float = 0.0,
) -> XauWalkforwardTradeOutcome:
    window_start, window_end, alignment = _plan_window(
        plan,
        bars,
        simulation_start=simulation_start,
        simulation_end=simulation_end,
        planning_time=planning_time,
        session_end_time=session_end_time,
    )
    if (
        plan.readiness == XauPlanReadiness.BLOCKED
        or plan.entry_level is None
        or plan.target_level is None
        or plan.stop_level is None
    ):
        return _outcome(
            plan,
            XauWalkforwardTradeStatus.UNAVAILABLE,
            bars_evaluated=0,
            window_start=window_start,
            window_end=window_end,
            alignment_status=alignment,
            cost_points=cost_points,
        )
    window_bars = [
        bar
        for bar in bars
        if window_start is not None
        and window_end is not None
        and window_start <= bar.timestamp <= window_end
    ]
    if not window_bars:
        return _outcome(
            plan,
            XauWalkforwardTradeStatus.UNAVAILABLE,
            bars_evaluated=0,
            window_start=window_start,
            window_end=window_end,
            alignment_status=XauWindowAlignmentStatus.NO_BARS_IN_WINDOW,
            cost_points=cost_points,
        )

    triggered_at: datetime | None = None
    touch_seen = False
    confirmation_at: datetime | None = None
    mfe: float | None = None
    mae: float | None = None
    bars_evaluated = 0
    first_bar_used = window_bars[0].timestamp
    last_bar_used = window_bars[-1].timestamp
    for bar in window_bars:
        if triggered_at is None:
            if plan.entry_type == XauEntryType.REJECTION_CONFIRMED:
                if confirmation_at is not None and bar.timestamp > confirmation_at:
                    triggered_at = bar.timestamp
                else:
                    if _entry_touched(plan, bar, entry_touch_policy):
                        touch_seen = True
                    if touch_seen and _is_rejection_confirmation(plan, bar):
                        confirmation_at = bar.timestamp
                    continue
            elif _entry_touched(plan, bar, entry_touch_policy):
                triggered_at = bar.timestamp
            else:
                continue

        bars_evaluated += 1
        favorable = _favorable_move(plan, bar)
        adverse = _adverse_move(plan, bar)
        mfe = favorable if mfe is None else max(mfe, favorable)
        mae = adverse if mae is None else min(mae, adverse)
        target_hit = _target_hit(plan, bar)
        stop_hit = _stop_hit(plan, bar)
        if target_hit and stop_hit:
            if same_bar_policy == "conservative_stop_first":
                return _exit(
                    plan,
                    XauWalkforwardTradeStatus.STOP_HIT,
                    triggered_at,
                    bar.timestamp,
                    plan.stop_level,
                    mfe,
                    mae,
                    bars_evaluated,
                    window_start=window_start,
                    window_end=window_end,
                    first_bar_used=first_bar_used,
                    last_bar_used=last_bar_used,
                    alignment_status=alignment,
                    cost_points=cost_points,
                    same_bar_ambiguous=True,
                    raw_result="target_and_stop_same_bar",
                    ambiguity_notes=["Target and stop were both inside the same candle."],
                )
            if same_bar_policy == "optimistic_target_first":
                return _exit(
                    plan,
                    XauWalkforwardTradeStatus.TARGET_HIT,
                    triggered_at,
                    bar.timestamp,
                    plan.target_level,
                    mfe,
                    mae,
                    bars_evaluated,
                    window_start=window_start,
                    window_end=window_end,
                    first_bar_used=first_bar_used,
                    last_bar_used=last_bar_used,
                    alignment_status=alignment,
                    cost_points=cost_points,
                    same_bar_ambiguous=True,
                    raw_result="target_and_stop_same_bar",
                    ambiguity_notes=["Target and stop were both inside the same candle."],
                )
            return _exit(
                plan,
                XauWalkforwardTradeStatus.AMBIGUOUS,
                triggered_at,
                bar.timestamp,
                None,
                mfe,
                mae,
                bars_evaluated,
                ambiguity_notes=["Target and stop were both inside the same candle."],
                window_start=window_start,
                window_end=window_end,
                first_bar_used=first_bar_used,
                last_bar_used=last_bar_used,
                alignment_status=alignment,
                cost_points=cost_points,
                same_bar_ambiguous=True,
                raw_result="target_and_stop_same_bar",
            )
        if target_hit:
            return _exit(
                plan,
                XauWalkforwardTradeStatus.TARGET_HIT,
                triggered_at,
                bar.timestamp,
                plan.target_level,
                mfe,
                mae,
                bars_evaluated,
                window_start=window_start,
                window_end=window_end,
                first_bar_used=first_bar_used,
                last_bar_used=last_bar_used,
                alignment_status=alignment,
                cost_points=cost_points,
            )
        if stop_hit:
            return _exit(
                plan,
                XauWalkforwardTradeStatus.STOP_HIT,
                triggered_at,
                bar.timestamp,
                plan.stop_level,
                mfe,
                mae,
                bars_evaluated,
                window_start=window_start,
                window_end=window_end,
                first_bar_used=first_bar_used,
                last_bar_used=last_bar_used,
                alignment_status=alignment,
                cost_points=cost_points,
            )

    if triggered_at is None:
        return _outcome(
            plan,
            XauWalkforwardTradeStatus.NO_FILL,
            bars_evaluated=len(window_bars),
            window_start=window_start,
            window_end=window_end,
            first_bar_used=first_bar_used,
            last_bar_used=last_bar_used,
            alignment_status=alignment,
            cost_points=cost_points,
        )
    last_bar = window_bars[-1]
    return _exit(
        plan,
        XauWalkforwardTradeStatus.EXPIRED,
        triggered_at,
        last_bar.timestamp,
        last_bar.close,
        mfe,
        mae,
        bars_evaluated,
        window_start=window_start,
        window_end=window_end,
        first_bar_used=first_bar_used,
        last_bar_used=last_bar_used,
        alignment_status=alignment,
        cost_points=cost_points,
    )


def _entry_touched(plan: XauSdMeanReversionPlan, bar: XauPriceBar, policy: str) -> bool:
    if policy == "close_through":
        if plan.side == XauTradeSide.LONG_REVERSION:
            return bar.close <= plan.entry_level
        return bar.close >= plan.entry_level
    return bar.low <= plan.entry_level <= bar.high


def _is_rejection_confirmation(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> bool:
    if bar.timestamp.minute % 5 != 4:
        return False
    if plan.side == XauTradeSide.LONG_REVERSION:
        return bar.close > plan.entry_level
    return bar.close < plan.entry_level


def _target_hit(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> bool:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return bar.high >= plan.target_level
    return bar.low <= plan.target_level


def _stop_hit(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> bool:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return bar.low <= plan.stop_level
    return bar.high >= plan.stop_level


def _favorable_move(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> float:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return max(bar.high - plan.entry_level, 0)
    return max(plan.entry_level - bar.low, 0)


def _adverse_move(plan: XauSdMeanReversionPlan, bar: XauPriceBar) -> float:
    if plan.side == XauTradeSide.LONG_REVERSION:
        return min(bar.low - plan.entry_level, 0)
    return min(plan.entry_level - bar.high, 0)


def _exit(
    plan: XauSdMeanReversionPlan,
    status: XauWalkforwardTradeStatus,
    triggered_at: datetime,
    exited_at: datetime,
    exit_level: float | None,
    mfe: float | None,
    mae: float | None,
    bars_evaluated: int,
    window_start: datetime | None,
    window_end: datetime | None,
    first_bar_used: datetime | None,
    last_bar_used: datetime | None,
    alignment_status: XauWindowAlignmentStatus,
    ambiguity_notes: list[str] | None = None,
    cost_points: float = 0.0,
    same_bar_ambiguous: bool = False,
    raw_result: str | None = None,
) -> XauWalkforwardTradeOutcome:
    gross_points = _gross_points(plan, exit_level)
    total_cost = cost_points if gross_points is not None else None
    return XauWalkforwardTradeOutcome(
        plan_id=plan.plan_id,
        session_date=plan.session_date,
        side=plan.side,
        entry_sd=plan.entry_sd,
        tp_mode=plan.tp_mode,
        sl_mode=plan.sl_mode,
        status=status,
        baseline_config=plan.baseline_config,
        entry_type=plan.entry_type,
        cycle_label=plan.cycle_label,
        cost_points=cost_points,
        triggered_at=triggered_at,
        exited_at=exited_at,
        entry_level=plan.entry_level,
        target_level=plan.target_level,
        stop_level=plan.stop_level,
        exit_level=exit_level,
        mfe_points=mfe,
        mae_points=mae,
        max_drawdown_points=abs(mae) if mae is not None else None,
        time_to_exit_minutes=(exited_at - triggered_at).total_seconds() / 60,
        bars_evaluated=bars_evaluated,
        simulation_window_start=window_start,
        simulation_window_end=window_end,
        plan_observed_at=plan.observed_at,
        first_bar_used=first_bar_used,
        last_bar_used=last_bar_used,
        window_alignment_status=alignment_status,
        ambiguity_notes=ambiguity_notes or [],
        same_bar_ambiguous=same_bar_ambiguous,
        raw_result=raw_result or status.value,
        gross_points=gross_points,
        total_cost_points=total_cost,
        net_points=gross_points - cost_points if gross_points is not None else None,
    )


def _outcome(
    plan: XauSdMeanReversionPlan,
    status: XauWalkforwardTradeStatus,
    *,
    bars_evaluated: int,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    first_bar_used: datetime | None = None,
    last_bar_used: datetime | None = None,
    alignment_status: XauWindowAlignmentStatus = XauWindowAlignmentStatus.INVALID,
    cost_points: float = 0.0,
) -> XauWalkforwardTradeOutcome:
    return XauWalkforwardTradeOutcome(
        plan_id=plan.plan_id,
        session_date=plan.session_date,
        side=plan.side,
        entry_sd=plan.entry_sd,
        tp_mode=plan.tp_mode,
        sl_mode=plan.sl_mode,
        status=status,
        baseline_config=plan.baseline_config,
        entry_type=plan.entry_type,
        cycle_label=plan.cycle_label,
        cost_points=cost_points,
        entry_level=plan.entry_level,
        target_level=plan.target_level,
        stop_level=plan.stop_level,
        bars_evaluated=bars_evaluated,
        simulation_window_start=window_start,
        simulation_window_end=window_end,
        plan_observed_at=plan.observed_at,
        first_bar_used=first_bar_used,
        last_bar_used=last_bar_used,
        window_alignment_status=alignment_status,
        raw_result=status.value,
    )


def _plan_window(
    plan: XauSdMeanReversionPlan,
    bars: list[XauPriceBar],
    *,
    simulation_start: datetime | None,
    simulation_end: datetime | None,
    planning_time: time,
    session_end_time: time,
) -> tuple[datetime | None, datetime | None, XauWindowAlignmentStatus]:
    timezone = plan.observed_at.tzinfo or (bars[0].timestamp.tzinfo if bars else None)
    if timezone is None:
        return None, None, XauWindowAlignmentStatus.INVALID
    session_start = datetime.combine(plan.session_date, planning_time, tzinfo=timezone)
    session_end = datetime.combine(plan.session_date, session_end_time, tzinfo=timezone)
    starts = [plan.observed_at, session_start]
    if plan.simulation_window_start is not None:
        starts.append(_coerce_timezone(plan.simulation_window_start, timezone))
    if simulation_start is not None:
        starts.append(_coerce_timezone(simulation_start, timezone))
    ends = [session_end]
    if plan.simulation_window_end is not None:
        ends.append(_coerce_timezone(plan.simulation_window_end, timezone))
    if simulation_end is not None:
        ends.append(_coerce_timezone(simulation_end, timezone))
    window_start = max(starts)
    window_end = min(ends)
    if window_end < window_start:
        return window_start, window_end, XauWindowAlignmentStatus.INVALID
    return window_start, window_end, XauWindowAlignmentStatus.ALIGNED


def _coerce_timezone(value: datetime, timezone) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def _gross_points(plan: XauSdMeanReversionPlan, exit_level: float | None) -> float | None:
    if plan.entry_level is None or exit_level is None:
        return None
    if plan.side == XauTradeSide.LONG_REVERSION:
        return exit_level - plan.entry_level
    return plan.entry_level - exit_level
