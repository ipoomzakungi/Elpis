import pytest

from src.backtest.report_store import ReportStore
from src.backtest.validation import ValidationReportService, build_cost_stress_profiles
from src.models.backtest import (
    BacktestAssumptions,
    BacktestRunRequest,
    BaselineMode,
    CostStressProfileName,
    ReportFormat,
    StrategyConfig,
    StrategyMode,
    ValidationRunRequest,
)

from tests.helpers.test_backtest_validation_data import write_validation_features


def test_cost_stress_profiles_are_predefined_and_bounded():
    profiles = build_cost_stress_profiles(base_fee_rate=0.0004, base_slippage_rate=0.0002)

    assert [profile.name for profile in profiles] == [
        CostStressProfileName.NORMAL,
        CostStressProfileName.HIGH_FEE,
        CostStressProfileName.HIGH_SLIPPAGE,
        CostStressProfileName.WORST_REASONABLE_COST,
    ]

    by_name = {profile.name: profile for profile in profiles}
    assert by_name[CostStressProfileName.NORMAL].fee_rate == pytest.approx(0.0004)
    assert by_name[CostStressProfileName.NORMAL].slippage_rate == pytest.approx(0.0002)
    assert by_name[CostStressProfileName.HIGH_FEE].fee_rate > by_name[CostStressProfileName.NORMAL].fee_rate
    assert by_name[CostStressProfileName.HIGH_FEE].slippage_rate == pytest.approx(0.0002)
    assert by_name[CostStressProfileName.HIGH_SLIPPAGE].fee_rate == pytest.approx(0.0004)
    assert by_name[CostStressProfileName.HIGH_SLIPPAGE].slippage_rate > by_name[CostStressProfileName.NORMAL].slippage_rate
    assert by_name[CostStressProfileName.WORST_REASONABLE_COST].fee_rate == pytest.approx(
        by_name[CostStressProfileName.HIGH_FEE].fee_rate
    )
    assert by_name[CostStressProfileName.WORST_REASONABLE_COST].slippage_rate == pytest.approx(
        by_name[CostStressProfileName.HIGH_SLIPPAGE].slippage_rate
    )
    assert all(profile.fee_rate <= 0.1 and profile.slippage_rate <= 0.1 for profile in profiles)


def test_cost_stress_runs_all_requested_profiles_and_modes(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "stress_features.parquet"
    write_validation_features(feature_path, row_count=16)

    service = ValidationReportService(report_store=ReportStore(base_path=isolated_data_paths / "reports"))
    request = ValidationRunRequest(
        base_config=BacktestRunRequest(
            symbol="BTCUSDT",
            provider="binance",
            timeframe="15m",
            feature_path=feature_path,
            initial_equity=10000,
            assumptions=BacktestAssumptions(fee_rate=0.0004, slippage_rate=0.0002),
            strategies=[
                StrategyConfig(
                    mode=StrategyMode.BREAKOUT,
                    atr_buffer=1.0,
                    risk_reward_multiple=1.5,
                    allow_short=True,
                )
            ],
            baselines=[BaselineMode.BUY_HOLD, BaselineMode.NO_TRADE],
            report_format=ReportFormat.JSON,
        ),
        stress_profiles=[
            CostStressProfileName.NORMAL,
            CostStressProfileName.HIGH_FEE,
            CostStressProfileName.HIGH_SLIPPAGE,
            CostStressProfileName.WORST_REASONABLE_COST,
        ],
    )

    results = service.run_cost_stress(request)

    assert {(row.profile.name, row.strategy_mode) for row in results} == {
        (profile, mode)
        for profile in request.stress_profiles
        for mode in {StrategyMode.BREAKOUT, StrategyMode.BUY_HOLD, StrategyMode.NO_TRADE}
    }
    assert all(row.category in {"strategy", "baseline"} for row in results)
    assert {row.outcome for row in results}.issubset(
        {"remained_positive", "turned_negative", "no_trades", "not_evaluable"}
    )
    assert any(row.strategy_mode == StrategyMode.NO_TRADE and row.outcome == "no_trades" for row in results)