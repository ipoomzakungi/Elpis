from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.fetched_cme_wall_state_tracker import (
    build_fetched_cme_wall_outcome_journal,
    build_fetched_cme_wall_role_summary,
    fetched_cme_wall_state_tracker_report_lines,
    report_text_is_safe,
    run_fetched_cme_wall_state_tracker,
)


def test_ranks_top_walls_above_and_below(tmp_path: Path) -> None:
    output, fetched_root, price_path = _write_fixture(tmp_path)

    result = run_fetched_cme_wall_state_tracker(
        output_dir=output,
        fetched_roots=[fetched_root],
        price_paths={"15m": price_path},
    )
    latest = result.latest_state.row(0, named=True)

    assert "CALL_VOLUME_WALL_110.00" in latest["top_3_walls_above"]
    assert "PUT_VOLUME_WALL_90.00" in latest["top_3_walls_below"]


def test_context_walls_are_not_hidden(tmp_path: Path) -> None:
    output, fetched_root, price_path = _write_fixture(tmp_path)

    result = run_fetched_cme_wall_state_tracker(
        output_dir=output,
        fetched_roots=[fetched_root],
        price_paths={"15m": price_path},
    )
    context = result.rankings.filter(pl.col("strike") == 120.0).row(0, named=True)

    assert context["context_threshold_passed"] is True
    assert context["active_threshold_passed"] is False
    assert context["rank_above"] is not None


def test_active_wall_threshold_separate_from_context_threshold(tmp_path: Path) -> None:
    output, fetched_root, price_path = _write_fixture(tmp_path)

    result = run_fetched_cme_wall_state_tracker(
        output_dir=output,
        fetched_roots=[fetched_root],
        price_paths={"15m": price_path},
    )
    active = result.rankings.filter(pl.col("strike") == 90.0).row(0, named=True)
    context = result.rankings.filter(pl.col("strike") == 120.0).row(0, named=True)

    assert active["active_threshold_passed"] is True
    assert active["context_threshold_passed"] is True
    assert context["active_threshold_passed"] is False
    assert context["context_threshold_passed"] is True


def test_wall_outcome_journal_uses_dukascopy_price(tmp_path: Path) -> None:
    output, fetched_root, price_path = _write_fixture(tmp_path)
    result = run_fetched_cme_wall_state_tracker(
        output_dir=output,
        fetched_roots=[fetched_root],
        price_paths={"15m": price_path},
    )

    journal = build_fetched_cme_wall_outcome_journal(
        rankings=result.rankings.filter(pl.col("strike") == 110.0),
        price_frame=pl.read_parquet(price_path),
    )
    row = journal.filter(pl.col("outcome_window") == "1h").row(0, named=True)

    assert row["price_at_snapshot"] == 100.0
    assert row["touched_wall"] is True
    assert row["outcome_status"] == "RESOLVED"


def test_wall_role_summary_marks_small_sample(tmp_path: Path) -> None:
    output, fetched_root, price_path = _write_fixture(tmp_path)
    result = run_fetched_cme_wall_state_tracker(
        output_dir=output,
        fetched_roots=[fetched_root],
        price_paths={"15m": price_path},
    )

    role = build_fetched_cme_wall_role_summary(outcome_journal=result.outcome_journal)

    assert not role.is_empty()
    assert bool(role.get_column("sample_size_warning").any())
    assert "INSUFFICIENT_SAMPLE" in set(role.get_column("current_role").to_list())


def test_latest_state_avoids_direct_order_terms(tmp_path: Path) -> None:
    output, fetched_root, price_path = _write_fixture(tmp_path)
    result = run_fetched_cme_wall_state_tracker(
        output_dir=output,
        fetched_roots=[fetched_root],
        price_paths={"15m": price_path},
    )
    text = result.paths["ranked_latest_state_md"].read_text(encoding="utf-8")
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(text) is None


def test_report_does_not_claim_money_result(tmp_path: Path) -> None:
    output, fetched_root, price_path = _write_fixture(tmp_path)
    result = run_fetched_cme_wall_state_tracker(
        output_dir=output,
        fetched_roots=[fetched_root],
        price_paths={"15m": price_path},
    )
    report = "\n".join(fetched_cme_wall_state_tracker_report_lines(result))

    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_redacted_paths_only() -> None:
    assert report_text_is_safe(r"C:\Users\example\private\wall.csv") is True


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    output = tmp_path / "outputs"
    fetched_root = tmp_path / "backend" / "data" / "reports" / "xau_quikstrike_fusion"
    report_dir = fetched_root / "xau_quikstrike_fusion_20260520_010000_data_20260520_daily_snapshot"
    output.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    _fetched_rows().write_csv(report_dir / "xau_vol_oi_input.csv")
    _latest_state().write_csv(output / "xau_indicator_latest_state_with_quikstrike_from_fetch.csv")
    price_path = output / "dukascopy_xau_15m.parquet"
    _price_rows().write_parquet(price_path)
    return output, fetched_root, price_path


def _fetched_rows() -> pl.DataFrame:
    rows = [
        _row(90.0, "put", 40.0, open_interest=80.0),
        _row(90.0, "call", 2.0, open_interest=10.0),
        _row(110.0, "call", 20.0, open_interest=60.0),
        _row(120.0, "call", 5.0, open_interest=200.0),
        _row(80.0, "put", 0.0, open_interest=150.0),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _row(
    strike: float,
    option_type: str,
    volume: float,
    *,
    open_interest: float,
) -> dict[str, object]:
    return {
        "date": "",
        "timestamp": "",
        "expiry": "2026-05-22",
        "expiration_code": "TEST",
        "strike": strike,
        "option_type": option_type,
        "open_interest": open_interest,
        "oi_change": 0.0,
        "volume": volume,
        "intraday_volume": volume,
        "implied_volatility": 0.22,
        "underlying_futures_price": 100.0,
    }


def _price_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": "2026-05-20T01:00:00+00:00",
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            },
            {
                "timestamp": "2026-05-20T01:15:00+00:00",
                "high": 108.0,
                "low": 99.0,
                "close": 107.0,
            },
            {
                "timestamp": "2026-05-20T01:30:00+00:00",
                "high": 111.0,
                "low": 103.0,
                "close": 109.0,
            },
            {
                "timestamp": "2026-05-20T02:00:00+00:00",
                "high": 112.0,
                "low": 106.0,
                "close": 111.0,
            },
            {
                "timestamp": "2026-05-20T05:00:00+00:00",
                "high": 112.0,
                "low": 104.0,
                "close": 108.0,
            },
            {
                "timestamp": "2026-05-21T01:00:00+00:00",
                "high": 115.0,
                "low": 96.0,
                "close": 105.0,
            },
        ],
        infer_schema_length=None,
    ).with_columns(pl.col("timestamp").str.to_datetime(time_zone="UTC"))


def _latest_state() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "latest_price": 100.0,
                "combined_indicator_action": "WATCH_ONLY",
            }
        ],
        infer_schema_length=None,
    )
