from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_wall_strategy_performance import (
    build_fee_stress,
    build_performance_summary,
    build_simulated_trade_ledger,
    build_strategy_definitions,
    cme_wall_strategy_performance_report_lines,
    report_text_is_safe,
    run_cme_wall_strategy_performance,
)


def test_trade_ledger_schema_exists(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))

    expected = {
        "trade_id",
        "strategy_name",
        "direction",
        "gross_pnl_points",
        "net_pnl_points",
        "data_quality",
        "pilot_warning",
    }

    assert expected.issubset(set(result.trades.columns))
    assert result.paths["trades_csv"].exists()


def test_performance_summary_calculates_net_gross_and_drawdown(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))
    row = result.performance_summary.filter(
        pl.col("strategy_name") == "WALL_REJECTION_FADE",
    ).row(0, named=True)

    assert row["total_trades"] >= 1
    assert row["gross_profit_points"] is not None
    assert row["net_profit_points"] is not None
    assert row["max_drawdown_points"] is not None


def test_equity_curve_created(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))

    assert not result.equity_curve.is_empty()
    assert result.paths["equity_curve_csv"].exists()
    assert result.paths["equity_curve_svg"].exists()


def test_bad_days_identified(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))

    assert "bad_day_reason" in result.bad_days.columns
    assert result.paths["bad_days_csv"].exists()


def test_fee_stress_applies_cost_multiplier(tmp_path: Path) -> None:
    output = _fixture_outputs(tmp_path)
    inputs = _fixture_inputs(output)
    trades = build_simulated_trade_ledger(inputs=inputs)
    summary = build_performance_summary(trades=trades, inputs=inputs)
    stress = build_fee_stress(trades=trades, performance_summary=summary)
    base = stress.filter(
        (pl.col("strategy_name") == "WALL_MAGNET_TO_NEAREST_WALL")
        & (pl.col("cost_multiplier") == 1.0),
    ).row(0, named=True)
    heavy = stress.filter(
        (pl.col("strategy_name") == "WALL_MAGNET_TO_NEAREST_WALL")
        & (pl.col("cost_multiplier") == 5.0),
    ).row(0, named=True)

    assert heavy["net_profit"] < base["net_profit"]


def test_hold_comparison_uses_same_date_range(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))
    row = result.vs_buy_hold.filter(
        pl.col("strategy_name") == "WALL_REJECTION_FADE",
    ).row(0, named=True)

    assert "buy_hold_return_points" in result.vs_buy_hold.columns
    assert result.vs_buy_hold.height == 6
    assert row["buy_hold_return_points"] == 5.0


def test_blind_wall_entries_are_not_allowed() -> None:
    definitions = build_strategy_definitions()
    text = "\n".join(definitions.get_column("excluded_shortcuts").to_list())

    assert "standalone CME wall" in text
    assert "unconfirmed" in text.lower()


def test_unconfirmed_wall_touch_does_not_create_trade(tmp_path: Path) -> None:
    output = _fixture_outputs(tmp_path, include_confirmed=False)
    inputs = _fixture_inputs(output)
    trades = build_simulated_trade_ledger(inputs=inputs)

    assert trades.filter(pl.col("strategy_name") == "WALL_REJECTION_FADE").is_empty()
    assert trades.filter(pl.col("strategy_name") == "WALL_ACCEPTANCE_CONTINUATION").is_empty()
    assert not trades.filter(pl.col("strategy_name") == "AVOID_DIRECT_WALL_TRADE").is_empty()


def test_sample_size_warning_enforced(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))

    assert bool(result.performance_summary.get_column("sample_size_warning").any())
    assert result.final_recommendation == "PILOT_ONLY_INSUFFICIENT_SAMPLE"


def test_report_avoids_direct_order_terms(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))
    report = "\n".join(cme_wall_strategy_performance_report_lines(result))
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(report) is None


def test_report_does_not_claim_money_result(tmp_path: Path) -> None:
    result = run_cme_wall_strategy_performance(output_dir=_fixture_outputs(tmp_path))
    report = "\n".join(cme_wall_strategy_performance_report_lines(result))

    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_redacted_paths_only() -> None:
    assert report_text_is_safe(r"C:\Users\example\private\cme.csv") is True


def _fixture_outputs(tmp_path: Path, *, include_confirmed: bool = True) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True)
    _outcome_rows(include_confirmed=include_confirmed).write_csv(
        output / "fetched_cme_wall_outcome_journal.csv",
    )
    _rankings_rows().write_csv(output / "fetched_cme_wall_rankings.csv")
    _daily_rows().write_csv(output / "fetched_cme_daily_wall_state.csv")
    _role_rows().write_csv(output / "fetched_cme_wall_role_summary.csv")
    _latest_rows().write_csv(output / "xau_indicator_latest_state_with_ranked_cme_walls.csv")
    _spread_rows().write_csv(output / "dukascopy_xau_spread_report.csv")
    _price_rows().write_parquet(output / "dukascopy_xau_15m.parquet")
    _sd_rows().write_csv(output / "gemini_sd_grid_entry_model_comparison.csv")
    _tp_sl_rows().write_csv(output / "gemini_tp_sl_model_comparison.csv")
    return output


def _fixture_inputs(output: Path) -> dict[str, pl.DataFrame]:
    return {
        "outcome_journal": pl.read_csv(output / "fetched_cme_wall_outcome_journal.csv"),
        "spread_report": pl.read_csv(output / "dukascopy_xau_spread_report.csv"),
        "sd_entry_comparison": pl.read_csv(output / "gemini_sd_grid_entry_model_comparison.csv"),
        "tp_sl_comparison": pl.read_csv(output / "gemini_tp_sl_model_comparison.csv"),
        "price_15m": pl.read_parquet(output / "dukascopy_xau_15m.parquet"),
    }


def _outcome_rows(*, include_confirmed: bool) -> pl.DataFrame:
    rows = [
        _journal_row(
            "2026-05-20T01:00:00+00:00",
            110.0,
            price=100.0,
            touched=True,
            rejected=include_confirmed,
            accepted=False,
            target=True,
            barrier=include_confirmed,
            interpretation="REJECTION_CANDIDATE" if include_confirmed else "IGNORED",
        ),
        _journal_row(
            "2026-05-20T02:00:00+00:00",
            90.0,
            price=100.0,
            touched=True,
            rejected=False,
            accepted=include_confirmed,
            target=True,
            barrier=False,
            interpretation="ACCEPTANCE_CANDIDATE" if include_confirmed else "IGNORED",
        ),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _journal_row(
    timestamp: str,
    wall: float,
    *,
    price: float,
    touched: bool,
    rejected: bool,
    accepted: bool,
    target: bool,
    barrier: bool,
    interpretation: str,
) -> dict[str, object]:
    return {
        "snapshot_timestamp": timestamp,
        "wall_level": wall,
        "wall_type": "CALL_VOLUME_WALL" if wall > price else "PUT_VOLUME_WALL",
        "option_type": "call" if wall > price else "put",
        "distance_bucket": "0_25",
        "volume_bucket": "LOW",
        "oi_bucket": "LOW",
        "dte_bucket": "0_1D",
        "price_at_snapshot": price,
        "distance_from_price": wall - price,
        "outcome_window": "1h",
        "touched_wall": touched,
        "rejected_wall": rejected,
        "accepted_wall": accepted,
        "closed_nearer_to_wall": target,
        "wall_acted_as_target": target,
        "wall_acted_as_barrier": barrier,
        "outcome_status": "RESOLVED",
        "interpretation": interpretation,
    }


def _rankings_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "snapshot_timestamp": "2026-05-20T01:00:00+00:00",
                "trade_date": "2026-05-20",
                "strike": 110.0,
                "wall_type": "CALL_VOLUME_WALL",
            }
        ],
        infer_schema_length=None,
    )


def _daily_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-20",
                "latest_price": 100.0,
                "active_wall": "CALL_VOLUME_WALL_110.00",
                "action_label": "WATCH_ONLY",
            }
        ],
        infer_schema_length=None,
    )


def _role_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "wall_type": "CALL_VOLUME_WALL",
                "event_count": 2,
                "sample_size_warning": True,
                "current_role": "INSUFFICIENT_SAMPLE",
            }
        ],
        infer_schema_length=None,
    )


def _latest_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "latest_price": 100.0,
                "active_wall": "CALL_VOLUME_WALL_110.00",
                "final_action_label": "WATCH_ONLY",
            }
        ],
        infer_schema_length=None,
    )


def _spread_rows() -> pl.DataFrame:
    return pl.DataFrame([{"average_spread": 1.0}], infer_schema_length=None)


def _price_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"timestamp": "2026-05-20T01:00:00+00:00", "close": 100.0},
            {"timestamp": "2026-05-20T03:00:00+00:00", "close": 105.0},
        ],
        infer_schema_length=None,
    ).with_columns(pl.col("timestamp").str.to_datetime(time_zone="UTC"))


def _sd_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "model_id": "REJECTION_CONFIRMED_2SD_FADE",
                "entry_count": 12,
                "win_rate": 0.5,
                "expectancy_proxy": 1.0,
                "average_mfe": 4.0,
                "average_mae": -2.0,
                "max_adverse_excursion": -8.0,
            }
        ],
        infer_schema_length=None,
    )


def _tp_sl_rows() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "model_id": "TP_FULL_BLOCK_25_SL_3_5SD",
                "max_drawdown_proxy": -10.0,
            }
        ],
        infer_schema_length=None,
    )
