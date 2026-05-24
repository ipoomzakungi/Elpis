from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.daily_forward_data_gate import (
    OhlcSource,
    PendingJournal,
    build_calendar_gate_frame,
    build_speckit_prereq_warning,
    coverage_row_for_journal,
    discover_pending_forward_journals,
    expected_market_session_date,
    is_weekend,
    proxy_only_label,
    run_daily_forward_data_gate,
    yahoo_symbol_allowed,
    _redacted_path,
)


def test_weekend_date_does_not_create_new_journal_rows() -> None:
    latest_replay = {
        "latest_available_replay_date": "2026-05-22",
        "latest_resolved_market_session_date": "2026-05-22",
        "is_weekend_artifact": False,
    }

    gate = build_calendar_gate_frame(
        today=date(2026, 5, 24),
        latest_replay=latest_replay,
        can_resolve_pending=False,
    )

    row = gate.row(0, named=True)
    assert is_weekend(date(2026, 5, 24)) is True
    assert expected_market_session_date(date(2026, 5, 24)) == date(2026, 5, 22)
    assert row["should_create_new_journal_rows"] is False
    assert "weekend" in row["reason_plain_english"].lower()


def test_weekend_artifact_is_not_treated_as_signal() -> None:
    latest_replay = {
        "latest_available_replay_date": "2026-05-23",
        "latest_resolved_market_session_date": "2026-05-22",
        "is_weekend_artifact": True,
    }

    gate = build_calendar_gate_frame(
        today=date(2026, 5, 24),
        latest_replay=latest_replay,
        can_resolve_pending=False,
    )

    assert gate.get_column("is_weekend_artifact").to_list() == [True, True]
    assert all(not value for value in gate.get_column("should_create_new_journal_rows").to_list())
    assert "weekend artifact" in gate.row(0, named=True)["reason_plain_english"].lower()


def test_daily_ohlc_cannot_resolve_intraday_windows() -> None:
    journal = _journal()
    daily = OhlcSource(
        provider_name="Yahoo Finance",
        symbol="GC=F",
        timeframe="1d",
        path=None,
        latest_timestamp=datetime(2026, 5, 24, tzinfo=UTC),
        date_range_start=datetime(2026, 5, 23, tzinfo=UTC),
        date_range_end=datetime(2026, 5, 24, tzinfo=UTC),
        rows=2,
        granularity="DAILY",
        current_status="AVAILABLE",
        usable_for=("DAILY_APPROX_OUTCOME",),
        recommended_fix="test",
        proxy_label="PROXY_ONLY",
    )

    row = coverage_row_for_journal(
        journal,
        [daily],
        today=date(2026, 5, 24),
        daily_approx_allowed=True,
    )

    assert row["coverage_30m"] is False
    assert row["coverage_1h"] is False
    assert row["coverage_4h"] is False
    assert row["coverage_session_close"] is True
    assert row["coverage_next_day"] is True
    assert row["can_resolve_full_outcome"] is False


def test_intraday_ohlc_can_resolve_partial_window_set() -> None:
    journal = _journal()
    intraday = OhlcSource(
        provider_name="Yahoo Finance",
        symbol="GC=F",
        timeframe="1m",
        path=None,
        latest_timestamp=journal.observation_timestamp + timedelta(minutes=45),
        date_range_start=journal.observation_timestamp,
        date_range_end=journal.observation_timestamp + timedelta(minutes=45),
        rows=46,
        granularity="INTRADAY",
        current_status="AVAILABLE",
        usable_for=("INTRADAY_OUTCOME",),
        recommended_fix="test",
        proxy_label="PROXY_ONLY",
    )

    row = coverage_row_for_journal(journal, [intraday], today=date(2026, 5, 24))

    assert row["coverage_30m"] is True
    assert row["coverage_1h"] is False
    assert row["can_resolve_any_window"] is True
    assert row["can_resolve_full_outcome"] is False


def test_missing_ohlc_leaves_outcome_pending() -> None:
    row = coverage_row_for_journal(_journal(), [], today=date(2026, 5, 24))

    assert row["can_resolve_any_window"] is False
    assert row["can_resolve_full_outcome"] is False
    assert "No approved intraday OHLC source" in row["missing_coverage_reason"]


def test_gld_whitelist_behavior_is_explicit(tmp_path: Path) -> None:
    provider = tmp_path / "backend" / "src" / "providers"
    provider.mkdir(parents=True)
    (provider / "yahoo_finance_provider.py").write_text(
        'ProviderSymbol(symbol="GLD", notes=["PROXY_ONLY"])\n',
        encoding="utf-8",
    )

    assert yahoo_symbol_allowed("GLD", repo_root=tmp_path) is True
    assert proxy_only_label("GLD") == "PROXY_ONLY"


def test_proxy_only_labels_are_preserved() -> None:
    assert proxy_only_label("GC=F") == "PROXY_ONLY"
    assert proxy_only_label("GLD") == "PROXY_ONLY"
    assert proxy_only_label("XAU/USD") == ""


def test_branch_naming_prereq_warning_is_non_blocking() -> None:
    warning = build_speckit_prereq_warning("codex/xau-vol-oi-research-pipeline")

    assert warning.status == "NON_BLOCKING_BRANCH_NAMING_WARNING"
    assert warning.blocking is False


def test_daily_note_is_written_under_outputs_daily_forward_notes(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)

    result = run_daily_forward_data_gate(
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
        current_date=date(2026, 5, 24),
        branch_name="codex/xau-vol-oi-research-pipeline",
    )

    assert result.daily_note_path.parent == tmp_path / "outputs" / "daily_forward_notes"
    assert result.daily_note_path.name == "frozen_rule_journal_20260524.md"


def test_reports_do_not_claim_profitability(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)

    result = run_daily_forward_data_gate(
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
        current_date=date(2026, 5, 24),
        branch_name="codex/xau-vol-oi-research-pipeline",
    )
    report_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            tmp_path / "outputs" / "daily_forward_data_gate.md",
            tmp_path / "outputs" / "outcome_coverage_check.md",
            tmp_path / "outputs" / "forward_data_provider_audit.md",
            tmp_path / "outputs" / "daily_forward_run_decision.md",
            result.daily_note_path,
        ]
    ).lower()

    assert "profitable" not in report_text
    assert "safe to trade" not in report_text


def test_frozen_rules_are_not_modified(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    frozen_rules = tmp_path / "outputs" / "guru_rule_definitions.yaml"
    frozen_rules.write_text("OPEN_DISTANCE_FILTER: frozen\n", encoding="utf-8")
    before = frozen_rules.read_text(encoding="utf-8")

    result = run_daily_forward_data_gate(
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
        current_date=date(2026, 5, 24),
        branch_name="codex/xau-vol-oi-research-pipeline",
    )

    assert frozen_rules.read_text(encoding="utf-8") == before
    assert "Frozen thresholds, rules, scores" in result.daily_note_path.read_text(
        encoding="utf-8"
    )


def test_redacted_paths_only() -> None:
    redacted = _redacted_path(Path("C:/Users/example/secret/gc=f_1m_ohlcv.parquet"))

    assert redacted.startswith("<REDACTED_PATH>/")
    assert "C:" not in redacted
    assert "Users" not in redacted
    assert "secret" not in redacted


def test_pending_journals_resolve_weekend_session_date(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)

    replay_rows = [
        {
            "original_replay_date": "2026-05-23",
            "resolved_market_session_date": "2026-05-22",
        }
    ]
    journals = discover_pending_forward_journals(tmp_path, replay_rows)

    assert journals[0].trade_date == "2026-05-23"
    assert journals[0].session_date == "2026-05-22"


def _journal() -> PendingJournal:
    observation = datetime(2026, 5, 23, 9, 24, tzinfo=UTC)
    return PendingJournal(
        journal_id="xau_forward_journal_test",
        observation_timestamp=observation,
        trade_date="2026-05-23",
        session_date="2026-05-22",
        outcome_windows=("30m", "1h", "4h", "session_close", "next_day"),
    )


def _write_minimal_repo(root: Path) -> None:
    output = root / "outputs"
    output.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "original_replay_date": "2026-05-23",
                "resolved_market_session_date": "2026-05-22",
                "remap_status": "APPLIED_MARKET_SESSION_ONLY",
            }
        ]
    ).write_csv(output / "current_week_replay_after_market_session_remap.csv")
    provider = root / "backend" / "src" / "providers"
    provider.mkdir(parents=True)
    (provider / "yahoo_finance_provider.py").write_text(
        'ProviderSymbol(symbol="GLD", notes=["PROXY_ONLY"])\n',
        encoding="utf-8",
    )
    journal_dir = (
        root
        / "backend"
        / "data"
        / "reports"
        / "xau_forward_journal"
        / "xau_forward_journal_data_20260523_test"
    )
    journal_dir.mkdir(parents=True)
    (journal_dir / "metadata.json").write_text(
        (
            '{"journal_id":"xau_forward_journal_data_20260523_test",'
            '"data_date":"2026-05-23",'
            '"snapshot_time":"2026-05-23T09:24:12Z"}'
        ),
        encoding="utf-8",
    )
    (journal_dir / "outcomes.json").write_text(
        '[{"window":"30m","status":"pending"}]',
        encoding="utf-8",
    )
