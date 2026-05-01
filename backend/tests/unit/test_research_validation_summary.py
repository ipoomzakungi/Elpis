from datetime import datetime

from src.models.backtest import (
    BacktestRunRequest,
    BacktestStatus,
    CostStressProfile,
    CostStressProfileName,
    DrawdownRecoveryStatus,
    ModeMetrics,
    ParameterSensitivityResult,
    RegimeCoverageReport,
    StrategyMode,
    StressOutcome,
    StressResult,
    TradeConcentrationReport,
    ValidationRun,
    ValidationSplitStatus,
    WalkForwardResult,
)
from src.models.research import ConcentrationWarningLevel
from src.research.aggregation import validation_summaries_from_run


def test_validation_summary_aggregates_stress_walk_regime_and_concentration():
    validation_run = _validation_run()

    summaries = validation_summaries_from_run("BTCUSDT", validation_run)

    assert summaries.sensitivity_fragile is True
    assert any("Parameter sensitivity" in note for note in summaries.notes)

    stress = {(row.profile, row.mode): row for row in summaries.stress}
    assert stress[("normal", "grid_range")].survived is True
    assert stress[("high_fee", "grid_range")].survived is False

    walk = {row.split_id: row for row in summaries.walk_forward}
    assert walk["split_001"].stable is True
    assert walk["split_002"].stable is None

    regimes = {row.regime: row for row in summaries.regime_coverage}
    assert regimes["RANGE"].bar_count == 10
    assert regimes["RANGE"].trade_count == 2
    assert regimes["RANGE"].return_pct == 1.25
    assert regimes["UNKNOWN"].notes

    concentration = summaries.concentration[0]
    assert concentration.warning_level == ConcentrationWarningLevel.HIGH
    assert concentration.top_1_profit_contribution_pct == 82.0
    assert concentration.max_consecutive_losses == 4
    assert concentration.drawdown_recovery_status == "not_recovered"
    assert any("concentration" in note.lower() for note in concentration.notes)


def test_validation_summary_marks_watch_level_for_moderate_concentration():
    validation_run = _validation_run(
        concentration=TradeConcentrationReport(
            top_1_profit_contribution_pct=55.0,
            top_5_profit_contribution_pct=65.0,
            top_10_profit_contribution_pct=65.0,
            max_consecutive_losses=2,
            drawdown_recovery_status=DrawdownRecoveryStatus.RECOVERED,
        )
    )

    summaries = validation_summaries_from_run("BTCUSDT", validation_run)

    assert summaries.concentration[0].warning_level == ConcentrationWarningLevel.WATCH


def _validation_run(concentration: TradeConcentrationReport | None = None) -> ValidationRun:
    mode_metrics = ModeMetrics(
        strategy_mode=StrategyMode.GRID_RANGE,
        category="strategy",
        total_return_pct=2.0,
        max_drawdown_pct=-1.0,
        number_of_trades=2,
    )
    return ValidationRun(
        validation_run_id="val_test_btcusdt_15m",
        status=BacktestStatus.COMPLETED,
        created_at=datetime(2026, 4, 1),
        completed_at=datetime(2026, 4, 1),
        symbol="BTCUSDT",
        provider="binance",
        timeframe="15m",
        source_backtest_config=BacktestRunRequest(symbol="BTCUSDT", timeframe="15m"),
        mode_metrics=[mode_metrics],
        stress_results=[
            StressResult(
                profile=CostStressProfile(
                    name=CostStressProfileName.NORMAL,
                    fee_rate=0.0004,
                    slippage_rate=0.0002,
                    description="normal",
                ),
                strategy_mode=StrategyMode.GRID_RANGE,
                category="strategy",
                metrics=mode_metrics,
                outcome=StressOutcome.REMAINED_POSITIVE,
            ),
            StressResult(
                profile=CostStressProfile(
                    name=CostStressProfileName.HIGH_FEE,
                    fee_rate=0.001,
                    slippage_rate=0.0002,
                    description="high fee",
                ),
                strategy_mode=StrategyMode.GRID_RANGE,
                category="strategy",
                metrics=mode_metrics.model_copy(update={"total_return_pct": -0.5}),
                outcome=StressOutcome.TURNED_NEGATIVE,
            ),
        ],
        sensitivity_results=[
            ParameterSensitivityResult(
                parameter_set_id="entry_0.2__atr_1.0__rr_2.0__cost_normal",
                grid_entry_threshold=0.2,
                atr_stop_buffer=1.0,
                breakout_risk_reward_multiple=2.0,
                stress_profile_name=CostStressProfileName.NORMAL,
                strategy_mode=StrategyMode.GRID_RANGE,
                metrics=mode_metrics,
                fragility_flag=True,
            )
        ],
        walk_forward_results=[
            WalkForwardResult(
                split_id="split_001",
                start_timestamp=datetime(2026, 4, 1),
                end_timestamp=datetime(2026, 4, 2),
                row_count=24,
                trade_count=2,
                status=ValidationSplitStatus.EVALUATED,
                mode_metrics=[mode_metrics],
            ),
            WalkForwardResult(
                split_id="split_002",
                start_timestamp=datetime(2026, 4, 2),
                end_timestamp=datetime(2026, 4, 3),
                row_count=4,
                trade_count=0,
                status=ValidationSplitStatus.INSUFFICIENT_DATA,
                mode_metrics=[],
            ),
        ],
        regime_coverage=RegimeCoverageReport(
            bar_counts={"RANGE": 10, "BREAKOUT_UP": 5, "UNKNOWN": 1},
            trades_per_regime={"RANGE": 2, "BREAKOUT_UP": 1, "UNKNOWN": 0},
            return_by_regime={"RANGE": {"return_pct_display": 1.25}},
            coverage_notes=["Unknown regimes were grouped as UNKNOWN."],
        ),
        concentration_report=concentration
        or TradeConcentrationReport(
            top_1_profit_contribution_pct=82.0,
            top_5_profit_contribution_pct=95.0,
            top_10_profit_contribution_pct=95.0,
            max_consecutive_losses=4,
            drawdown_recovery_status=DrawdownRecoveryStatus.NOT_RECOVERED,
        ),
    )
