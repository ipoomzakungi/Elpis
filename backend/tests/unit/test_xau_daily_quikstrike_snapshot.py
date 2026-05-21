from datetime import UTC, datetime

from scripts.xau_daily_quikstrike_snapshot import _resolve_data_date


def test_cme_bangkok_noon_policy_uses_previous_day_before_noon():
    data_date = _resolve_data_date(
        explicit_data_date=None,
        policy="cme-bangkok-noon",
        capture_time=datetime(2026, 5, 21, 1, 0, tzinfo=UTC),
    )

    assert data_date.isoformat() == "2026-05-20"


def test_cme_bangkok_noon_policy_uses_same_day_after_noon():
    data_date = _resolve_data_date(
        explicit_data_date=None,
        policy="cme-bangkok-noon",
        capture_time=datetime(2026, 5, 21, 6, 0, tzinfo=UTC),
    )

    assert data_date.isoformat() == "2026-05-21"


def test_explicit_data_date_overrides_policy():
    data_date = _resolve_data_date(
        explicit_data_date="2026-05-19",
        policy="capture-date",
        capture_time=datetime(2026, 5, 21, 6, 0, tzinfo=UTC),
    )

    assert data_date.isoformat() == "2026-05-19"
