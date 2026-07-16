from __future__ import annotations

import json
from datetime import date

import pytest

from src.xau_vol2vol_history_walkforward.browser_collector import (
    _catalog_sessions,
    _collection_history,
    _existing_catalog_sessions,
    _merge_catalog_sessions,
    _valid_existing,
)
from src.xau_vol2vol_history_walkforward.collection_manifest import (
    Vol2VolCollectionStatus,
    atomic_write_text,
    inspect_payload,
)


def test_catalog_sessions_keeps_only_sanitized_advertised_fields() -> None:
    sessions = _catalog_sessions(
        {
            "availableSessions": [
                {
                    "sessionDate": "2026-07-07",
                    "seriesLabel": "G2WN6",
                    "snapshotCount": 548,
                    "secretField": "must-not-copy",
                }
            ]
        }
    )

    assert sessions == [
        {
            "sessionDate": "2026-07-07",
            "displayDate": None,
            "seriesLabel": "G2WN6",
            "label": None,
            "snapshotCount": 548,
            "latestAt": None,
        }
    ]


def test_inspect_payload_rejects_silent_date_substitution() -> None:
    body = json.dumps({"sessionDate": "2026-07-10", "snapshots": []})

    _, row = inspect_payload(
        requested_session_date=date(2026, 5, 30),
        body=body,
        output_path=None,
    )

    assert row.status == Vol2VolCollectionStatus.REJECTED_DATE_MISMATCH
    assert row.returned_session_date == date(2026, 7, 10)
    assert row.output_path is None


@pytest.mark.parametrize("forbidden_key", ["cookies", "headers", "cf_clearance", "csrfToken"])
def test_inspect_payload_rejects_browser_session_material(forbidden_key: str) -> None:
    body = json.dumps(
        {
            "sessionDate": "2026-07-07",
            "snapshots": [],
            forbidden_key: "redacted",
        }
    )

    with pytest.raises(ValueError, match="forbidden browser session material"):
        inspect_payload(
            requested_session_date=date(2026, 7, 7),
            body=body,
            output_path=None,
        )


def test_valid_existing_matching_file_is_skipped(tmp_path) -> None:
    path = tmp_path / "daily" / "2026-07-07" / "raw.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "sessionDate": "2026-07-07",
                "snapshots": [
                    {
                        "observedAt": "2026-07-07T01:00:00Z",
                        "series": "G2WN6",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    row = _valid_existing(path, date(2026, 7, 7))

    assert row is not None
    assert row.status == Vol2VolCollectionStatus.SKIPPED_EXISTING
    assert row.snapshot_count == 1


def test_valid_existing_retries_incomplete_stored_session(tmp_path) -> None:
    path = tmp_path / "daily" / "2026-07-15" / "raw.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"sessionDate": "2026-07-15", "snapshots": [{"id": 1}]}),
        encoding="utf-8",
    )
    path.with_name("collection_meta.json").write_text(
        json.dumps({"complete": False}),
        encoding="utf-8",
    )

    assert _valid_existing(path, date(2026, 7, 15)) is None


def test_merge_catalog_sessions_retains_history_and_refreshes_current() -> None:
    merged = _merge_catalog_sessions(
        [
            {"sessionDate": "2026-07-14", "snapshotCount": 500},
            {"sessionDate": "2026-07-15", "snapshotCount": 20},
        ],
        [{"sessionDate": "2026-07-15", "snapshotCount": 84}],
    )

    assert merged == [
        {"sessionDate": "2026-07-14", "snapshotCount": 500},
        {"sessionDate": "2026-07-15", "snapshotCount": 84},
    ]


def test_existing_catalog_recovers_sessions_from_latest_daily_raw(tmp_path) -> None:
    catalog = tmp_path / "catalog" / "available_sessions.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps({"availableSessions": [{"sessionDate": "2026-07-15"}]}),
        encoding="utf-8",
    )
    raw = tmp_path / "daily" / "2026-07-13" / "raw.json"
    raw.parent.mkdir(parents=True)
    raw.write_text(
        json.dumps(
            {
                "sessionDate": "2026-07-13",
                "availableSessions": [
                    {"sessionDate": "2026-07-13", "snapshotCount": 500},
                    {"sessionDate": "2026-07-14", "snapshotCount": 100},
                ],
                "snapshots": [],
            }
        ),
        encoding="utf-8",
    )
    partial = tmp_path / "daily" / "2026-07-15" / "raw.json"
    partial.parent.mkdir(parents=True)
    partial.write_text(
        json.dumps(
            {
                "sessionDate": "2026-07-15",
                "availableSessions": [
                    {"sessionDate": "2026-07-15", "snapshotCount": 88}
                ],
                "snapshots": [],
            }
        ),
        encoding="utf-8",
    )

    retained = _existing_catalog_sessions(catalog, daily_root=tmp_path / "daily")

    assert [item["sessionDate"] for item in retained] == [
        "2026-07-13",
        "2026-07-14",
        "2026-07-15",
    ]


def test_atomic_write_replaces_temporary_file(tmp_path) -> None:
    path = tmp_path / "raw.json"

    atomic_write_text(path, '{"sessionDate":"2026-07-07"}')

    assert json.loads(path.read_text(encoding="utf-8"))["sessionDate"] == "2026-07-07"
    assert not (tmp_path / ".raw.json.tmp").exists()


def test_collection_history_retains_partial_hash_during_completion(tmp_path) -> None:
    metadata = tmp_path / "collection_meta.json"
    metadata.write_text(
        json.dumps(
            {
                "sha256": "partial-hash",
                "fetched_at": "2026-07-15T07:00:00+07:00",
                "snapshot_count": 88,
                "complete": False,
            }
        ),
        encoding="utf-8",
    )

    history = _collection_history(
        metadata,
        sha256="completed-hash",
        fetched_at="2026-07-16T06:00:00+07:00",
        snapshot_count=548,
        complete=True,
    )

    assert [item["sha256"] for item in history] == [
        "partial-hash",
        "completed-hash",
    ]
    assert history[0]["complete"] is False
    assert history[1]["complete"] is True
