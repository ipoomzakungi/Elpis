from collections.abc import Sequence
from typing import Any

from src.models.backtest import StrategyConfig, StrategyMode, StrategySignal, TradeSide

DEFAULT_ATR_BUFFER = 1.0
DEFAULT_RISK_REWARD_MULTIPLE = 1.5


def generate_breakout_signals(
    rows: Sequence[dict[str, Any]],
    config: StrategyConfig,
    allow_short: bool,
) -> list[StrategySignal]:
    signals: list[StrategySignal] = []
    atr_buffer = config.atr_buffer if config.atr_buffer is not None else DEFAULT_ATR_BUFFER
    risk_reward = (
        config.risk_reward_multiple
        if config.risk_reward_multiple is not None
        else DEFAULT_RISK_REWARD_MULTIPLE
    )

    for index, row in enumerate(rows[:-1]):
        regime = row.get("regime")
        close = float(row["close"])
        atr = float(row.get("atr") or 0.0)

        if regime == "BREAKOUT_UP":
            stop_loss = max(0.01, close - (atr * atr_buffer))
            signals.append(
                StrategySignal(
                    signal_id=f"breakout_{index:06d}_long",
                    strategy_mode=StrategyMode.BREAKOUT,
                    signal_timestamp=row["timestamp"],
                    side=TradeSide.LONG,
                    entry_bar_index=index + 1,
                    stop_loss=stop_loss,
                    take_profit=close + ((close - stop_loss) * risk_reward),
                    regime="BREAKOUT_UP",
                    reason="regime_breakout_up_long",
                )
            )
            continue

        if regime == "BREAKOUT_DOWN" and allow_short:
            stop_loss = close + (atr * atr_buffer)
            signals.append(
                StrategySignal(
                    signal_id=f"breakout_{index:06d}_short",
                    strategy_mode=StrategyMode.BREAKOUT,
                    signal_timestamp=row["timestamp"],
                    side=TradeSide.SHORT,
                    entry_bar_index=index + 1,
                    stop_loss=stop_loss,
                    take_profit=max(0.01, close - ((stop_loss - close) * risk_reward)),
                    regime="BREAKOUT_DOWN",
                    reason="regime_breakout_down_short",
                )
            )

    return signals