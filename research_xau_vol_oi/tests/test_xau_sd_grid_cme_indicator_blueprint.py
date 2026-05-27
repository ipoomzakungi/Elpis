from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.xau_sd_grid_cme_indicator_blueprint import (
    _safe_report_text,
    build_action_mapping,
    build_concept_map,
    build_latest_indicator_state,
    report_text_is_safe,
    run_xau_sd_grid_cme_indicator_blueprint,
    xau_sd_grid_cme_indicator_blueprint_report_lines,
)


def test_sd_is_not_equal_to_25_grid() -> None:
    concept = _rows(build_concept_map(inputs=_inputs()), "concept")

    assert concept["SD_LEVEL"]["what_it_is"] != concept["GRID_25"]["what_it_is"]
    assert "volatility" in concept["SD_LEVEL"]["what_it_is"].lower()
    assert "25" in concept["GRID_25"]["calculation_method"]


def test_grid_is_target_reference_only(tmp_path: Path) -> None:
    result = run_xau_sd_grid_cme_indicator_blueprint(output_dir=_write_inputs(tmp_path))
    actions = _rows(result.action_mapping, "indicator_state")

    assert actions["grid_25_nearby"]["manual_action"] == "TARGET_REFERENCE"
    assert actions["half_grid_12_50_nearby"]["manual_action"] == "TARGET_REFERENCE"


def test_blind_3sd_is_not_allow_candidate() -> None:
    actions = _rows(build_action_mapping(), "indicator_state")

    assert actions["touch_3sd_only"]["manual_action"] == "WATCH_ONLY"
    assert actions["touch_3sd_no_rejection"]["manual_action"] == "BLOCK"
    assert actions["touch_3sd_no_rejection"]["manual_action"] != "ALLOW_RESEARCH_CANDIDATE"


def test_rejection_confirmed_2sd_is_allow_research_candidate() -> None:
    actions = _rows(build_action_mapping(), "indicator_state")

    assert actions["touch_2sd_reject_back_inside"]["manual_action"] == "ALLOW_RESEARCH_CANDIDATE"


def test_cme_wall_is_not_automatic_entry() -> None:
    concept = _rows(build_concept_map(inputs=_inputs()), "concept")
    actions = _rows(build_action_mapping(), "indicator_state")

    assert "automatic" in concept["CME_OI_WALL"]["invalid_use"].lower()
    assert actions["cme_wall_nearby"]["manual_action"] == "WATCH_ONLY"


def test_stale_or_missing_data_blocks() -> None:
    actions = _rows(build_action_mapping(), "indicator_state")
    latest = build_latest_indicator_state(inputs={"price_15m": pl.DataFrame()}).row(0, named=True)

    assert actions["data_stale"]["manual_action"] == "INSUFFICIENT_DATA"
    assert latest["final_action"] == "INSUFFICIENT_DATA"


def test_latest_indicator_state_avoids_direct_order_terms(tmp_path: Path) -> None:
    result = run_xau_sd_grid_cme_indicator_blueprint(output_dir=_write_inputs(tmp_path))
    text = (tmp_path / "outputs" / "xau_indicator_latest_state.md").read_text(encoding="utf-8")

    assert result.latest_state.height == 1
    assert re.search(r"\bbuy\b|\bsell\b", text, flags=re.IGNORECASE) is None
    assert report_text_is_safe(text)


def test_report_does_not_claim_money_performance(tmp_path: Path) -> None:
    result = run_xau_sd_grid_cme_indicator_blueprint(output_dir=_write_inputs(tmp_path))
    report = "\n".join(xau_sd_grid_cme_indicator_blueprint_report_lines(result))

    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_reports_use_redacted_paths_only() -> None:
    redacted = _safe_report_text(r"C:\Users\example\private\input.csv")

    assert "C:\\Users" not in redacted
    assert "<REDACTED_PATH>" in redacted


def _write_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _sd_grid_decision().write_csv(output / "sd_grid_confirmation_decision_summary.csv")
    _component_guide().write_csv(output / "xau_trade_quality_component_guide_sd_grid_updated.csv")
    _manual_checklist().write_csv(output / "xau_manual_trade_review_checklist_sd_grid_updated.csv")
    _entry_models().write_csv(output / "gemini_sd_grid_entry_model_comparison.csv")
    _tp_sl_models().write_csv(output / "gemini_tp_sl_model_comparison.csv")
    _grid_tests().write_csv(output / "gemini_grid_clustering_test.csv")
    _cme_plan().write_csv(output / "gemini_cme_wall_test_plan.csv")
    _cme_wall_map().write_csv(output / "cme_wall_map_by_date.csv")
    _cme_magnet().write_csv(output / "cme_wall_magnet_target_test.csv")
    _cme_reaction().write_csv(output / "cme_wall_rejection_acceptance_test.csv")
    _cme_put_call().write_csv(output / "cme_put_call_wall_behavior.csv")
    _price_frame("15m").write_parquet(output / "dukascopy_xau_15m.parquet")
    _price_frame("1h").write_parquet(output / "dukascopy_xau_1h.parquet")
    _price_frame("4h").write_parquet(output / "dukascopy_xau_4h.parquet")
    return output


def _inputs() -> dict[str, pl.DataFrame]:
    return {
        "cme_wall_test_plan": _cme_plan(),
        "cme_wall_map": _cme_wall_map(),
        "price_15m": _price_frame("15m"),
    }


def _sd_grid_decision() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "decision_id": "REJECTION_CONFIRMED_2SD_CANDIDATE",
                "manual_action": "ALLOW_RESEARCH_CANDIDATE",
                "decision_label": "REJECTION_CONFIRMED_2SD_CANDIDATE",
                "evidence_summary": "events=2131; expectancy_proxy=1.0193; tail_risk_count=182",
                "interpretation": "2SD close-back-inside is the preferred research candidate.",
                "limitation": "Candidate status is not validated edge.",
                "final_recommendation": "CONFIRMATION_REQUIRED",
            }
        ],
        infer_schema_length=None,
    )


def _component_guide() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "component_name": "grid_25_component",
                "current_role": "TARGET_REFERENCE",
                "manual_action": "TARGET_REFERENCE",
                "current_confidence": "RANDOM_LIKE",
                "sd_grid_result": "reference only",
                "how_to_interpret": "Use as reference.",
                "when_to_ignore": "Standalone touch.",
                "required_data": "Dukascopy OHLC",
                "manual_review_question": "Reference only?",
            }
        ],
        infer_schema_length=None,
    )


def _manual_checklist() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "section": "E_SD_GRID_CONFIRMATION",
                "check_item": "Is grid used only as reference?",
                "manual_interpretation": "Use TARGET_REFERENCE.",
                "journal_action": "TARGET_REFERENCE",
            }
        ],
        infer_schema_length=None,
    )


def _entry_models() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "model_id": "REJECTION_CONFIRMED_2SD_FADE",
                "event_count": 2131,
                "entry_count": 2131,
                "expectancy_proxy": 1.0193,
                "tail_risk_count": 182,
            }
        ],
        infer_schema_length=None,
    )


def _tp_sl_models() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "model_id": "TP_FULL_BLOCK_25_SL_3_5SD",
                "target_model": "FIXED_25",
                "stop_model": "SD_3_5",
                "expectancy_proxy": 0.3220,
            }
        ],
        infer_schema_length=None,
    )


def _grid_tests() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "grid_test_id": "15m_$25_GRID_CLUSTERING",
                "timeframe": "15m",
                "grid_type": "$25_GRID_CLUSTERING",
                "interpretation": "GRID_CLUSTERING_RANDOM_LIKE",
            }
        ],
        infer_schema_length=None,
    )


def _cme_plan() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "rule_id": "WALL_AS_MAGNET",
                "required_cme_fields": "trade_date|strike|total_oi",
                "current_available_rows": 75079,
                "current_testable_rows": 11,
                "can_test_now": True,
                "current_result_if_available": "Pilot rows only.",
                "next_cme_data_needed": "Need more timestamp-safe CME OI dates.",
            }
        ],
        infer_schema_length=None,
    )


def _cme_wall_map() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-26",
                "expiry": "2026-06-01",
                "strike": 4550.0,
                "option_type": "call",
                "call_oi": 1000.0,
                "put_oi": 0.0,
                "total_oi": 1000.0,
                "wall_type": "CALL_WALL",
                "spot_equivalent_level": 4550.0,
                "confidence": "PILOT_ONLY",
            }
        ],
        infer_schema_length=None,
    )


def _cme_magnet() -> pl.DataFrame:
    return pl.DataFrame(
        [{"case_type": "NEAREST_WALL", "event_count": 11, "interpretation": "INSUFFICIENT_SAMPLE"}],
        infer_schema_length=None,
    )


def _cme_reaction() -> pl.DataFrame:
    return pl.DataFrame(
        [{"wall_touch_count": 52, "interpretation": "INSUFFICIENT_SAMPLE"}],
        infer_schema_length=None,
    )


def _cme_put_call() -> pl.DataFrame:
    return pl.DataFrame(
        [{"wall_type": "CALL_WALL", "event_count": 11, "interpretation": "INSUFFICIENT_SAMPLE"}],
        infer_schema_length=None,
    )


def _price_frame(timeframe: str) -> pl.DataFrame:
    minutes = {"15m": 15, "1h": 60, "4h": 240}[timeframe]
    start = datetime(2026, 5, 26, tzinfo=UTC)
    rows = []
    for index in range(5):
        timestamp = start + timedelta(minutes=minutes * index)
        close = 100.0 + index * 1.5
        rows.append(
            {
                "timestamp": timestamp,
                "trade_date": "2026-05-26",
                "timeframe": timeframe,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _rows(frame: pl.DataFrame, key: str) -> dict[str, dict[str, object]]:
    return {str(row[key]): row for row in frame.to_dicts()}
