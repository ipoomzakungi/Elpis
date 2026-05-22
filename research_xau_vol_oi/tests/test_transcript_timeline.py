from datetime import UTC, datetime

import polars as pl

from research_xau_vol_oi.config import Signal
from research_xau_vol_oi.transcript_timeline import (
    align_transcripts_to_market,
    build_transcript_rule_timeline,
    parse_transcript_file,
    transcript_rule_coverage,
    transcript_rule_performance,
)


def _feature_table() -> pl.DataFrame:
    rows = []
    for index, timestamp in enumerate(
        [
            datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
            datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
            datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
        ]
    ):
        rows.append(
            {
                "timestamp": timestamp,
                "session_date": timestamp.date().isoformat(),
                "open": 2400.0 + index,
                "high": 2405.0 + index,
                "low": 2395.0 + index,
                "close": 2401.0 + index,
            }
        )
    return pl.DataFrame(rows)


def _events() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "event_timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
                "source_bar_timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
                "signal": Signal.FADE_WALL_SHORT.value,
                "reason": "resistance_rejection",
            },
            {
                "event_timestamp": datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
                "source_bar_timestamp": datetime(2026, 5, 21, 10, 45, tzinfo=UTC),
                "signal": Signal.NO_TRADE.value,
                "reason": "no_trade_discipline",
            },
            {
                "event_timestamp": datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
                "source_bar_timestamp": datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
                "signal": Signal.FADE_WALL_SHORT.value,
                "reason": "resistance_rejection",
            },
        ]
    )


def _trades() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "event_timestamp": datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
                "signal": Signal.FADE_WALL_SHORT.value,
                "net_pnl_points": -4.0,
            },
            {
                "event_timestamp": datetime(2026, 5, 22, 10, 0, tzinfo=UTC),
                "signal": Signal.FADE_WALL_SHORT.value,
                "net_pnl_points": 8.0,
            },
        ]
    )


def test_parse_transcript_date_availability_and_rule_tags(tmp_path) -> None:
    path = tmp_path / "2026-05-21 - xau guru [abc123].txt"
    path.write_text(
        "Title: XAU OI wall 1 SD\n"
        "Published: 2026-05-21 10:30:00\n"
        "OI OpenInterest แนวต้าน 2405 ไม่เทรด 1 SD ปิดเหนือ rejection basis IV\n",
        encoding="utf-8",
    )

    record = parse_transcript_file(path)[0]

    assert record["transcript_id"] == "abc123"
    assert record["transcript_date"] == "2026-05-21"
    assert record["availability_timestamp"] == datetime(2026, 5, 21, 10, 30, tzinfo=UTC)
    assert "OI_WALL" in record["detected_rule_tags"]
    assert "NO_TRADE_DISCIPLINE" in record["detected_rule_tags"]
    assert "2405" in record["extracted_numeric_levels"]


def test_default_availability_after_session_close_blocks_same_session(tmp_path) -> None:
    path = tmp_path / "2026-05-21 - evening transcript [late123].txt"
    path.write_text("Title: Evening OI\nOI 1 SD ไม่เทรด แนวต้าน 2400\n", encoding="utf-8")

    timeline = build_transcript_rule_timeline(transcript_paths=[path])
    alignment = align_transcripts_to_market(timeline, _feature_table(), _events(), _trades())
    oi_same_day = alignment.filter(
        (pl.col("rule_tag") == "OI_WALL") & (pl.col("window_label") == "same_day")
    ).row(0, named=True)
    oi_next = alignment.filter(
        (pl.col("rule_tag") == "OI_WALL") & (pl.col("window_label") == "next_session")
    ).row(0, named=True)

    assert timeline.row(0, named=True)["availability_timestamp"] == datetime(
        2026, 5, 21, 21, 1, tzinfo=UTC
    )
    assert oi_same_day["event_count"] == 0
    assert oi_next["event_count"] == 1
    assert oi_next["no_lookahead_violations"] == 0


def test_no_future_transcript_joins() -> None:
    timeline = pl.DataFrame(
        [
            {
                "transcript_id": "t1",
                "source_path": "synthetic",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 10, 30, tzinfo=UTC),
                "title": "synthetic",
                "detected_rule_tags": "REJECTION_AT_WALL",
                "confidence_score": 0.8,
                "extracted_numeric_levels": "",
                "extracted_basis_values": "",
                "extracted_iv_values": "",
                "extracted_sd_values": "",
                "extracted_oi_strikes": "",
                "notes": "",
            }
        ]
    )

    alignment = align_transcripts_to_market(timeline, _feature_table(), _events(), _trades())
    same_day = alignment.filter(
        (pl.col("rule_tag") == "REJECTION_AT_WALL") & (pl.col("window_label") == "same_day")
    ).row(0, named=True)

    assert same_day["event_count"] == 1
    assert same_day["first_event_timestamp"] == datetime(2026, 5, 21, 10, 45, tzinfo=UTC)
    assert same_day["no_lookahead_violations"] == 0


def test_no_trade_rows_are_retained_in_alignment() -> None:
    timeline = pl.DataFrame(
        [
            {
                "transcript_id": "t1",
                "source_path": "synthetic",
                "transcript_date": "2026-05-21",
                "availability_timestamp": datetime(2026, 5, 21, 10, 30, tzinfo=UTC),
                "title": "synthetic",
                "detected_rule_tags": "NO_TRADE_DISCIPLINE",
                "confidence_score": 0.8,
                "extracted_numeric_levels": "",
                "extracted_basis_values": "",
                "extracted_iv_values": "",
                "extracted_sd_values": "",
                "extracted_oi_strikes": "",
                "notes": "",
            }
        ]
    )

    alignment = align_transcripts_to_market(timeline, _feature_table(), _events(), _trades())
    same_day = alignment.filter(pl.col("window_label") == "same_day").row(0, named=True)

    assert same_day["event_count"] == 1
    assert same_day["no_trade_event_count"] == 1


def test_rule_coverage_and_performance_schema(tmp_path) -> None:
    path = tmp_path / "2026-05-21 - xau guru [schema1].txt"
    path.write_text("Title: XAU rejection\nPublished: 2026-05-21 09:00:00\nrejection OI wall\n", encoding="utf-8")
    timeline = build_transcript_rule_timeline(transcript_paths=[path])
    alignment = align_transcripts_to_market(timeline, _feature_table(), _events(), _trades())
    coverage = transcript_rule_coverage(timeline, alignment)
    performance = transcript_rule_performance(alignment, _trades())

    assert {"rule_tag", "transcript_count", "five_session_event_count"}.issubset(coverage.columns)
    assert {"rule_tag", "window_label", "decision_label", "sample_size_warning"}.issubset(
        performance.columns
    )
    assert performance.filter(pl.col("rule_tag") == "REJECTION_AT_WALL").height == 4


def test_combined_transcript_file_parses_multiple_sections(tmp_path) -> None:
    path = tmp_path / "combined_transcripts.txt"
    path.write_text(
        "==============================\n"
        "Date: 2026-05-21\nVideo ID: one123\nTitle: first OI\nOI wall 1 SD\n"
        "==============================\n"
        "Date: 2026-05-22\nVideo ID: two456\nTitle: second IV\nIV RV VRP no trade\n",
        encoding="utf-8",
    )

    records = parse_transcript_file(path)

    assert len(records) == 2
    assert records[0]["transcript_id"] == "one123"
    assert records[1]["transcript_id"] == "two456"
