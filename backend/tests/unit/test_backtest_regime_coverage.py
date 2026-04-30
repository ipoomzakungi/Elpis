from datetime import datetime, timedelta

from src.backtest.validation import calculate_regime_coverage
from src.models.backtest import ExitReason, StrategyMode, TradeRecord, TradeSide
from tests.helpers.test_backtest_validation_data import make_validation_feature_rows


def test_calculate_regime_coverage_counts_expected_and_unknown_regimes():
    features = make_validation_feature_rows(row_count=8)
    features = features.with_columns(
        regime=features["regime"].scatter([6, 7], ["CHOP", None])
    )
    trades = [
        _trade(1, regime="RANGE", net_pnl=40.0),
        _trade(2, regime="BREAKOUT_UP", net_pnl=-10.0),
        _trade(3, regime="CHOP", net_pnl=20.0),
        _trade(4, regime=None, net_pnl=-5.0),
    ]

    report = calculate_regime_coverage(features=features, trades=trades)

    assert report.bar_counts["RANGE"] == 2
    assert report.bar_counts["BREAKOUT_UP"] == 2
    assert report.bar_counts["BREAKOUT_DOWN"] == 1
    assert report.bar_counts["AVOID"] == 1
    assert report.bar_counts["UNKNOWN"] == 2
    assert report.trades_per_regime["RANGE"] == 1
    assert report.trades_per_regime["BREAKOUT_UP"] == 1
    assert report.trades_per_regime["UNKNOWN"] == 2
    assert report.return_by_regime["RANGE"]["net_pnl"] == 40.0
    assert report.return_by_regime["UNKNOWN"]["number_of_trades"] == 2
    assert any("unknown regime labels" in note for note in report.coverage_notes)


def test_calculate_regime_coverage_handles_missing_regime_column():
    features = make_validation_feature_rows(row_count=4).drop("regime")

    report = calculate_regime_coverage(features=features, trades=[])

    assert report.bar_counts["UNKNOWN"] == 4
    assert report.coverage_notes == [
        "Feature data did not include regime labels; all bars were counted as UNKNOWN."
    ]


def _trade(index: int, regime: str | None, net_pnl: float) -> TradeRecord:
    timestamp = datetime(2026, 4, 1) + timedelta(minutes=15 * index)
    return TradeRecord(
        trade_id=f"T{index:06d}",
        run_id="coverage_run",
        strategy_mode=StrategyMode.GRID_RANGE,
        provider="binance",
        symbol="BTCUSDT",
        timeframe="15m",
        side=TradeSide.LONG,
        regime_at_signal=regime,
        signal_timestamp=timestamp,
        entry_timestamp=timestamp + timedelta(minutes=15),
        entry_price=100.0,
        exit_timestamp=timestamp + timedelta(minutes=30),
        exit_price=100.0 + net_pnl,
        exit_reason=ExitReason.TAKE_PROFIT if net_pnl >= 0 else ExitReason.STOP_LOSS,
        quantity=1.0,
        notional=100.0,
        gross_pnl=net_pnl,
        fees=0.0,
        slippage=0.0,
        net_pnl=net_pnl,
        return_pct=net_pnl / 100.0,
        holding_bars=1,
    )
