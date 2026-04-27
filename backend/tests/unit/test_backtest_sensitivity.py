import pytest

from src.backtest.report_store import ReportStore
from src.backtest.validation import (
    ValidationReportService,
    apply_fragility_flags,
    validate_sensitivity_grid_size,
)
from src.models.backtest import (
    BacktestAssumptions,
    BacktestRunRequest,
    CostStressProfileName,
    ModeMetrics,
    ParameterSensitivityResult,
    ReportFormat,
    SensitivityGrid,
    StrategyConfig,
    StrategyMode,
    ValidationRunRequest,
)

from tests.helpers.test_backtest_validation_data import write_validation_features


def test_sensitivity_grid_size_validation_rejects_runaway_local_grids():
    grid = SensitivityGrid(
        grid_entry_threshold=[0.1, 0.15, 0.2, 0.25, 0.3],
        atr_stop_buffer=[0.5, 0.75, 1.0, 1.25, 1.5],
        breakout_risk_reward_multiple=[1.0, 1.5, 2.0, 2.5, 3.0],
        fee_slippage_profile=[CostStressProfileName.NORMAL, CostStressProfileName.HIGH_FEE],
    )

    with pytest.raises(ValueError, match="parameter grid exceeds local validation limit"):
        validate_sensitivity_grid_size(grid)


def test_parameter_sensitivity_executes_bounded_grid(isolated_data_paths):
    feature_path = isolated_data_paths / "processed" / "sensitivity_features.parquet"
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
                    mode=StrategyMode.GRID_RANGE,
                    entry_threshold=0.15,
                    atr_buffer=1.0,
                    allow_short=True,
                ),
                StrategyConfig(
                    mode=StrategyMode.BREAKOUT,
                    atr_buffer=1.0,
                    risk_reward_multiple=1.5,
                    allow_short=True,
                ),
            ],
            baselines=[],
            report_format=ReportFormat.JSON,
        ),
        sensitivity_grid=SensitivityGrid(
            grid_entry_threshold=[0.1, 0.2],
            atr_stop_buffer=[0.75],
            breakout_risk_reward_multiple=[1.5, 2.0],
            fee_slippage_profile=[CostStressProfileName.NORMAL],
        ),
    )

    results = service.run_parameter_sensitivity(request)

    parameter_sets = {row.parameter_set_id for row in results}
    assert parameter_sets == {
        "entry_0.1__atr_0.75__rr_1.5__cost_normal",
        "entry_0.1__atr_0.75__rr_2.0__cost_normal",
        "entry_0.2__atr_0.75__rr_1.5__cost_normal",
        "entry_0.2__atr_0.75__rr_2.0__cost_normal",
    }
    assert {row.strategy_mode for row in results}.issuperset(
        {StrategyMode.GRID_RANGE, StrategyMode.BREAKOUT}
    )
    assert all(row.stress_profile_name == CostStressProfileName.NORMAL for row in results)
    assert all(isinstance(row.fragility_flag, bool) for row in results)


def test_fragility_flags_isolated_strong_parameter_setting():
    results = [
        _sensitivity_result("set_1", -1.0),
        _sensitivity_result("set_2", 12.0),
        _sensitivity_result("set_3", -0.5),
    ]

    flagged = apply_fragility_flags(results)

    assert [row.fragility_flag for row in flagged] == [False, True, False]
    assert "isolated" in " ".join(flagged[1].notes).lower()


def _sensitivity_result(parameter_set_id: str, total_return_pct: float) -> ParameterSensitivityResult:
    return ParameterSensitivityResult(
        parameter_set_id=parameter_set_id,
        grid_entry_threshold=0.15,
        atr_stop_buffer=1.0,
        breakout_risk_reward_multiple=1.5,
        stress_profile_name=CostStressProfileName.NORMAL,
        strategy_mode=StrategyMode.GRID_RANGE,
        metrics=ModeMetrics(
            strategy_mode=StrategyMode.GRID_RANGE,
            category="strategy",
            total_return_pct=total_return_pct,
            max_drawdown_pct=-1.0,
            number_of_trades=1,
            equity_basis="total_mark_to_market",
        ),
    )