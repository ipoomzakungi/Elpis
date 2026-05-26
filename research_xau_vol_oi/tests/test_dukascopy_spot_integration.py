from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.dukascopy_spot_integration import (
    build_price_source_priority_report,
    build_spread_report,
    create_canonical_spot_table,
    dukascopy_report_lines,
    report_text_is_safe,
    resample_canonical_spot,
    resolve_forward_outcomes_with_dukascopy,
    run_cme_overlap_validation,
    run_dukascopy_spot_integration,
    run_guru_price_only_test,
    run_price_only_rule_backtest,
    validate_canonical_spot,
)


def test_bid_ask_merge_creates_mid_and_spread_correctly() -> None:
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=2))
    row = canonical.row(0, named=True)

    assert row["mid_open"] == 100.5
    assert row["mid_high"] == 101.5
    assert row["mid_low"] == 99.5
    assert row["mid_close"] == 100.75
    assert row["spread_close"] == 0.5
    assert row["source"] == "DUKASCOPY"


def test_spread_report_detects_abnormal_spread(tmp_path: Path) -> None:
    raw = _raw_bid_ask_frame(rows=3).with_columns(
        pl.when(pl.arange(0, pl.len()) == 1)
        .then(pl.col("bid_close") + 20.0)
        .otherwise(pl.col("ask_close"))
        .alias("ask_close")
    )
    canonical = create_canonical_spot_table(raw, abnormal_spread_points=5.0)
    validation = validate_canonical_spot(canonical, abnormal_spread_points=5.0)
    report = build_spread_report(
        canonical,
        validation=validation,
        source_path=tmp_path / "xauusd_m1.parquet",
        abnormal_spread_points=5.0,
    )

    assert validation.abnormal_spread_count == 1
    assert report.row(0, named=True)["abnormal_spread_count"] == 1


def test_m1_to_15m_resample_works() -> None:
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=31))

    resampled = resample_canonical_spot(canonical, "15m")

    first = resampled.row(0, named=True)
    assert resampled.height == 3
    assert first["mid_open"] == canonical.row(0, named=True)["mid_open"]
    assert first["mid_high"] == canonical.head(15).select(pl.max("mid_high")).item()
    assert first["mid_close"] == canonical.row(14, named=True)["mid_close"]


def test_m1_to_4h_resample_works() -> None:
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=481))

    resampled = resample_canonical_spot(canonical, "4h")

    assert resampled.height == 3
    assert resampled.row(0, named=True)["timeframe"] == "4h"
    assert resampled.row(0, named=True)["mid_high"] == canonical.head(240).select(
        pl.max("mid_high")
    ).item()


def test_dukascopy_is_preferred_over_yahoo_for_xau_spot(tmp_path: Path) -> None:
    raw_path = tmp_path / "data_pipeline" / "data" / "processed" / "xauusd_m1.parquet"
    raw_path.parent.mkdir(parents=True)
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=120))
    canonical.write_parquet(raw_path)
    yahoo = tmp_path / "data" / "raw" / "yahoo"
    yahoo.mkdir(parents=True)
    (yahoo / "xauusd_15m_ohlcv.parquet").write_bytes(b"placeholder")
    validation = validate_canonical_spot(canonical)

    priority = build_price_source_priority_report(
        repo_root=tmp_path,
        output_dir=tmp_path / "outputs",
        cleaned_path=raw_path,
        validation=validation,
    )

    selected = priority.filter(pl.col("selected")).row(0, named=True)
    assert selected["source_type"] == "TRUE_XAUUSD_SPOT_BID_ASK"


def test_price_only_rules_run_without_cme() -> None:
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=8000, trend=0.05))
    resampled = {tf: resample_canonical_spot(canonical, tf) for tf in ("15m", "30m", "1h", "4h", "1d")}

    result = run_price_only_rule_backtest(resampled)

    assert set(result.get_column("rule").to_list()).issuperset(
        {"NO_TRADE_MIDDLE_RANGE", "ACCEPTANCE_BREAKOUT", "REJECTION_AFTER_LEVEL_TOUCH"}
    )
    assert "source" in result.columns
    assert result.filter(pl.col("trade_count") > 0).height > 0


def test_cme_overlap_does_not_treat_dukascopy_as_cme(tmp_path: Path) -> None:
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=1440))

    overlap = run_cme_overlap_validation(canonical=canonical, output_dir=tmp_path)

    assert overlap.height > 0
    assert not any(overlap.get_column("has_cme_oi").to_list())
    assert not any(overlap.get_column("can_test_oi_wall").to_list())
    assert set(overlap.get_column("validation_grade").to_list()) == {"PRICE_ONLY"}


def test_guru_timing_unknown_remains_context_only() -> None:
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=8000, trend=0.05))
    resampled = {tf: resample_canonical_spot(canonical, tf) for tf in ("15m", "30m", "1h", "4h", "1d")}
    backtest = run_price_only_rule_backtest(resampled)

    guru = run_guru_price_only_test(price_backtest=backtest, output_dir=Path("missing-output-dir"))

    assert guru.filter(pl.col("context_only_event_count") > 0).height > 0
    assert "TIMING_UNKNOWN_CONTEXT_ONLY" in set(guru.get_column("leakage_warning").to_list())


def test_forward_outcome_resolver_uses_dukascopy_intraday(tmp_path: Path) -> None:
    canonical = create_canonical_spot_table(_raw_bid_ask_frame(rows=3000))
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    pl.DataFrame(
        [
            {
                "journal_id": "journal_1",
                "observation_timestamp": "2026-05-20T00:00:00Z",
                "trade_date": "2026-05-20",
            }
        ]
    ).write_csv(outputs / "outcome_coverage_check.csv")
    resampled = {tf: resample_canonical_spot(canonical, tf) for tf in ("15m", "30m", "1h", "4h", "1d")}

    resolved = resolve_forward_outcomes_with_dukascopy(
        canonical=canonical,
        resampled=resampled,
        output_dir=outputs,
    )

    assert set(resolved.get_column("window").to_list()) == {
        "30m",
        "1h",
        "4h",
        "session_close",
        "next_day",
    }
    assert resolved.filter(pl.col("newly_resolved")).height >= 3
    assert set(resolved.get_column("source").to_list()) == {"DUKASCOPY"}


def test_run_layer_writes_expected_outputs_and_uses_redacted_paths(tmp_path: Path) -> None:
    cleaned = tmp_path / "data_pipeline" / "data" / "processed" / "xauusd_m1.parquet"
    cleaned.parent.mkdir(parents=True)
    _raw_bid_ask_frame(rows=3000, trend=0.03).write_parquet(cleaned)

    result = run_dukascopy_spot_integration(
        cleaned_path=cleaned,
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
    )

    assert result.validation.validation_pass
    assert (tmp_path / "outputs" / "dukascopy_xau_m1_mid.parquet").exists()
    assert (tmp_path / "outputs" / "dukascopy_xau_15m.parquet").exists()
    text = (tmp_path / "outputs" / "dukascopy_xau_spread_report.md").read_text(
        encoding="utf-8"
    )
    assert "<REDACTED_PATH>/" in text
    assert str(tmp_path) not in text
    assert "C:" not in text


def test_run_layer_reuses_cache_when_source_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    cleaned = tmp_path / "data_pipeline" / "data" / "processed" / "xauusd_m1.parquet"
    output_dir = tmp_path / "outputs"
    cleaned.parent.mkdir(parents=True)
    _raw_bid_ask_frame(rows=3000, trend=0.03).write_parquet(cleaned)
    first = run_dukascopy_spot_integration(
        cleaned_path=cleaned,
        output_dir=output_dir,
        repo_root=tmp_path,
    )

    def fail_cache_miss(*_args: object, **_kwargs: object) -> pl.DataFrame:
        raise AssertionError("Dukascopy cache was not used")

    monkeypatch.setattr(
        "research_xau_vol_oi.dukascopy_spot_integration.create_canonical_spot_table",
        fail_cache_miss,
    )
    cached = run_dukascopy_spot_integration(
        cleaned_path=cleaned,
        output_dir=output_dir,
        repo_root=tmp_path,
    )

    assert cached.validation.row_count == first.validation.row_count
    assert cached.resample_report.height == first.resample_report.height


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    cleaned = tmp_path / "data_pipeline" / "data" / "processed" / "xauusd_m1.parquet"
    cleaned.parent.mkdir(parents=True)
    _raw_bid_ask_frame(rows=3000, trend=0.03).write_parquet(cleaned)

    result = run_dukascopy_spot_integration(
        cleaned_path=cleaned,
        output_dir=tmp_path / "outputs",
        repo_root=tmp_path,
    )
    text = "\n".join(dukascopy_report_lines(result)).lower()

    assert "profitable" not in text
    assert "live ready" not in text
    assert report_text_is_safe(text)


def _raw_bid_ask_frame(rows: int, *, trend: float = 0.1) -> pl.DataFrame:
    start = datetime(2026, 5, 20, 0, 0, tzinfo=UTC)
    timestamps = [start + timedelta(minutes=index) for index in range(rows)]
    base = [100.0 + index * trend + (index % 30) * 0.02 for index in range(rows)]
    bid_close = [value + 0.5 for value in base]
    ask_close = [value + 1.0 for value in base]
    return pl.DataFrame(
        {
            "datetime": timestamps,
            "bid_open": base,
            "bid_high": [value + 1.0 for value in base],
            "bid_low": [value - 1.0 for value in base],
            "bid_close": bid_close,
            "ask_open": [value + 1.0 for value in base],
            "ask_high": [value + 2.0 for value in base],
            "ask_low": [value for value in base],
            "ask_close": ask_close,
        },
        schema={
            "datetime": pl.Datetime(time_zone="UTC"),
            "bid_open": pl.Float64,
            "bid_high": pl.Float64,
            "bid_low": pl.Float64,
            "bid_close": pl.Float64,
            "ask_open": pl.Float64,
            "ask_high": pl.Float64,
            "ask_low": pl.Float64,
            "ask_close": pl.Float64,
        },
    )
