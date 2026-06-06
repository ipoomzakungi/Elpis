from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from research_xau_vol_oi.cme_wall_entry_filter_audit import (
    cme_wall_entry_filter_audit_report_lines,
    report_text_is_safe,
    run_cme_wall_entry_filter_audit,
)


def test_acceptance_is_only_research_allowed_filter(tmp_path: Path) -> None:
    result = run_cme_wall_entry_filter_audit(output_dir=_fixture_outputs(tmp_path))
    policy = {
        row["strategy_name"]: row
        for row in result.strategy_policy.to_dicts()
    }

    assert result.final_recommendation == "CME_FILTER_ONLY_RESEARCH_ALLOWED"
    assert policy["WALL_ACCEPTANCE_CONTINUATION"]["policy"] == "RESEARCH_ALLOW_FILTER"
    assert policy["WALL_REJECTION_CONFIRMED_FADE"]["policy"] == "BLOCK_AS_DIRECTION"
    assert policy["SD_2_REJECTION_CONFIRMED_FADE"]["policy"] == "WATCH_ONLY_COST_DRAG"


def test_filter_scenarios_show_acceptance_but_not_all_active(tmp_path: Path) -> None:
    result = run_cme_wall_entry_filter_audit(output_dir=_fixture_outputs(tmp_path))
    scenarios = {
        row["scenario"]: row
        for row in result.filter_scenarios.to_dicts()
    }

    assert scenarios["ACCEPTANCE_CONTINUATION_ONLY"]["net_pnl"] > 0
    assert scenarios["ALL_REALISTIC_ACTIVE_CANDIDATES"]["net_pnl"] < 0


def test_smc_overlay_guidance_blocks_standalone_cme_direction(tmp_path: Path) -> None:
    result = run_cme_wall_entry_filter_audit(output_dir=_fixture_outputs(tmp_path))
    guidance = {
        row["guidance"]: row
        for row in result.smc_overlay_guidance.to_dicts()
    }

    assert guidance["SMC_WITH_CME_FILTER_ONLY"]["status"] == "RESEARCH_ALLOWED"
    assert guidance["BLOCK_REJECTION_AS_DIRECTION"]["status"] == "BLOCK"
    assert "standalone" in guidance["SMC_WITH_CME_FILTER_ONLY"]["blocked_context"].lower()


def test_reports_avoid_direct_order_terms_and_money_result_claims(tmp_path: Path) -> None:
    result = run_cme_wall_entry_filter_audit(output_dir=_fixture_outputs(tmp_path))
    report = "\n".join(cme_wall_entry_filter_audit_report_lines(result))
    direct_order_pattern = re.compile(r"\b(?:bu[y]|se[ll])\b", flags=re.IGNORECASE)

    assert direct_order_pattern.search(report) is None
    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def _fixture_outputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True)
    _trade_events().write_csv(output / "cme_wall_realistic_trade_events.csv")
    _performance().write_csv(output / "cme_wall_realistic_performance_summary.csv")
    return output


def _trade_events() -> pl.DataFrame:
    rows = [
        _trade("WALL_ACCEPTANCE_CONTINUATION", 12.0, 11.0),
        _trade("WALL_ACCEPTANCE_CONTINUATION", -4.0, -5.0),
        _trade("WALL_REJECTION_CONFIRMED_FADE", -10.0, -11.0),
        _trade("SD_2_REJECTION_CONFIRMED_FADE", 8.0, -1.0, spread=8.0),
        _trade("COMBINED_CONSERVATIVE_REALISTIC", 4.0, -2.0, spread=5.0),
    ]
    return pl.DataFrame(rows, infer_schema_length=None)


def _trade(
    strategy: str,
    gross: float,
    net: float,
    *,
    spread: float = 0.5,
) -> dict[str, object]:
    return {
        "strategy_name": strategy,
        "direction": "LONG",
        "gross_pnl_points": gross,
        "spread_cost_points": spread,
        "slippage_points": 0.5,
        "net_pnl_points": net,
    }


def _performance() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "strategy_name": "WALL_ACCEPTANCE_CONTINUATION",
                "net_profit_points": 6.0,
                "profit_factor": 3.0,
            },
            {
                "strategy_name": "WALL_REJECTION_CONFIRMED_FADE",
                "net_profit_points": -11.0,
                "profit_factor": 0.0,
            },
            {
                "strategy_name": "SD_2_REJECTION_CONFIRMED_FADE",
                "net_profit_points": -1.0,
                "profit_factor": 2.0,
            },
            {
                "strategy_name": "COMBINED_CONSERVATIVE_REALISTIC",
                "net_profit_points": -2.0,
                "profit_factor": 1.1,
            },
        ],
        infer_schema_length=None,
    )
