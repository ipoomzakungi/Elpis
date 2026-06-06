from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.xau_indicator_chart_watchlist import (
    ALLOWED_ACTIONS,
    build_indicator_levels_latest,
    build_indicator_watchlist_latest,
    report_text_is_safe,
    run_xau_indicator_chart_watchlist_output,
    xau_indicator_chart_watchlist_report_lines,
)


def test_latest_outputs_are_written_and_chart_exists(tmp_path: Path) -> None:
    result = run_xau_indicator_chart_watchlist_output(output_dir=_write_inputs(tmp_path))

    assert result.paths["levels_csv"].exists()
    assert result.paths["levels_md"].exists()
    assert result.paths["watchlist_csv"].exists()
    assert result.paths["watchlist_md"].exists()
    assert result.chart_path.exists()
    assert result.watchlist_latest.row(0, named=True)["final_action"] in ALLOWED_ACTIONS


def test_sd_and_grid_levels_stay_separated(tmp_path: Path) -> None:
    result = run_xau_indicator_chart_watchlist_output(output_dir=_write_inputs(tmp_path))
    rows = result.levels_latest.to_dicts()
    concepts = {str(row["concept"]) for row in rows}
    sd_sources = {str(row["source"]) for row in rows if row["concept"] == "SD_LEVEL"}

    assert "SD_LEVEL" in concepts
    assert "GRID_25" in concepts
    assert "HALF_GRID_12_50" in concepts
    assert {"+1SD", "-1SD", "+2SD", "-2SD", "+3SD", "-3SD", "+3.5SD", "-3.5SD"} <= {
        str(row["level_name"]) for row in rows
    }
    assert sd_sources == {"REALIZED_VOL_PROXY"}


def test_grid_levels_are_target_reference_only(tmp_path: Path) -> None:
    result = run_xau_indicator_chart_watchlist_output(output_dir=_write_inputs(tmp_path))
    grid_rows = result.levels_latest.filter(pl.col("layer") == "GRID").to_dicts()

    assert grid_rows
    assert {row["manual_action"] for row in grid_rows} == {"TARGET_REFERENCE"}
    assert all("reference" in str(row["valid_use"]).lower() for row in grid_rows)


def test_cme_wall_rows_are_context_not_candidate(tmp_path: Path) -> None:
    result = run_xau_indicator_chart_watchlist_output(output_dir=_write_inputs(tmp_path))
    cme_rows = result.levels_latest.filter(pl.col("layer") == "CME_WALL").to_dicts()

    assert {row["level_name"] for row in cme_rows} >= {
        "NEAREST_CALL_WALL",
        "NEAREST_PUT_WALL",
        "MAX_OI_PIN",
        "LOW_OI_GAP",
    }
    assert all(row["manual_action"] in {"WATCH_ONLY", "INSUFFICIENT_DATA"} for row in cme_rows)
    assert all(row["manual_action"] != "ALLOW_RESEARCH_CANDIDATE" for row in cme_rows)
    assert any("PILOT_ONLY" in str(row["confidence"]) for row in cme_rows)


def test_raw_sd_touches_are_watch_only_and_confirmed_2sd_can_be_candidate() -> None:
    raw_2sd = _watchlist_for_confirmation("TOUCHING_2SD_NO_CONFIRMATION")
    raw_3sd = _watchlist_for_confirmation("TOUCHING_3SD_NO_CONFIRMATION")
    confirmed_2sd = _watchlist_for_confirmation("REJECTION_BACK_INSIDE_2SD")

    assert raw_2sd.row(0, named=True)["final_action"] == "WATCH_ONLY"
    assert raw_3sd.row(0, named=True)["final_action"] == "WATCH_ONLY"
    assert confirmed_2sd.row(0, named=True)["final_action"] == "ALLOW_RESEARCH_CANDIDATE"


def test_report_and_chart_text_are_safe(tmp_path: Path) -> None:
    result = run_xau_indicator_chart_watchlist_output(output_dir=_write_inputs(tmp_path))
    report = "\n".join(xau_indicator_chart_watchlist_report_lines(result))
    chart = result.chart_path.read_text(encoding="utf-8")
    watchlist = result.paths["watchlist_md"].read_text(encoding="utf-8")

    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)
    assert direct_order_pattern.search(report) is None
    assert direct_order_pattern.search(chart) is None
    assert direct_order_pattern.search(watchlist) is None
    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)
    assert report_text_is_safe(chart)
    assert report_text_is_safe(watchlist)


def _watchlist_for_confirmation(confirmation: str) -> pl.DataFrame:
    context = {
        "timestamp": "2026-05-26T00:45:00+00:00",
        "latest_price": 121.0,
        "timeframe": "15m",
        "latest_bar": {
            "open": 120.0,
            "high": 122.0,
            "low": 119.0,
            "close": 121.0,
        },
        "session_open": 100.0,
        "one_sd": 10.0,
        "sd_source": "REALIZED_VOL_PROXY",
        "sigma_close": 2.1,
        "sd_state": "TOUCHING_2SD" if "2SD" in confirmation else "TOUCHING_3SD",
        "confirmation_state": confirmation,
    }
    levels = build_indicator_levels_latest(inputs={}, context=context)
    return build_indicator_watchlist_latest(levels=levels, context=context)


def _write_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    (output / "charts").mkdir(parents=True, exist_ok=True)
    (output / "xau_indicator_blueprint_v1.yaml").write_text(
        "version: xau_indicator_blueprint_v1\n"
        "research_only: true\n"
        "source: REALIZED_VOL_PROXY\n",
        encoding="utf-8",
    )
    _action_mapping().write_csv(output / "xau_indicator_action_mapping.csv")
    _latest_state().write_csv(output / "xau_indicator_latest_state.csv")
    _concept_map().write_csv(output / "xau_sd_grid_cme_concept_map.csv")
    _price_frame("15m").write_parquet(output / "dukascopy_xau_15m.parquet")
    _price_frame("1h").write_parquet(output / "dukascopy_xau_1h.parquet")
    _price_frame("4h").write_parquet(output / "dukascopy_xau_4h.parquet")
    _cme_wall_map().write_csv(output / "cme_wall_map_by_date.csv")
    return output


def _action_mapping() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"indicator_state": "touch_2sd_only", "manual_action": "WATCH_ONLY"},
            {
                "indicator_state": "touch_2sd_reject_back_inside",
                "manual_action": "ALLOW_RESEARCH_CANDIDATE",
            },
            {"indicator_state": "grid_25_nearby", "manual_action": "TARGET_REFERENCE"},
            {"indicator_state": "cme_wall_nearby", "manual_action": "WATCH_ONLY"},
        ],
        infer_schema_length=None,
    )


def _latest_state() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "as_of_timestamp": "2026-05-26T00:45:00+00:00",
                "latest_price": 121.0,
                "latest_timeframe": "15m",
                "sd_state": "TOUCHING_2SD",
                "grid_state": "REFERENCE_ONLY",
                "cme_wall_state": "PILOT_ONLY",
                "confirmation_state": "TOUCHING_2SD_NO_CONFIRMATION",
                "data_quality_state": "TRUE_IV_MISSING",
                "final_action": "WATCH_ONLY",
                "plain_english_summary": "Synthetic latest state.",
            }
        ],
        infer_schema_length=None,
    )


def _concept_map() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "concept": "CME_OI_WALL",
                "current_confidence": "PILOT_ONLY_11_CME_ROWS",
            }
        ],
        infer_schema_length=None,
    )


def _cme_wall_map() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-26",
                "wall_type": "CALL_WALL",
                "call_oi": 1000.0,
                "put_oi": 0.0,
                "total_oi": 1000.0,
                "spot_equivalent_level": 125.0,
            },
            {
                "trade_date": "2026-05-26",
                "wall_type": "PUT_WALL",
                "call_oi": 0.0,
                "put_oi": 900.0,
                "total_oi": 900.0,
                "spot_equivalent_level": 87.5,
            },
            {
                "trade_date": "2026-05-26",
                "wall_type": "MAX_OI_PIN",
                "call_oi": 500.0,
                "put_oi": 1800.0,
                "total_oi": 2300.0,
                "spot_equivalent_level": 112.5,
            },
            {
                "trade_date": "2026-05-26",
                "wall_type": "LOW_OI_GAP",
                "call_oi": 1.0,
                "put_oi": 1.0,
                "total_oi": 2.0,
                "spot_equivalent_level": 137.5,
            },
        ],
        infer_schema_length=None,
    )


def _price_frame(timeframe: str) -> pl.DataFrame:
    minutes = {"15m": 15, "1h": 60, "4h": 240}[timeframe]
    start = datetime(2026, 5, 26, tzinfo=UTC)
    rows = []
    for index, close in enumerate([100.0, 105.0, 111.0, 121.0]):
        timestamp = start + timedelta(minutes=minutes * index)
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": "2026-05-26",
                "timeframe": timeframe,
                "open": close - 1.0,
                "high": close + 2.0,
                "low": close - 2.0,
                "close": close,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)
