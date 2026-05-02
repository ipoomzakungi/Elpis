from fastapi.testclient import TestClient

from src.data_sources.readiness import OPTIONAL_PROVIDER_ENV_VARS
from src.main import app
from src.models.data_sources import DataSourceProviderType


def test_readiness_contract_returns_provider_statuses_without_secret_values(monkeypatch):
    _clear_optional_vendor_environment(monkeypatch)
    secret_value = "DO_NOT_LEAK_ABC987654321"
    monkeypatch.setenv("KAIKO_API_KEY", secret_value)
    client = TestClient(app)

    response = client.get("/api/v1/data-sources/readiness")

    assert response.status_code == 200
    assert secret_value not in response.text
    assert "ABC987" not in response.text
    assert "654321" not in response.text

    body = response.json()
    statuses = body["provider_statuses"]
    assert statuses
    assert all(status["secret_value_returned"] is False for status in statuses)

    kaiko = _find_provider(statuses, DataSourceProviderType.KAIKO_OPTIONAL)
    assert kaiko["configured"] is True
    assert kaiko["status"] == "configured"
    assert kaiko["env_var_name"] == "KAIKO_API_KEY"
    assert "KAIKO_API_KEY" in response.text

    tardis = _find_provider(statuses, DataSourceProviderType.TARDIS_OPTIONAL)
    assert tardis["configured"] is False
    assert tardis["status"] == "unavailable_optional"
    assert tardis["missing_actions"]


def test_capabilities_contract_returns_expected_provider_matrix():
    client = TestClient(app)

    response = client.get("/api/v1/data-sources/capabilities")

    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    providers = {row["provider_type"] for row in capabilities}

    assert "binance_public" in providers
    assert "yahoo_finance" in providers
    assert "local_file" in providers
    assert "kaiko_optional" in providers
    assert "tardis_optional" in providers
    assert "coinglass_optional" in providers
    assert "cryptoquant_optional" in providers
    assert "cme_quikstrike_local_or_optional" in providers
    assert "forbidden_private_trading" in providers

    forbidden = _find_provider(capabilities, DataSourceProviderType.FORBIDDEN_PRIVATE_TRADING)
    assert forbidden["tier"] == "tier_2_forbidden_v0"
    assert "live_trading" in forbidden["unsupported"]
    assert "private_trading_keys" in forbidden["unsupported"]
    assert forbidden["forbidden_reason"]


def test_yahoo_capabilities_contract_labels_ohlcv_only_limitations():
    client = TestClient(app)

    response = client.get("/api/v1/data-sources/capabilities")

    assert response.status_code == 200
    yahoo = _find_provider(response.json()["capabilities"], DataSourceProviderType.YAHOO_FINANCE)

    assert yahoo["supports"] == ["ohlcv_proxy"]
    for unsupported in [
        "crypto_open_interest",
        "open_interest",
        "funding",
        "gold_options_oi",
        "futures_oi",
        "iv",
        "implied_volatility",
        "xauusd_spot_execution",
    ]:
        assert unsupported in yahoo["unsupported"]
    assert any("ohlcv/proxy-only" in note.lower() for note in yahoo["limitations"])
    assert any("not a source" in note.lower() for note in yahoo["limitations"])


def test_forbidden_private_trading_readiness_remains_forbidden():
    client = TestClient(app)

    response = client.get("/api/v1/data-sources/readiness")

    assert response.status_code == 200
    forbidden = _find_provider(
        response.json()["provider_statuses"],
        DataSourceProviderType.FORBIDDEN_PRIVATE_TRADING,
    )
    assert forbidden["status"] == "forbidden"
    assert forbidden["configured"] is False
    assert forbidden["capabilities"]["forbidden_reason"]
    assert "execution credentials" in forbidden["capabilities"]["forbidden_reason"]


def test_preflight_contract_returns_blocked_missing_data_actions(isolated_data_paths):
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/preflight",
        json={
            "crypto_assets": ["BTCUSDT"],
            "proxy_assets": ["GC=F"],
            "processed_feature_root": str(isolated_data_paths / "processed"),
            "xau_options_oi_file_path": str(
                isolated_data_paths / "raw" / "xau" / "missing.csv"
            ),
            "requested_capabilities": [
                "ohlcv",
                "open_interest",
                "funding",
                "gold_options_oi",
                "futures_oi",
                "iv",
                "xauusd_spot_execution",
            ],
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["crypto_results"][0]["status"] == "blocked"
    assert payload["proxy_results"][0]["status"] == "blocked"
    assert payload["xau_result"]["status"] == "blocked"
    assert payload["proxy_results"][0]["unsupported_capabilities"] == [
        "open_interest",
        "funding",
        "gold_options_oi",
        "futures_oi",
        "iv",
        "xauusd_spot_execution",
    ]
    assert any(
        action["provider_type"] == "binance_public"
        for action in payload["missing_data_actions"]
    )
    assert any(
        action["provider_type"] == "local_file"
        for action in payload["missing_data_actions"]
    )


def test_preflight_contract_rejects_missing_research_acknowledgement():
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/preflight",
        json={"research_only_acknowledged": False},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def _clear_optional_vendor_environment(monkeypatch) -> None:
    for env_var_name in OPTIONAL_PROVIDER_ENV_VARS.values():
        monkeypatch.delenv(env_var_name, raising=False)


def _find_provider(rows: list[dict], provider_type: DataSourceProviderType) -> dict:
    for row in rows:
        if row["provider_type"] == provider_type.value:
            return row
    raise AssertionError(f"provider not found: {provider_type.value}")
