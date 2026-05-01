import pytest
from pydantic import ValidationError

from src.models.research_execution import (
    ProxyResearchWorkflowConfig,
    ResearchEvidenceDecision,
    ResearchExecutionRunRequest,
    ResearchExecutionWorkflowStatus,
    ResearchExecutionWorkflowType,
    XauVolOiWorkflowConfig,
)


def test_execution_config_normalizes_crypto_assets_and_defaults():
    request = ResearchExecutionRunRequest.model_validate(
        {
            "name": "first evidence run",
            "research_only_acknowledged": True,
            "crypto": {
                "enabled": True,
                "primary_assets": [" btcusdt ", "ethusdt"],
                "optional_assets": [" solusdt "],
            },
        }
    )

    assert request.name == "first evidence run"
    assert request.crypto is not None
    assert request.crypto.workflow_type == ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET
    assert request.crypto.primary_assets == ["BTCUSDT", "ETHUSDT"]
    assert request.crypto.optional_assets == ["SOLUSDT"]
    assert request.crypto.timeframe == "15m"
    assert request.crypto.required_capabilities == [
        "ohlcv",
        "regime",
        "open_interest",
        "funding",
        "volume_confirmation",
    ]


def test_execution_config_exposes_bounded_status_and_decision_enums():
    assert {status.value for status in ResearchExecutionWorkflowStatus} == {
        "completed",
        "partial",
        "blocked",
        "skipped",
        "failed",
    }
    assert {decision.value for decision in ResearchEvidenceDecision} == {
        "continue",
        "refine",
        "reject",
        "data_blocked",
        "inconclusive",
    }


def test_execution_config_requires_research_only_acknowledgement():
    with pytest.raises(ValidationError, match="research_only_acknowledged must be true"):
        ResearchExecutionRunRequest.model_validate(
            {
                "research_only_acknowledged": False,
                "crypto": {"enabled": True},
            }
        )


def test_execution_config_requires_at_least_one_enabled_workflow():
    with pytest.raises(ValidationError, match="at least one workflow must be enabled"):
        ResearchExecutionRunRequest.model_validate(
            {
                "research_only_acknowledged": True,
                "crypto": {"enabled": False},
                "proxy": {"enabled": False},
                "xau": {"enabled": False},
            }
        )


def test_execution_config_rejects_forbidden_execution_fields():
    with pytest.raises(ValidationError, match="live-trading fields are not allowed"):
        ResearchExecutionRunRequest.model_validate(
            {
                "research_only_acknowledged": True,
                "crypto": {"enabled": True},
                "broker": {"api_key": "not allowed"},
            }
        )


def test_execution_config_proxy_and_xau_defaults_are_research_only():
    proxy = ProxyResearchWorkflowConfig(assets=[" spy ", "gc=f"])
    xau = XauVolOiWorkflowConfig(options_oi_file_path="data/raw/xau/options.csv")

    assert proxy.workflow_type == ResearchExecutionWorkflowType.PROXY_OHLCV
    assert proxy.provider == "yahoo_finance"
    assert proxy.assets == ["SPY", "GC=F"]
    assert proxy.required_capabilities == ["ohlcv"]
    assert xau.workflow_type == ResearchExecutionWorkflowType.XAU_VOL_OI
    assert xau.required_capabilities == ["gold_options_oi"]
