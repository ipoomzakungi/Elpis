from collections.abc import Sequence
from typing import Any

from src.models.backtest import StrategyMode, StrategySignal, TradeSide

DEFAULT_ATR_BUFFER = 1.0
DEFAULT_RISK_REWARD_MULTIPLE = 1.5


def generate_buy_hold_signals(rows: Sequence[dict[str, Any]]) -> list[StrategySignal]:
    if len(rows) < 2:
        return []
    first_row = rows[0]
    return [
        StrategySignal(
            signal_id="buy_hold_000000_long",
            strategy_mode=StrategyMode.BUY_HOLD,
            signal_timestamp=first_row["timestamp"],
            side=TradeSide.LONG,
            entry_bar_index=1,
            stop_loss=0.01,
            take_profit=None,
            regime=first_row.get("regime"),
            reason="passive_buy_hold_baseline",
        )
    ]


def generate_price_breakout_signals(
    rows: Sequence[dict[str, Any]],
    allow_short: bool,
) -> list[StrategySignal]:
    signals: list[StrategySignal] = []
    for index, row in enumerate(rows[:-1]):
        close = float(row["close"])
        previous_close = float(rows[index - 1]["close"]) if index > 0 else None
        atr = float(row.get("atr") or 0.0)
        range_high = float(row["range_high"])
        range_low = float(row["range_low"])

        if close > range_high and (previous_close is None or previous_close <= range_high):
            stop_loss = max(0.01, close - (atr * DEFAULT_ATR_BUFFER))
            signals.append(
                StrategySignal(
                    signal_id=f"price_breakout_{index:06d}_long",
                    strategy_mode=StrategyMode.PRICE_BREAKOUT,
                    signal_timestamp=row["timestamp"],
                    side=TradeSide.LONG,
                    entry_bar_index=index + 1,
                    stop_loss=stop_loss,
                    take_profit=close + ((close - stop_loss) * DEFAULT_RISK_REWARD_MULTIPLE),
                    regime=row.get("regime"),
                    reason="price_only_breakout_long",
                )
            )
            continue

        if allow_short and close < range_low and (
            previous_close is None or previous_close >= range_low
        ):
            stop_loss = close + (atr * DEFAULT_ATR_BUFFER)
            signals.append(
                StrategySignal(
                    signal_id=f"price_breakout_{index:06d}_short",
                    strategy_mode=StrategyMode.PRICE_BREAKOUT,
                    signal_timestamp=row["timestamp"],
                    side=TradeSide.SHORT,
                    entry_bar_index=index + 1,
                    stop_loss=stop_loss,
                    take_profit=max(
                        0.01,
                        close - ((stop_loss - close) * DEFAULT_RISK_REWARD_MULTIPLE),
                    ),
                    regime=row.get("regime"),
                    reason="price_only_breakout_short",
                )
            )

    return signals


def generate_no_trade_signals() -> list[StrategySignal]:
    return []