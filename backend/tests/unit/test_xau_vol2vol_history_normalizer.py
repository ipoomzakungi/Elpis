from __future__ import annotations

from datetime import date
from pathlib import Path

from src.models.xau_vol2vol_history_walkforward import XauHistorySourceMode
from src.xau_vol2vol_history_walkforward import history_client
from src.xau_vol2vol_history_walkforward.history_normalizer import normalize_payload


def test_normalizer_preserves_missing_values_as_none() -> None:
    payload = {
        "snapshots": [
            {
                "id": "one",
                "kind": "intraday",
                "observedAt": "2026-07-08T10:00:00+00:00",
                "sessionDate": "2026-07-08",
                "series": "G2WN6",
                "rows": [{"strike": 4100, "call": "", "put": None, "total": ""}],
            }
        ]
    }

    rows, ranges, warnings = normalize_payload(payload)

    assert not warnings
    assert rows[0].call is None
    assert rows[0].put is None
    assert rows[0].total is None
    assert ranges[0].future_open is None


def test_normalizer_parses_multiple_key_shapes() -> None:
    payload = {
        "data": [
            {
                "createdAt": "2026-07-08T10:00:00+00:00",
                "session_date": "2026-07-08",
                "contract": "OGQ6",
                "title": "Monthly Open Interest",
                "rows": [
                    {
                        "Strike": "4100",
                        "Call": "10",
                        "Put": "5",
                        "Total": "15",
                        "volSettle": "25.5",
                    }
                ],
            }
        ]
    }

    rows, _, _ = normalize_payload(payload)

    assert rows[0].session_date == date(2026, 7, 8)
    assert rows[0].snapshot_kind == "monthly_open_interest"
    assert rows[0].series == "OGQ6"
    assert rows[0].strike == 4100
    assert rows[0].call == 10
    assert rows[0].put == 5
    assert rows[0].total == 15
    assert rows[0].vol_settle == 25.5


def test_http_history_client_uses_configured_template_without_real_network(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fetched_urls: list[str] = []

    def fake_fetch_json(url: str):
        fetched_urls.append(url)
        return {"snapshots": []}

    monkeypatch.setattr(history_client, "_fetch_json", fake_fetch_json)
    monkeypatch.setattr(history_client.time, "sleep", lambda _: None)

    result = history_client.load_history_payloads(
        source_mode=XauHistorySourceMode.HTTP_ENDPOINT,
        session_date_from=date(2026, 6, 1),
        session_date_to=date(2026, 6, 1),
        endpoint_template="https://example.test/api/monthly-oi?targetMonth={target_month}",
        cache_root=tmp_path,
        rate_limit_seconds=0,
    )

    assert len(result.payloads) == 1
    assert fetched_urls == ["https://example.test/api/monthly-oi?targetMonth=2026-06"]
