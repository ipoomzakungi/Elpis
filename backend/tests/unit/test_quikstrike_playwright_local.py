from datetime import date

from scripts.quikstrike_playwright_extract import _load_env_file
from src.models.quikstrike import QuikStrikeViewType
from src.quikstrike.playwright_local import (
    QuikStrikeBrowserPageNotReadyError,
    QuikStrikeCdpConnectionError,
    _find_gold_vol2vol_page,
    _prepare_gold_vol2vol_from_mode,
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
    assert request.dom_metadata_by_view[QuikStrikeViewType.INTRADAY_VOLUME].expiration == date(
        2026, 5, 14
    )
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


def test_find_gold_vol2vol_page_requires_ready_vol2vol_chart():
    browser = _FakeBrowser(
        [
            _FakePage(
                {
                    "header_text": "Gold (OG|GC) Summary",
                    "selector_text": "Gold (OG|GC)",
                    "charts": [],
                }
            ),
            _FakePage(_payload("Intraday Volume")),
        ]
    )

    page = _find_gold_vol2vol_page(browser)

    assert page.payload["header_text"].endswith("Intraday Volume")


def test_find_gold_vol2vol_page_rejects_generic_gold_page():
    browser = _FakeBrowser(
        [
            _FakePage(
                {
                    "header_text": "Gold (OG|GC) Summary",
                    "selector_text": "Gold (OG|GC)",
                    "charts": [],
                }
            )
        ]
    )

    try:
        _find_gold_vol2vol_page(browser)
    except QuikStrikeBrowserPageNotReadyError as exc:
        assert "QUIKOPTIONS VOL2VOL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("generic Gold page was accepted as Vol2Vol-ready")


def test_prepare_gold_vol2vol_clicks_nav_from_gold_summary_without_mode_query():
    page = _GoldSummaryPage()
    browser = _FakeBrowser([page])

    _prepare_gold_vol2vol_from_mode(browser, "", debug_page_state=False)

    assert "#ctl00_ucMenuBar_lvMenuBar_ctrl7_lbMenuItem" in page.clicked_selectors
    assert page.ready is True


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


class _FakeBrowser:
    def __init__(self, pages: list["_FakePage"]) -> None:
        self.contexts = [_FakeContext(pages)]


class _FakeContext:
    def __init__(self, pages: list["_FakePage"]) -> None:
        self.pages = pages


class _FakePage:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def evaluate(self, _script: str, *_args: object) -> dict:
        return self.payload


class _GoldSummaryPage:
    def __init__(self) -> None:
        self.url = "https://cmegroup-sso.quikstrike.net//User/QuikStrikeView.aspx?pf=6&pid=40"
        self.body_text = "Gold (OG|GC) Summary QUIKOPTIONS VOL2VOL"
        self.clicked_selectors: list[str] = []
        self.ready = False

    def wait_for_timeout(self, _timeout_ms: int) -> None:
        return None

    def wait_for_load_state(self, _state: str) -> None:
        return None

    def evaluate(self, _script: str, *args: object) -> object:
        if args and isinstance(args[0], list):
            return any(str(item).lower() in self.body_text.lower() for item in args[0])
        if args and isinstance(args[0], str):
            selector = args[0]
            if selector == "#ctl00_ucMenuBar_lvMenuBar_ctrl7_lbMenuItem":
                self.clicked_selectors.append(selector)
                self.ready = True
                self.body_text = "Gold (OG|GC) Intraday Volume"
                return True
            return False
        if self.ready:
            return _payload("Intraday Volume")
        return {
            "header_text": "Gold (OG|GC) Summary",
            "selector_text": "Gold (OG|GC)",
            "charts": [],
        }
