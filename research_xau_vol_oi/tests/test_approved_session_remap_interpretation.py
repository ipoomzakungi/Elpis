import polars as pl

from research_xau_vol_oi.approved_session_remap_interpretation import (
    build_current_week_replay_after_market_session_remap,
    build_current_week_same_day_guru_overlay,
    build_market_session_remap_decisions,
    build_same_day_playbook_matches,
    build_same_day_transcript_interpretation_debug,
    current_week_same_day_guru_overlay_markdown,
)


def test_approved_market_remap_changes_market_session_date_only() -> None:
    decisions = build_market_session_remap_decisions(_suggestions())
    remapped = build_current_week_replay_after_market_session_remap(
        decisions=decisions,
        current_week_resolved=_resolved(["2026-05-16"]),
        replay=_replay(["2026-05-16"]),
        session_calendar=_calendar(),
    )

    row = remapped.row(0, named=True)

    assert row["resolved_market_session_date"] == "2026-05-15"
    assert row["remap_status"] == "APPLIED_MARKET_SESSION_ONLY"
    assert row["transcript_availability_date_unchanged"] is True


def test_transcript_availability_is_not_remapped() -> None:
    remapped = build_current_week_replay_after_market_session_remap(
        decisions=build_market_session_remap_decisions(_suggestions()),
        current_week_resolved=_resolved(["2026-05-16"]),
        replay=_replay(["2026-05-16"]),
        session_calendar=_calendar(),
    )

    row = remapped.row(0, named=True)

    assert "transcript availability date remains unchanged" in row["plain_english_summary"]


def test_same_day_transcript_is_passed_to_interpretation_debug() -> None:
    debug = _debug_for_text("วันนี้ไม่เทรดถ้า OI wall ยังไม่ชัด และต้องดู basis")

    row = debug.row(0, named=True)

    assert row["clean_transcript_id"] == "clean_1"
    assert row["transcript_date"] == "2026-05-14"
    assert row["text_length"] > 0


def test_rule_keyword_hits_produce_context_filter_market_map_rows() -> None:
    debug = _debug_for_text("วันนี้ไม่เทรดถ้า OI wall ยังไม่ชัด และต้องดู basis")

    row = debug.row(0, named=True)

    assert row["extracted_context_count"] >= 3
    assert row["extracted_filter_count"] >= 1
    assert row["extracted_market_map_count"] >= 2


def test_strict_trade_rule_can_remain_zero_without_failing() -> None:
    debug = _debug_for_text("วันนี้ไม่เทรดถ้า OI wall ยังไม่ชัด และต้องดู basis")

    row = debug.row(0, named=True)

    assert row["extracted_trade_rule_count"] == 0
    assert row["why_no_context_or_filter"] == "EXTRACTOR_ONLY_USES_REVIEW_EPISODES"


def test_same_day_playbook_matcher_finds_no_trade_filter_logic() -> None:
    debug = _debug_for_text("วันนี้ไม่เทรดเพราะมีข่าว ต้องรอ filter ก่อน")
    matches = build_same_day_playbook_matches(
        interpretation_debug=debug,
        knowledge_base=_knowledge_base(),
        text_index=_text_index("วันนี้ไม่เทรดเพราะมีข่าว ต้องรอ filter ก่อน"),
    )

    assert matches.filter(pl.col("logic_id") == "glkb_no_trade_discipline").height == 1
    assert matches.filter(pl.col("usable_as_filter")).height >= 1


def test_output_distinguishes_same_day_overlay_from_historical_playbook() -> None:
    debug = _debug_for_text("วันนี้ไม่เทรดถ้า OI wall ยังไม่ชัด")
    matches = build_same_day_playbook_matches(
        interpretation_debug=debug,
        knowledge_base=_knowledge_base(),
        text_index=_text_index("วันนี้ไม่เทรดถ้า OI wall ยังไม่ชัด"),
    )
    overlay = build_current_week_same_day_guru_overlay(
        current_week_replay_after_remap=_remapped(["2026-05-14"]),
        interpretation_debug=debug,
        playbook_matches=matches,
        historical_playbook_replay=_playbook(["2026-05-14"]),
    )

    row = overlay.row(0, named=True)

    assert row["same_day_filter_matches"] >= 1
    assert row["historical_playbook_overlay_matches"] >= 1
    assert row["final_guru_overlay_state"] == "SAME_DAY_FILTER_READY"


def test_report_does_not_claim_profitability() -> None:
    markdown = current_week_same_day_guru_overlay_markdown(
        build_current_week_same_day_guru_overlay(
            current_week_replay_after_remap=_remapped(["2026-05-14"]),
            interpretation_debug=pl.DataFrame(),
            playbook_matches=pl.DataFrame(),
            historical_playbook_replay=_playbook(["2026-05-14"]),
        ),
        final_recommendation="HISTORICAL_PLAYBOOK_ONLY",
    ).lower()

    assert "profitable" not in markdown
    assert "safe to trade" not in markdown
    assert "live ready" not in markdown


def test_redacted_paths_only() -> None:
    overlay = build_current_week_same_day_guru_overlay(
        current_week_replay_after_remap=pl.DataFrame(
            [
                {
                    "original_replay_date": "2026-05-14",
                    "resolved_market_session_date": "2026-05-14",
                }
            ]
        ),
        interpretation_debug=pl.DataFrame(),
        playbook_matches=pl.DataFrame(),
        historical_playbook_replay=pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-14",
                    "no_trade_filter_playbook_active": True,
                    "market_map_playbook_active": False,
                    "trade_rule_playbook_active": False,
                    "plain_english_summary": r"C:\Users\example\secret.txt",
                }
            ]
        ),
    )

    markdown = current_week_same_day_guru_overlay_markdown(
        overlay,
        final_recommendation="HISTORICAL_PLAYBOOK_ONLY",
    )

    assert r"C:\Users" not in markdown


def _debug_for_text(text: str) -> pl.DataFrame:
    return build_same_day_transcript_interpretation_debug(
        clean_transcript_set=_clean(),
        current_week_replay_after_remap=_remapped(["2026-05-14"]),
        transcript_availability=_availability(),
        readiness=pl.DataFrame(),
        knowledge_base=_knowledge_base(),
        text_index=_text_index(text),
    )


def _text_index(text: str) -> dict[str, dict[str, object]]:
    return {
        "content-a": {
            "text": text,
            "text_length": len(text),
            "thai_text_detected": True,
        }
    }


def _suggestions() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "original_replay_date": "2026-05-16",
                "suggested_market_session_date": "2026-05-15",
                "reason": "Weekend market session artifact.",
            }
        ]
    )


def _calendar() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "replay_trade_date": "2026-05-16",
                "has_cme_futures_rows": True,
                "has_option_oi_rows": True,
                "has_xau_spot_rows": False,
                "has_basis_rows": False,
            }
        ]
    )


def _replay(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "futures_available": True,
                "oi_available": True,
                "spot_available": trade_date != "2026-05-16",
                "basis_available": trade_date != "2026-05-16",
                "wall_type": "FUTURES_STRIKE_LEVEL",
            }
            for trade_date in dates
        ]
    )


def _resolved(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "original_replay_date": trade_date,
                "resolved_session_date": trade_date,
                "data_state": "WEEKEND_ARTIFACT" if trade_date == "2026-05-16" else "COMPLETE_FOR_PILOT",
            }
            for trade_date in dates
        ]
    )


def _remapped(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "original_replay_date": trade_date,
                "resolved_market_session_date": trade_date,
                "remap_status": "NO_REMAP_NEEDED",
                "transcript_availability_date_unchanged": True,
            }
            for trade_date in dates
        ]
    )


def _clean() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": "2026-05-14",
                "transcript_time": "",
                "content_hash": "content-a",
                "included_in_clean_set": True,
            }
        ]
    )


def _availability() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "replay_trade_date": "2026-05-14",
                "transcript_date": "2026-05-14",
                "availability_relation": "UNKNOWN",
            }
        ]
    )


def _knowledge_base() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "logic_id": "glkb_no_trade_discipline",
                "logic_name": "No-trade discipline",
                "logic_type": "NO_TRADE_FILTER",
            },
            {
                "logic_id": "glkb_oi_wall",
                "logic_name": "Open-interest wall zone",
                "logic_type": "OI_WALL_ZONE",
            },
            {
                "logic_id": "glkb_basis_adjustment",
                "logic_name": "Basis-adjusted strike mapping",
                "logic_type": "BASIS_MAPPING",
            },
        ]
    )


def _playbook(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "no_trade_filter_playbook_active": True,
                "market_map_playbook_active": True,
                "trade_rule_playbook_active": False,
            }
            for trade_date in dates
        ]
    )
