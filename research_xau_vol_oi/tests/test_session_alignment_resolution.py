from pathlib import Path

import polars as pl

from research_xau_vol_oi.session_alignment_resolution import (
    build_current_week_replay_resolved,
    build_refined_missing_data_action_plan,
    build_same_date_transcript_resolution,
    build_same_day_guru_signal_readiness,
    build_session_calendar_audit,
    build_transcript_manifest_dedup_audit,
    current_week_replay_resolved_markdown,
    session_calendar_audit_markdown,
)


def test_saturday_replay_date_is_flagged_as_possible_calendar_issue() -> None:
    audit = build_session_calendar_audit(
        replay=_replay(["2026-05-16"]),
        spot=_spot(["2026-05-15"]),
        basis=_basis(["2026-05-15"]),
    )

    row = audit.row(0, named=True)

    assert row["day_of_week"] == "Saturday"
    assert row["is_weekend"] is True
    assert row["likely_calendar_date_issue"] is True


def test_adjacent_friday_mapping_is_suggested_when_data_exists() -> None:
    audit = build_session_calendar_audit(
        replay=_replay(["2026-05-15", "2026-05-16"]),
        spot=_spot(["2026-05-15"]),
        basis=_basis(["2026-05-15"]),
    )

    saturday = audit.filter(pl.col("replay_trade_date") == "2026-05-16").row(0, named=True)

    assert saturday["possible_previous_trading_day"] == "2026-05-15"
    assert saturday["recommended_session_mapping"] == "REMAP_TO_2026-05-15"
    assert saturday["likely_session_date"] == "2026-05-15"


def test_missing_same_date_transcript_on_weekend_suggests_shift_first() -> None:
    resolution = build_same_date_transcript_resolution(
        alignment=_alignment_missing(["2026-05-16"]),
        manifest=_manifest(["2026-05-15", "2026-05-18"]),
        playbook_replay=_playbook(["2026-05-16"]),
    )

    row = resolution.row(0, named=True)

    assert row["day_of_week"] == "Saturday"
    assert row["possible_session_shift_match"] is True
    assert row["should_fetch_transcript"] is False


def test_manifest_dedup_reports_clean_count_separately_from_total_rows() -> None:
    audit = build_transcript_manifest_dedup_audit(
        pl.DataFrame(
            [
                _manifest_row("h1", "2026-05-14", "g1", "source file"),
                _manifest_row("h2", "2026-05-14", "g1", "zip entry; not extracted"),
                _manifest_row("h3", "2026-05-15", "g2", "source file"),
                _manifest_row("h4", "2026-05-15", "g2", "zip entry; not extracted"),
            ]
        )
    )

    row = audit.row(0, named=True)

    assert row["total_manifest_rows"] == 4
    assert row["clean_transcript_count"] == 2
    assert row["zip_entry_rows"] == 2


def test_context_filter_rows_do_not_become_trade_rule_rows() -> None:
    readiness = build_same_day_guru_signal_readiness(
        alignment=_alignment_same(["2026-05-14"]),
        interpretation=pl.DataFrame(
            [
                {
                    "transcript_id": "t1",
                    "transcript_date": "2026-05-14",
                    "usable_as_context": True,
                    "usable_as_filter": False,
                    "usable_as_market_map": True,
                    "usable_as_trade_rule": False,
                    "logic_type": "OI_WALL_ZONE",
                    "reason_not_trade_signal": "MARKET_MAP_ONLY",
                },
                {
                    "transcript_id": "t2",
                    "transcript_date": "2026-05-14",
                    "usable_as_context": True,
                    "usable_as_filter": True,
                    "usable_as_market_map": False,
                    "usable_as_trade_rule": False,
                    "logic_type": "NO_TRADE_FILTER",
                    "reason_not_trade_signal": "FILTER_ONLY",
                },
            ]
        ),
    )

    row = readiness.row(0, named=True)

    assert row["context_rows"] == 2
    assert row["filter_rows"] == 1
    assert row["market_map_rows"] == 1
    assert row["trade_rule_rows"] == 0
    assert row["can_use_as_same_day_trade_rule"] is False


def test_playbook_overlay_is_distinct_from_same_day_transcript() -> None:
    resolved = build_current_week_replay_resolved(
        replay=_replay(["2026-05-13"]),
        session_calendar=build_session_calendar_audit(replay=_replay(["2026-05-13"])),
        transcript_resolution=build_same_date_transcript_resolution(
            alignment=_alignment_missing(["2026-05-13"]),
            manifest=_manifest(["2026-05-14"]),
            playbook_replay=_playbook(["2026-05-13"]),
        ),
        readiness=pl.DataFrame(),
        playbook_replay=_playbook(["2026-05-13"]),
    )

    row = resolved.row(0, named=True)

    assert row["same_day_transcript_state"] in {"SESSION_SHIFT_MATCH", "PLAYBOOK_ONLY"}
    assert row["guru_state"] == "HISTORICAL_PLAYBOOK_OVERLAY"


def test_missing_data_action_plan_can_output_remap_session_date() -> None:
    calendar = build_session_calendar_audit(
        replay=_replay(["2026-05-15", "2026-05-16"]),
        spot=_spot(["2026-05-15"]),
        basis=_basis(["2026-05-15"]),
    )
    action_plan = build_refined_missing_data_action_plan(
        missing_spot_basis_plan=pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-16",
                    "missing_component": "xau_spot_price|basis",
                    "suggested_file_needed": "xauusd_spot_2026-05-16_intraday.csv",
                    "where_to_place_file": "data/raw/xau/",
                }
            ]
        ),
        session_calendar=calendar,
        transcript_resolution=pl.DataFrame(),
    )

    row = action_plan.row(0, named=True)

    assert row["final_action"] == "REMAP_SESSION_DATE"
    assert row["calendar_issue_possible"] is True


def test_report_does_not_claim_profitability() -> None:
    report = current_week_replay_resolved_markdown(
        build_current_week_replay_resolved(
            replay=_replay(["2026-05-14"]),
            session_calendar=build_session_calendar_audit(replay=_replay(["2026-05-14"])),
            transcript_resolution=pl.DataFrame(),
            readiness=pl.DataFrame(),
            playbook_replay=_playbook(["2026-05-14"]),
        ),
        final_recommendation="PLAYBOOK_OVERLAY_READY",
        secondary_recommendation="SAME_DAY_TRADE_RULE_NOT_READY",
    ).lower()

    assert "profitable" not in report
    assert "safe to trade" not in report
    assert "live ready" not in report


def test_paths_are_redacted(tmp_path: Path) -> None:
    raw_path = rf"C:\Users\example\secret\{tmp_path.name}\file.csv"
    frame = pl.DataFrame(
        [
            {
                "replay_trade_date": "2026-05-14",
                "day_of_week": "Thursday",
                "is_weekend": False,
                "has_cme_futures_rows": True,
                "has_option_oi_rows": True,
                "has_xau_spot_rows": True,
                "has_basis_rows": True,
                "likely_session_date": "2026-05-14",
                "likely_calendar_date_issue": False,
                "possible_previous_trading_day": "2026-05-13",
                "possible_next_trading_day": "2026-05-15",
                "recommended_session_mapping": "KEEP_REPLAY_DATE",
                "reason_plain_english": raw_path,
            }
        ]
    )

    markdown = session_calendar_audit_markdown(frame)

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _replay(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "futures_available": True,
                "oi_available": True,
                "spot_available": trade_date not in {"2026-05-16", "2026-05-23"},
                "basis_available": trade_date not in {"2026-05-16", "2026-05-23"},
            }
            for trade_date in dates
        ]
    )


def _spot(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame([{"trade_date": trade_date, "close": 2400.0} for trade_date in dates])


def _basis(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame([{"trade_date": trade_date, "basis": 5.0} for trade_date in dates])


def _alignment_missing(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "transcript_same_date_count": 0,
                "same_date_transcript_available": False,
            }
            for trade_date in dates
        ]
    )


def _alignment_same(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "transcript_same_date_count": 2,
                "same_date_transcript_available": True,
            }
            for trade_date in dates
        ]
    )


def _manifest(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [_manifest_row(f"h{index}", trade_date, f"g{index}", "source file") for index, trade_date in enumerate(dates)]
    )


def _manifest_row(hash_value: str, trade_date: str, group: str, notes: str) -> dict[str, object]:
    return {
        "source_id_hash": hash_value,
        "file_name": f"{hash_value}.txt",
        "detected_date": trade_date,
        "duplicate_group": group,
        "notes": notes,
    }


def _playbook(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "historical_playbook_overlay_state": "HISTORICAL_PLAYBOOK_OVERLAY_AVAILABLE",
            }
            for trade_date in dates
        ]
    )
