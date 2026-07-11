from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from src.models.xau_vol2vol_history_walkforward import XauMappingMode
from src.xau_vol2vol_history_walkforward.data_lake import load_vol2vol_data_lake
from src.xau_vol2vol_history_walkforward.history_normalizer import normalize_payload
from src.xau_vol2vol_history_walkforward.planning import select_planning_cycles
from src.xau_vol2vol_history_walkforward.sd_zone_audit import (
    build_preregistered_exit_backtest,
    build_sd_zone_audit,
    build_session_coverage_rows,
    compare_mapping_modes,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit XAU SD-zone semantics and rolling Vol2Vol mapping.",
    )
    parser.add_argument("--session-date-from", required=True)
    parser.add_argument("--session-date-to", required=True)
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--price-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--morning-plan-time", default="07:00")
    parser.add_argument("--day-end-time", default="23:59:59")
    parser.add_argument("--source-alignment-tolerance-seconds", type=int, default=300)
    parser.add_argument("--snapshot-freshness-tolerance-seconds", type=int, default=1800)
    parser.add_argument("--bar-interval-minutes", type=int, default=1)
    parser.add_argument("--price-source-label", default="dukascopy_xauusd_spot_bid")
    parser.add_argument("--output-root", default="data/reports/xau_sd_zone_audit")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    date_from = date.fromisoformat(args.session_date_from)
    date_to = date.fromisoformat(args.session_date_to)
    load_result = load_vol2vol_data_lake(
        root=Path(args.vol2vol_data_root),
        session_date_from=date_from,
        session_date_to=date_to,
    )
    ranges = []
    strike_rows = []
    for payload in load_result.payloads:
        normalized_strikes, normalized_ranges, _ = normalize_payload(payload)
        strike_rows.extend(normalized_strikes)
        ranges.extend(normalized_ranges)
    price_result = load_traded_bars_folder(
        Path(args.price_bars_folder),
        timezone=args.timezone,
    )
    morning = _parse_time(args.morning_plan_time)
    day_end = _parse_time(args.day_end_time)
    result_sets = []
    for planning_mode, planning_times in (
        ("fixed_morning", (morning,)),
        ("rolling_30m", _rolling_times(morning, day_end)),
    ):
        for mapping_mode in XauMappingMode:
            selections, issues = select_planning_cycles(
                range_snapshots=ranges,
                strike_rows=strike_rows,
                bars=price_result.bars,
                session_date_from=date_from,
                session_date_to=date_to,
                planning_times=planning_times,
                timezone=args.timezone,
                planning_mode=planning_mode,
                day_end_time=day_end,
                require_complete_window=True,
                require_one_sd=True,
                mapping_mode=mapping_mode,
                source_alignment_tolerance_seconds=(
                    args.source_alignment_tolerance_seconds
                ),
                snapshot_freshness_tolerance_seconds=(
                    args.snapshot_freshness_tolerance_seconds
                ),
                bar_interval_minutes=args.bar_interval_minutes,
                join_by_observed_trading_date=True,
            )
            diagnostics, opportunities, summary = build_sd_zone_audit(
                selections,
                price_result.bars,
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
    comparison = compare_mapping_modes(result_sets)
    exit_backtest = build_preregistered_exit_backtest(
        result_sets,
        price_result.bars,
    )
    coverage_rows, exclusion_counts = build_session_coverage_rows(
        ranges,
        price_result.bars,
        result_sets,
        timezone=args.timezone,
        bar_interval_minutes=args.bar_interval_minutes,
    )
    run_id = f"xau_sd_zone_audit_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    report_dir = Path(args.output_root) / run_id
    if report_dir.exists() and not args.overwrite:
        raise FileExistsError(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    alignment_payload = {
        "run_id": run_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "vol2vol_valid_session_count": len({item.session_date for item in ranges}),
        "xau_candle_row_count": len(price_result.bars),
        "price_source_label": args.price_source_label,
        "bar_interval_minutes": args.bar_interval_minutes,
        "session_coverage": coverage_rows,
        "unique_excluded_sessions_by_reason": exclusion_counts,
        "result_sets": result_sets,
        "comparison": comparison,
        "preregistered_exit_backtest": exit_backtest,
        "warnings": load_result.warnings + price_result.warnings,
        "true_basis_validation": "unavailable",
        "research_only": True,
        "signal_allowed": False,
    }
    semantics_payload = {
        "definitions": {
            "zone_2_entry": "1SD boundary; entrance to the 1SD-2SD zone",
            "zone_2_mid": "1.5SD midpoint inside the 1SD-2SD zone",
            "literal_2sd": "exact 2SD boundary",
            "literal_3sd": "exact 3SD boundary",
        },
        "summaries": [item["summary"] for item in result_sets],
        "comparison": comparison,
        "research_only": True,
        "signal_allowed": False,
    }
    _write_json(report_dir / "source_alignment_audit.json", alignment_payload)
    _write_json(report_dir / "sd_semantics_comparison.json", semantics_payload)
    _write_json(report_dir / "preregistered_exit_backtest.json", exit_backtest)
    markdown = _markdown(alignment_payload, semantics_payload, report_dir)
    (report_dir / "source_alignment_audit.md").write_text(markdown, encoding="utf-8")
    (report_dir / "sd_semantics_comparison.md").write_text(markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "report_dir": report_dir.resolve().as_posix(),
                "summaries": semantics_payload["summaries"],
                "touch_classification_change_count": comparison[
                    "touch_classification_change_count"
                ],
                "true_basis_validation": "unavailable",
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _rolling_times(start: time, end: time) -> tuple[time, ...]:
    anchor = datetime.combine(date(2000, 1, 1), start)
    limit = datetime.combine(date(2000, 1, 1), end)
    values = []
    while anchor <= limit:
        values.append(anchor.time())
        anchor += timedelta(minutes=30)
    return tuple(values)


def _parse_time(value: str) -> time:
    parts = [int(part) for part in value.split(":")]
    return time(*parts)


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _markdown(alignment: dict, semantics: dict, report_dir: Path) -> str:
    lines = [
        "# XAU Source Alignment and SD Semantics Audit",
        "",
        "Research-only. No signal or execution output.",
        "",
        f"- Vol2Vol sessions loaded: `{alignment['vol2vol_valid_session_count']}`",
        f"- XAU candle rows: `{alignment['xau_candle_row_count']}`",
        f"- Price source: `{alignment['price_source_label']}`",
        f"- Session coverage rows: `{len(alignment['session_coverage'])}`",
        f"- True GC/MGC basis validation: `{alignment['true_basis_validation']}`",
        "",
        "## Definitions",
    ]
    for key, value in semantics["definitions"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Results"])
    for item in semantics["summaries"]:
        lines.extend(
            [
                "",
                f"### {item['planning_mode']} / {item['mapping_mode']}",
                f"- Testable sessions: `{item['testable_session_count']}`",
                f"- Plan versions: `{item['testable_plan_version_count']}`",
                f"- Source gap p50/p95/max: `{item['source_alignment_p50_seconds']}` / "
                f"`{item['source_alignment_p95_seconds']}` / "
                f"`{item['source_alignment_max_seconds']}` seconds",
            ]
        )
        for label, stats in item["entry_definitions"].items():
            lines.append(
                f"- `{label}` touches=`{stats['touch_count']}` "
                f"sessions=`{stats['unique_touched_sessions']}` "
                f"return_0.5SD=`{stats['return_0_5sd_count']}`"
            )
    lines.extend(["", "## Preregistered Exit Backtest"])
    for experiment in alignment["preregistered_exit_backtest"]["experiments"]:
        lines.append(
            f"- `{experiment['planning_mode']} / {experiment['mapping_mode']}` "
            f"opportunities=`{experiment['unique_market_opportunity_count']}` "
            f"configurations=`{experiment['configuration_outcome_count']}`"
        )
        for summary in experiment["summary_by_strategy_and_cost"]:
            if summary["cost_points"] != 1.0:
                continue
            lines.append(
                f"  - Strategy `{summary['strategy_id']}` cost=1.0 "
                f"fills=`{summary['configuration_fill_count']}` "
                f"targets=`{summary['target_hit_count']}` "
                f"stops=`{summary['stop_hit_count']}` "
                f"net_expectancy=`{summary['net_expectancy_points']}`"
            )
    lines.extend(["", "## Coverage Exclusions"])
    for reason, count in alignment["unique_excluded_sessions_by_reason"].items():
        lines.append(f"- `{reason}`: `{count}` sessions")
    lines.extend(
        [
            "",
            "## Comparison",
            "- Touch classifications changed between mapping modes: "
            f"`{alignment['comparison']['touch_classification_change_count']}`",
            "- Rolling orders are cancel-and-replace because each plan window ends "
            "immediately before the next 30-minute checkpoint.",
            "- Cost-adjusted expectancy uses the preregistered A-D exit rules above.",
            "",
            "## Artifacts",
            f"- `{(report_dir.resolve() / 'source_alignment_audit.json').as_posix()}`",
            f"- `{(report_dir.resolve() / 'sd_semantics_comparison.json').as_posix()}`",
            f"- `{(report_dir.resolve() / 'preregistered_exit_backtest.json').as_posix()}`",
            "",
            "signal_allowed=false",
            "research_only=true",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
