from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal
from research_xau_vol_oi.score_calibration import (
    build_signal_kill_list,
    classify_score_monotonicity,
    feature_ablation,
    score_bucket_performance,
    score_decile,
    walk_forward_score_calibration,
)
from research_xau_vol_oi.signal_score import score_signal_events


def _times(count: int) -> list[datetime]:
    start = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    return [start + timedelta(minutes=15 * index) for index in range(count)]


def _price_frame(count: int = 10) -> pl.DataFrame:
    times = _times(count)
    rows = []
    for index, timestamp in enumerate(times):
        close = 2400.0 + index
        rows.append(
            {
                "timestamp": timestamp,
                "open": close,
                "high": close + 2.0,
                "low": close - 2.0,
                "close": close,
                "session_open": 2400.0,
                "one_sd_remaining": 20.0,
                "sigma_position": 1.2,
                "sigma_zone": "between_1_2sd",
                "data_quality_state": "VALID",
                "rv_percent": 12.0,
                "volume": 100.0 + index,
                "vol_regime": "BALANCED",
                "wall_level": close + 4.0,
                "wall_score": 0.4,
                "distance_to_nearest_wall": 4.0,
                "freshness_weight": 1.5,
                "dte_weight": 0.8,
                "wall_score_bucket": "high",
                "dte_bucket": "0_3d",
                "wall_side": "resistance",
                "basis_available": True,
            }
        )
    return pl.DataFrame(rows)


def _score_rows() -> pl.DataFrame:
    times = _times(4)
    return pl.DataFrame(
        [
            _score_row(times[0], Signal.NO_TRADE.value, 5, "NONE"),
            _score_row(times[1], Signal.FADE_WALL_SHORT.value, 55, "SHORT"),
            _score_row(times[2], Signal.FADE_WALL_SHORT.value, 85, "SHORT"),
            _score_row(times[3], Signal.NO_TRADE_MIDDLE.value, 25, "NONE"),
        ]
    )


def _score_row(timestamp, label, score, direction):
    return {
        "event_timestamp": timestamp,
        "source_bar_timestamp": timestamp,
        "source_signal": label,
        "source_reason": "synthetic",
        "signal_label": label,
        "signal_score": score,
        "trade_direction": direction,
        "entry_reason": "synthetic",
        "invalidation_level": None,
        "target_level": None,
        "risk_warning": "research-only",
        "close": 2400.0,
        "sigma_position": 1.2,
        "distance_to_nearest_wall": 4.0,
        "wall_score": 0.4,
        "freshness_weight": 1.5,
        "dte_weight": 0.8,
        "vol_regime": "BALANCED",
        "session_open_side": "above_session_open",
        "research_only": True,
    }


def _signal_events() -> pl.DataFrame:
    times = _times(4)
    return pl.DataFrame(
        [
            {
                "event_timestamp": timestamp,
                "source_bar_timestamp": timestamp,
                "available_wall_timestamp": timestamp - timedelta(minutes=15),
                "signal": Signal.FADE_WALL_SHORT.value,
                "reason": "synthetic",
                "sigma_zone": "between_1_2sd",
                "wall_score_bucket": "high",
                "dte_bucket": "0_3d",
                "vol_regime": "BALANCED",
            }
            for timestamp in times
        ]
    )


def test_score_decile_grouping_retains_no_trade_rows() -> None:
    scores = _score_rows()
    performance = score_bucket_performance(_price_frame(), _signal_events(), scores)
    deciles = performance.filter(pl.col("group_type") == "score_decile")

    assert score_decile(100) == "90-100"
    assert deciles.get_column("event_count").sum() == scores.height
    assert "0-10" in set(deciles.get_column("bucket").to_list())
    assert "80-90" in set(deciles.get_column("bucket").to_list())


def test_no_trade_rows_retained_in_signal_label_group() -> None:
    scores = _score_rows()
    performance = score_bucket_performance(_price_frame(), _signal_events(), scores)
    no_trade = performance.filter(
        (pl.col("group_type") == "signal_label")
        & (pl.col("bucket") == Signal.NO_TRADE.value)
    ).row(0, named=True)

    assert no_trade["event_count"] == 1
    assert no_trade["trade_count"] == 0


def test_threshold_selection_no_lookahead_skips_train_trade_exiting_in_test() -> None:
    price = _price_frame(9)
    event_time = _times(9)[4]
    scores = pl.DataFrame([_score_row(event_time, Signal.FADE_WALL_SHORT.value, 95, "SHORT")])
    cfg = ResearchConfig(
        walk_forward_train_bars=5,
        walk_forward_test_bars=4,
        backtest_horizon_bars=2,
    )

    walk_forward = walk_forward_score_calibration(
        price,
        scores,
        config=cfg,
        thresholds=(90,),
        min_sample_size=1,
    )

    first = walk_forward.row(0, named=True)
    assert first["selected_threshold"] is None
    assert first["pass_fail"] == "FAIL"


def test_signal_kill_logic_recommends_kill_and_control_only() -> None:
    deciles = pl.DataFrame(
        [
            {
                "group_type": "signal_label",
                "bucket": Signal.FADE_WALL_LONG.value,
                "event_count": 30,
                "trade_count": 30,
                "win_rate": 0.3,
                "average_win": 1.0,
                "average_loss": -2.0,
                "expectancy": -1.0,
                "profit_factor": 0.5,
                "max_drawdown": -10.0,
                "average_mae": -2.0,
                "average_mfe": 1.0,
                "average_holding_time": 8.0,
                "sample_size_warning": False,
            },
            {
                "group_type": "signal_label",
                "bucket": Signal.NO_TRADE.value,
                "event_count": 40,
                "trade_count": 0,
                "win_rate": None,
                "average_win": 0.0,
                "average_loss": 0.0,
                "expectancy": None,
                "profit_factor": None,
                "max_drawdown": 0.0,
                "average_mae": 0.0,
                "average_mfe": 0.0,
                "average_holding_time": 0.0,
                "sample_size_warning": True,
            },
        ]
    )
    kill_list = build_signal_kill_list(deciles, pl.DataFrame(), pl.DataFrame(), min_sample_size=20)
    recommendations = {
        row["signal_label"]: row["recommendation"] for row in kill_list.to_dicts()
    }

    assert recommendations[Signal.FADE_WALL_LONG.value] == "KILL"
    assert recommendations[Signal.NO_TRADE.value] == "CONTROL_ONLY"


def test_ablation_output_schema() -> None:
    price = _price_frame(4)
    events = pl.DataFrame(
        [
            {
                "event_timestamp": _times(4)[1],
                "source_bar_timestamp": _times(4)[1],
                "available_wall_timestamp": _times(4)[0],
                "signal": Signal.FADE_WALL_SHORT.value,
                "reason": "resistance_rejection",
                "close": 2401.0,
                "wall_level": 2405.0,
                "wall_score": 0.4,
                "wall_side": "resistance",
                "basis_available": True,
            }
        ]
    )
    scores = score_signal_events(price, events)
    ablation = feature_ablation(price, events, scores, threshold=50)

    assert ablation.height > 0
    assert {
        "removed_component",
        "change_in_expectancy",
        "change_in_profit_factor",
        "change_in_trade_count",
        "change_in_no_trade_count",
        "impact",
    }.issubset(ablation.columns)


def test_monotonicity_classification() -> None:
    base = {
        "group_type": "score_decile",
        "event_count": 20,
        "trade_count": 20,
        "win_rate": 0.5,
        "average_win": 1.0,
        "average_loss": -1.0,
        "profit_factor": 1.0,
        "max_drawdown": -1.0,
        "average_mae": -1.0,
        "average_mfe": 1.0,
        "average_holding_time": 8.0,
        "sample_size_warning": False,
    }
    increasing = pl.DataFrame(
        [
            {**base, "bucket": "50-60", "expectancy": 0.1},
            {**base, "bucket": "60-70", "expectancy": 0.2},
            {**base, "bucket": "70-80", "expectancy": 0.3},
        ]
    )
    failing = pl.DataFrame(
        [
            {**base, "bucket": "50-60", "expectancy": 1.0},
            {**base, "bucket": "60-70", "expectancy": -0.2},
            {**base, "bucket": "90-100", "expectancy": 0.1},
        ]
    )

    assert classify_score_monotonicity(increasing)["monotonic_pass"]
    assert classify_score_monotonicity(failing)["monotonic_fail"]
