from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau_vol2vol_history_walkforward import (
    XauHistorySourceMode,
    XauSdEntryLevel,
    XauSlMode,
    XauTpMode,
)
from src.xau_vol2vol_history_walkforward.history_client import load_history_payloads
from src.xau_vol2vol_history_walkforward.history_normalizer import (
    latest_range_by_session,
    latest_strikes_by_session,
    normalize_payload,
)
from src.xau_vol2vol_history_walkforward.range_plan_builder import (
    XauRangePlanBuildConfig,
    build_sd_mean_reversion_plans,
)
from src.xau_vol2vol_history_walkforward.report_store import (
    XauVol2VolHistoryWalkforwardReportStore,
    new_walkforward_run_id,
)
from src.xau_vol2vol_history_walkforward.statistics import build_walkforward_stats
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars,
    simulate_plans,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run research-only Vol2Vol history SD walk-forward preparation.",
    )
    parser.add_argument("--session-date-from", required=True)
    parser.add_argument("--session-date-to", required=True)
    parser.add_argument(
        "--history-source-mode",
        choices=[item.value for item in XauHistorySourceMode],
        required=True,
    )
    parser.add_argument("--history-file")
    parser.add_argument("--history-folder")
    parser.add_argument("--history-endpoint-template")
    parser.add_argument("--rate-limit-seconds", type=float, default=1.0)
    parser.add_argument("--price-bars-path")
    parser.add_argument("--cycle-label", default="manual")
    parser.add_argument(
        "--entry-sd",
        action="append",
        choices=[item.value for item in XauSdEntryLevel],
        default=[],
    )
    parser.add_argument(
        "--tp-mode",
        action="append",
        choices=[item.value for item in XauTpMode],
        default=[],
    )
    parser.add_argument(
        "--sl-mode",
        action="append",
        choices=[item.value for item in XauSlMode],
        default=[],
    )
    parser.add_argument("--include-one-sd", action="store_true")
    parser.add_argument("--minimum-oi-total", type=float)
    parser.add_argument("--wormhole-threshold-total", type=float, default=5.0)
    parser.add_argument(
        "--entry-touch-policy",
        choices=["touch", "close_through"],
        default="touch",
    )
    parser.add_argument(
        "--same-bar-policy",
        choices=["ambiguous", "conservative_stop_first", "optimistic_target_first"],
        default="ambiguous",
    )
    parser.add_argument("--simulation-end-time", default="23:00")
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--output-root")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    session_date_from = date.fromisoformat(args.session_date_from)
    session_date_to = date.fromisoformat(args.session_date_to)
    load_result = load_history_payloads(
        source_mode=XauHistorySourceMode(args.history_source_mode),
        session_date_from=session_date_from,
        session_date_to=session_date_to,
        history_file=Path(args.history_file) if args.history_file else None,
        history_folder=Path(args.history_folder) if args.history_folder else None,
        endpoint_template=args.history_endpoint_template,
        rate_limit_seconds=args.rate_limit_seconds,
    )

    strike_rows = []
    range_snapshots = []
    warnings = list(load_result.warnings)
    for payload in load_result.payloads:
        normalized_strikes, normalized_ranges, normalized_warnings = normalize_payload(payload)
        strike_rows.extend(normalized_strikes)
        range_snapshots.extend(normalized_ranges)
        warnings.extend(normalized_warnings)

    range_by_session = latest_range_by_session(range_snapshots)
    strikes_by_session = latest_strikes_by_session(strike_rows)
    entry_sds = _entry_sds(args.entry_sd, args.include_one_sd)
    config = XauRangePlanBuildConfig(
        cycle_label=args.cycle_label,
        entry_sds=tuple(entry_sds),
        tp_modes=tuple(XauTpMode(item) for item in args.tp_mode)
        if args.tp_mode
        else XauRangePlanBuildConfig().tp_modes,
        sl_modes=tuple(XauSlMode(item) for item in args.sl_mode)
        if args.sl_mode
        else XauRangePlanBuildConfig().sl_modes,
        wormhole_threshold_total=args.wormhole_threshold_total,
    )
    plans = []
    for session_date, range_snapshot in sorted(range_by_session.items()):
        if session_date_from <= session_date <= session_date_to:
            plans.extend(
                build_sd_mean_reversion_plans(
                    range_snapshot=range_snapshot,
                    strike_rows=strikes_by_session.get(session_date, []),
                    config=config,
                )
            )

    outcomes = []
    if args.price_bars_path:
        bars = load_traded_bars(Path(args.price_bars_path), timezone=args.timezone)
        simulation_end = _simulation_end(session_date_to, args.simulation_end_time, args.timezone)
        outcomes = simulate_plans(
            plans,
            bars,
            simulation_end=simulation_end,
            entry_touch_policy=args.entry_touch_policy,
            same_bar_policy=args.same_bar_policy,
        )
    else:
        warnings.append("No price bars supplied; Vol2Vol data preparation ran without simulation.")
    run_id = new_walkforward_run_id()
    stats = build_walkforward_stats(
        run_id=run_id,
        plans=plans,
        outcomes=outcomes,
        session_date_from=session_date_from,
        session_date_to=session_date_to,
    )
    report_store = XauVol2VolHistoryWalkforwardReportStore(
        reports_dir=Path(args.output_root) if args.output_root else None
    )
    report_dir = report_store.persist_run(
        stats=stats,
        range_snapshots=range_snapshots,
        strike_rows=strike_rows,
        plans=plans,
        outcomes=outcomes,
        raw_manifest={
            "source_mode": args.history_source_mode,
            "source_paths": [str(path) for path in load_result.source_paths],
            "warnings": warnings,
            "research_only": True,
            "signal_allowed": False,
        },
        overwrite=args.overwrite,
    )
    summary = {
        "run_id": run_id,
        "report_dir": report_dir.as_posix(),
        "plan_count": len(plans),
        "outcome_count": len(outcomes),
        "target_hit_count": stats.target_hit_count,
        "stop_hit_count": stats.stop_hit_count,
        "warnings": warnings,
        "signal_allowed": False,
        "research_only": True,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _entry_sds(values: list[str], include_one_sd: bool) -> list[XauSdEntryLevel]:
    selected = [XauSdEntryLevel(item) for item in values] if values else [
        XauSdEntryLevel.TWO_SD,
        XauSdEntryLevel.THREE_SD,
    ]
    if include_one_sd and XauSdEntryLevel.ONE_SD not in selected:
        selected.insert(0, XauSdEntryLevel.ONE_SD)
    return selected


def _simulation_end(session_date: date, value: str, timezone: str) -> datetime:
    hour, minute = [int(part) for part in value.split(":", maxsplit=1)]
    return datetime.combine(session_date, time(hour=hour, minute=minute), tzinfo=ZoneInfo(timezone))


if __name__ == "__main__":
    raise SystemExit(main())
