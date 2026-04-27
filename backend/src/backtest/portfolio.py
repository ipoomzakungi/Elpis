from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.models.backtest import (
    BacktestAssumptions,
    ExitReason,
    Position,
    TradeRecord,
    TradeSide,
)


@dataclass(frozen=True)
class ExitDecision:
    reason: ExitReason
    price: float


@dataclass(frozen=True)
class PositionSizing:
    quantity: float
    notional: float
    requested_quantity: float
    requested_notional: float
    capped: bool


NO_LEVERAGE_CAP_NOTE = "Position notional capped to available equity for no-leverage v0."


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_loss: float,
    risk_per_trade: float,
) -> tuple[float, float]:
    sizing = calculate_position_sizing(
        equity=equity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        risk_per_trade=risk_per_trade,
    )
    return sizing.quantity, sizing.notional


def calculate_position_sizing(
    equity: float,
    entry_price: float,
    stop_loss: float,
    risk_per_trade: float,
    max_notional: float | None = None,
) -> PositionSizing:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    per_unit_risk = abs(entry_price - stop_loss)
    if per_unit_risk <= 0:
        raise ValueError("entry_price and stop_loss must not be equal")
    risk_amount = equity * risk_per_trade
    requested_quantity = risk_amount / per_unit_risk
    requested_notional = requested_quantity * entry_price
    quantity = requested_quantity
    notional = requested_notional
    capped = False

    if max_notional is not None:
        if max_notional <= 0:
            raise ValueError("max_notional must be positive")
        if requested_notional > max_notional:
            notional = max_notional
            quantity = max_notional / entry_price
            capped = True

    return PositionSizing(
        quantity=quantity,
        notional=notional,
        requested_quantity=requested_quantity,
        requested_notional=requested_notional,
        capped=capped,
    )


def calculate_capital_position_sizing(
    equity: float,
    entry_price: float,
    capital_fraction: float,
) -> PositionSizing:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if equity <= 0:
        raise ValueError("equity must be positive")
    if capital_fraction <= 0 or capital_fraction > 1:
        raise ValueError("capital_fraction must be greater than 0 and less than or equal to 1")

    notional = equity * capital_fraction
    quantity = notional / entry_price
    return PositionSizing(
        quantity=quantity,
        notional=notional,
        requested_quantity=quantity,
        requested_notional=notional,
        capped=False,
    )


def apply_entry_slippage(side: TradeSide, price: float, slippage_rate: float) -> float:
    if side == TradeSide.LONG:
        return price * (1 + slippage_rate)
    return price * (1 - slippage_rate)


def apply_exit_slippage(side: TradeSide, price: float, slippage_rate: float) -> float:
    if side == TradeSide.LONG:
        return price * (1 - slippage_rate)
    return price * (1 + slippage_rate)


def calculate_entry_fee(notional: float, fee_rate: float) -> float:
    return abs(notional) * fee_rate


def evaluate_exit(
    position: Position,
    bar: dict[str, Any],
    is_final_bar: bool,
) -> ExitDecision | None:
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])

    if position.side == TradeSide.LONG:
        stop_hit = low <= position.stop_loss
        take_profit_hit = position.take_profit is not None and high >= position.take_profit
    else:
        stop_hit = high >= position.stop_loss
        take_profit_hit = position.take_profit is not None and low <= position.take_profit

    if stop_hit:
        return ExitDecision(reason=ExitReason.STOP_LOSS, price=position.stop_loss)
    if take_profit_hit and position.take_profit is not None:
        return ExitDecision(reason=ExitReason.TAKE_PROFIT, price=position.take_profit)
    if is_final_bar:
        return ExitDecision(reason=ExitReason.END_OF_DATA, price=close)
    return None


def close_position(
    run_id: str,
    trade_index: int,
    position: Position,
    exit_timestamp: datetime,
    raw_exit_price: float,
    exit_reason: ExitReason,
    assumptions: BacktestAssumptions,
    signal_timestamp: datetime,
    symbol: str,
    timeframe: str,
    provider: str | None,
    regime_at_signal: str | None,
    holding_bars: int,
) -> TradeRecord:
    exit_price = apply_exit_slippage(position.side, raw_exit_price, assumptions.slippage_rate)
    exit_notional = position.quantity * exit_price
    exit_fee = calculate_entry_fee(exit_notional, assumptions.fee_rate)

    if position.side == TradeSide.LONG:
        gross_pnl = (exit_price - position.entry_price) * position.quantity
        slippage_cost = (
            (position.entry_price - position.notional / position.quantity)
            + (raw_exit_price - exit_price)
        ) * position.quantity
    else:
        gross_pnl = (position.entry_price - exit_price) * position.quantity
        slippage_cost = (
            (position.notional / position.quantity - position.entry_price)
            + (exit_price - raw_exit_price)
        ) * position.quantity

    fees = position.entry_fee + exit_fee
    net_pnl = gross_pnl - fees
    assumptions_snapshot = assumptions.model_dump(mode="json")
    if position.requested_notional is not None or position.sizing_method != "risk_fractional":
        assumptions_snapshot["sizing"] = {
            "method": position.sizing_method,
            "requested_notional": position.requested_notional or position.notional,
            "capped_notional": position.notional,
            "notional_cap": position.notional_cap,
            "capped": position.requested_notional is not None
            and position.requested_notional > position.notional,
            "notes": position.sizing_notes,
        }

    return TradeRecord(
        trade_id=f"T{trade_index:06d}",
        run_id=run_id,
        strategy_mode=position.strategy_mode,
        provider=provider,
        symbol=symbol,
        timeframe=timeframe,
        side=position.side,
        regime_at_signal=regime_at_signal,
        signal_timestamp=signal_timestamp,
        entry_timestamp=position.entry_timestamp,
        entry_price=position.entry_price,
        exit_timestamp=exit_timestamp,
        exit_price=exit_price,
        exit_reason=exit_reason,
        quantity=position.quantity,
        notional=position.notional,
        gross_pnl=gross_pnl,
        fees=fees,
        slippage=max(slippage_cost, 0.0),
        net_pnl=net_pnl,
        return_pct=net_pnl / position.notional,
        holding_bars=holding_bars,
        assumptions_snapshot=assumptions_snapshot,
    )
