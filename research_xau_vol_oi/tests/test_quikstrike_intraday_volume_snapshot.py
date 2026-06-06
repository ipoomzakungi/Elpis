from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.quikstrike_intraday_volume_snapshot import (
    _safe_report_text,
    build_example_4550_scenarios,
    build_intraday_volume_snapshot,
    build_manual_snapshot_template,
    build_wall_scenarios,
    quikstrike_intraday_volume_report_lines,
    report_text_is_safe,
    run_quikstrike_intraday_volume_snapshot,
)


def test_manual_template_created(tmp_path: Path) -> None:
    result = run_quikstrike_intraday_volume_snapshot(output_dir=_write_inputs(tmp_path))
    template = result.paths["manual_template_csv"]
    guide = result.paths["manual_guide_md"]

    assert template.exists()
    assert guide.exists()
    assert set(build_manual_snapshot_template().columns) >= {
        "snapshot_timestamp",
        "product",
        "expiration",
        "future_price",
        "strike",
        "put_volume",
        "call_volume",
    }


def test_call_and_put_volume_walls_detected() -> None:
    snapshot = build_intraday_volume_snapshot(_manual_rows())
    rows = _rows(snapshot, "strike")

    assert rows["4550.0"]["wall_type"] == "CALL_VOLUME_WALL"
    assert rows["4500.0"]["wall_type"] == "PUT_VOLUME_WALL"
    assert rows["4550.0"]["is_active_wall"] is True
    assert rows["4500.0"]["is_active_wall"] is True


def test_within_100_dollar_window_flag_works() -> None:
    snapshot = build_intraday_volume_snapshot(_manual_rows(include_far=True))
    rows = _rows(snapshot, "strike")

    assert rows["4550.0"]["within_100_dollar_window"] is True
    assert rows["4700.0"]["within_100_dollar_window"] is False
    assert rows["4700.0"]["is_active_wall"] is False


def test_4550_example_produces_watch_decision_wall(tmp_path: Path) -> None:
    result = run_quikstrike_intraday_volume_snapshot(output_dir=_write_inputs(tmp_path))
    latest = result.latest_state.row(0, named=True)
    example_recommendations = {
        row["final_recommendation"] for row in result.example_scenarios.to_dicts()
    }

    assert result.final_recommendation == "WATCH_4550_DECISION_WALL"
    assert latest["quikstrike_context_state"] == "WATCH_4550_DECISION_WALL"
    assert example_recommendations == {"WATCH_4550_DECISION_WALL"}


def test_call_wall_is_not_automatic_directional_action() -> None:
    snapshot = build_intraday_volume_snapshot(_manual_rows())
    scenarios = build_wall_scenarios(snapshot)
    wall_4550 = scenarios.filter(pl.col("wall_level") == 4550.0).to_dicts()

    assert wall_4550
    assert all(row["action_label"] != "ALLOW_RESEARCH_CANDIDATE" for row in wall_4550)
    assert any(row["action_label"] == "TARGET_REFERENCE" for row in wall_4550)


def test_acceptance_and_rejection_require_confirmation() -> None:
    snapshot = build_intraday_volume_snapshot(_manual_rows())
    scenarios = build_wall_scenarios(snapshot)
    reaction_rows = scenarios.filter(
        pl.col("scenario").is_in(["WALL_REJECTION_WATCH", "WALL_ACCEPTANCE_WATCH"])
    ).to_dicts()

    assert reaction_rows
    assert all("close" in row["required_confirmation"].lower() for row in reaction_rows)
    assert all(row["action_label"] == "WATCH_ONLY" for row in reaction_rows)


def test_report_outputs_avoid_direct_order_terms_and_money_claims(tmp_path: Path) -> None:
    result = run_quikstrike_intraday_volume_snapshot(output_dir=_write_inputs(tmp_path))
    report = "\n".join(quikstrike_intraday_volume_report_lines(result))
    snapshot = result.paths["snapshot_md"].read_text(encoding="utf-8")
    scenario = result.paths["example_md"].read_text(encoding="utf-8")
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(report) is None
    assert direct_order_pattern.search(snapshot) is None
    assert direct_order_pattern.search(scenario) is None
    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)
    assert report_text_is_safe(snapshot)
    assert report_text_is_safe(scenario)


def test_redacted_paths_only() -> None:
    redacted = _safe_report_text(r"C:\Users\example\private\quikstrike.csv")

    assert "C:\\Users" not in redacted
    assert "<REDACTED_PATH>" in redacted


def test_example_scenario_maps_requested_references() -> None:
    example = build_example_4550_scenarios()
    rows = _rows(example, "scenario_id")

    assert rows["A_ACCEPTS_ABOVE_4550"]["target_reference"] == 4600.0
    assert rows["B_REJECTS_4550"]["target_reference"] == 4525.0
    assert rows["D_BREAKS_BELOW_4525"]["target_reference"] == 4500.0
    assert rows["C_STAYS_4525_4550"]["action_label"] == "BLOCK"


def _write_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _manual_rows().write_csv(output / "quikstrike_intraday_volume_manual.csv")
    _latest_indicator_state().write_csv(output / "xau_indicator_latest_state.csv")
    return output


def _manual_rows(*, include_far: bool = False) -> pl.DataFrame:
    rows = [
        _row(4500.0, put_volume=78.0, call_volume=5.0),
        _row(4525.0, put_volume=51.0, call_volume=35.0),
        _row(4550.0, put_volume=20.0, call_volume=155.0),
        _row(4575.0, put_volume=0.0, call_volume=0.0),
        _row(4600.0, put_volume=0.0, call_volume=50.0),
    ]
    if include_far:
        rows.append(_row(4700.0, put_volume=0.0, call_volume=250.0))
    return pl.DataFrame(rows, infer_schema_length=None)


def _row(strike: float, *, put_volume: float, call_volume: float) -> dict[str, object]:
    return {
        "snapshot_timestamp": "2026-05-27T08:00:00+00:00",
        "product": "Gold",
        "expiration": "G4WK6",
        "dte": 0.53,
        "future_price": 4532.6,
        "strike": strike,
        "put_volume": put_volume,
        "call_volume": call_volume,
        "total_volume": put_volume + call_volume,
        "volatility": 24.56,
        "volatility_change": 0.11,
        "future_change": -2.4,
        "range_label": "unit_test",
        "notes": "structured test row",
    }


def _latest_indicator_state() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "as_of_timestamp": "2026-05-26T03:45:00+00:00",
                "latest_price": 4542.5035,
                "latest_timeframe": "15m",
                "sd_source": "REALIZED_VOL_PROXY",
                "sd_state": "TOUCHING_2SD",
                "grid_state": "REFERENCE_ONLY",
                "cme_wall_state": "PILOT_ONLY",
                "confirmation_state": "TOUCHING_2SD_NO_CONFIRMATION",
                "final_action": "WATCH_ONLY",
                "final_recommendation": "INDICATOR_BLUEPRINT_READY",
                "plain_english_summary": "Synthetic latest state.",
            }
        ],
        infer_schema_length=None,
    )


def _rows(frame: pl.DataFrame, key: str) -> dict[str, dict[str, object]]:
    return {str(row[key]): row for row in frame.to_dicts()}
