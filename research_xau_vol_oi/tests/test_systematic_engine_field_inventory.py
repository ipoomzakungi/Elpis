import polars as pl

from research_xau_vol_oi.systematic_engine_field_inventory import (
    DEFAULT_CURRENT_OUTPUT_FIELDS,
    STATUS_AVAILABLE,
    STATUS_DERIVED,
    STATUS_MISSING,
    STATUS_PARTIAL,
    build_engine_inventory_summary,
    build_systematic_engine_field_inventory,
    engine_inventory_markdown,
)


def test_inventory_marks_report_level_iv_as_partial_not_available() -> None:
    inventory = build_systematic_engine_field_inventory()
    row = _row(inventory, "report_level_iv")

    assert row["status"] == STATUS_AVAILABLE
    assert "report_level_iv" in row["present_fields"]
    assert "vol_settle" in row["present_fields"]
    assert "implied_volatility" in row["present_fields"]
    assert row["missing_fields"] == ""


def test_inventory_marks_cme_numeric_sd_bands_as_partial_gap() -> None:
    inventory = build_systematic_engine_field_inventory()
    row = _row(inventory, "cme_numeric_sd_bands")

    assert row["status"] == STATUS_AVAILABLE
    assert "range_label" in row["present_fields"]
    assert "expected_range" in row["present_fields"]
    assert "cme_numeric_1sd" in row["present_fields"]
    assert row["missing_fields"] == ""
    assert row["blocks_daily_map"] is True
    assert row["blocks_backtest"] is True


def test_inventory_marks_official_release_timestamp_missing_and_backtest_blocking() -> None:
    inventory = build_systematic_engine_field_inventory()
    row = _row(inventory, "official_release_ts")

    assert row["status"] == STATUS_AVAILABLE
    assert row["present_fields"] == "official_release_ts"
    assert row["missing_fields"] == ""
    assert row["blocks_backtest"] is True


def test_inventory_marks_intraday_volume_available() -> None:
    inventory = build_systematic_engine_field_inventory()
    row = _row(inventory, "intraday_volume")

    assert row["status"] == STATUS_AVAILABLE
    assert "intraday_volume" in row["present_fields"]
    assert row["blocks_intraday_engine"] is True


def test_inventory_marks_gex_derivable_only_when_greeks_are_available() -> None:
    inventory = build_systematic_engine_field_inventory()
    row = _row(inventory, "gex_and_gamma_regime")

    assert row["status"] == STATUS_DERIVED
    assert "gross_gex" in row["missing_fields"]
    assert "net_gex_assumed" in row["missing_fields"]
    assert "gamma_regime" in row["missing_fields"]
    assert row["blocks_intraday_engine"] is True


def test_inventory_accepts_future_cme_parity_fields() -> None:
    fields = dict(DEFAULT_CURRENT_OUTPUT_FIELDS)
    fields["cme_expected_range_snapshot"] = (
        "reference_futures_price",
        "report_level_iv",
        "fractional_dte",
        "cme_numeric_1sd",
        "cme_numeric_2sd",
        "cme_numeric_3sd",
    )

    inventory = build_systematic_engine_field_inventory(fields)

    assert _row(inventory, "report_level_iv")["status"] == STATUS_AVAILABLE
    assert _row(inventory, "fractional_dte")["status"] == STATUS_AVAILABLE
    assert _row(inventory, "cme_numeric_sd_bands")["status"] == STATUS_AVAILABLE


def test_inventory_shows_old_gap_without_expected_range_snapshot() -> None:
    fields = {
        source: values
        for source, values in DEFAULT_CURRENT_OUTPUT_FIELDS.items()
        if source != "cme_expected_range_snapshot"
    }

    inventory = build_systematic_engine_field_inventory(fields)

    assert _row(inventory, "report_level_iv")["status"] == STATUS_PARTIAL
    assert _row(inventory, "cme_numeric_sd_bands")["status"] == STATUS_PARTIAL
    assert _row(inventory, "official_release_ts")["status"] == STATUS_MISSING


def test_inventory_summary_and_markdown_are_research_only() -> None:
    inventory = build_systematic_engine_field_inventory()
    summary = build_engine_inventory_summary(inventory)
    markdown = engine_inventory_markdown(inventory)

    assert isinstance(summary, pl.DataFrame)
    assert summary.get_column("field_count").sum() == inventory.height
    assert "Research-only field inventory" in markdown
    assert "profitability claim" in markdown


def _row(inventory: pl.DataFrame, engine_field: str) -> dict[str, object]:
    rows = inventory.filter(pl.col("engine_field") == engine_field).to_dicts()
    assert len(rows) == 1
    return rows[0]
