from fastapi.testclient import TestClient

from src.main import app
from tests.helpers.test_xau_data import write_sample_xau_options_csv


def test_optional_paid_provider_keys_are_non_blocking_and_presence_only(
    isolated_data_paths,
    monkeypatch,
):
    for env_var_name in [
        "KAIKO_API_KEY",
        "TARDIS_API_KEY",
        "COINGLASS_API_KEY",
        "CRYPTOQUANT_API_KEY",
        "CME_QUIKSTRIKE_API_KEY",
    ]:
        monkeypatch.delenv(env_var_name, raising=False)
    secret = "PAID_PROVIDER_SECRET_SHOULD_NOT_APPEAR"
    monkeypatch.setenv("KAIKO_API_KEY", secret)

    options_path = isolated_data_paths / "raw" / "xau" / "options.csv"
    options_path.parent.mkdir(parents=True, exist_ok=True)
    write_sample_xau_options_csv(options_path)
    client = TestClient(app)

    response = client.post(
        "/api/v1/data-sources/preflight",
        json={
            "crypto_assets": [],
            "proxy_assets": [],
            "xau_options_oi_file_path": str(options_path),
            "require_optional_vendors": [
                "kaiko_optional",
                "tardis_optional",
                "coinglass_optional",
                "cryptoquant_optional",
                "cme_quikstrike_local_or_optional",
            ],
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 200
    assert secret not in response.text
    payload = response.json()
    assert payload["status"] == "completed"
    statuses = {
        provider["provider_type"]: provider for provider in payload["optional_vendor_results"]
    }
    assert statuses["kaiko_optional"]["status"] == "configured"
    assert statuses["kaiko_optional"]["configured"] is True
    for provider_type in [
        "tardis_optional",
        "coinglass_optional",
        "cryptoquant_optional",
        "cme_quikstrike_local_or_optional",
    ]:
        assert statuses[provider_type]["status"] == "unavailable_optional"
        assert statuses[provider_type]["configured"] is False
    assert all(action["blocking"] is False for action in payload["missing_data_actions"])
