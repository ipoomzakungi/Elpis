from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.models.xau_vol2vol_history_walkforward import (
    XauOiConfluenceLabel,
    XauOiConfluenceState,
    XauPlanReadiness,
    XauSdEntryLevel,
    XauSdMeanReversionPlan,
    XauSlMode,
    XauTpMode,
    XauTradeSide,
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
    XauVolRegimeLabel,
    XauWormholeLabel,
    XauWormholeState,
)


@dataclass(frozen=True)
class XauRangePlanBuildConfig:
    cycle_label: str = "manual"
    entry_sds: tuple[XauSdEntryLevel, ...] = (XauSdEntryLevel.TWO_SD, XauSdEntryLevel.THREE_SD)
    tp_modes: tuple[XauTpMode, ...] = (
        XauTpMode.HALF_SD,
        XauTpMode.ONE_SD,
        XauTpMode.FIXED_12_5,
        XauTpMode.FIXED_25,
    )
    sl_modes: tuple[XauSlMode, ...] = (
        XauSlMode.NEXT_HALF_SD,
        XauSlMode.NEXT_SD,
        XauSlMode.THREE_5SD,
    )
    sides: tuple[XauTradeSide, ...] = (
        XauTradeSide.LONG_REVERSION,
        XauTradeSide.SHORT_REVERSION,
    )
    oi_buffer_points: float = 5.0
    wormhole_threshold_total: float = 5.0


def map_future_level_to_cfd(future_level: float, diff: float) -> float:
    return future_level - diff


def build_sd_mean_reversion_plans(
    *,
    range_snapshot: XauVol2VolRangeDeskSnapshot,
    strike_rows: list[XauVol2VolStrikeSnapshot] | None = None,
    config: XauRangePlanBuildConfig | None = None,
) -> list[XauSdMeanReversionPlan]:
    config = config or XauRangePlanBuildConfig()
    levels = _mapped_levels(range_snapshot)
    blocked = _blocked_reasons(range_snapshot, levels)
    plans: list[XauSdMeanReversionPlan] = []
    rows = strike_rows or []
    for side in config.sides:
        for entry_sd in config.entry_sds:
            entry = _entry_level(levels, side, entry_sd)
            for tp_mode in config.tp_modes:
                target = _target_level(levels, side, entry_sd, entry, tp_mode)
                for sl_mode in config.sl_modes:
                    stop = _stop_level(levels, side, entry_sd, entry, sl_mode)
                    reasons = list(blocked)
                    if entry is None:
                        reasons.append(f"Missing {entry_sd.value} entry level for {side.value}.")
                    if target is None:
                        reasons.append(f"Missing target level for {tp_mode.value}.")
                    if stop is None:
                        reasons.append(f"Missing stop level for {sl_mode.value}.")
                    readiness = XauPlanReadiness.BLOCKED if reasons else XauPlanReadiness.READY
                    risk = _risk_points(side, entry, stop)
                    reward = _reward_points(side, entry, target)
                    rr = reward / risk if risk and reward is not None else None
                    confluence = _oi_confluence(
                        entry=entry,
                        rows=rows,
                        diff=range_snapshot.diff,
                        buffer_points=config.oi_buffer_points,
                    )
                    wormhole = _wormhole_state(
                        entry=entry,
                        target=target,
                        stop=stop,
                        side=side,
                        rows=rows,
                        diff=range_snapshot.diff,
                        threshold=config.wormhole_threshold_total,
                    )
                    plans.append(
                        XauSdMeanReversionPlan(
                            plan_id=_plan_id(
                                range_snapshot.session_date,
                                config.cycle_label,
                                side,
                                entry_sd,
                                tp_mode,
                                sl_mode,
                            ),
                            session_date=range_snapshot.session_date,
                            cycle_label=config.cycle_label,
                            observed_at=range_snapshot.observed_at,
                            side=side,
                            entry_sd=entry_sd,
                            entry_level=entry,
                            tp_mode=tp_mode,
                            target_level=target,
                            sl_mode=sl_mode,
                            stop_level=stop,
                            open_price=range_snapshot.cfd_open,
                            sd_step_points=levels.sd_step,
                            rr_points=rr,
                            risk_points=risk,
                            oi_confluence=confluence,
                            wormhole_state=wormhole,
                            vol_regime_label=_vol_regime(range_snapshot.vol_now),
                            readiness=readiness,
                            blocked_reasons=reasons,
                        )
                    )
    return plans


@dataclass(frozen=True)
class _Levels:
    open_price: float | None
    sd_step: float | None
    buy_1: float | None
    buy_2: float | None
    buy_3: float | None
    sell_1: float | None
    sell_2: float | None
    sell_3: float | None


def _mapped_levels(snapshot: XauVol2VolRangeDeskSnapshot) -> _Levels:
    diff = snapshot.diff

    def mapped(cfd_value: float | None, future_value: float | None) -> float | None:
        if cfd_value is not None:
            return cfd_value
        if future_value is not None and diff is not None:
            return map_future_level_to_cfd(future_value, diff)
        return None

    buy_1 = mapped(snapshot.cfd_buy_1sd, snapshot.future_buy_1sd)
    buy_2 = mapped(snapshot.cfd_buy_2sd, snapshot.future_buy_2sd)
    buy_3 = mapped(snapshot.cfd_buy_3sd, snapshot.future_buy_3sd)
    sell_1 = mapped(snapshot.cfd_sell_1sd, snapshot.future_sell_1sd)
    sell_2 = mapped(snapshot.cfd_sell_2sd, snapshot.future_sell_2sd)
    sell_3 = mapped(snapshot.cfd_sell_3sd, snapshot.future_sell_3sd)
    step = snapshot.sd_step_1
    if step is None:
        candidates = [
            abs(value - snapshot.cfd_open)
            for value in (buy_1, sell_1)
            if value is not None and snapshot.cfd_open is not None
        ]
        step = sum(candidates) / len(candidates) if candidates else None
    return _Levels(snapshot.cfd_open, step, buy_1, buy_2, buy_3, sell_1, sell_2, sell_3)


def _blocked_reasons(snapshot: XauVol2VolRangeDeskSnapshot, levels: _Levels) -> list[str]:
    reasons: list[str] = []
    if snapshot.diff is None:
        reasons.append("Missing Diff/Basis; futures levels cannot be mapped to CFD/XAUUSD.")
    if levels.sd_step is None:
        reasons.append("Missing SD step; TP/SL grid cannot be built.")
    if any(value is None for value in (levels.buy_2, levels.buy_3, levels.sell_2, levels.sell_3)):
        reasons.append("Missing 2SD/3SD CFD levels.")
    return reasons


def _entry_level(levels: _Levels, side: XauTradeSide, entry_sd: XauSdEntryLevel) -> float | None:
    if side == XauTradeSide.LONG_REVERSION:
        return {
            XauSdEntryLevel.ONE_SD: levels.buy_1,
            XauSdEntryLevel.TWO_SD: levels.buy_2,
            XauSdEntryLevel.THREE_SD: levels.buy_3,
        }[entry_sd]
    return {
        XauSdEntryLevel.ONE_SD: levels.sell_1,
        XauSdEntryLevel.TWO_SD: levels.sell_2,
        XauSdEntryLevel.THREE_SD: levels.sell_3,
    }[entry_sd]


def _target_level(
    levels: _Levels,
    side: XauTradeSide,
    entry_sd: XauSdEntryLevel,
    entry: float | None,
    tp_mode: XauTpMode,
) -> float | None:
    if entry is None:
        return None
    step = levels.sd_step
    if tp_mode == XauTpMode.OPEN_PRICE:
        return levels.open_price
    if tp_mode == XauTpMode.NEXT_WALL:
        return None
    if tp_mode == XauTpMode.FIXED_12_5:
        distance = 12.5
    elif tp_mode == XauTpMode.FIXED_25:
        distance = 25.0
    elif tp_mode == XauTpMode.HALF_SD:
        distance = step / 2 if step is not None else None
    elif tp_mode == XauTpMode.ONE_SD:
        distance = step
    else:
        distance = None
    if distance is None:
        return None
    return entry + distance if side == XauTradeSide.LONG_REVERSION else entry - distance


def _stop_level(
    levels: _Levels,
    side: XauTradeSide,
    entry_sd: XauSdEntryLevel,
    entry: float | None,
    sl_mode: XauSlMode,
) -> float | None:
    if entry is None:
        return None
    step = levels.sd_step
    if sl_mode == XauSlMode.FIXED_12_5:
        distance = 12.5
    elif sl_mode == XauSlMode.FIXED_25:
        distance = 25.0
    elif sl_mode == XauSlMode.NEXT_HALF_SD:
        distance = step / 2 if step is not None else None
    elif sl_mode == XauSlMode.THREE_5SD:
        distance = step / 2 if step is not None else None
        base = levels.buy_3 if side == XauTradeSide.LONG_REVERSION else levels.sell_3
        if base is None or distance is None:
            return None
        return base - distance if side == XauTradeSide.LONG_REVERSION else base + distance
    elif sl_mode in {XauSlMode.NEXT_SD, XauSlMode.THREE_SD}:
        if entry_sd == XauSdEntryLevel.ONE_SD:
            return levels.buy_2 if side == XauTradeSide.LONG_REVERSION else levels.sell_2
        return levels.buy_3 if side == XauTradeSide.LONG_REVERSION else levels.sell_3
    else:
        distance = None
    if distance is None:
        return None
    return entry - distance if side == XauTradeSide.LONG_REVERSION else entry + distance


def _risk_points(side: XauTradeSide, entry: float | None, stop: float | None) -> float | None:
    if entry is None or stop is None:
        return None
    return entry - stop if side == XauTradeSide.LONG_REVERSION else stop - entry


def _reward_points(side: XauTradeSide, entry: float | None, target: float | None) -> float | None:
    if entry is None or target is None:
        return None
    return target - entry if side == XauTradeSide.LONG_REVERSION else entry - target


def _oi_confluence(
    *,
    entry: float | None,
    rows: list[XauVol2VolStrikeSnapshot],
    diff: float | None,
    buffer_points: float,
) -> XauOiConfluenceState:
    if entry is None or not rows:
        return XauOiConfluenceState(confluence_label=XauOiConfluenceLabel.UNAVAILABLE)
    ranked = sorted(
        [row for row in rows if row.total is not None],
        key=lambda row: row.total or 0,
        reverse=True,
    )
    if not ranked:
        return XauOiConfluenceState(confluence_label=XauOiConfluenceLabel.UNAVAILABLE)
    best = min(ranked, key=lambda row: abs(_mapped_strike(row, diff) - entry))
    top_rank = ranked.index(best) + 1
    distance = abs(_mapped_strike(best, diff) - entry)
    label = XauOiConfluenceLabel.WEAK
    if top_rank <= 5 and distance <= buffer_points:
        label = XauOiConfluenceLabel.STRONG
    elif top_rank <= 10 or distance <= buffer_points * 2:
        label = XauOiConfluenceLabel.MEDIUM
    return XauOiConfluenceState(
        nearest_strike=_mapped_strike(best, diff),
        nearest_total=best.total,
        nearest_call=best.call,
        nearest_put=best.put,
        top_rank=top_rank,
        distance_points=distance,
        distance_to_entry_points=distance,
        confluence_label=label,
        notes=["OI is structural context only, not a buy/sell signal."],
    )


def _wormhole_state(
    *,
    entry: float | None,
    target: float | None,
    stop: float | None,
    side: XauTradeSide,
    rows: list[XauVol2VolStrikeSnapshot],
    diff: float | None,
    threshold: float,
) -> XauWormholeState | None:
    if entry is None:
        return None
    target_min = _min_total_between(rows, diff, entry, target)
    stop_min = _min_total_between(rows, diff, entry, stop)
    target_vacuum = target_min is not None and target_min <= threshold
    stop_vacuum = stop_min is not None and stop_min <= threshold
    if target_vacuum and stop_vacuum:
        label = XauWormholeLabel.BOTH_SIDES_VACUUM
    elif target_vacuum:
        label = XauWormholeLabel.TARGET_VACUUM
    elif stop_vacuum:
        label = XauWormholeLabel.STOP_VACUUM
    elif target_min is None and stop_min is None:
        label = XauWormholeLabel.UNAVAILABLE
    else:
        label = XauWormholeLabel.NONE
    return XauWormholeState(
        entry_level=entry,
        side=side,
        low_activity_between_entry_and_target=target_vacuum,
        low_activity_between_entry_and_stop=stop_vacuum,
        min_total_between_entry_and_target=target_min,
        min_total_between_entry_and_stop=stop_min,
        wormhole_label=label,
        notes=["Wormhole means low-activity gap/vacuum context, not direction."],
    )


def _min_total_between(
    rows: list[XauVol2VolStrikeSnapshot],
    diff: float | None,
    a: float,
    b: float | None,
) -> float | None:
    if b is None:
        return None
    lower, upper = sorted((a, b))
    totals = [
        row.total
        for row in rows
        if row.total is not None and lower <= _mapped_strike(row, diff) <= upper
    ]
    if not totals:
        return None
    return min(totals)


def _mapped_strike(row: XauVol2VolStrikeSnapshot, diff: float | None) -> float:
    return row.strike - diff if diff is not None else row.strike


def _vol_regime(vol_now: float | None) -> XauVolRegimeLabel:
    if vol_now is None:
        return XauVolRegimeLabel.UNAVAILABLE
    if vol_now >= 40:
        return XauVolRegimeLabel.HIGH
    if vol_now <= 15:
        return XauVolRegimeLabel.LOW
    return XauVolRegimeLabel.NORMAL


def _plan_id(
    session_date: date,
    cycle_label: str,
    side: XauTradeSide,
    entry_sd: XauSdEntryLevel,
    tp_mode: XauTpMode,
    sl_mode: XauSlMode,
) -> str:
    return "_".join(
        [
            "xau_v2v_plan",
            session_date.isoformat(),
            cycle_label,
            side.value,
            entry_sd.value,
            tp_mode.value,
            sl_mode.value,
        ]
    ).replace("-", "")
