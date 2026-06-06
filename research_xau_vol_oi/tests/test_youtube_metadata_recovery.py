import polars as pl

from research_xau_vol_oi.youtube_metadata_recovery import (
    MANUAL_TEMPLATE_COLUMNS,
    build_manual_metadata_entry_template,
    build_timing_audit_after_metadata,
    build_transcript_timezone_audit,
    build_youtube_metadata_fetch_requests,
    generate_metadata_fetch_command_texts,
    normalize_timestamp,
    parse_info_json_metadata,
    transcript_timezone_audit_markdown,
    youtube_metadata_fetch_plan_markdown,
    youtube_metadata_local_discovery_markdown,
)
from research_xau_vol_oi.transcript_timing_evidence import (
    build_transcript_availability_classification,
)
from research_xau_vol_oi.youtube_metadata_recovery import (
    apply_timezone_confidence_to_timing_audit,
)


def test_info_json_publish_time_parsing() -> None:
    metadata = parse_info_json_metadata(
        {
            "id": "abc123XYZ90",
            "webpage_url": "https://www.youtube.com/watch?v=abc123XYZ90",
            "timestamp": "2026-05-14T08:30:00Z",
        }
    )

    assert metadata.video_id == "abc123XYZ90"
    assert metadata.publish_time == "2026-05-14T08:30:00+00:00"
    assert metadata.raw_timezone == "UTC_OFFSET"
    assert metadata.timing_confidence == "HIGH"


def test_info_json_live_start_time_parsing() -> None:
    metadata = parse_info_json_metadata(
        {
            "id": "abc123XYZ90",
            "live_start_time": 1778749200,
            "live_end_time": 1778752800,
        }
    )

    assert metadata.live_start_time.startswith("2026")
    assert metadata.live_end_time.startswith("2026")
    assert metadata.raw_timezone == "UTC"
    assert metadata.timing_confidence == "HIGH"


def test_missing_url_creates_fetch_request() -> None:
    requests = build_youtube_metadata_fetch_requests(
        pl.DataFrame(
            [
                {
                    "clean_transcript_id": "clean_1",
                    "transcript_date": "2026-05-14",
                    "title_hash": "title-a",
                    "discovered_video_id_hash": "",
                    "discovered_video_url_hash": "",
                    "discovered_publish_time": "",
                    "discovered_live_start_time": "",
                    "discovered_live_end_time": "",
                    "_raw_video_url": "",
                    "_video_url": "",
                    "_video_id": "",
                }
            ]
        )
    )

    row = requests.row(0, named=True)

    assert row["missing_video_url"] is True
    assert row["suggested_user_action"] == "PROVIDE_VIDEO_URL"


def test_generated_fetch_commands_use_skip_download() -> None:
    sh_text, ps_text = generate_metadata_fetch_command_texts(
        _discovery_with_url(),
        local_debug=False,
    )

    assert "--skip-download" in sh_text
    assert "--write-info-json" in ps_text
    assert "youtube.com" not in sh_text
    assert "<video_url_for_hash_hash-a>" in ps_text


def test_commands_are_not_executed() -> None:
    sh_text, ps_text = generate_metadata_fetch_command_texts(_discovery_with_url())

    assert "never executes this file automatically" in sh_text
    assert "never executes this file automatically" in ps_text


def test_raw_urls_are_redacted_unless_local_debug() -> None:
    redacted, _ = generate_metadata_fetch_command_texts(_discovery_with_url(), local_debug=False)
    debug, _ = generate_metadata_fetch_command_texts(_discovery_with_url(), local_debug=True)
    markdown = youtube_metadata_local_discovery_markdown(_discovery_with_url())

    assert "youtube.com" not in redacted
    assert "youtube.com" in debug
    assert "youtube.com" not in markdown
    assert "hash-a" in markdown


def test_manual_metadata_template_schema() -> None:
    template = build_manual_metadata_entry_template(_fetch_plan())

    assert template.columns == list(MANUAL_TEMPLATE_COLUMNS)
    assert template.row(0, named=True)["reviewer_confidence"] == "MEDIUM"


def test_timezone_normalization_with_explicit_timezone() -> None:
    normalized = normalize_timestamp(
        "2026-05-14T08:30:00",
        raw_timezone="Asia/Bangkok",
    )

    assert normalized["timezone_confidence"] == "HIGH"
    assert normalized["normalized_bangkok_timestamp"].startswith("2026-05-14T08:30:00")
    assert normalized["normalized_utc_timestamp"].startswith("2026-05-14T01:30:00")


def test_unknown_timezone_does_not_unlock_same_session_classification() -> None:
    timing = build_timing_audit_after_metadata(
        timing_audit=_timing_audit(),
        discovery=pl.DataFrame(),
        manual_candidates={},
    )
    timezone_audit = build_transcript_timezone_audit(timing)
    reclass_timing = apply_timezone_confidence_to_timing_audit(timing, timezone_audit)
    availability = build_transcript_availability_classification(
        timing_audit=reclass_timing,
        remapped_replay=_remapped(),
        playbook_matches=_matches(),
    )

    assert availability.row(0, named=True)["availability_relation"] == "UNKNOWN"
    assert availability.row(0, named=True)["can_use_as_same_session_filter"] is False


def test_reclassification_upgrades_only_high_medium_confidence_metadata() -> None:
    timing = build_timing_audit_after_metadata(
        timing_audit=_two_timing_rows(),
        discovery=_discovery_with_metadata(),
        manual_candidates={},
    )
    timezone_audit = build_transcript_timezone_audit(timing)
    reclass_timing = apply_timezone_confidence_to_timing_audit(timing, timezone_audit)
    availability = build_transcript_availability_classification(
        timing_audit=reclass_timing,
        remapped_replay=_remapped(two=True),
        playbook_matches=_matches(two=True),
    )

    by_id = {row["clean_transcript_id"]: row for row in availability.to_dicts()}

    assert by_id["clean_1"]["availability_relation"] == "DURING_SESSION"
    assert by_id["clean_1"]["can_use_as_same_session_filter"] is True
    assert by_id["clean_2"]["availability_relation"] == "UNKNOWN"
    assert by_id["clean_2"]["can_use_as_same_session_filter"] is False


def test_report_does_not_claim_profitability() -> None:
    markdown = youtube_metadata_fetch_plan_markdown(
        build_youtube_metadata_fetch_requests(_discovery_with_url())
    ).lower()

    assert "profitable" not in markdown
    assert "safe to trade" not in markdown
    assert "live ready" not in markdown


def test_redacted_paths_only() -> None:
    markdown = transcript_timezone_audit_markdown(
        pl.DataFrame(
            [
                {
                    "clean_transcript_id": "clean_1",
                    "raw_timestamp": r"C:\Users\example\secret.txt",
                    "raw_timezone": "",
                    "inferred_timezone": "",
                    "normalized_utc_timestamp": "",
                    "normalized_bangkok_timestamp": "",
                    "normalized_cme_exchange_timestamp": "",
                    "timezone_confidence": "UNKNOWN",
                    "notes": r"C:\Users\example\secret.txt",
                }
            ]
        )
    )

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _discovery_with_url() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": "2026-05-14",
                "title_hash": "title-a",
                "content_hash": "content-a",
                "local_metadata_found": True,
                "discovered_video_id_hash": "id-hash",
                "discovered_video_url_hash": "hash-a",
                "metadata_source": "MANIFEST",
                "discovered_publish_time": "",
                "discovered_live_start_time": "",
                "discovered_live_end_time": "",
                "timing_confidence": "UNKNOWN",
                "redacted_metadata_path": "<REDACTED_PATH>/<METADATA_FILE>.jsonl",
                "notes": "Raw URL suppressed.",
                "_video_url": "",
                "_raw_video_url": "https://www.youtube.com/watch?v=abc123XYZ90",
                "_video_id": "abc123XYZ90",
                "_raw_timezone": "",
            }
        ]
    )


def _fetch_plan() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": "2026-05-14",
                "required_metadata": "video_url|video_id|publish_time|live_start_time|live_end_time",
                "suggested_file_needed": ".info.json",
                "suggested_command_template": "yt-dlp --skip-download --write-info-json <video_url>",
                "where_to_place_file": "configured transcript root",
                "rerun_command": "python -m research_xau_vol_oi.report",
            }
        ]
    )


def _timing_audit() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": "2026-05-14",
                "title_hash": "title-a",
                "content_hash": "content-a",
                "detected_publish_timestamp": "2026-05-14T08:30:00",
                "detected_live_start_timestamp": "",
                "detected_live_end_timestamp": "",
                "detected_transcript_start_timestamp": "",
                "detected_transcript_end_timestamp": "",
                "timing_source": "FILENAME",
                "timing_confidence": "MEDIUM",
                "timing_notes": "filename time without timezone",
            }
        ]
    )


def _two_timing_rows() -> pl.DataFrame:
    rows = _timing_audit().to_dicts()
    rows.append(
        {
            **rows[0],
            "clean_transcript_id": "clean_2",
            "content_hash": "content-b",
            "detected_publish_timestamp": "",
            "timing_confidence": "UNKNOWN",
        }
    )
    return pl.DataFrame(rows)


def _discovery_with_metadata() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "discovered_publish_time": "2026-05-14T08:30:00+07:00",
                "discovered_live_start_time": "",
                "discovered_live_end_time": "",
                "metadata_source": "INFO_JSON",
                "timing_confidence": "HIGH",
                "notes": "explicit timezone",
            },
            {
                "clean_transcript_id": "clean_2",
                "discovered_publish_time": "2026-05-14T08:30:00",
                "discovered_live_start_time": "",
                "discovered_live_end_time": "",
                "metadata_source": "INFO_JSON",
                "timing_confidence": "LOW",
                "notes": "missing timezone",
            },
        ]
    )


def _remapped(*, two: bool = False) -> pl.DataFrame:
    rows = [
        {
            "original_replay_date": "2026-05-14",
            "resolved_market_session_date": "2026-05-14",
        }
    ]
    if two:
        rows.append(
            {
                "original_replay_date": "2026-05-14",
                "resolved_market_session_date": "2026-05-14",
            }
        )
    return pl.DataFrame(rows)


def _matches(*, two: bool = False) -> pl.DataFrame:
    rows = [
        {
            "clean_transcript_id": "clean_1",
            "replay_date": "2026-05-14",
            "usable_as_context": True,
            "usable_as_filter": True,
            "usable_as_market_map": True,
            "usable_as_trade_rule": False,
        }
    ]
    if two:
        rows.append(
            {
                **rows[0],
                "clean_transcript_id": "clean_2",
            }
        )
    return pl.DataFrame(rows)
