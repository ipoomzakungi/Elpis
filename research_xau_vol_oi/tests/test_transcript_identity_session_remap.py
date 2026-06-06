import polars as pl

from research_xau_vol_oi.transcript_identity_session_remap import (
    build_clean_transcript_set,
    build_current_week_replay_after_approved_remap,
    build_same_day_guru_reinterpretation_after_identity,
    build_session_remap_suggestions,
    build_transcript_identity_audit,
    build_transcript_session_availability,
    current_week_replay_after_approved_remap_markdown,
    transcript_identity_audit_markdown,
)


def test_same_date_with_different_content_is_classified_same_day_different_live() -> None:
    identity = build_transcript_identity_audit(
        pl.DataFrame(
            [
                _manifest_row("h1", "2026-05-14", "content-a", "source file"),
                _manifest_row("h2", "2026-05-14", "content-b", "source file"),
            ]
        )
    )

    classes = set(identity.get_column("identity_class").to_list())

    assert classes == {"SAME_DAY_DIFFERENT_LIVE"}
    assert not any(identity.get_column("duplicate_safe_to_collapse").to_list())


def test_same_content_across_extracted_file_and_zip_entry_is_collapsible() -> None:
    identity = build_transcript_identity_audit(
        pl.DataFrame(
            [
                _manifest_row("h1", "2026-05-14", "content-a", "source file"),
                _manifest_row("h2", "2026-05-14", "content-a", "zip entry; not extracted"),
            ]
        )
    )
    clean = build_clean_transcript_set(identity)
    zip_row = identity.filter(pl.col("file_type") == "ZIP_ENTRY").row(0, named=True)

    assert zip_row["identity_class"] == "ZIP_ENTRY_DUPLICATE"
    assert zip_row["duplicate_safe_to_collapse"] is True
    assert _included_clean_count(clean) == 1


def test_txt_srt_same_video_is_not_treated_as_two_independent_signals() -> None:
    identity = build_transcript_identity_audit(
        pl.DataFrame(
            [
                _manifest_row(
                    "h1",
                    "2026-05-14",
                    "content-txt",
                    "source file",
                    file_name="video.txt",
                    video_id="abc123",
                ),
                _manifest_row(
                    "h2",
                    "2026-05-14",
                    "content-srt",
                    "source file",
                    file_name="video.srt",
                    video_id="abc123",
                ),
            ]
        )
    )
    clean = build_clean_transcript_set(identity)

    assert set(identity.get_column("identity_class").to_list()) == {
        "SAME_VIDEO_MULTIPLE_FORMATS",
        "SIDECAR_FILE",
    }
    assert _included_clean_count(clean) == 1


def test_clean_transcript_set_keeps_multiple_same_day_unique_lives() -> None:
    clean = build_clean_transcript_set(
        build_transcript_identity_audit(
            pl.DataFrame(
                [
                    _manifest_row("h1", "2026-05-14", "content-a", "source file"),
                    _manifest_row("h2", "2026-05-14", "content-b", "source file"),
                ]
            )
        )
    )

    assert _included_clean_count(clean) == 2


def test_saturday_transcript_is_not_used_as_friday_predictive_signal() -> None:
    availability = build_transcript_session_availability(
        clean_transcript_set=_clean_set(["2026-05-23"]),
        replay=_replay(["2026-05-22"]),
    )

    row = availability.row(0, named=True)

    assert row["availability_relation"] == "WEEKEND_RECAP"
    assert row["can_use_as_same_session_input"] is False


def test_saturday_transcript_can_be_next_session_prep_or_weekend_recap() -> None:
    availability = build_transcript_session_availability(
        clean_transcript_set=_clean_set(["2026-05-23"]),
        replay=_replay(["2026-05-22", "2026-05-25"]),
    )

    relations = {
        row["replay_trade_date"]: row["availability_relation"]
        for row in availability.to_dicts()
    }

    assert relations["2026-05-22"] == "WEEKEND_RECAP"
    assert relations["2026-05-25"] == "NEXT_SESSION_PREP"


def test_remap_suggestions_are_pending_by_default() -> None:
    suggestions = build_session_remap_suggestions(
        session_calendar=_calendar(["2026-05-16"], ["2026-05-15"])
    )

    row = suggestions.row(0, named=True)

    assert row["approval_status"] == "PENDING"


def test_remap_is_not_applied_unless_approved() -> None:
    suggestions = build_session_remap_suggestions(
        session_calendar=_calendar(["2026-05-16"], ["2026-05-15"])
    )
    after = build_current_week_replay_after_approved_remap(
        current_week_resolved=_resolved(["2026-05-16"]),
        replay=_replay(["2026-05-16"]),
        suggestions=suggestions,
        transcript_availability=pl.DataFrame(),
        playbook_replay=_playbook(["2026-05-16"]),
    )

    row = after.row(0, named=True)

    assert row["market_session_date"] == "2026-05-16"
    assert row["approval_status"] == "REMAP_PENDING_APPROVAL"
    assert row["remap_applied"] is False


def test_approved_remap_affects_market_session_date_but_not_transcript_availability() -> None:
    suggestions = build_session_remap_suggestions(
        session_calendar=_calendar(["2026-05-16"], ["2026-05-15"]),
        decisions=pl.DataFrame(
            [
                {
                    "original_replay_date": "2026-05-16",
                    "suggested_market_session_date": "2026-05-15",
                    "approval_status": "APPROVED",
                    "reviewer_notes": "reviewed",
                }
            ]
        ),
    )
    availability = pl.DataFrame(
        [
            {
                "replay_trade_date": "2026-05-16",
                "availability_relation": "WEEKEND_RECAP",
                "can_use_as_same_session_input": False,
            }
        ]
    )
    after = build_current_week_replay_after_approved_remap(
        current_week_resolved=_resolved(["2026-05-16"]),
        replay=_replay(["2026-05-16"]),
        suggestions=suggestions,
        transcript_availability=availability,
        playbook_replay=_playbook(["2026-05-16"]),
    )

    row = after.row(0, named=True)

    assert row["market_session_date"] == "2026-05-15"
    assert row["approval_status"] == "REMAP_APPROVED"
    assert row["transcript_state"] == "POST_EVENT_TRANSCRIPT"


def test_same_day_context_filter_are_distinct_from_trade_rule_rows() -> None:
    reinterpretation = build_same_day_guru_reinterpretation_after_identity(
        clean_transcript_set=_clean_set(["2026-05-14"]),
        transcript_availability=pl.DataFrame(),
        readiness=pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-14",
                    "context_rows": 2,
                    "filter_rows": 1,
                    "market_map_rows": 1,
                    "trade_rule_rows": 0,
                    "post_event_rows": 0,
                }
            ]
        ),
        replay=_replay(["2026-05-14"]),
    )

    row = reinterpretation.row(0, named=True)

    assert row["context_rows"] == 2
    assert row["filter_rows"] == 1
    assert row["market_map_rows"] == 1
    assert row["trade_rule_rows"] == 0


def test_reports_use_redacted_paths_only() -> None:
    identity = build_transcript_identity_audit(
        pl.DataFrame(
            [
                _manifest_row(
                    "h1",
                    "2026-05-14",
                    "content-a",
                    r"C:\Users\example\secret\file.txt",
                )
            ]
        )
    )

    markdown = transcript_identity_audit_markdown(identity)

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def test_report_does_not_claim_profitability() -> None:
    markdown = current_week_replay_after_approved_remap_markdown(
        build_current_week_replay_after_approved_remap(
            current_week_resolved=_resolved(["2026-05-14"]),
            replay=_replay(["2026-05-14"]),
            suggestions=pl.DataFrame(),
            transcript_availability=pl.DataFrame(),
            playbook_replay=_playbook(["2026-05-14"]),
        ),
        final_recommendation="CLEAN_TRANSCRIPT_SET_READY",
    ).lower()

    assert "profitable" not in markdown
    assert "safe to trade" not in markdown
    assert "live ready" not in markdown


def _manifest_row(
    hash_value: str,
    trade_date: str,
    content_group: str,
    notes: str,
    *,
    file_name: str | None = None,
    video_id: str = "",
) -> dict[str, object]:
    return {
        "source_id_hash": hash_value,
        "file_name": file_name or f"{hash_value}.txt",
        "detected_date": trade_date,
        "duplicate_group": content_group,
        "detected_title": f"title {hash_value}",
        "detected_video_id": video_id,
        "notes": notes,
        "path_redacted": True,
    }


def _clean_set(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": f"clean_{index}",
                "transcript_record_ids_included": f"tr_{index}",
                "selected_record_id": f"tr_{index}",
                "transcript_date": trade_date,
                "transcript_time": "",
                "title_hash": f"title_{index}",
                "content_hash": f"content_{index}",
                "identity_class": "UNIQUE_TRANSCRIPT",
                "included_in_clean_set": True,
                "collapse_reason": "",
                "keep_reason": "Unique transcript retained.",
            }
            for index, trade_date in enumerate(dates)
        ]
    )


def _calendar(original_dates: list[str], target_dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "replay_trade_date": original,
                "day_of_week": "Saturday",
                "likely_calendar_date_issue": True,
                "likely_session_date": target,
                "recommended_session_mapping": f"REMAP_TO_{target}",
                "reason_plain_english": f"{original} should be reviewed against {target}.",
            }
            for original, target in zip(original_dates, target_dates, strict=False)
        ]
    )


def _replay(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame([{"trade_date": trade_date} for trade_date in dates])


def _resolved(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "original_replay_date": trade_date,
                "resolved_session_date": trade_date,
                "data_state": "COMPLETE_FOR_PILOT",
                "guru_state": "HISTORICAL_PLAYBOOK_OVERLAY",
            }
            for trade_date in dates
        ]
    )


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


def _included_clean_count(frame: pl.DataFrame) -> int:
    return sum(1 for value in frame.get_column("included_in_clean_set").to_list() if value)
