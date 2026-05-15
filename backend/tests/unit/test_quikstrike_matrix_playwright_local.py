import pytest

from src.models.quikstrike_matrix import QuikStrikeMatrixViewType
from src.quikstrike_matrix.extraction import build_extraction_from_request
from src.quikstrike_matrix.playwright_local import (
    MATRIX_VIEW_LINK_SELECTORS,
    OPEN_INTEREST_NAV_SELECTOR,
    _click_view,
    _prepare_gold_matrix_from_quikstrike_page,
    build_prompted_request_from_page,
    build_request_from_browser_payloads,
    collect_sanitized_page_payload,
    select_matrix_table_payload,
)


def test_browser_payload_builder_creates_matrix_request_from_sanitized_tables():
    request = build_request_from_browser_payloads(
        {
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: _payload("OI Matrix", "120"),
            QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: _payload("OI Change Matrix", "-12"),
            QuikStrikeMatrixViewType.VOLUME_MATRIX: _payload("Volume Matrix", "33"),
        }
    )

    extraction = build_extraction_from_request(request)

    assert request.requested_views == [
        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
        QuikStrikeMatrixViewType.VOLUME_MATRIX,
    ]
    assert extraction.result.row_count == 12
    assert extraction.result.strike_count == 1
    assert extraction.result.expiration_count == 2
    assert extraction.result.conversion_eligible is True


def test_select_matrix_table_prefers_table_with_strike_rows_and_expirations():
    selected = select_matrix_table_payload(
        [
            {"html_table": "<table><tr><td>not matrix</td></tr></table>", "text": "layout"},
            _payload("OI Matrix", "120")["tables"][0],
        ],
        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
    )

    assert "G2RK6" in selected["html_table"]


def test_collect_sanitized_page_payload_rejects_secret_material_from_fake_page():
    page = _FakePage({"cookies": "blocked"})

    with pytest.raises(ValueError, match="secret/session fields"):
        collect_sanitized_page_payload(page)


def test_prompted_request_collects_after_each_user_controlled_view_prompt():
    prompts: list[str] = []
    page = _CyclingFakePage(
        [
            _payload("OI Matrix", "120"),
            _payload("OI Change Matrix", "-12"),
            _payload("Volume Matrix", "33"),
        ]
    )

    request = build_prompted_request_from_page(
        page,
        [
            QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
            QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
            QuikStrikeMatrixViewType.VOLUME_MATRIX,
        ],
        view_prompt=lambda view: prompts.append(view.value),
    )

    assert prompts == ["open_interest_matrix", "oi_change_matrix", "volume_matrix"]
    assert page.evaluate_count == 3
    assert set(request.tables_by_view) == {
        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
        QuikStrikeMatrixViewType.OI_CHANGE_MATRIX,
        QuikStrikeMatrixViewType.VOLUME_MATRIX,
    }


def test_click_view_uses_stable_matrix_selectors():
    page = _AutoMatrixFakePage()

    _click_view(page, QuikStrikeMatrixViewType.OI_CHANGE_MATRIX)

    assert page.clicked_selectors == [
        MATRIX_VIEW_LINK_SELECTORS[QuikStrikeMatrixViewType.OI_CHANGE_MATRIX]
    ]
    assert page.active_view == QuikStrikeMatrixViewType.OI_CHANGE_MATRIX


def test_prepare_gold_matrix_clicks_open_interest_nav_and_oi_matrix():
    page = _AutoMatrixFakePage(body_text="Gold (OG|GC) QUIKOPTIONS VOL2VOL")
    browser = _FakeBrowser([page])

    _prepare_gold_matrix_from_quikstrike_page(browser)

    assert OPEN_INTEREST_NAV_SELECTOR in page.clicked_selectors
    assert MATRIX_VIEW_LINK_SELECTORS[QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX] in (
        page.clicked_selectors
    )
    assert page.active_view == QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX


def _payload(label: str, first_value: str) -> dict:
    return {
        "visible_text": f"Gold (OG|GC) OPEN INTEREST Matrix {label}",
        "tables": [
            {
                "caption": label,
                "text": f"{label} Strike G2RK6 G2RM6 Call Put",
                "html_table": (
                    "<table><thead><tr><th rowspan='2'>Strike</th>"
                    "<th colspan='2'>G2RK6 GC 2 DTE 4722.6</th>"
                    "<th colspan='2'>G2RM6 GC 30 DTE 4740.5</th></tr>"
                    "<tr><th>Call</th><th>Put</th><th>Call</th><th>Put</th></tr>"
                    f"</thead><tbody><tr><th>4700</th><td>{first_value}</td>"
                    "<td>95</td><td>10</td><td>11</td></tr></tbody></table>"
                ),
            }
        ],
    }


class _FakePage:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def evaluate(self, _script: str) -> dict:
        return self.payload


class _CyclingFakePage:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.evaluate_count = 0

    def evaluate(self, _script: str) -> dict:
        payload = self.payloads[self.evaluate_count]
        self.evaluate_count += 1
        return payload


class _FakeBrowser:
    def __init__(self, pages: list["_AutoMatrixFakePage"]) -> None:
        self.contexts = [_FakeContext(pages)]


class _FakeContext:
    def __init__(self, pages: list["_AutoMatrixFakePage"]) -> None:
        self.pages = pages


class _AutoMatrixFakePage:
    def __init__(
        self,
        *,
        body_text: str = "Gold (OG|GC) Open Interest Chart Matrix",
    ) -> None:
        self.active_view = QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX
        self.body_text = body_text
        self.clicked_selectors: list[str] = []
        self.matrix_ready = False
        self.mouse = _FakeMouse(self)

    def title(self) -> str:
        return "QuikStrike"

    def locator(self, _selector: str) -> object:
        raise RuntimeError("force evaluate fallback")

    def get_by_text(self, _label: str, exact: bool = True) -> object:
        raise RuntimeError("selector path should be used")

    def wait_for_timeout(self, _timeout_ms: int) -> None:
        return None

    def evaluate(self, _script: str, arg: object | None = None) -> object:
        if isinstance(arg, list):
            return any(str(item).lower() in self.body_text.lower() for item in arg)
        if isinstance(arg, str) and arg.startswith("#"):
            self.clicked_selectors.append(arg)
            if arg == OPEN_INTEREST_NAV_SELECTOR:
                self.body_text = "Gold (OG|GC) Open Interest Chart Matrix"
                self.matrix_ready = False
                return True
            for view, selector in MATRIX_VIEW_LINK_SELECTORS.items():
                if arg == selector:
                    self.active_view = view
                    self.matrix_ready = True
                    return True
            return False
        if not self.matrix_ready:
            return {"visible_text": self.body_text, "tables": []}
        return _payload(MATRIX_VIEW_LABEL_FOR_TEST[self.active_view], "120")


class _FakeMouse:
    def __init__(self, page: _AutoMatrixFakePage) -> None:
        self.page = page

    def click(self, _x: float, _y: float) -> None:
        return None


MATRIX_VIEW_LABEL_FOR_TEST = {
    QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: "OI Matrix",
    QuikStrikeMatrixViewType.OI_CHANGE_MATRIX: "OI Change Matrix",
    QuikStrikeMatrixViewType.VOLUME_MATRIX: "Volume Matrix",
}
