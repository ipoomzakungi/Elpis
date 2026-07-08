from __future__ import annotations

from datetime import date

from src.models.xau_vol2vol_history_walkforward import XauWalkforwardStats
from src.xau_vol2vol_history_walkforward.ai_pack_builder import build_ai_pack_markdown


def test_ai_pack_includes_research_only_warning_and_top_configs() -> None:
    stats = XauWalkforwardStats(
        run_id="run",
        session_date_from=date(2026, 6, 25),
        session_date_to=date(2026, 7, 8),
        plan_count=1,
        triggered_count=1,
        no_fill_count=0,
        target_hit_count=1,
        stop_hit_count=0,
        expired_count=0,
        ambiguous_count=0,
        fill_rate=1,
        target_hit_rate_after_fill=1,
        stop_hit_rate_after_fill=0,
        grouped_stats=[
            {
                "group_by": "tp_mode",
                "group": "half_sd",
                "count": 1,
                "target_hit_rate_after_fill": 1,
                "fill_rate": 1,
            }
        ],
    )

    markdown = build_ai_pack_markdown(
        stats=stats,
        range_snapshots=[],
        strike_rows=[],
        plans=[],
        outcomes=[],
    )

    assert "Research-only. Not a buy/sell signal." in markdown
    assert "tp_mode=half_sd" in markdown
    assert "signal_allowed: `false`" in markdown
