from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.config import ResearchConfig
from research_xau_vol_oi.market_map_proof_pack import (
    build_expiry_pin_test_report,
    build_filter_avoided_pnl_report,
    build_market_map_precision_report,
    build_wall_level_events,
    decide_final_proof_pack,
    run_market_map_proof_pack,
)


def _features() -> pl.DataFrame:
    start = datetime(2026, 5, 14, 0, 0, tzinfo=UTC)
    rows = []
    for index in range(80):
        close = 100.0 + (index % 8) * 0.5
        rows.append(
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "open": close - 0.1,
                "high": close + 1.5,
                "low": close - 1.0,
                "close": close,
                "one_sd_remaining": 4.0,
                "sigma_zone": "inside_1sd" if index % 2 == 0 else "edge_1sd",
                "vol_regime": "BALANCED",
                "event_tags": "CPI" if index % 17 == 0 else "",
            }
        )
    return pl.DataFrame(rows)


def _walls(features: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for index, bar in enumerate(features.head(35).to_dicts()):
        level = float(bar["close"]) + 1.0
        rows.append(
            {
                "timestamp": bar["timestamp"],
                "wall_id": f"wall-{index}",
                "expiry": "2026-05-15",
                "strike": level + 7.0,
                "wall_level": level,
                "spot_equivalent_strike": level,
                "wall_score": 0.35,
                "total_oi": 1000.0 + index,
                "normalized_total_oi": 1.0,
                "dte": 1.0,
                "wall_side": "resistance",
                "distance_to_spot": 1.0,
                "low_oi_gap_to_next_wall": index % 2 == 0,
                "next_wall_distance": 30.0,
                "largest_near_expiry_wall": True,
            }
        )
    return pl.DataFrame(rows)


def _signals(features: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for index, bar in enumerate(features.head(50).to_dicts()):
        signal = "NO_TRADE_MIDDLE" if index < 30 else "FADE_WALL_SHORT"
        rows.append(
            {
                "event_timestamp": bar["timestamp"],
                "signal": signal,
                "close": bar["close"],
                "wall_level": float(bar["close"]) + 1.0,
                "wall_side": "resistance",
                "sigma_position": 0.2,
                "sigma_zone": bar["sigma_zone"],
                "vol_regime": bar["vol_regime"],
                "dte": 1.0,
                "dte_bucket": "0_3D",
                "event_tags": bar["event_tags"],
            }
        )
    return pl.DataFrame(rows)


def test_market_map_report_contains_required_controls() -> None:
    features = _features()
    wall_events = build_wall_level_events(
        features,
        _walls(features),
        config=ResearchConfig(backtest_horizon_bars=4),
    )
    report = build_market_map_precision_report(
        features,
        wall_events,
        config=ResearchConfig(backtest_horizon_bars=4),
    )

    assert {"actual_top_wall", "matched_random_strike", "random_level_placebo", "matched_state_placebo"}.issubset(
        set(report.get_column("cohort").to_list())
    )
    assert "top_wall_vs_control" in set(report.get_column("test_name").to_list())
    assert {"expiry_bucket", "event_day_tag"}.issubset(set(report.get_column("bucket_type").to_list()))


def test_filter_value_report_keeps_no_trade_rows_and_controls() -> None:
    features = _features()
    report = build_filter_avoided_pnl_report(
        features,
        _signals(features),
        config=ResearchConfig(backtest_horizon_bars=4),
    )

    actual = report.filter(pl.col("control_type") == "actual_no_trade_labels").row(0, named=True)
    assert actual["no_trade_count"] > 0
    assert "matched_state_placebo" in set(report.get_column("control_type").to_list())
    assert "event_day_control" in set(report.get_column("control_type").to_list())
    assert "expiry_bucket_control" in set(report.get_column("control_type").to_list())


def test_expiry_pin_report_has_control_rows() -> None:
    features = _features()
    wall_events = build_wall_level_events(features, _walls(features))
    report = build_expiry_pin_test_report(features, wall_events)

    assert "expiry_pin_vs_control" in set(report.get_column("test_name").to_list())
    assert "matched_random_strike" in set(report.get_column("control_type").to_list())


def test_run_market_map_proof_pack_writes_outputs(tmp_path) -> None:
    features = _features()
    result = run_market_map_proof_pack(
        feature_table=features,
        walls=_walls(features),
        signal_events=_signals(features),
        output_dir=tmp_path,
        config=ResearchConfig(backtest_horizon_bars=4),
    )

    assert result.final_decision in {
        "MAP_USEFUL_NOT_TRADABLE",
        "FILTER_USEFUL",
        "TRADE_RULE_NOT_PROVEN",
        "NO_EDGE_FOUND",
    }
    assert (tmp_path / "market_map_precision_report.csv").exists()
    assert (tmp_path / "filter_avoided_pnl_report.csv").exists()
    assert (tmp_path / "expiry_pin_test_report.csv").exists()
    assert (tmp_path / "proof_pack.md").exists()


def test_final_decision_priority() -> None:
    assert decide_final_proof_pack("MAP_USEFUL_NOT_TRADABLE", "FILTER_USEFUL", "TRADE_RULE_NOT_PROVEN") == "FILTER_USEFUL"
    assert (
        decide_final_proof_pack("MAP_USEFUL_NOT_TRADABLE", "NO_EDGE_FOUND", "TRADE_RULE_NOT_PROVEN")
        == "MAP_USEFUL_NOT_TRADABLE"
    )
