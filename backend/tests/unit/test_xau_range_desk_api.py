from fastapi.testclient import TestClient

from src.main import app


def test_range_desk_plan_endpoint_maps_levels_and_disables_signals() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/research/xau/range-desk/plan",
        json={
            "future_reference_price": 4500.0,
            "traded_reference_price": 4470.0,
            "levels": [
                {"label": "lower_1sd", "futures_level": 4490.0},
                {"label": "upper_1sd", "futures_level": 4510.0},
                {"label": "lower_2sd", "futures_level": 4470.0},
                {"label": "upper_2sd", "futures_level": 4530.0},
                {"label": "lower_3sd", "futures_level": 4450.0},
                {"label": "upper_3sd", "futures_level": 4550.0},
            ],
            "oi_walls": [{"wall_id": "wall_4520", "futures_level": 4520.0}],
            "research_only_acknowledged": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["basis_snapshot"]["diff_points"] == 30.0
    assert payload["mapped_oi_walls"][0]["mapped_traded_level"] == 4490.0
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True
