from __future__ import annotations

from src.models.xau_vol2vol_history_walkforward import (
    XauSdMeanReversionPlan,
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
    XauWalkforwardStats,
    XauWalkforwardTradeOutcome,
)


def build_ai_pack_markdown(
    *,
    stats: XauWalkforwardStats,
    range_snapshots: list[XauVol2VolRangeDeskSnapshot],
    strike_rows: list[XauVol2VolStrikeSnapshot],
    plans: list[XauSdMeanReversionPlan],
    outcomes: list[XauWalkforwardTradeOutcome],
) -> str:
    lines = [
        f"# XAU Vol2Vol History Walk-Forward {stats.run_id}",
        "",
        "Research-only. Not a buy/sell signal. No live trading, paper orders, "
        "broker execution, lot sizing, spread, slippage, or PnL is included.",
        "",
        "## Scope",
        f"- Date range: `{stats.session_date_from}` to `{stats.session_date_to}`",
        f"- Range snapshots: `{len(range_snapshots)}`",
        f"- Strike rows: `{len(strike_rows)}`",
        f"- Plans: `{len(plans)}`",
        f"- Outcomes: `{len(outcomes)}`",
        f"- signal_allowed: `{str(stats.signal_allowed).lower()}`",
        f"- research_only: `{str(stats.research_only).lower()}`",
        "",
        "## Overall Stats",
        f"- Fill rate: `{stats.fill_rate}`",
        f"- Target hit rate after fill: `{stats.target_hit_rate_after_fill}`",
        f"- Stop hit rate after fill: `{stats.stop_hit_rate_after_fill}`",
        f"- Avg MFE points: `{stats.avg_mfe_points}`",
        f"- Avg MAE points: `{stats.avg_mae_points}`",
        f"- Worst MAE points: `{stats.worst_mae_points}`",
        "",
        "## Top Config Groups",
    ]
    top_groups = sorted(
        stats.grouped_stats,
        key=lambda item: (
            item.get("target_hit_rate_after_fill") is not None,
            item.get("target_hit_rate_after_fill") or 0,
        ),
        reverse=True,
    )[:10]
    if not top_groups:
        lines.append("- unavailable")
    for group in top_groups:
        lines.append(
            "- `{group_by}={group}` count=`{count}` target_after_fill=`{target}` "
            "fill_rate=`{fill}`".format(
                group_by=group["group_by"],
                group=group["group"],
                count=group["count"],
                target=group["target_hit_rate_after_fill"],
                fill=group["fill_rate"],
            )
        )
    lines.extend(
        [
            "",
            "## Warnings",
            "- Small sample is not proof.",
            "- OI is structural map context only.",
            "- Wormhole means low-activity gap/vacuum context, not direction.",
            "",
            "## Missing Before Shadow Signal",
            "- Larger walk-forward sample.",
            "- Clean traded-side XAUUSD/CFD bars aligned to the tested sessions.",
            "- Basis/Diff validation against the traded instrument.",
            "- Shadow-only decision rules after evidence review.",
        ]
    )
    lines.extend(f"- {warning}" for warning in stats.warnings)
    return "\n".join(lines) + "\n"
