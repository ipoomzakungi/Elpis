import polars as pl

from research_xau_vol_oi.transcript_timing_evidence import (
    build_same_day_filter_evidence,
    build_same_day_market_map_evidence,
    build_transcript_availability_classification,
    build_transcript_metadata_fetch_plan,
    classify_availability_relation,
    parse_filename_timing,
    parse_metadata_json_timing,
    parse_srt_timecodes,
    same_day_filter_evidence_markdown,
    transcript_availability_classification_markdown,
)


def test_filename_timestamp_parsing() -> None:
    timing = parse_filename_timing("guru_live_2026-05-14_08-30-15.txt")

    assert timing.timing_source == "FILENAME"
    assert timing.timing_confidence == "MEDIUM"
    assert timing.detected_publish_timestamp == "2026-05-14T08:30:15"
    assert timing.detected_live_start_timestamp == "2026-05-14T08:30:15"


def test_metadata_json_timestamp_parsing() -> None:
    timing = parse_metadata_json_timing(
        {
            "timestamp": "2026-05-14T08:30:00Z",
            "live_start_time": "2026-05-14T08:15:00Z",
            "live_end_time": "2026-05-14T09:05:00Z",
        }
    )

    assert timing.timing_source == "YOUTUBE_METADATA_JSON"
    assert timing.timing_confidence == "HIGH"
    assert timing.detected_publish_timestamp == "2026-05-14T08:30:00"
    assert timing.detected_live_start_timestamp == "2026-05-14T08:15:00"
    assert timing.detected_live_end_timestamp == "2026-05-14T09:05:00"


def test_srt_timecode_only_gives_relative_time_not_publish_time() -> None:
    timing = parse_srt_timecodes(
        "1\n00:00:01,000 --> 00:00:03,500\nhello\n\n"
        "2\n00:04:10,000 --> 00:04:12,000\nworld\n"
    )

    assert timing.timing_source == "SRT_TIMECODE"
    assert timing.timing_confidence == "LOW"
    assert timing.detected_publish_timestamp == ""
    assert timing.detected_transcript_start_timestamp == "00:00:01.000"
    assert timing.detected_transcript_end_timestamp == "00:04:12.000"


def test_unknown_timing_cannot_be_same_session_predictive_input() -> None:
    availability = build_transcript_availability_classification(
        timing_audit=_timing_audit(
            publish="",
            confidence="UNKNOWN",
            transcript_date="2026-05-14",
        ),
        remapped_replay=_remapped(["2026-05-14"]),
        playbook_matches=_matches(["2026-05-14"]),
    )

    row = availability.row(0, named=True)

    assert row["availability_relation"] == "UNKNOWN"
    assert row["can_use_as_same_session_context"] is False
    assert row["can_use_as_same_session_filter"] is False
    assert row["can_use_as_same_session_market_map"] is False


def test_post_session_cannot_be_used_as_same_session_signal() -> None:
    availability = build_transcript_availability_classification(
        timing_audit=_timing_audit(
            publish="2026-05-14T22:05:00",
            confidence="HIGH",
            transcript_date="2026-05-14",
        ),
        remapped_replay=_remapped(["2026-05-14"]),
        playbook_matches=_matches(["2026-05-14"]),
    )

    row = availability.row(0, named=True)

    assert row["availability_relation"] == "POST_SESSION"
    assert row["can_use_as_same_session_filter"] is False
    assert row["can_use_as_same_session_trade_rule"] is False


def test_next_session_prep_applies_only_to_next_valid_session() -> None:
    next_session = classify_availability_relation(
        transcript_date="2026-05-16",
        resolved_market_session_date="2026-05-18",
        timestamp="",
        timing_confidence="UNKNOWN",
    )
    later_session = classify_availability_relation(
        transcript_date="2026-05-16",
        resolved_market_session_date="2026-05-19",
        timestamp="",
        timing_confidence="UNKNOWN",
    )

    assert next_session == "NEXT_SESSION_PREP"
    assert later_session == "HISTORICAL_PLAYBOOK_ONLY"


def test_same_day_filter_evidence_with_unknown_timing_is_context_only() -> None:
    evidence = build_same_day_filter_evidence(
        remapped_replay=_remapped(["2026-05-14"]),
        playbook_matches=_matches(["2026-05-14"]),
        availability_classification=_unknown_availability(),
        filter_replay=pl.DataFrame(),
        replay=_replay(["2026-05-14"]),
        historical_playbook_replay=pl.DataFrame(),
    )

    row = evidence.row(0, named=True)

    assert row["same_day_filter_matches"] == 1
    assert row["timing_confirmed_filter_matches"] == 0
    assert row["unknown_timing_filter_matches"] == 1
    assert row["evidence_status"] == "TIMING_UNKNOWN_CONTEXT_ONLY"


def test_market_map_evidence_requires_basis_for_spot_equivalent_walls() -> None:
    evidence = build_same_day_market_map_evidence(
        remapped_replay=pl.DataFrame(
            [
                {
                    "original_replay_date": "2026-05-14",
                    "resolved_market_session_date": "2026-05-14",
                    "spot_basis_join_result": "SPOT_BASIS_MISSING",
                    "wall_mapping_result": "SPOT_EQUIVALENT_WALLS_AVAILABLE",
                    "cme_data_join_result": "CME_JOIN_OK",
                }
            ]
        ),
        playbook_matches=_matches(["2026-05-14"]),
        availability_classification=_unknown_availability(),
        replay=pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-14",
                    "oi_available": True,
                    "basis_available": False,
                    "nearest_wall_above_price": 2400.0,
                    "nearest_wall_below_price": 2350.0,
                }
            ]
        ),
    )

    row = evidence.row(0, named=True)

    assert row["same_day_market_map_matches"] == 1
    assert row["basis_available"] is False
    assert row["spot_equivalent_walls_available"] is False
    assert row["confidence"] == "CONTEXT_ONLY"


def test_metadata_fetch_plan_is_created_for_unknown_timing() -> None:
    plan = build_transcript_metadata_fetch_plan(
        _timing_audit(publish="", confidence="UNKNOWN", transcript_date="2026-05-14")
    )

    row = plan.row(0, named=True)

    assert plan.height == 1
    assert row["required_metadata"] == "video_url|video_id|publish_time|live_start_time|live_end_time"
    assert "yt-dlp --skip-download --write-info-json" in row["suggested_command_template"]


def test_report_does_not_claim_profitability() -> None:
    markdown = same_day_filter_evidence_markdown(
        pl.DataFrame(
            [
                {
                    "original_replay_date": "2026-05-14",
                    "resolved_market_session_date": "2026-05-14",
                    "same_day_filter_matches": 1,
                    "timing_confirmed_filter_matches": 0,
                    "unknown_timing_filter_matches": 1,
                    "no_trade_filter_active": True,
                    "active_filter_logic_names": "No-trade discipline",
                    "base_trade_candidates_count": 1,
                    "blocked_trade_candidates_count": 1,
                    "known_bad_trades_blocked": 0,
                    "known_good_trades_blocked": 0,
                    "avoided_loss_proxy": 0.0,
                    "opportunity_cost_proxy": 0.0,
                    "net_filter_value_proxy": 0.0,
                    "false_block_rate": None,
                    "evidence_status": "TIMING_UNKNOWN_CONTEXT_ONLY",
                    "plain_english_summary": "Evidence only; no outcome claim.",
                }
            ]
        )
    ).lower()

    assert "profitable" not in markdown
    assert "safe to trade" not in markdown
    assert "live ready" not in markdown


def test_reports_use_redacted_paths_only() -> None:
    markdown = transcript_availability_classification_markdown(
        pl.DataFrame(
            [
                {
                    "clean_transcript_id": "clean_1",
                    "transcript_date": "2026-05-14",
                    "resolved_market_session_date": "2026-05-14",
                    "detected_publish_timestamp": r"C:\Users\example\secret.txt",
                    "detected_live_start_timestamp": "",
                    "session_open_timestamp": "2026-05-14T04:00:00",
                    "session_close_timestamp": "2026-05-14T21:00:00",
                    "availability_relation": "UNKNOWN",
                    "can_use_as_same_session_context": False,
                    "can_use_as_same_session_filter": False,
                    "can_use_as_same_session_market_map": False,
                    "can_use_as_same_session_trade_rule": False,
                    "reason_plain_english": r"C:\Users\example\secret.txt",
                }
            ]
        )
    )

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _timing_audit(
    *,
    publish: str,
    confidence: str,
    transcript_date: str,
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": transcript_date,
                "title_hash": "title-a",
                "content_hash": "content-a",
                "detected_publish_timestamp": publish,
                "detected_live_start_timestamp": "",
                "detected_live_end_timestamp": "",
                "detected_transcript_start_timestamp": "",
                "detected_transcript_end_timestamp": "",
                "timing_source": "UNKNOWN" if not publish else "YOUTUBE_METADATA_JSON",
                "timing_confidence": confidence,
                "timing_notes": "test timing row",
            }
        ]
    )


def _remapped(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "original_replay_date": trade_date,
                "resolved_market_session_date": trade_date,
                "spot_basis_join_result": "SPOT_BASIS_AVAILABLE",
                "wall_mapping_result": "SPOT_EQUIVALENT_WALLS_AVAILABLE",
                "cme_data_join_result": "CME_JOIN_OK",
            }
            for trade_date in dates
        ]
    )


def _matches(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "replay_date": trade_date,
                "logic_id": "glkb_no_trade_discipline",
                "logic_name": "No-trade discipline",
                "usable_as_context": True,
                "usable_as_filter": True,
                "usable_as_market_map": False,
                "usable_as_trade_rule": False,
            }
            for trade_date in dates
        ]
        + [
            {
                "clean_transcript_id": "clean_1",
                "replay_date": trade_date,
                "logic_id": "glkb_oi_wall",
                "logic_name": "Open-interest wall zone",
                "usable_as_context": True,
                "usable_as_filter": False,
                "usable_as_market_map": True,
                "usable_as_trade_rule": False,
            }
            for trade_date in dates
        ]
    )


def _unknown_availability() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": "2026-05-14",
                "resolved_market_session_date": "2026-05-14",
                "availability_relation": "UNKNOWN",
                "can_use_as_same_session_context": False,
                "can_use_as_same_session_filter": False,
                "can_use_as_same_session_market_map": False,
                "can_use_as_same_session_trade_rule": False,
            }
        ]
    )


def _replay(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "touched_wall": True,
                "no_trade_filter_active": False,
                "oi_available": True,
                "basis_available": True,
            }
            for trade_date in dates
        ]
    )
