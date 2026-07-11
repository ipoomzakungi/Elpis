from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from src.models.xau_vol2vol_history_walkforward import XauMappingMode, XauSourceClass
from src.xau_vol2vol_history_walkforward.contract_horizon_audit import (
    build_contract_alignment_audit,
    build_holding_horizon_comparison,
)
from src.xau_vol2vol_history_walkforward.data_lake import load_vol2vol_data_lake
from src.xau_vol2vol_history_walkforward.history_normalizer import normalize_payload
from src.xau_vol2vol_history_walkforward.planning import select_planning_cycles
from src.xau_vol2vol_history_walkforward.sd_zone_audit import build_sd_zone_audit
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare XAU basis sources and predefined holding horizons.",
    )
    parser.add_argument("--session-date-from", required=True)
    parser.add_argument("--session-date-to", required=True)
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--spot-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    parser.add_argument(
        "--futures-proxy-bars-folder",
        default="data/imports/xau/yahoo/gc_f/5m",
    )
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--source-gap-limit-seconds", type=int, default=300)
    parser.add_argument("--mismatch-threshold-points", type=float, default=20.0)
    parser.add_argument("--roll-jump-threshold-points", type=float, default=20.0)
    parser.add_argument("--output-root", default="data/reports/xau_contract_horizon_audit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    date_from = date.fromisoformat(args.session_date_from)
    date_to = date.fromisoformat(args.session_date_to)
    loaded = load_vol2vol_data_lake(
        root=Path(args.vol2vol_data_root),
        session_date_from=date_from,
        session_date_to=date_to,
    )
    ranges = []
    strike_rows = []
    for payload in loaded.payloads:
        normalized_strikes, normalized, _ = normalize_payload(payload)
        strike_rows.extend(normalized_strikes)
        ranges.extend(normalized)
    spot = load_traded_bars_folder(Path(args.spot_bars_folder), timezone=args.timezone)
    proxy = load_traded_bars_folder(
        Path(args.futures_proxy_bars_folder), timezone=args.timezone
    )
    morning = time(7, 0)
    day_end = time(23, 59, 59)
    spot_selections, spot_issues = select_planning_cycles(
        range_snapshots=ranges,
        strike_rows=strike_rows,
        bars=spot.bars,
        session_date_from=date_from,
        session_date_to=date_to,
        planning_times=(morning,),
        timezone=args.timezone,
        planning_mode="fixed_morning",
        day_end_time=day_end,
        require_complete_window=False,
        require_one_sd=True,
        mapping_mode=XauMappingMode.DISTANCE_REANCHORED,
        source_alignment_tolerance_seconds=args.source_gap_limit_seconds,
        snapshot_freshness_tolerance_seconds=1800,
        join_by_observed_trading_date=True,
    )
    alignment = build_contract_alignment_audit(
        spot_selections,
        spot.bars,
        proxy.bars,
        source_gap_limit_seconds=args.source_gap_limit_seconds,
        mismatch_threshold_points=args.mismatch_threshold_points,
        roll_jump_threshold_points=args.roll_jump_threshold_points,
    )
    result_sets = []
    for planning_mode, planning_times in (
        ("fixed_morning", (morning,)),
        ("rolling_30m", _rolling_times(morning, day_end)),
    ):
        for mapping_mode in XauMappingMode:
            selections, issues = select_planning_cycles(
                range_snapshots=ranges,
                strike_rows=strike_rows,
                bars=proxy.bars,
                session_date_from=date_from,
                session_date_to=date_to,
                planning_times=planning_times,
                timezone=args.timezone,
                planning_mode=planning_mode,
                day_end_time=day_end,
                require_complete_window=True,
                require_one_sd=True,
                mapping_mode=mapping_mode,
                source_alignment_tolerance_seconds=args.source_gap_limit_seconds,
                snapshot_freshness_tolerance_seconds=1800,
                bar_interval_minutes=5,
                join_by_observed_trading_date=True,
            )
            diagnostics, opportunities, summary = build_sd_zone_audit(
                selections,
                proxy.bars,
                planning_mode=planning_mode,
            )
            result_sets.append(
                {
                    "planning_mode": planning_mode,
                    "mapping_mode": mapping_mode.value,
                    "selection_issues": issues,
                    "diagnostics": diagnostics,
                    "opportunities": opportunities,
                    "summary": summary,
                    "research_only": True,
                    "signal_allowed": False,
                }
            )
    horizons = build_holding_horizon_comparison(
        result_sets,
        proxy.bars,
        source_class=XauSourceClass.CONTINUOUS_FUTURES_PROXY,
    )
    run_id = f"xau_contract_horizon_audit_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    report_dir = Path(args.output_root) / run_id
    report_dir.mkdir(parents=True, exist_ok=False)
    alignment.update(
        {
            "run_id": run_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "vol2vol_session_count": len({row.session_date for row in ranges}),
            "dukascopy_spot_bar_count": len(spot.bars),
            "yahoo_futures_proxy_bar_count": len(proxy.bars),
            "spot_selection_issues": spot_issues,
            "warnings": loaded.warnings + spot.warnings + proxy.warnings,
        }
    )
    _write_json(report_dir / "contract_alignment_audit.json", alignment)
    _write_json(report_dir / "holding_horizon_comparison.json", horizons)
    handoff = _review_handoff(report_dir, alignment, horizons)
    (report_dir / "review_handoff.md").write_text(handoff, encoding="utf-8")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "report_dir": report_dir.resolve().as_posix(),
                "contract_alignment_observations": alignment["observation_count"],
                "accepted_basis_comparisons": alignment["accepted_observation_count"],
                "contract_mismatches": alignment["mismatch_count"],
                "touch_classification_changes": alignment[
                    "touch_classification_change_count"
                ],
                "holding_horizon_experiment_count": len(horizons["experiments"]),
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _rolling_times(start: time, end: time) -> tuple[time, ...]:
    current = datetime.combine(date(2000, 1, 1), start)
    limit = datetime.combine(date(2000, 1, 1), end)
    values = []
    while current <= limit:
        values.append(current.time())
        current += timedelta(minutes=30)
    return tuple(values)


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _review_handoff(report_dir: Path, alignment: dict, horizons: dict) -> str:
    lines = [
        "# XAU Contract Alignment and Holding Horizon Review",
        "",
        "Research-only. Yahoo GC=F is a continuous-futures proxy, not an exact "
        "contract or broker XAUUSD source.",
        "",
        "## Source Audit",
        f"- Vol2Vol sessions: `{alignment['vol2vol_session_count']}`",
        f"- Dukascopy spot bars: `{alignment['dukascopy_spot_bar_count']}`",
        f"- Yahoo GC=F proxy bars: `{alignment['yahoo_futures_proxy_bar_count']}`",
        f"- Synchronized three-way observations: `{alignment['accepted_observation_count']}`",
        f"- Proxy-aligned observations: `{alignment['proxy_count']}`",
        f"- Contract mismatches: `{alignment['mismatch_count']}`",
        "- Possible roll discontinuities: "
        f"`{alignment['possible_contract_roll_discontinuity_count']}`",
        "- Mapping touch classifications changed: "
        f"`{alignment['touch_classification_change_count']}`",
        "- True exact-contract basis validation: `unavailable`",
        "",
        "## Holding Horizons",
    ]
    for experiment in horizons["experiments"]:
        lines.append(
            f"- `{experiment['planning_mode']} / {experiment['mapping_mode']} / "
            f"{experiment['holding_horizon']}`: opportunities="
            f"`{experiment['unique_market_opportunity_count']}`, configurations="
            f"`{experiment['configuration_outcome_count']}`, exclusions="
            f"`{experiment['horizon_exclusions']}`"
        )
        for row in experiment["summary"]:
            if row["cost_points"] != 1.0:
                continue
            lines.append(
                f"  - `{row['strategy_id']} / {row['side']}` fills="
                f"`{row['configuration_fill_count']}` targets=`{row['target_hit_count']}` "
                f"stops=`{row['stop_hit_count']}` time_profit="
                f"`{row['time_exit_profit_count']}` time_loss="
                f"`{row['time_exit_loss_count']}` expectancy="
                f"`{row['net_expectancy_points']}`"
            )
    lines.extend(
        [
            "",
            "## Artifacts",
            f"- `{(report_dir.resolve() / 'contract_alignment_audit.json').as_posix()}`",
            f"- `{(report_dir.resolve() / 'holding_horizon_comparison.json').as_posix()}`",
            f"- `{(report_dir.resolve() / 'review_handoff.md').as_posix()}`",
            "",
            "signal_allowed=false",
            "research_only=true",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
