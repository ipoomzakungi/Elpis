import pytest

from src.models.data_bootstrap import (
    DataBootstrapArtifactType,
    DataBootstrapAssetStatus,
    DataBootstrapProvider,
    DataBootstrapStatus,
    PublicDataBootstrapRequest,
)


def test_public_bootstrap_request_normalizes_allowed_symbols_and_timeframes():
    request = PublicDataBootstrapRequest(
        binance_symbols=["btcusdt", "ETHUSDT", "BTCUSDT"],
        optional_binance_symbols=["solusdt"],
        binance_timeframes=["15M", "1h", "15m"],
        yahoo_symbols=["spy", "GC=F"],
        yahoo_timeframes=["1D"],
        research_only_acknowledged=True,
    )

    assert request.binance_symbols == ["BTCUSDT", "ETHUSDT"]
    assert request.optional_binance_symbols == ["SOLUSDT"]
    assert request.binance_timeframes == ["15m", "1h"]
    assert request.yahoo_symbols == ["SPY", "GC=F"]
    assert request.yahoo_timeframes == ["1d"]


def test_public_bootstrap_request_rejects_forbidden_scope_fields():
    with pytest.raises(ValueError, match="live-trading fields"):
        PublicDataBootstrapRequest(
            binance_symbols=["BTCUSDT"],
            research_only_acknowledged=True,
            order={"symbol": "BTCUSDT"},
        )


def test_public_bootstrap_request_rejects_unacknowledged_research_scope():
    with pytest.raises(ValueError, match="research_only_acknowledged"):
        PublicDataBootstrapRequest(research_only_acknowledged=False)


def test_public_bootstrap_request_rejects_unsupported_public_symbols_and_timeframes():
    with pytest.raises(ValueError, match="unsupported public bootstrap symbol"):
        PublicDataBootstrapRequest(
            binance_symbols=["NOTREAL"],
            research_only_acknowledged=True,
        )

    with pytest.raises(ValueError, match="unsupported public bootstrap timeframe"):
        PublicDataBootstrapRequest(
            binance_symbols=["BTCUSDT"],
            binance_timeframes=["5m"],
            research_only_acknowledged=True,
        )


def test_data_bootstrap_enums_expose_009_statuses():
    assert DataBootstrapProvider.BINANCE_PUBLIC == "binance_public"
    assert DataBootstrapStatus.PARTIAL == "partial"
    assert DataBootstrapAssetStatus.DOWNLOADED == "downloaded"
    assert DataBootstrapArtifactType.PROCESSED_FEATURES == "processed_features"
