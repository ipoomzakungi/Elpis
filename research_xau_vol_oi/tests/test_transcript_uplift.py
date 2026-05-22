from datetime import UTC, datetime, timedelta

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal
from research_xau_vol_oi.transcript_uplift import (
    build_transcript_conditioned_events,
    build_transcript_rule_keep_kill,
    transcript_placebo_tests,
    transcript_rule_combination_uplift,
    transcript_rule_uplift,
    walk_forward_transcript_uplift,
)


def _timeline() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "transcript_id": "pre",
                "source_path": "pre.txt",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 9, 0, tzinfo=UTC),
                "title": "pre",
                "detected_rule_tags": "BASIS_ADJUSTMENT|IV_EXPECTED_MOVE",
                "confidence_score": 0.55,
                "extracted_numeric_levels": "",
                "extracted_basis_values": "",
                "extracted_iv_values": "",
                "extracted_sd_values": "",
                "extracted_oi_strikes": "",
                "notes": "",
            },
            {
                "transcript_id": "t1",
                "source_path": "t1.txt",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 10, 30, tzinfo=UTC),
                "title": "t1",
                "detected_rule_tags": "OI_WALL|REJECTION_AT_WALL|NO_TRADE_DISCIPLINE",
                "confidence_score": 0.8,
                "extracted_numeric_levels": "",
                "extracted_basis_values": "",
                "extracted_iv_values": "",
                "extracted_sd_values": "",
                "extracted_oi_strikes": "",
                "notes": "",
            },
            {
                "transcript_id": "t2",
                "source_path": "t2.txt",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
                "title": "t2",
                "detected_rule_tags": "OI_WALL|INTRADAY_VOLUME",
                "confidence_score": 0.6,
                "extracted_numeric_levels": "",
                "extracted_basis_values": "",
                "extracted_iv_values": "",
                "extracted_sd_values": "",
                "extracted_oi_strikes": "",
                "notes": "",
            },
            {
                "transcript_id": "future",
                "source_path": "future.txt",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
                "title": "future",
                "detected_rule_tags": "IV_RV_VRP",
                "confidence_score": 0.7,
                "extracted_numeric_levels": "",
                "extracted_basis_values": "",
                "extracted_iv_values": "",
                "extracted_sd_values": "",
                "extracted_oi_strikes": "",
                "notes": "",
            },
        ]
    )


def _events() -> pl.DataFrame:
    base = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "event_timestamp": base,
                "source_bar_timestamp": base,
                "signal": Signal.NO_TRADE.value,
                "sigma_zone": "inside_1sd",
                "reason": "control_no_trade",
            },
            {
                "event_timestamp": base + timedelta(minutes=20),
                "source_bar_timestamp": base + timedelta(minutes=20),
                "signal": Signal.FADE_WALL_SHORT.value,
                "sigma_zone": "inside_1sd",
                "reason": "before_oi_rule",
            },
            {
                "event_timestamp": base + timedelta(minutes=40),
                "source_bar_timestamp": base + timedelta(minutes=40),
                "signal": Signal.FADE_WALL_SHORT.value,
                "sigma_zone": "inside_1sd",
                "reason": "after_oi_rule",
            },
            {
                "event_timestamp": base + timedelta(minutes=50),
                "source_bar_timestamp": base + timedelta(minutes=50),
                "signal": Signal.NO_TRADE_MIDDLE.value,
                "sigma_zone": "inside_1sd",
                "reason": "after_oi_no_trade",
            },
            {
                "event_timestamp": base + timedelta(minutes=70),
                "source_bar_timestamp": base + timedelta(minutes=70),
                "signal": Signal.FADE_WALL_SHORT.value,
                "sigma_zone": "outside_1sd",
                "reason": "after_duplicate_oi",
            },
        ]
    )


def _trades() -> pl.DataFrame:
    base = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "event_timestamp": base + timedelta(minutes=20),
                "signal": Signal.FADE_WALL_SHORT.value,
                "net_pnl_points": -5.0,
                "mae_points": -7.0,
                "mfe_points": 1.0,
                "time_in_trade_bars": 4,
            },
            {
                "event_timestamp": base + timedelta(minutes=40),
                "signal": Signal.FADE_WALL_SHORT.value,
                "net_pnl_points": 8.0,
                "mae_points": -1.0,
                "mfe_points": 10.0,
                "time_in_trade_bars": 4,
            },
            {
                "event_timestamp": base + timedelta(minutes=70),
                "signal": Signal.FADE_WALL_SHORT.value,
                "net_pnl_points": 4.0,
                "mae_points": -2.0,
                "mfe_points": 6.0,
                "time_in_trade_bars": 4,
            },
            {
                "event_timestamp": base + timedelta(minutes=20),
                "signal": Signal.BOLLINGER_BASELINE.value,
                "net_pnl_points": 1.0,
            },
            {
                "event_timestamp": base + timedelta(minutes=20),
                "signal": Signal.RANDOM_BASELINE.value,
                "net_pnl_points": -1.0,
            },
        ]
    )


def test_active_rule_no_lookahead() -> None:
    conditioned = build_transcript_conditioned_events(_events(), _timeline())
    before_oi = conditioned.filter(pl.col("signal") == Signal.FADE_WALL_SHORT.value).row(0, named=True)
    after_oi = conditioned.filter(pl.col("event_timestamp") == datetime(2026, 5, 21, 10, 40, tzinfo=UTC)).row(
        0,
        named=True,
    )

    assert before_oi["has_oi_wall_tag"] is False
    assert before_oi["has_basis_adjustment_tag"] is True
    assert after_oi["has_oi_wall_tag"] is True
    assert "IV_RV_VRP" not in after_oi["active_transcript_rule_tags"]


def test_deduplicated_active_tags() -> None:
    conditioned = build_transcript_conditioned_events(_events(), _timeline())
    later = conditioned.filter(pl.col("event_timestamp") == datetime(2026, 5, 21, 11, 10, tzinfo=UTC)).row(
        0,
        named=True,
    )

    assert later["active_transcript_rule_tags"].split("|").count("OI_WALL") == 1
    assert later["active_rule_count"] == len(set(later["active_transcript_rule_tags"].split("|")))


def test_no_trade_rows_retained() -> None:
    conditioned = build_transcript_conditioned_events(_events(), _timeline())
    uplift = transcript_rule_uplift(conditioned, _trades(), min_sample_size=1)
    oi = uplift.filter(pl.col("rule_id") == "OI_WALL").row(0, named=True)

    assert conditioned.height == _events().height
    assert conditioned.filter(pl.col("no_trade_row_retained")).height == 2
    assert oi["no_trade_count"] == 1


def test_uplift_calculation() -> None:
    conditioned = build_transcript_conditioned_events(_events(), _timeline())
    uplift = transcript_rule_uplift(conditioned, _trades(), min_sample_size=1)
    oi = uplift.filter(pl.col("rule_id") == "OI_WALL").row(0, named=True)

    assert oi["directional_trade_count"] == 2
    assert oi["expectancy"] == 6.0
    assert oi["without_tag_expectancy"] == -5.0
    assert oi["uplift_vs_no_tag"] == 11.0


def test_rule_combination_schema() -> None:
    conditioned = build_transcript_conditioned_events(_events(), _timeline())
    combos = transcript_rule_combination_uplift(conditioned, _trades(), min_sample_size=1)

    assert {
        "rule_id",
        "rule_type",
        "required_tags",
        "uplift_vs_no_tag",
        "uplift_vs_base_score",
    }.issubset(combos.columns)
    assert combos.filter(pl.col("rule_id") == "OI_WALL+REJECTION_AT_WALL").height == 1


def test_walk_forward_no_leakage() -> None:
    base = datetime(2026, 5, 21, 10, 0, tzinfo=UTC)
    feature_table = pl.DataFrame(
        [{"timestamp": base + timedelta(minutes=10 * index), "close": 2400.0 + index} for index in range(12)]
    )
    cfg = ResearchConfig(walk_forward_train_bars=4, walk_forward_test_bars=4)
    conditioned = build_transcript_conditioned_events(_events(), _timeline())
    walk = walk_forward_transcript_uplift(feature_table, conditioned, _trades(), config=cfg, min_sample_size=1)

    assert not walk.is_empty()
    assert walk.get_column("no_lookahead").all()
    assert walk.row(0, named=True)["train_end"] < walk.row(0, named=True)["test_start"]


def test_placebo_shuffle_test() -> None:
    placebo = transcript_placebo_tests(_events(), _timeline(), _trades(), min_sample_size=1)

    assert set(placebo.get_column("placebo_type").to_list()) == {
        "REAL",
        "SHUFFLED_TAGS",
        "SHIFTED_AVAILABILITY",
        "LEAKAGE_PLACEBO",
    }
    assert placebo.filter(pl.col("placebo_type") == "LEAKAGE_PLACEBO").row(0, named=True)[
        "used_future_transcripts"
    ]


def test_keep_kill_recommendation_logic() -> None:
    rule_uplift = pl.DataFrame(
        [
            {
                "rule_id": "NEGATIVE_RULE",
                "rule_type": "rule_tag",
                "event_count": 10,
                "directional_trade_count": 25,
                "no_trade_count": 1,
                "expectancy": -2.0,
                "profit_factor": 0.5,
                "uplift_vs_no_tag": -3.0,
            },
            {
                "rule_id": "SMALL_RULE",
                "rule_type": "rule_tag",
                "event_count": 2,
                "directional_trade_count": 1,
                "no_trade_count": 0,
                "expectancy": 5.0,
                "profit_factor": 2.0,
                "uplift_vs_no_tag": 5.0,
            },
            {
                "rule_id": "POSITIVE_RULE",
                "rule_type": "rule_tag",
                "event_count": 30,
                "directional_trade_count": 25,
                "no_trade_count": 3,
                "expectancy": 5.0,
                "profit_factor": 2.0,
                "uplift_vs_no_tag": 5.0,
            },
        ]
    )
    keep_kill = build_transcript_rule_keep_kill(
        rule_uplift,
        pl.DataFrame(),
        pl.DataFrame(),
        pl.DataFrame(),
        min_sample_size=20,
    )

    rows = {row["rule_id"]: row["recommendation"] for row in keep_kill.to_dicts()}
    assert rows["NEGATIVE_RULE"] == "KILL"
    assert rows["SMALL_RULE"] == "UNVALIDATED"
    assert rows["POSITIVE_RULE"] == "QUARANTINE"
