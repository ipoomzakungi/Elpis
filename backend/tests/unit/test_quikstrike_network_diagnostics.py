import json

from src.quikstrike.network_diagnostics import (
    _sanitize_page_snapshot,
    analyze_network_diagnostics,
    build_network_diagnostics_report,
)


def test_network_diagnostics_redacts_full_locations_and_query_values():
    snapshot = {
        "title": "QuikStrike Gold",
        "location": (
            "https://cmegroup-sso.quikstrike.net/User/QuikStrikeView.aspx"
            "?mode=private-mode&sessionToken=secret-session"
        ),
        "resources": [
            {
                "name": (
                    "https://cmegroup-sso.quikstrike.net/User/OpenInterestData.ashx"
                    "?pid=40&token=secret-token&mode=matrix"
                ),
                "initiatorType": "xmlhttprequest",
                "responseStatus": 200,
                "duration": 12.3456,
                "transferSize": 2048,
                "encodedBodySize": 1024,
                "decodedBodySize": 4096,
            }
        ],
    }

    sanitized = _sanitize_page_snapshot(snapshot, context_index=0, page_index=0)
    serialized = json.dumps(sanitized)

    assert "https://" not in serialized
    assert "private-mode" not in serialized
    assert "secret-session" not in serialized
    assert "secret-token" not in serialized
    assert sanitized["page_location"]["query_keys"] == ["mode"]
    assert sanitized["page_location"]["redacted_query_key_count"] == 1
    assert sanitized["resources"][0]["query_keys"] == ["mode", "pid"]
    assert sanitized["resources"][0]["redacted_query_key_count"] == 1
    assert sanitized["resources"][0]["api_candidate"] is True


def test_network_diagnostics_analysis_marks_xhr_as_unproven_api_candidate():
    snapshots = [
        {
            "phase": "after_matrix_capture",
            "status": "completed",
            "pages": [
                {
                    "resources": [
                        {
                            "host": "cmegroup-sso.quikstrike.net",
                            "path": "/User/OpenInterestData.ashx",
                            "initiator_type": "xmlhttprequest",
                            "api_candidate": True,
                            "document_like": False,
                        }
                    ]
                }
            ],
        }
    ]

    analysis = analyze_network_diagnostics(snapshots)

    assert analysis["xhr_fetch_count"] == 1
    assert analysis["api_candidate_count"] == 1
    assert "unproven" in analysis["api_only_assessment"]


def test_network_diagnostics_report_records_sanitization_policy():
    report = build_network_diagnostics_report([], analyze=True)

    policy = report["sanitization_policy"]
    assert policy["stores_headers"] is False
    assert policy["stores_cookies"] is False
    assert policy["stores_request_bodies"] is False
    assert policy["stores_response_bodies"] is False
    assert policy["stores_full_locations"] is False
    assert "analysis" in report
