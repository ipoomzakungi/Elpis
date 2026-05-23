from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_history_importer import (
    build_canonical_cme_tables,
    classify_validation_grade_days,
    load_and_detect_cme_files,
)
from research_xau_vol_oi.current_data_usability_audit import (
    build_cme_fetch_tool_gap_audit,
    build_current_cme_date_usability,
    build_iv_field_mapping_audit,
    build_ohlc_guru_price_only_pilot,
    build_spot_basis_join_audit,
    run_current_data_usability_audit,
)


def test_partial_cme_day_is_not_labeled_only_unusable() -> None:
    frames = _frames(
        validation_days=pl.DataFrame(
            [
                {
                    "trade_date": "2026-05-15",
                    "validation_grade": "UNUSABLE",
                    "has_xau_spot_price": False,
                    "has_gc_futures_price": True,
                    "has_basis": False,
                    "has_option_oi_by_strike": True,
                    "has_option_oi_change": True,
                    "has_option_volume": True,
                    "has_option_iv": False,
                    "has_option_settlement": False,
                    "has_expiry_dte": True,
                    "has_macro_event_flag": False,
                }
            ]
        ),
        option_oi=_oi_rows("2026-05-15"),
        futures=_futures_rows("2026-05-15"),
    )

    audit = build_current_cme_date_usability(frames)
    row = audit.filter(pl.col("trade_date") == "2026-05-15").row(0, named=True)

    assert row["current_validation_grade"] == "UNUSABLE"
    assert row["pilot_usability_grade"] == "CME_OI_VOLUME_NEEDS_SPOT_BASIS"
    assert row["can_use_for_cme_oi_pilot"] is True


def test_oi_volume_futures_missing_spot_becomes_needs_spot_basis() -> None:
    audit = build_current_cme_date_usability(
        _frames(option_oi=_oi_rows("2026-05-15"), futures=_futures_rows("2026-05-15"))
    )

    row = audit.filter(pl.col("trade_date") == "2026-05-15").row(0, named=True)

    assert row["pilot_usability_grade"] == "CME_OI_VOLUME_NEEDS_SPOT_BASIS"
    assert row["next_fix_needed"] == "Add XAU spot/proxy OHLC for the date."


def test_iv_column_implied_volatility_maps_to_option_iv(tmp_path: Path) -> None:
    source = tmp_path / "quikstrike_iv_20260515.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-15T12:00:00Z",
                "expiry": "2026-05-16",
                "dte": 1,
                "strike": 4700,
                "open_interest": 10,
                "implied_volatility": 0.22,
            }
        ]
    ).write_csv(source)

    canonical = build_canonical_cme_tables(load_and_detect_cme_files([source]))

    assert canonical["option_iv_by_strike"].height == 1
    assert canonical["option_iv_by_strike"].row(0, named=True)["implied_vol"] == 22.0


def test_iv_field_mapping_audit_reports_likely_importer_gap(tmp_path: Path) -> None:
    source = tmp_path / "quikstrike_iv_20260515.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-15T12:00:00Z",
                "expiry": "2026-05-16",
                "dte": 1,
                "strike": 4700,
                "implied_volatility": 0.22,
            }
        ]
    ).write_csv(source)
    date_usability = build_current_cme_date_usability(_frames(futures=_futures_rows("2026-05-15")))

    audit = build_iv_field_mapping_audit(
        output_root=tmp_path,
        search_roots=[tmp_path],
        canonical_iv=pl.DataFrame(),
        date_usability=date_usability,
    )
    row = audit.row(0, named=True)

    assert row["likely_iv_column"] == "implied_volatility"
    assert row["likely_iv_unit"] == "decimal"
    assert row["mapping_fix_needed"] is True


def test_basis_missing_due_to_spot_missing_is_explained(tmp_path: Path) -> None:
    spot_basis = build_spot_basis_join_audit(
        frames=_frames(futures=_futures_rows("2026-05-15")),
        output_root=tmp_path,
        search_roots=[tmp_path],
    )

    row = spot_basis.filter(pl.col("trade_date") == "2026-05-15").row(0, named=True)

    assert row["basis_missing_reason"] == "missing_xau_spot_price"
    assert row["likely_root_cause"] == "missing_spot"


def test_spot_and_futures_can_calculate_basis(tmp_path: Path) -> None:
    spot_basis = build_spot_basis_join_audit(
        frames=_frames(
            futures=_futures_rows("2026-05-15"),
            spot=_spot_rows("2026-05-15"),
        ),
        output_root=tmp_path,
        search_roots=[tmp_path],
    )

    row = spot_basis.filter(pl.col("trade_date") == "2026-05-15").row(0, named=True)

    assert row["basis_can_be_calculated_from_existing"] is True
    assert row["basis_missing_reason"] == "importer_failure_or_stale_basis_output"


def test_pilot_usability_grade_exists_alongside_strict_grade() -> None:
    canonical = {
        "option_oi_by_strike": _oi_rows("2026-05-15"),
        "option_iv_by_strike": pl.DataFrame(),
        "futures_price": _futures_rows("2026-05-15"),
        "xau_spot_price": pl.DataFrame(),
        "basis": pl.DataFrame(),
        "macro_event_calendar": pl.DataFrame(),
    }

    days = classify_validation_grade_days(canonical)
    row = days.row(0, named=True)

    assert row["strict_validation_grade"] == "UNUSABLE"
    assert row["pilot_usability_grade"] == "CME_OI_VOLUME_NEEDS_SPOT_BASIS"
    assert row["validation_grade"] == "UNUSABLE"


def test_ohlc_guru_pilot_can_run_without_cme() -> None:
    frames = _frames(
        transcript_conditioned_events=pl.DataFrame(
            [
                {
                    "event_timestamp": "2026-05-15T12:00:00Z",
                    "signal": "NO_TRADE",
                    "no_trade_row_retained": True,
                }
            ]
        ),
        guru_episode_outcomes=pl.DataFrame(
            [
                {
                    "rule_tag": "NO_TRADE_DISCIPLINE",
                    "thesis_type": "FILTER",
                    "outcome_label": "NO_CLEAR_OUTCOME",
                    "direction_correct": None,
                    "wall_rejected": False,
                }
            ]
        ),
        signal_events=pl.DataFrame([{"signal": "NO_TRADE"}]),
    )

    pilot = build_ohlc_guru_price_only_pilot(frames)
    row = pilot.filter(pl.col("logic_bucket") == "overall_price_only_guru").row(0, named=True)

    assert row["event_count"] == 1
    assert row["validation_status"] == "PRICE_ONLY_FILTER_CANDIDATE"


def test_fetch_tool_audit_reports_missing_spot_basis_iv_settlement(tmp_path: Path) -> None:
    script = tmp_path / "daily_quikstrike.ps1"
    script.write_text("quikstrike vol2vol matrix open interest strike volume", encoding="utf-8")

    audit = build_cme_fetch_tool_gap_audit(script_roots=[tmp_path])
    missing = audit.row(0, named=True)["missing_sources"]

    assert "XAU/USD spot OHLC" in missing
    assert "basis calculation" in missing
    assert "QuikVol / IV" in missing
    assert "option settlements" in missing
    assert audit.row(0, named=True)["requires_manual_export"] is True


def test_reports_do_not_claim_edge_and_redact_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _oi_rows("2026-05-15").write_parquet(output_dir / "cme_canonical_option_oi_by_strike.parquet")
    _futures_rows("2026-05-15").write_parquet(output_dir / "cme_canonical_futures_price.parquet")
    raw = tmp_path / "raw_quikstrike_iv_20260515.csv"
    pl.DataFrame(
        [
            {
                "timestamp": "2026-05-15T12:00:00Z",
                "expiry": "2026-05-16",
                "dte": 1,
                "strike": 4700,
                "implied_volatility": 0.22,
            }
        ]
    ).write_csv(raw)

    result = run_current_data_usability_audit(output_dir=output_dir, search_roots=[tmp_path])

    assert result.final_recommendation == "CURRENT_WEEK_PILOT_READY"
    for report in output_dir.glob("*.md"):
        text = report.read_text(encoding="utf-8").lower()
        assert str(tmp_path).lower() not in text
        assert "profitable" not in text
        assert "safe to trade" not in text
        assert "live ready" not in text


def _frames(**overrides: pl.DataFrame) -> dict[str, pl.DataFrame]:
    frames = {
        "validation_days": pl.DataFrame(),
        "option_oi": pl.DataFrame(),
        "option_iv": pl.DataFrame(),
        "futures": pl.DataFrame(),
        "spot": pl.DataFrame(),
        "basis": pl.DataFrame(),
        "events": pl.DataFrame(),
        "validation_dataset": pl.DataFrame(),
        "guru_kb": pl.DataFrame(),
        "guru_priority": pl.DataFrame(),
        "gold_baseline": pl.DataFrame(),
        "signal_events": pl.DataFrame(),
        "backtest_summary": pl.DataFrame(),
        "transcript_timeline": pl.DataFrame(),
        "transcript_conditioned_events": pl.DataFrame(),
        "guru_episode_outcomes": pl.DataFrame(),
    }
    frames.update(overrides)
    return frames


def _oi_rows(trade_date: str) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "asof_timestamp": datetime.fromisoformat(f"{trade_date}T12:00:00+00:00"),
                "trade_date": trade_date,
                "expiry": "2026-05-16",
                "dte": 1.0,
                "strike": 4700.0,
                "total_oi": 100.0,
                "total_oi_change": 10.0,
                "total_volume": 25.0,
            }
        ]
    )


def _futures_rows(trade_date: str) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": datetime.fromisoformat(f"{trade_date}T12:00:00+00:00").astimezone(UTC),
                "trade_date": trade_date,
                "close": 4705.0,
                "settle": 4705.0,
                "futures_symbol": "GC",
            }
        ]
    )


def _spot_rows(trade_date: str) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": datetime.fromisoformat(f"{trade_date}T12:00:00+00:00").astimezone(UTC),
                "trade_date": trade_date,
                "close": 4701.0,
                "symbol": "XAUUSD",
            }
        ]
    )
