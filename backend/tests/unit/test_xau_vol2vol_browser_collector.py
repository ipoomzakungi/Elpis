from __future__ import annotations

import json
from datetime import date

import pytest

from src.xau_vol2vol_history_walkforward.browser_collector import (
    _catalog_sessions,
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


def test_atomic_write_replaces_temporary_file(tmp_path) -> None:
    path = tmp_path / "raw.json"

    atomic_write_text(path, '{"sessionDate":"2026-07-07"}')

    assert json.loads(path.read_text(encoding="utf-8"))["sessionDate"] == "2026-07-07"
    assert not (tmp_path / ".raw.json.tmp").exists()
