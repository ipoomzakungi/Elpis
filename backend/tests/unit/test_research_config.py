import pytest
from pydantic import ValidationError

from src.models.research import (
    ResearchAssetClass,
    ResearchFeatureGroup,
    ResearchRunRequest,
)


def test_research_config_normalizes_assets_and_defaults():
    request = ResearchRunRequest.model_validate(
        {
            "assets": [
                {
                    "symbol": " btcusdt ",
                    "provider": " BINANCE ",
                    "asset_class": "crypto",
                    "timeframe": " 15m ",
                }
            ]
        }
    )

    asset = request.assets[0]
    assert asset.symbol == "BTCUSDT"
    assert asset.provider == "binance"
    assert asset.asset_class == ResearchAssetClass.CRYPTO
    assert asset.timeframe == "15m"
    assert asset.enabled is True
    assert asset.required_feature_groups == [
        ResearchFeatureGroup.OHLCV,
        ResearchFeatureGroup.REGIME,
    ]
    assert request.include_blocked_assets is True


def test_research_config_rejects_all_disabled_assets():
    with pytest.raises(ValidationError, match="at least one enabled asset is required"):
        ResearchRunRequest.model_validate(
            {
                "assets": [
                    {
                        "symbol": "BTCUSDT",
                        "provider": "binance",
                        "asset_class": "crypto",
                        "timeframe": "15m",
                        "enabled": False,
                    }
                ]
            }
        )


def test_research_config_rejects_forbidden_live_trading_fields():
    with pytest.raises(ValidationError, match="live-trading fields are not allowed"):
        ResearchRunRequest.model_validate(
            {
                "assets": [
                    {
                        "symbol": "BTCUSDT",
                        "provider": "binance",
                        "asset_class": "crypto",
                        "timeframe": "15m",
                    }
                ],
                "broker": {"api_key": "not-allowed"},
            }
        )

