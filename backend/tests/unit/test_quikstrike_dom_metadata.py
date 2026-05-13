from datetime import date

import pytest

from src.models.quikstrike import QuikStrikeViewType
from src.quikstrike.dom_metadata import infer_view_type, parse_dom_metadata


def test_parse_dom_metadata_extracts_gold_header_context():
    metadata = parse_dom_metadata(
        "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 (+35.9) - Open Interest",
        selector_text="Metals Precious Metals Gold (OG|GC) OG3K6 15 May 2026",
    )

    assert metadata.product == "Gold"
    assert metadata.option_product_code == "OG|GC"
    assert metadata.futures_symbol == "GC"
    assert metadata.expiration == date(2026, 5, 15)
    assert metadata.dte == 2.59
    assert metadata.future_reference_price == 4722.6
    assert metadata.selected_view_type == QuikStrikeViewType.OPEN_INTEREST
    assert metadata.source_view == "QUIKOPTIONS VOL2VOL"


def test_parse_dom_metadata_infers_supported_view_types():
    assert infer_view_type("Gold (OG|GC) - Intraday Volume") == (
        QuikStrikeViewType.INTRADAY_VOLUME
    )
    assert infer_view_type("Gold (OG|GC) - EOD Volume") == QuikStrikeViewType.EOD_VOLUME
    assert infer_view_type("Gold (OG|GC) - Open Interest") == (
        QuikStrikeViewType.OPEN_INTEREST
    )
    assert infer_view_type("Gold (OG|GC) - Open Interest Change") == (
        QuikStrikeViewType.OI_CHANGE
    )
    assert infer_view_type("Gold (OG|GC) - Churn (Change in OI/Volume)") == (
        QuikStrikeViewType.CHURN
    )


def test_parse_dom_metadata_accepts_explicit_view_type():
    metadata = parse_dom_metadata(
        "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6",
        selector_text="OG3K6 15 May 2026",
        selected_view_type=QuikStrikeViewType.CHURN,
    )

    assert metadata.selected_view_type == QuikStrikeViewType.CHURN


def test_parse_dom_metadata_records_warnings_for_missing_optional_context():
    metadata = parse_dom_metadata(
        "Gold (OG|GC) - EOD Volume",
        selected_view_type=QuikStrikeViewType.EOD_VOLUME,
    )

    assert metadata.expiration is None
    assert metadata.dte is None
    assert metadata.future_reference_price is None
    assert len(metadata.warnings) == 3


def test_parse_dom_metadata_rejects_non_gold_or_wrong_surface():
    with pytest.raises(ValueError, match="Gold"):
        parse_dom_metadata(
            "Corn (OZC|ZC) OZCM6 (9.62 DTE) vs 478.75 - Open Interest",
        )

    with pytest.raises(ValueError, match="QUIKOPTIONS VOL2VOL"):
        parse_dom_metadata(
            "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - Open Interest",
            surface="Open Interest",
        )


def test_parse_dom_metadata_rejects_secret_like_text():
    with pytest.raises(ValueError, match="secret/session fields"):
        parse_dom_metadata(
            "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - Open Interest Cookie: abc",
        )
