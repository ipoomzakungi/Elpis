from datetime import UTC, datetime

import pytest

from src.models.quikstrike import QuikStrikeExtractionRequest, QuikStrikeViewType
from src.quikstrike.dom_metadata import parse_dom_metadata
from src.quikstrike.highcharts_reader import parse_highcharts_chart
from src.quikstrike.range_bands import (
    build_range_bands_payload,
    range_bands_payload_has_data,
)


def test_range_bands_payload_builds_cumulative_sd_bands_from_chart_segments() -> None:
    view = QuikStrikeViewType.INTRADAY_VOLUME
    request = QuikStrikeExtractionRequest(
        requested_views=[view],
        dom_metadata_by_view={
            view: parse_dom_metadata(
                "Gold (OG|GC) OG1M6 (0.47 DTE) vs 4478.2 - Intraday Volume",
                selector_text="Gold (OG|GC) OG1M6 5 Jun 2026",
                selected_view_type=view,
            )
        },
        highcharts_by_view={
            view: parse_highcharts_chart(
                {
                    "title": {"text": "OG1M6 Intraday Volume"},
                    "series": [
                        {
                            "name": "Ranges",
                            "data": [
                                {"x": 4436.3, "x2": 4478.2, "Tag": {"Range": "1"}},
                                {"x": 4478.2, "x2": 4520.1, "Tag": {"Range": "1"}},
                                {"x": 4394.9, "x2": 4436.3, "Tag": {"Range": "2"}},
                                {"x": 4520.1, "x2": 4561.5, "Tag": {"Range": "2"}},
                                {"x": 4354.0, "x2": 4394.9, "Tag": {"Range": "3"}},
                                {"x": 4561.5, "x2": 4604.0, "Tag": {"Range": "3"}},
                            ],
                        }
                    ],
                },
                view,
            )
        },
        research_only_acknowledged=True,
    )

    payload = build_range_bands_payload(
        extraction_id="quikstrike_range_fixture",
        request=request,
        created_at=datetime(2026, 6, 5, tzinfo=UTC),
    )

    assert range_bands_payload_has_data(payload) is True
    bands = payload["views"][0]["cumulative_bands"]
    assert bands[0]["label"] == "1SD"
    assert bands[0]["lower_strike"] == 4436.3
    assert bands[0]["upper_strike"] == 4520.1
    assert bands[0]["cme_numeric_sd"] == pytest.approx(41.9)
    assert bands[1]["label"] == "2SD"
    assert bands[1]["cme_numeric_sd"] == pytest.approx(83.3)
    assert bands[2]["label"] == "3SD"
    assert bands[2]["upper_strike"] == 4604.0
