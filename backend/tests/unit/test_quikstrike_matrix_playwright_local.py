import pytest

from src.models.quikstrike_matrix import QuikStrikeMatrixViewType
from src.quikstrike_matrix.extraction import build_extraction_from_request
from src.quikstrike_matrix.playwright_local import (
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
