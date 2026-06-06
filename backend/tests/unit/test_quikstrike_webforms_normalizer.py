from src.models.quikstrike import QuikStrikeViewType
from src.models.quikstrike_matrix import QuikStrikeMatrixViewType
from src.quikstrike.playwright_local import build_request_from_browser_payloads
from src.quikstrike.webforms_normalizer import (
    build_matrix_payload_from_webforms_page,
    build_vol2vol_payload_from_webforms_page,
    extract_json_settings,
)
from src.quikstrike_matrix.playwright_local import (
    build_request_from_browser_payloads as build_matrix_request_from_browser_payloads,
)


def test_extract_json_settings_from_webforms_script() -> None:
    snippet = (
        'Sys.Application.add_init(function() { $create(UserControlsV2.QuikOptionsV2V.Chart, '
        '{"JSONSettings":"{\\"ValueName\\":\\"Open Interest\\",'
        '\\"Call\\":{\\"name\\":\\"Call\\",\\"data\\":[{\\"x\\":4500,\\"y\\":12,'
        '\\"Tag\\":{\\"StrikeId\\":\\"c1\\"}}]},'
        '\\"Put\\":{\\"name\\":\\"Put\\",\\"data\\":[{\\"x\\":4500,\\"y\\":8,'
        '\\"Tag\\":{\\"StrikeId\\":\\"p1\\"}}]}}"}); });'
    )

    payload = extract_json_settings(snippet)

    assert payload["ValueName"] == "Open Interest"
    assert payload["Call"]["data"][0]["x"] == 4500
    assert payload["Put"]["data"][0]["y"] == 8


def test_build_vol2vol_payload_from_webforms_page_matches_existing_contract() -> None:
    json_settings = (
        '{\\"ValueName\\":\\"Open Interest\\",'
        '\\"Call\\":{\\"name\\":\\"Call\\",\\"data\\":[{\\"x\\":4500,\\"y\\":12,'
        '\\"Tag\\":{\\"StrikeId\\":\\"c1\\"}}]},'
        '\\"Put\\":{\\"name\\":\\"Put\\",\\"data\\":[{\\"x\\":4500,\\"y\\":8,'
        '\\"Tag\\":{\\"StrikeId\\":\\"p1\\"}}]}}'
    )
    page = """
    <h3>Gold (OG|GC) <span>OG2M6</span> <span>(6.16 DTE)</span>
    vs <span>4365.3</span> <span> - </span> Open Interest</h3>
    <span><strong>Expiration:&nbsp;</strong>OG2M6</span>
    <script>
    Sys.Application.add_init(function() {
      $create(UserControlsV2.QuikOptionsV2V.Chart, {"JSONSettings":"__SETTINGS__"});
    });
    </script>
    """.replace("__SETTINGS__", json_settings)

    payload = build_vol2vol_payload_from_webforms_page(
        page,
        QuikStrikeViewType.OPEN_INTEREST,
    )
    request = build_request_from_browser_payloads({QuikStrikeViewType.OPEN_INTEREST: payload})

    assert request.requested_views == [QuikStrikeViewType.OPEN_INTEREST]
    chart = request.highcharts_by_view[QuikStrikeViewType.OPEN_INTEREST]
    assert {series.series_name for series in chart.series} == {"Call", "Put"}


def test_build_matrix_payload_from_webforms_page_sanitizes_table_contract() -> None:
    page = """
    <h3>Gold (OG|GC) Open Interest Matrix</h3>
    <table>
      <tr><th>Strike</th><th colspan="2">GCQ6 4365.3 OG2M6 6.16 DTE</th></tr>
      <tr><th></th><th>C</th><th>P</th></tr>
      <tr><td>4500</td><td>10</td><td>20</td></tr>
      <tr><td>4510</td><td></td><td>5</td></tr>
    </table>
    """

    payload = build_matrix_payload_from_webforms_page(
        page,
        QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX,
    )
    request = build_matrix_request_from_browser_payloads(
        {QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX: payload}
    )

    assert request.requested_views == [QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX]
    table = request.tables_by_view[QuikStrikeMatrixViewType.OPEN_INTEREST_MATRIX]
    assert "<script" not in table.html_table.lower()
    assert "4500" in table.html_table
