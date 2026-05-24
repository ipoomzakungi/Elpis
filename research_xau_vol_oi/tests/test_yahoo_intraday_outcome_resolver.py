from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.daily_forward_data_gate import (
    build_calendar_gate_frame,
    build_run_decision_frame,
)
from research_xau_vol_oi.yahoo_intraday_outcome_resolver import (
    LocalOhlcSource,
    YahooIntradayConfig,
    build_forward_outcome_preview,
    build_intraday_resample_coverage,
    build_partial_outcome_resolution,
    build_yahoo_intraday_fetch_plan,
    resample_ohlc,
    run_yahoo_intraday_outcome_resolver,
)


def test_yfinance_interval_plan_includes_intraday_intervals(tmp_path: Path) -> None:
    plan = build_yahoo_intraday_fetch_plan(
        repo_root=tmp_path,
        output_dir=tmp_path / "outputs",
        coverage=_coverage_frame(all_covered=False),
        provider_audit=pl.DataFrame(),
        config=YahooIntradayConfig(),
        current_time=datetime(2026, 5, 24, 10, 47, tzinfo=UTC),
    )

    gc_intervals = set(
        plan.filter(pl.col("symbol") == "GC=F").get_column("interval").to_list()
    )

    assert {"1m", "30m", "60m", "1h"}.issubset(gc_intervals)


def test_4h_is_resampled_not_a_direct_required_fetch(tmp_path: Path) -> None:
    plan = build_yahoo_intraday_fetch_plan(
        repo_root=tmp_path,
        output_dir=tmp_path / "outputs",
        coverage=_coverage_frame(all_covered=False),
        provider_audit=pl.DataFrame(),
        config=YahooIntradayConfig(),
        current_time=datetime(2026, 5, 24, 10, 47, tzinfo=UTC),
    )

    row = plan.filter((pl.col("symbol") == "GC=F") & (pl.col("interval") == "4h")).row(
        0,
        named=True,
    )

    assert row["can_fetch_directly"] is False
    assert "RESAMPLE_FROM_INTRADAY" in row["notes"]


def test_30m_resampling_from_1m_works() -> None:
    frame = _minute_frame(datetime(2026, 5, 20, tzinfo=UTC), 61)

    resampled = resample_ohlc(frame, "30m")

    first = resampled.row(0, named=True)
    assert resampled.height == 3
    assert first["open"] == 100.0
    assert first["high"] == 130.0
    assert first["low"] == 99.0
    assert first["close"] == 128.5


def test_1h_resampling_from_1m_works() -> None:
    frame = _minute_frame(datetime(2026, 5, 20, tzinfo=UTC), 121)

    resampled = resample_ohlc(frame, "1h")

    first = resampled.row(0, named=True)
    assert resampled.height == 3
    assert first["open"] == 100.0
    assert first["high"] == 160.0
    assert first["close"] == 158.5


def test_4h_resampling_from_1m_or_1h_works(tmp_path: Path) -> None:
    one_minute = LocalOhlcSource(
        symbol="GC=F",
        interval="1m",
        path=tmp_path / "gc=f_1m_ohlcv.parquet",
        frame=_minute_frame(datetime(2026, 5, 20, tzinfo=UTC), 241),
        quality="INTRADAY_DIRECT",
    )
    one_hour = LocalOhlcSource(
        symbol="GC=F",
        interval="1h",
        path=tmp_path / "gc=f_1h_ohlcv.parquet",
        frame=_hour_frame(datetime(2026, 5, 20, tzinfo=UTC), 5),
        quality="INTRADAY_DIRECT",
    )

    coverage, _ = build_intraday_resample_coverage([one_minute, one_hour])

    rows = coverage.filter(pl.col("target_interval") == "4h").to_dicts()
    qualities = {row["source_interval"]: row["quality"] for row in rows}
    assert qualities["1m"] == "EXACT_FROM_1M"
    assert qualities["1h"] == "RESAMPLED_FROM_1H"


def test_partial_resolver_resolves_covered_rows_and_leaves_uncovered_pending(
    tmp_path: Path,
) -> None:
    coverage = _coverage_frame(all_covered=True).vstack(_coverage_frame(all_covered=False))
    source = LocalOhlcSource(
        symbol="GC=F",
        interval="1m",
        path=tmp_path / "gc=f_1m_ohlcv.parquet",
        frame=_minute_frame(datetime(2026, 5, 20, tzinfo=UTC), 1500),
        quality="EXACT_FROM_1M",
    )

    resolution = build_partial_outcome_resolution(coverage)
    preview = build_forward_outcome_preview(coverage=coverage, sources=[source])

    assert resolution.row(0, named=True)["can_resolve_full"] is True
    assert resolution.row(1, named=True)["can_resolve_full"] is False
    assert preview.filter(pl.col("resolution_action") == "preview_resolve").height == 5
    assert preview.filter(pl.col("resolution_action") == "leave_pending").height == 5


def test_weekend_artifact_blocks_new_rows_but_not_old_outcome_resolution() -> None:
    latest_replay = {
        "latest_available_replay_date": "2026-05-24",
        "latest_resolved_market_session_date": "2026-05-22",
        "is_weekend_artifact": True,
    }
    calendar = build_calendar_gate_frame(
        today=datetime(2026, 5, 24, tzinfo=UTC).date(),
        latest_replay=latest_replay,
        can_resolve_pending=True,
    )
    outcome_coverage = _coverage_frame(all_covered=True)

    decision, final = build_run_decision_frame(
        calendar_gate=calendar,
        outcome_coverage=outcome_coverage,
        provider_audit=pl.DataFrame(),
        latest_replay=latest_replay,
        pending_journal_count=1,
    )

    row = calendar.row(0, named=True)
    assert row["should_create_new_journal_rows"] is False
    assert row["should_resolve_pending_outcomes"] is True
    assert decision.row(0, named=True)["run_state"] == "SKIP_NEW_ROWS_BUT_RESOLVE_OLD_OUTCOMES"
    assert final == "SKIP_NEW_ROWS_BUT_RESOLVE_OLD_OUTCOMES"


def test_daily_ohlc_does_not_resolve_intraday_windows(tmp_path: Path) -> None:
    daily_source = LocalOhlcSource(
        symbol="GC=F",
        interval="1d",
        path=tmp_path / "gc=f_1d_ohlcv.parquet",
        frame=_daily_frame(datetime(2026, 5, 20, tzinfo=UTC), 2),
        quality="DAILY_APPROX",
    )

    preview = build_forward_outcome_preview(
        coverage=_coverage_frame(all_covered=True),
        sources=[daily_source],
    )
    resample_coverage, _ = build_intraday_resample_coverage([daily_source])

    assert preview.filter(pl.col("resolution_action") == "preview_resolve").is_empty()
    assert set(resample_coverage.get_column("quality").to_list()) == {"DAILY_APPROX"}
    assert not any(resample_coverage.get_column("coverage_ok").to_list())


def test_forward_journal_status_files_are_generated(tmp_path: Path) -> None:
    _write_resolver_inputs(tmp_path)

    run_yahoo_intraday_outcome_resolver(
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
        current_time=datetime(2026, 5, 24, 10, 47, tzinfo=UTC),
    )

    assert (tmp_path / "outputs" / "forward_journal_status_report.md").exists()
    assert (tmp_path / "outputs" / "forward_journal_scorecard.csv").exists()


def test_useful_evidence_report_does_not_claim_profitability(tmp_path: Path) -> None:
    _write_resolver_inputs(tmp_path)

    run_yahoo_intraday_outcome_resolver(
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
        current_time=datetime(2026, 5, 24, 10, 47, tzinfo=UTC),
    )

    text = (tmp_path / "outputs" / "useful_evidence_so_far.md").read_text(
        encoding="utf-8"
    )
    assert "No proven money edge yet" in text
    assert "profitable" not in text.lower()


def test_reports_use_redacted_paths(tmp_path: Path) -> None:
    _write_resolver_inputs(tmp_path)

    run_yahoo_intraday_outcome_resolver(
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
        current_time=datetime(2026, 5, 24, 10, 47, tzinfo=UTC),
    )

    text = (tmp_path / "outputs" / "intraday_resample_coverage.md").read_text(
        encoding="utf-8"
    )
    assert "<REDACTED_PATH>/" in text
    assert str(tmp_path) not in text
    assert "C:" not in text


def _coverage_frame(*, all_covered: bool) -> pl.DataFrame:
    observation = (
        "2026-05-20T00:00:00Z"
        if all_covered
        else "2026-05-24T10:47:36.169050Z"
    )
    return pl.DataFrame(
        [
            {
                "journal_id": f"journal_{'covered' if all_covered else 'pending'}",
                "observation_timestamp": observation,
                "trade_date": "2026-05-20" if all_covered else "2026-05-24",
                "session_date": "2026-05-20" if all_covered else "2026-05-22",
                "required_windows": "30m|1h|4h|session_close|next_day",
                "required_ohlc_granularity": "intraday_only",
                "available_ohlc_sources": "GC=F 1m PROXY_ONLY",
                "latest_available_ohlc_timestamp": "2026-05-22T20:59:00Z",
                "coverage_30m": all_covered,
                "coverage_1h": all_covered,
                "coverage_4h": all_covered,
                "coverage_session_close": all_covered,
                "coverage_next_day": all_covered,
                "can_resolve_any_window": all_covered,
                "can_resolve_full_outcome": all_covered,
                "missing_coverage_reason": (
                    "All required windows have usable OHLC coverage."
                    if all_covered
                    else "Latest intraday OHLC timestamp is before observation."
                ),
                "next_check_recommended_at": "2026-05-25T22:00:00Z",
            }
        ]
    )


def _minute_frame(start: datetime, rows: int) -> pl.DataFrame:
    return _ohlc_frame(start, rows, timedelta(minutes=1))


def _hour_frame(start: datetime, rows: int) -> pl.DataFrame:
    return _ohlc_frame(start, rows, timedelta(hours=1))


def _daily_frame(start: datetime, rows: int) -> pl.DataFrame:
    return _ohlc_frame(start, rows, timedelta(days=1))


def _ohlc_frame(start: datetime, rows: int, step: timedelta) -> pl.DataFrame:
    timestamps = [start + index * step for index in range(rows)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index for index in range(rows)],
            "high": [101.0 + index for index in range(rows)],
            "low": [99.0 + index for index in range(rows)],
            "close": [99.5 + index for index in range(rows)],
            "volume": [1.0 for _ in range(rows)],
        },
        schema={
            "timestamp": pl.Datetime(time_zone="UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        },
    )


def _write_resolver_inputs(root: Path) -> None:
    output = root / "outputs"
    output.mkdir(parents=True)
    _coverage_frame(all_covered=True).vstack(_coverage_frame(all_covered=False)).write_csv(
        output / "outcome_coverage_check.csv"
    )
    pl.DataFrame(
        [
            {
                "rule_id": "IV_EXPECTED_RANGE_FILTER",
                "rule_type": "FILTER",
                "event_count": 10,
            }
        ]
    ).write_csv(output / "guru_rule_backtest_summary.csv")
    pl.DataFrame(
        [
            {
                "rule_id": "IV_EXPECTED_RANGE_FILTER",
                "rule_type": "FILTER",
            }
        ]
    ).write_csv(output / "guru_rule_library.csv")
    yahoo_dir = root / "data" / "raw" / "yahoo"
    yahoo_dir.mkdir(parents=True)
    _minute_frame(datetime(2026, 5, 20, tzinfo=UTC), 1500).write_parquet(
        yahoo_dir / "gc=f_1m_ohlcv.parquet"
    )
