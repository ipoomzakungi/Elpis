from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.guru_cme_hypothesis_lab import (
    basis_adjusted_wall_level,
    build_cme_only_rule_candidates,
    build_cme_wall_map_by_date,
    build_guru_wall_logic_hypotheses,
    build_sd_grid_behavior_test,
    choose_final_recommendation,
    report_text_is_safe,
    run_guru_cme_hypothesis_lab,
)


def test_wall_as_target_hypothesis_exists() -> None:
    wall_map = build_cme_wall_map_by_date(inputs=_inputs())
    hypotheses = build_guru_wall_logic_hypotheses(inputs=_inputs(), wall_map=wall_map)

    assert "WALL_AS_TARGET" in hypotheses.get_column("hypothesis_id").to_list()


def test_wall_as_rejection_hypothesis_exists() -> None:
    wall_map = build_cme_wall_map_by_date(inputs=_inputs())
    hypotheses = build_guru_wall_logic_hypotheses(inputs=_inputs(), wall_map=wall_map)

    assert "WALL_AS_REJECTION" in hypotheses.get_column("hypothesis_id").to_list()


def test_put_and_call_walls_are_separated() -> None:
    wall_map = build_cme_wall_map_by_date(inputs=_inputs())
    wall_types = set(wall_map.get_column("wall_type").to_list())

    assert "CALL_WALL" in wall_types
    assert "PUT_WALL" in wall_types


def test_basis_adjusted_wall_level_calculated() -> None:
    assert basis_adjusted_wall_level(4500.0, -5.0) == 4505.0
    assert basis_adjusted_wall_level(4500.0, 7.5) == 4492.5


def test_max_oi_pin_wall_detected() -> None:
    wall_map = build_cme_wall_map_by_date(inputs=_inputs())
    pin = wall_map.filter(pl.col("wall_type") == "MAX_OI_PIN")

    assert pin.height >= 1
    assert pin.row(0, named=True)["total_oi"] >= 1000


def test_low_oi_gap_detected() -> None:
    wall_map = build_cme_wall_map_by_date(inputs=_inputs())

    assert wall_map.filter(pl.col("wall_type") == "LOW_OI_GAP").height >= 1


def test_25_grid_test_output_exists() -> None:
    grid = build_sd_grid_behavior_test(inputs=_inputs())
    methods = set(grid.get_column("method").to_list())

    assert "TWENTY_FIVE_DOLLAR_GRID" in methods
    assert grid.filter(pl.col("method") == "TWENTY_FIVE_DOLLAR_GRID").row(0, named=True)["event_count"] > 0


def test_cme_only_rules_never_output_buy_or_sell() -> None:
    wall_map = build_cme_wall_map_by_date(inputs=_inputs())
    hypotheses = build_guru_wall_logic_hypotheses(inputs=_inputs(), wall_map=wall_map)
    rules = build_cme_only_rule_candidates(
        hypotheses=hypotheses,
        wall_map=wall_map,
        magnet_test=pl.DataFrame(),
        rejection_acceptance_test=pl.DataFrame(),
        sd_grid_behavior=build_sd_grid_behavior_test(inputs=_inputs()),
    )
    text = rules.write_csv()

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()


def test_insufficient_cme_sample_forces_pilot_label() -> None:
    wall_map = build_cme_wall_map_by_date(inputs=_inputs())
    final = choose_final_recommendation(
        wall_map=wall_map,
        magnet_test=pl.DataFrame(),
        rejection_acceptance_test=pl.DataFrame(),
        put_call_behavior=pl.DataFrame(),
    )

    assert final == "NEED_MORE_CME_DATA"


def test_reports_do_not_claim_profitability(tmp_path: Path) -> None:
    output = _write_inputs(tmp_path)

    run_guru_cme_hypothesis_lab(output_dir=output)
    text = (output / "guru_wall_logic_hypotheses.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert report_text_is_safe(text)


def test_reports_use_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_inputs(tmp_path, path_in_excerpt=True)

    run_guru_cme_hypothesis_lab(output_dir=output)
    text = (output / "guru_wall_logic_hypotheses.md").read_text(encoding="utf-8")

    assert str(tmp_path) not in text
    assert "C:" not in text
    assert "<REDACTED_PATH>" in text
    assert report_text_is_safe(text)


def _inputs(*, path_in_excerpt: bool = False) -> dict[str, object]:
    return {
        "guru_logic_knowledge_base": _guru_logic(path_in_excerpt=path_in_excerpt),
        "guru_logic_priority_rank": pl.DataFrame(),
        "same_day_playbook_matches": _same_day_playbook(),
        "current_week_cme_guru_replay": pl.DataFrame(),
        "cme_oi": _cme_oi(),
        "cme_iv": _cme_iv(),
        "basis": _basis(),
        "price_1h": _price_intraday(),
        "price_1d": _price_daily(),
    }


def _write_inputs(tmp_path: Path, *, path_in_excerpt: bool = False) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _guru_logic(path_in_excerpt=path_in_excerpt).write_csv(output / "guru_logic_knowledge_base.csv")
    _same_day_playbook().write_csv(output / "same_day_playbook_matches.csv")
    _cme_oi().write_parquet(output / "cme_canonical_option_oi_by_strike.parquet")
    _cme_iv().write_parquet(output / "cme_canonical_option_iv_by_strike.parquet")
    _basis().write_parquet(output / "xau_basis_backfilled.parquet")
    _price_intraday().write_parquet(output / "dukascopy_xau_1h.parquet")
    _price_daily().write_parquet(output / "dukascopy_xau_1d.parquet")
    return output


def _guru_logic(*, path_in_excerpt: bool = False) -> pl.DataFrame:
    excerpt = r"C:\Users\example\secret.csv wall target magnet logic" if path_in_excerpt else "wall target magnet logic"
    return pl.DataFrame(
        [
            {
                "logic_id": "wall_target",
                "logic_name": "Wall target market map",
                "logic_type": "MARKET_MAP",
                "description": "CME wall can be target context.",
                "representative_excerpts": excerpt,
            },
            {
                "logic_id": "wall_rejection",
                "logic_name": "Wall rejection",
                "logic_type": "CONFIRMATION",
                "description": "touch wall and reject back inside",
                "representative_excerpts": "rejection at wall",
            },
        ],
        infer_schema_length=None,
    )


def _same_day_playbook() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "logic_id": "basis",
                "logic_name": "Basis-adjusted strike mapping",
                "matched_text_excerpt": "basis adjusted strike maps futures wall to spot",
            }
        ],
        infer_schema_length=None,
    )


def _cme_oi() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _oi_row("2026-05-15", 4475.0, call_oi=50, put_oi=1200, total_oi=1250, put_volume=50),
            _oi_row("2026-05-15", 4500.0, call_oi=10, put_oi=10, total_oi=20, call_volume=2, put_volume=2),
            _oi_row("2026-05-15", 4525.0, call_oi=1400, put_oi=40, total_oi=1440, call_volume=80),
        ],
        infer_schema_length=None,
    )


def _oi_row(
    trade_date: str,
    strike: float,
    *,
    call_oi: float,
    put_oi: float,
    total_oi: float,
    call_volume: float = 0.0,
    put_volume: float = 0.0,
) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "expiry": trade_date,
        "dte": 1.0,
        "strike": strike,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "total_oi": total_oi,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "total_volume": call_volume + put_volume,
        "call_oi_change": call_volume / 2,
        "put_oi_change": put_volume / 2,
        "total_oi_change": (call_volume + put_volume) / 2,
    }


def _cme_iv() -> pl.DataFrame:
    return pl.DataFrame(
        [{"trade_date": "2026-05-15", "expiry": "2026-05-15", "strike": 4500.0, "implied_vol": 18.0}],
        infer_schema_length=None,
    )


def _basis() -> pl.DataFrame:
    return pl.DataFrame(
        [{"trade_date": "2026-05-15", "basis": 5.0}],
        infer_schema_length=None,
    )


def _price_intraday() -> pl.DataFrame:
    start = datetime(2026, 5, 15, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": start + timedelta(hours=index),
                "trade_date": "2026-05-15",
                "open": 4500.0 + index,
                "high": 4525.0 + index,
                "low": 4475.0 - index,
                "close": 4510.0 + index,
            }
            for index in range(4)
        ],
        infer_schema_length=None,
    )


def _price_daily() -> pl.DataFrame:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    rows = []
    for index in range(40):
        open_price = 4400.0 + index
        rows.append(
            {
                "timestamp": start + timedelta(days=index),
                "trade_date": (start + timedelta(days=index)).date().isoformat(),
                "open": open_price,
                "high": open_price + 30.0,
                "low": open_price - 20.0,
                "close": open_price + 10.0,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)
