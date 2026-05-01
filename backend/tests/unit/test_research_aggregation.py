from datetime import datetime

from src.models.research import (
    ConcentrationAssetRow,
    ConcentrationWarningLevel,
    RegimeCoverageAssetRow,
    ResearchAssetClassification,
    ResearchAssetConfig,
    ResearchAssetRunStatus,
    ResearchCapabilitySnapshot,
    ResearchFeatureGroup,
    ResearchPreflightResult,
    ResearchPreflightStatus,
    StrategyComparisonRow,
    StressSurvivalRow,
    WalkForwardStabilityRow,
)
from src.research.aggregation import classify_asset_evidence


def test_classifies_missing_data_blocked_asset():
    asset = _asset_result(
        status=ResearchAssetRunStatus.BLOCKED,
        preflight_status=ResearchPreflightStatus.MISSING_DATA,
    )

    assert classify_asset_evidence(asset) == ResearchAssetClassification.MISSING_DATA


def test_classifies_no_trade_completed_asset_as_not_worth_continuing():
    asset = _asset_result(
        strategy_comparison=[
            StrategyComparisonRow(
                symbol="BTCUSDT",
                provider="binance",
                mode="grid_range",
                category="strategy",
                number_of_trades=0,
            )
        ]
    )

    assert classify_asset_evidence(asset) == ResearchAssetClassification.NOT_WORTH_CONTINUING


def test_classifies_fragile_when_stress_walk_forward_or_concentration_warns():
    asset = _asset_result(
        strategy_comparison=[
            StrategyComparisonRow(
                symbol="BTCUSDT",
                provider="binance",
                mode="grid_range",
                category="strategy",
                number_of_trades=2,
            )
        ],
        stress_summary=[
            StressSurvivalRow(
                symbol="BTCUSDT",
                mode="grid_range",
                profile="high_fee",
                outcome="turned_negative",
                survived=False,
            )
        ],
        walk_forward_summary=[
            WalkForwardStabilityRow(
                symbol="BTCUSDT",
                split_id="split_001",
                status="evaluated",
                row_count=24,
                trade_count=1,
                stable=False,
            )
        ],
        concentration_summary=[
            ConcentrationAssetRow(
                symbol="BTCUSDT",
                top_1_profit_contribution_pct=85.0,
                max_consecutive_losses=3,
                drawdown_recovery_status="not_recovered",
                warning_level=ConcentrationWarningLevel.HIGH,
            )
        ],
    )

    assert (
        classify_asset_evidence(asset, sensitivity_fragile=True)
        == ResearchAssetClassification.FRAGILE
    )


def test_classifies_robust_when_validation_evidence_has_no_fragility_flags():
    asset = _asset_result(
        strategy_comparison=[
            StrategyComparisonRow(
                symbol="BTCUSDT",
                provider="binance",
                mode="grid_range",
                category="strategy",
                number_of_trades=2,
            )
        ],
        stress_summary=[
            StressSurvivalRow(
                symbol="BTCUSDT",
                mode="grid_range",
                profile="normal",
                outcome="remained_positive",
                survived=True,
            )
        ],
        walk_forward_summary=[
            WalkForwardStabilityRow(
                symbol="BTCUSDT",
                split_id="split_001",
                status="evaluated",
                row_count=24,
                trade_count=1,
                stable=True,
            )
        ],
        regime_coverage_summary=[
            RegimeCoverageAssetRow(
                symbol="BTCUSDT",
                regime="RANGE",
                bar_count=12,
                trade_count=1,
                return_pct=1.0,
            )
        ],
        concentration_summary=[
            ConcentrationAssetRow(
                symbol="BTCUSDT",
                top_1_profit_contribution_pct=30.0,
                max_consecutive_losses=1,
                drawdown_recovery_status="recovered",
                warning_level=ConcentrationWarningLevel.NONE,
            )
        ],
    )

    assert classify_asset_evidence(asset) == ResearchAssetClassification.ROBUST


def _asset_result(**updates):
    asset = ResearchAssetConfig(
        symbol="BTCUSDT",
        provider="binance",
        asset_class="crypto",
        timeframe="15m",
        required_feature_groups=[ResearchFeatureGroup.OHLCV, ResearchFeatureGroup.REGIME],
    )
    preflight = ResearchPreflightResult(
        symbol=asset.symbol,
        provider=asset.provider,
        status=updates.pop("preflight_status", ResearchPreflightStatus.READY),
        feature_path="data/processed/btcusdt_15m_features.parquet",
        row_count=48,
        first_timestamp=datetime(2026, 4, 1),
        last_timestamp=datetime(2026, 4, 2),
        capability_snapshot=ResearchCapabilitySnapshot(
            provider="binance",
            supports_ohlcv=True,
            supports_open_interest=True,
            supports_funding_rate=True,
            detected_ohlcv=True,
            detected_regime=True,
            detected_open_interest=True,
            detected_funding_rate=True,
        ),
    )
    defaults = {
        "symbol": asset.symbol,
        "provider": asset.provider,
        "asset_class": asset.asset_class,
        "status": updates.pop("status", ResearchAssetRunStatus.COMPLETED),
        "classification": ResearchAssetClassification.INCONCLUSIVE,
        "preflight": preflight,
    }
    defaults.update(updates)
    from src.models.research import ResearchAssetResult

    return ResearchAssetResult(**defaults)
