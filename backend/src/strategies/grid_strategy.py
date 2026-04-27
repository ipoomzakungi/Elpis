from collections.abc import Sequence
from typing import Any

from src.models.backtest import StrategyConfig, StrategyMode, StrategySignal, TradeSide

DEFAULT_ENTRY_THRESHOLD = 0.5
DEFAULT_ATR_BUFFER = 1.0


def generate_grid_range_signals(
    rows: Sequence[dict[str, Any]],
    config: StrategyConfig,
    allow_short: bool,
) -> list[StrategySignal]:
    signals: list[StrategySignal] = []
    threshold = config.entry_threshold if config.entry_threshold is not None else DEFAULT_ENTRY_THRESHOLD
    atr_buffer = config.atr_buffer if config.atr_buffer is not None else DEFAULT_ATR_BUFFER

    for index, row in enumerate(rows[:-1]):
        if row.get("regime") != "RANGE":
            continue

        range_high = float(row["range_high"])
        range_low = float(row["range_low"])
        range_mid = float(row["range_mid"])
        close = float(row["close"])
        atr = float(row.get("atr") or 0.0)
        range_size = range_high - range_low
        if range_size <= 0:
            continue

        lower_entry_zone = range_low + (range_size * threshold)
        upper_entry_zone = range_high - (range_size * threshold)

        if close <= lower_entry_zone:
            signals.append(
                StrategySignal(
                    signal_id=f"grid_range_{index:06d}_long",
                    strategy_mode=StrategyMode.GRID_RANGE,
                    signal_timestamp=row["timestamp"],
                    side=TradeSide.LONG,
                    entry_bar_index=index + 1,
                    stop_loss=max(0.01, range_low - (atr * atr_buffer)),
                    take_profit=_take_profit(close=close, range_mid=range_mid, config=config),
                    regime="RANGE",
                    reason="range_lower_boundary_long",
                )
            )
            continue

        if allow_short and close >= upper_entry_zone:
            signals.append(
                StrategySignal(
                    signal_id=f"grid_range_{index:06d}_short",
                    strategy_mode=StrategyMode.GRID_RANGE,
                    signal_timestamp=row["timestamp"],
                    side=TradeSide.SHORT,
                    entry_bar_index=index + 1,
                    stop_loss=range_high + (atr * atr_buffer),
                    take_profit=_take_profit(close=close, range_mid=range_mid, config=config),
                    regime="RANGE",
                    reason="range_upper_boundary_short",
                )
            )

    return signals


def _take_profit(close: float, range_mid: float, config: StrategyConfig) -> float | None:
    if config.take_profit is not None and config.take_profit.value is not None:
        return config.take_profit.value
    if config.take_profit is None or config.take_profit.mode == "range_mid":
        return range_mid
    if config.take_profit.mode == "next_grid":
        step = abs(range_mid - close)
        return close + step if close < range_mid else max(0.01, close - step)
    return range_mid