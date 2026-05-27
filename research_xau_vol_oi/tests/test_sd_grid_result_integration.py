from __future__ import annotations

import hashlib
import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.sd_grid_result_integration import (
    build_latest_watchlist_overlay,
    report_text_is_safe,
    run_sd_grid_result_integration,
    sd_grid_result_integration_report_lines,
)


def test_blind_3sd_is_not_allowed_research_candidate(tmp_path: Path) -> None:
    result = run_sd_grid_result_integration(output_dir=_write_inputs(tmp_path))
    rules = _rows(result.rulebook, "rule_id")

    assert rules["BLIND_3SD_TOUCH"]["manual_action"] == "BLOCK"
    assert rules["BLIND_3SD_TOUCH"]["manual_action"] != "ALLOW_RESEARCH_CANDIDATE"


def test_blind_2sd_is_watch_only(tmp_path: Path) -> None:
    result = run_sd_grid_result_integration(output_dir=_write_inputs(tmp_path))
    rules = _rows(result.rulebook, "rule_id")

    assert rules["BLIND_2SD_TOUCH"]["manual_action"] == "WATCH_ONLY"


def test_rejection_confirmed_2sd_is_research_candidate(tmp_path: Path) -> None:
    result = run_sd_grid_result_integration(output_dir=_write_inputs(tmp_path))
    rules = _rows(result.rulebook, "rule_id")
    components = _rows(result.updated_component_guide, "component_name")

    assert rules["REJECTION_CONFIRMED_2SD_FADE"]["manual_action"] == "ALLOW_RESEARCH_CANDIDATE"
    assert components["rejection_confirmed_2sd_component"]["manual_action"] == "ALLOW_RESEARCH_CANDIDATE"


def test_grid_is_target_reference_only(tmp_path: Path) -> None:
    result = run_sd_grid_result_integration(output_dir=_write_inputs(tmp_path))
    rules = _rows(result.rulebook, "rule_id")

    assert rules["GRID_25"]["manual_action"] == "TARGET_REFERENCE"
    assert rules["GRID_12_50"]["manual_action"] == "TARGET_REFERENCE"


def test_true_iv_missing_is_insufficient_data(tmp_path: Path) -> None:
    result = run_sd_grid_result_integration(output_dir=_write_inputs(tmp_path))
    rules = _rows(result.rulebook, "rule_id")

    assert rules["TRUE_IV_SD"]["manual_action"] == "INSUFFICIENT_DATA"
    assert "CME IV" in rules["TRUE_IV_SD"]["required_confirmation"]


def test_checklist_avoids_direct_order_terms(tmp_path: Path) -> None:
    output = _write_inputs(tmp_path)
    run_sd_grid_result_integration(output_dir=output)
    text = (output / "xau_manual_trade_review_checklist_sd_grid_updated.md").read_text(
        encoding="utf-8",
    )

    assert re.search(r"\bbuy\b|\bsell\b", text, flags=re.IGNORECASE) is None
    assert report_text_is_safe(text)


def test_report_does_not_claim_money_performance(tmp_path: Path) -> None:
    result = run_sd_grid_result_integration(output_dir=_write_inputs(tmp_path))
    report = "\n".join(sd_grid_result_integration_report_lines(result))

    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_score_v1_weights_are_unchanged(tmp_path: Path) -> None:
    output = _write_inputs(tmp_path)
    score_config = output / "xau_trade_quality_score_v1.yaml"
    before = _sha256(score_config)

    run_sd_grid_result_integration(output_dir=output)

    assert _sha256(score_config) == before


def test_reports_use_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_inputs(tmp_path, include_private_path=True)

    run_sd_grid_result_integration(output_dir=output)
    text = (output / "xau_trade_quality_component_guide_sd_grid_updated.md").read_text(
        encoding="utf-8",
    )

    assert "C:\\Users" not in text
    assert str(tmp_path) not in text
    assert "<REDACTED_PATH>" in text
    assert report_text_is_safe(text)


def test_latest_overlay_blocks_inside_1sd_and_marks_grid_reference() -> None:
    overlay = build_latest_watchlist_overlay(
        events=_events(),
        daily_watchlist=_daily_watchlist(),
        score_rows=pl.DataFrame(),
    )
    row = overlay.row(0, named=True)

    assert row["current_score"] == 47
    assert row["current_bucket"] == "WATCH_ONLY"
    assert row["manual_action"] == "BLOCK"
    assert row["grid_target_reference_nearby"]
    assert row["sd_proxy_source"] == "REALIZED_VOL_PROXY"


def _write_inputs(tmp_path: Path, *, include_private_path: bool = False) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _entry_models().write_csv(output / "gemini_sd_grid_entry_model_comparison.csv")
    _tp_sl_models().write_csv(output / "gemini_tp_sl_model_comparison.csv")
    _grid_tests().write_csv(output / "gemini_grid_clustering_test.csv")
    _rule_decision().write_csv(output / "gemini_sd_grid_rule_decision.csv")
    _events().write_csv(output / "gemini_sd_grid_events.csv")
    _component_guide(include_private_path=include_private_path).write_csv(
        output / "xau_trade_quality_component_guide.csv",
    )
    _manual_checklist().write_csv(output / "xau_manual_trade_review_checklist.csv")
    _daily_watchlist().write_csv(output / "xau_trade_quality_daily_watchlist.csv")
    _score_rows().write_csv(output / "xau_trade_quality_score.csv")
    (output / "xau_trade_quality_score_v1.yaml").write_text(
        "\n".join(
            [
                "version: xau_trade_quality_score_v1",
                "tuning_allowed: false",
                "threshold_optimization_allowed: false",
                "score_components:",
                "  - component_name: acceptance_breakout_component",
                "    fixed_score_weight: 30",
                "  - component_name: rejection_after_touch_component",
                "    fixed_score_weight: 6",
            ]
        ),
        encoding="utf-8",
    )
    return output


def _entry_models() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _entry_row("BLIND_2SD_FADE", 12290, -9.7792, 4016),
            _entry_row("BLIND_3SD_FADE", 3249, -9.1880, 2040),
            _entry_row("REJECTION_CONFIRMED_2SD_FADE", 2131, 1.0193, 182),
            _entry_row("REJECTION_CONFIRMED_3SD_FADE", 536, -3.4999, 131),
            _entry_row("ACCEPTANCE_CONTINUATION", 1622, 0.1779, 419),
            _entry_row("NO_TRADE_1SD_FILTER", 119684, 0.0, 0, entry_count=0),
        ],
        infer_schema_length=None,
    )


def _entry_row(
    model_id: str,
    event_count: int,
    expectancy_proxy: float,
    tail_risk_count: int,
    *,
    entry_count: int | None = None,
) -> dict[str, object]:
    return {
        "model_id": model_id,
        "event_count": event_count,
        "entry_count": event_count if entry_count is None else entry_count,
        "win_rate": 0.1,
        "target_hit_rate": 0.2,
        "stop_hit_rate": 0.3,
        "expectancy_proxy": expectancy_proxy,
        "average_mfe": 1.0,
        "average_mae": -1.0,
        "max_adverse_excursion": -10.0,
        "spread_cost_estimate": 0.5,
        "tail_risk_count": tail_risk_count,
        "sample_size_warning": False,
    }


def _tp_sl_models() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "model_id": "TP_FULL_BLOCK_25_SL_3_5SD",
                "target_model": "FIXED_25",
                "stop_model": "SD_3_5",
                "event_count": 2667,
                "target_hit_rate": 0.1631,
                "stop_hit_rate": 0.0832,
                "avg_win_proxy": 25.0,
                "avg_loss_proxy": -34.7567,
                "expectancy_proxy": 0.3220,
                "max_drawdown_proxy": -1017.1123,
                "tail_loss_warning": False,
            }
        ],
        infer_schema_length=None,
    )


def _grid_tests() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _grid_row("15m_$25_GRID_CLUSTERING", "$25_GRID_CLUSTERING"),
            _grid_row("15m_$12_50_HALF_BLOCK_CLUSTERING", "$12_50_HALF_BLOCK_CLUSTERING"),
        ],
        infer_schema_length=None,
    )


def _grid_row(grid_test_id: str, grid_type: str) -> dict[str, object]:
    return {
        "grid_test_id": grid_test_id,
        "timeframe": "15m",
        "grid_type": grid_type,
        "touch_count": 10,
        "high_low_cluster_rate": 0.11,
        "turning_point_cluster_rate": 0.10,
        "random_grid_baseline": 0.12,
        "uplift_vs_random": -0.01,
        "p_value_proxy": 0.75,
        "dynamic_band_cluster_rate": 0.96,
        "interpretation": "GRID_CLUSTERING_RANDOM_LIKE",
    }


def _rule_decision() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "rule_id": "OVERALL",
                "decision_label": "CONFIRMATION_REQUIRED",
                "evidence_summary": (
                    "Most promising=REJECTION_CONFIRMED_2SD_FADE; "
                    "dangerous=BLIND_3SD_FADE."
                ),
                "limitation": "Use as watchlist research.",
                "final_recommendation": "CONFIRMATION_REQUIRED",
            }
        ],
        infer_schema_length=None,
    )


def _events() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "event_id": "SDGRID_1",
                "timeframe": "4h",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "trade_date": "2026-05-26",
                "bar_index": 1,
                "event_type": "INSIDE_1SD",
                "level_type": "1SD",
                "side": "MIDDLE",
                "trigger_price": 4542.5,
                "open": 4559.9,
                "high": 4560.1,
                "low": 4527.7,
                "close": 4542.5,
                "session_open": 4559.9,
                "one_sd_value": 41.18,
                "sd_proxy_source": "REALIZED_VOL_PROXY",
                "sigma_high": 0.0,
                "sigma_low": -0.7,
                "sigma_close": -0.4,
                "grid_size": None,
                "grid_level": None,
                "close_back_inside": False,
                "hold_beyond_level": False,
                "continues_beyond_3_5sd": False,
            },
            {
                "event_id": "SDGRID_2",
                "timeframe": "4h",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "trade_date": "2026-05-26",
                "bar_index": 1,
                "event_type": "TOUCH_25_GRID",
                "level_type": "GRID",
                "side": "BELOW_GRID",
                "trigger_price": 4550.0,
                "open": 4559.9,
                "high": 4560.1,
                "low": 4527.7,
                "close": 4542.5,
                "session_open": 4559.9,
                "one_sd_value": 41.18,
                "sd_proxy_source": "REALIZED_VOL_PROXY",
                "sigma_high": 0.0,
                "sigma_low": -0.7,
                "sigma_close": -0.4,
                "grid_size": 25.0,
                "grid_level": 4550.0,
                "close_back_inside": False,
                "hold_beyond_level": False,
                "continues_beyond_3_5sd": False,
            },
        ],
        infer_schema_length=None,
    )


def _component_guide(*, include_private_path: bool = False) -> pl.DataFrame:
    required = r"C:\Users\example\private.csv" if include_private_path else "Dukascopy OHLC"
    return pl.DataFrame(
        [
            {
                "component_name": "acceptance_breakout_component",
                "current_role": "POSITIVE_CONFIRMATION",
                "how_to_interpret": "Close and hold behavior.",
                "when_to_ignore": "When blockers exist.",
                "required_data": required,
                "current_confidence": "TOO_EARLY",
                "manual_review_question": "Did price close and hold?",
            },
            {
                "component_name": "custom_context_component",
                "current_role": "CONTEXT_ONLY",
                "how_to_interpret": "Context-only base row.",
                "when_to_ignore": "When data is incomplete.",
                "required_data": required,
                "current_confidence": "TOO_EARLY",
                "manual_review_question": "Is base context timestamp-safe?",
            }
        ],
        infer_schema_length=None,
    )


def _manual_checklist() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "section": "A_DATA_QUALITY",
                "check_item": "Dukascopy coverage is fresh.",
                "manual_interpretation": "Use INSUFFICIENT_DATA when coverage is unclear.",
                "journal_action": "INSUFFICIENT_DATA",
            }
        ],
        infer_schema_length=None,
    )


def _daily_watchlist() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "session_date": "2026-05-26",
                "timeframe": "15m",
                "latest_price": 4542.5035,
                "latest_score": 47,
                "score_bucket": "WATCH_ONLY",
                "active_positive_components": "data_quality_component",
                "active_negative_components": "guru_filter_component",
                "blocked_reasons": "GURU_FILTER_CONTEXT",
                "watch_reasons": "CME_WALL_CONTEXT",
                "journal_action": "WATCH_ONLY",
            }
        ],
        infer_schema_length=None,
    )


def _score_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": "2026-05-26T00:00:00+00:00",
                "timeframe": "15m",
                "trade_quality_score": 47,
                "score_bucket": "WATCH_ONLY",
            }
        ],
        infer_schema_length=None,
    )


def _rows(frame: pl.DataFrame, key: str) -> dict[str, dict[str, object]]:
    return {str(row[key]): row for row in frame.to_dicts()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
