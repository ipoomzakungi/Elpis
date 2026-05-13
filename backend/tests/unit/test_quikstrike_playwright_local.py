from scripts.quikstrike_playwright_extract import _load_env_file
from src.models.quikstrike import QuikStrikeViewType
from src.quikstrike.playwright_local import (
    QuikStrikeCdpConnectionError,
    build_request_from_browser_payloads,
    select_chart_payload,
)


def test_build_request_from_browser_payloads_creates_strict_fixture_request():
    request = build_request_from_browser_payloads(
        {
            QuikStrikeViewType.INTRADAY_VOLUME: _payload("Intraday Volume"),
            QuikStrikeViewType.OPEN_INTEREST: _payload("Open Interest"),
        }
    )

    assert request.requested_views == [
        QuikStrikeViewType.INTRADAY_VOLUME,
        QuikStrikeViewType.OPEN_INTEREST,
    ]
    assert request.dom_metadata_by_view[QuikStrikeViewType.INTRADAY_VOLUME].product == "Gold"
    assert (
        request.highcharts_by_view[QuikStrikeViewType.OPEN_INTEREST].series[0].points[0].x
        == 4700
    )


def test_select_chart_payload_prefers_put_call_chart_with_matching_title():
    selected = select_chart_payload(
        [
            {"chart_title": "Context", "series": [{"name": "Vol Settle", "data": []}]},
            _chart("G2RK6 Open Interest"),
        ],
        QuikStrikeViewType.OPEN_INTEREST,
    )

    assert selected["chart_title"] == "G2RK6 Open Interest"


def test_browser_payload_rejects_secret_like_fields():
    payload = _payload("Intraday Volume")
    payload["headers"] = {"Authorization": "not allowed"}

    try:
        build_request_from_browser_payloads({QuikStrikeViewType.INTRADAY_VOLUME: payload})
    except ValueError as exc:
        assert "secret/session fields" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("secret-like browser payload was accepted")


def test_cdp_connection_error_has_manual_browser_guidance():
    error = QuikStrikeCdpConnectionError("Start Chrome manually with debugging port.")

    assert "Chrome" in str(error)
    assert "debugging port" in str(error)


def test_env_file_loader_accepts_non_secret_local_settings(tmp_path):
    env_file = tmp_path / ".env.quikstrike.local"
    env_file.write_text(
        "\n".join(
            [
                "QUIKSTRIKE_MODE=launch",
                "QUIKSTRIKE_WAIT_SECONDS=30",
                "QUIKSTRIKE_DRIVE_VIEWS=true",
            ]
        ),
        encoding="utf-8",
    )

    loaded = _load_env_file(env_file)

    assert loaded["QUIKSTRIKE_MODE"] == "launch"
    assert loaded["QUIKSTRIKE_WAIT_SECONDS"] == "30"


def test_env_file_loader_rejects_credentials(tmp_path):
    env_file = tmp_path / ".env.quikstrike.local"
    env_file.write_text("QUIKSTRIKE_PASSWORD=not-allowed\n", encoding="utf-8")

    try:
        _load_env_file(env_file)
    except ValueError as exc:
        assert "credential/session key" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("credential-bearing env file was accepted")


def _payload(view_label: str) -> dict:
    return {
        "header_text": f"Gold (OG|GC) G2RK6 (1.46 DTE) vs 4719.5 (+32.8) - {view_label}",
        "selector_text": "Gold (OG|GC) Expiration: G2RK6 14 May 2026",
        "charts": [_chart(f"G2RK6 {view_label}")],
    }


def _chart(title: str) -> dict:
    return {
        "chart_title": title,
        "series": [
            {
                "name": "Put",
                "data": [
                    {
                        "x": 4700,
                        "y": 117,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "strike-4700"},
                    }
                ],
            },
            {
                "name": "Call",
                "data": [
                    {
                        "x": 4700,
                        "y": 34,
                        "name": "4700",
                        "category": "4700",
                        "Tag": {"StrikeId": "strike-4700"},
                    }
                ],
            },
            {"name": "Vol Settle", "data": [{"x": 4700, "y": 26.75}]},
            {"name": "Ranges", "data": [{"x": 4650, "x2": 4750, "Tag": {"Range": "1SD"}}]},
        ],
    }
