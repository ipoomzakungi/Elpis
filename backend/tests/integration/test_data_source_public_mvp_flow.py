from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.research_data import write_synthetic_research_features
from tests.helpers.test_xau_data import write_sample_xau_options_csv


def test_public_no_key_preflight_completes_with_ready_public_and_local_inputs(
    isolated_data_paths,
):
    processed_root = isolated_data_paths / "processed"
    raw_root = isolated_data_paths / "raw"
    write_synthetic_research_features(
        processed_root / "btcusdt_15m_features.parquet",
        symbol="BTCUSDT",
        rows=12,
    )
    write_synthetic_research_features(
        processed_root / "spy_1d_features.parquet",
        symbol="SPY",
        rows=10,
        include_regime=False,
        include_open_interest=False,
        include_funding=False,
    )
    options_path = raw_root / "xau" / "options.csv"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    write_sample_xau_options_csv(options_path)
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/preflight",
        json={
            "crypto_assets": ["BTCUSDT"],
            "proxy_assets": ["SPY"],
            "processed_feature_root": str(processed_root),
            "xau_options_oi_file_path": str(options_path),
            "requested_capabilities": ["ohlcv", "open_interest", "funding", "iv"],
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["crypto_results"][0]["status"] == "ready"
    assert payload["crypto_results"][0]["row_count"] == 12
    assert payload["proxy_results"][0]["status"] == "ready"
    assert payload["proxy_results"][0]["unsupported_capabilities"] == [
        "open_interest",
        "funding",
        "iv",
    ]
    assert payload["xau_result"]["status"] == "ready"
    assert payload["xau_result"]["row_count"] == 2
    assert all(action["blocking"] is False for action in payload["missing_data_actions"])
    assert any("research-only" in warning.lower() for warning in payload["warnings"])
