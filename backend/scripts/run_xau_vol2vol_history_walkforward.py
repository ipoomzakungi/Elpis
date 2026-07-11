from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, time
from pathlib import Path

from src.config import get_settings
from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import (
    XauHistorySourceMode,
    XauMappingMode,
    XauSdEntryLevel,
    XauSdMeanReversionPlan,
    XauSlMode,
    XauTimeExitPolicy,
    XauTpMode,
    XauVol2VolRangeDeskSnapshot,
    XauWalkforwardTradeStatus,
)
from src.xau_market_context.price_loader import latest_bar_at_or_before
from src.xau_vol2vol_history_walkforward.baselines import (
    BASELINES,
    build_predefined_baseline_plans,
)
from src.xau_vol2vol_history_walkforward.conservative_statistics import (
    build_conservative_statistics,
)
from src.xau_vol2vol_history_walkforward.coverage_audit import (
    build_coverage_and_integrity_audit,
    integrity_blocks_backtest,
    persist_audit_report,
)
from src.xau_vol2vol_history_walkforward.data_lake import load_vol2vol_data_lake
from src.xau_vol2vol_history_walkforward.history_client import load_history_payloads
from src.xau_vol2vol_history_walkforward.history_normalizer import normalize_payload
from src.xau_vol2vol_history_walkforward.morning_path_analysis import (
    build_daily_sd_paths,
    build_opportunity_map,
)
from src.xau_vol2vol_history_walkforward.planning import (
    XauPlanningSelection,
    planning_plan_metadata,
    select_planning_cycles,
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
    XauPriceBarFolderLoadResult,
    load_traded_bars,
    load_traded_bars_folder,
    simulate_plans,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run research-only Vol2Vol history SD walk-forward preparation.",
    )
    parser.add_argument("--session-date-from")
    parser.add_argument("--session-date-to")
    parser.add_argument(
        "--history-source-mode",
        choices=[item.value for item in XauHistorySourceMode],
        default=XauHistorySourceMode.UNAVAILABLE.value,
    )
    parser.add_argument("--history-file")
    parser.add_argument("--history-folder")
    parser.add_argument("--history-endpoint-template")
    parser.add_argument("--rate-limit-seconds", type=float, default=1.0)
    parser.add_argument("--use-data-lake", action="store_true")
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument("--monthly-target")
    parser.add_argument("--price-bars-path")
    parser.add_argument("--price-bars-folder")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--basis-tolerance-seconds", type=int, default=300)
    parser.add_argument(
        "--mapping-mode",
        choices=[item.value for item in XauMappingMode],
        default=XauMappingMode.DISTANCE_REANCHORED.value,
    )
    parser.add_argument("--source-alignment-tolerance-seconds", type=int, default=300)
    parser.add_argument("--snapshot-freshness-tolerance-seconds", type=int, default=1800)
    parser.add_argument("--cycle-label", default="manual")
    parser.add_argument(
        "--baseline-config",
        action="append",
        choices=sorted(BASELINES),
        default=[],
    )
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
        default="conservative_stop_first",
    )
    parser.add_argument(
        "--planning-mode",
        choices=["fixed_morning", "scheduled_refresh"],
        default="scheduled_refresh",
    )
    parser.add_argument("--morning-plan-time", default="07:00")
    parser.add_argument("--day-end-time", default="23:59:59")
    parser.add_argument("--refresh-time", action="append", default=[])
    parser.add_argument("--planning-time", action="append", default=[])
    parser.add_argument("--simulation-end-time", default="23:00")
    parser.add_argument("--spread-points", action="append", type=float, default=[])
    parser.add_argument("--slippage-points", type=float, default=0.0)
    parser.add_argument(
        "--time-exit-policy",
        choices=[item.value for item in XauTimeExitPolicy],
        default=XauTimeExitPolicy.CLOSE_AT_CYCLE_END.value,
    )
    parser.add_argument("--bootstrap-seed", type=int, default=31)
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--output-root")
    parser.add_argument("--comparison-report")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if args.price_bars_path and args.price_bars_folder:
        parser.error("Choose only one of --price-bars-path or --price-bars-folder")
    price_result = _load_price_inputs(args)
    if args.audit_only:
        if not args.use_data_lake:
            parser.error("--audit-only requires --use-data-lake")
        coverage, integrity = build_coverage_and_integrity_audit(
            vol2vol_root=Path(args.vol2vol_data_root),
            price_result=price_result,
            timezone=args.timezone,
            basis_tolerance_seconds=args.basis_tolerance_seconds,
        )
        audit_dir = persist_audit_report(
            output_root=(
                Path(args.output_root) if args.output_root else get_settings().data_reports_path
            ),
            coverage=coverage,
            integrity=integrity,
        )
        print(
            json.dumps(
                {
                    "audit_dir": audit_dir.as_posix(),
                    "coverage": coverage,
                    "integrity": integrity,
                    "research_only": True,
                    "signal_allowed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.session_date_from or not args.session_date_to:
        parser.error("--session-date-from and --session-date-to are required for a backtest")
    session_date_from = date.fromisoformat(args.session_date_from)
    session_date_to = date.fromisoformat(args.session_date_to)
    if args.use_data_lake:
        load_result = load_vol2vol_data_lake(
            root=Path(args.vol2vol_data_root),
            session_date_from=session_date_from,
            session_date_to=session_date_to,
            monthly_target=args.monthly_target,
        )
    else:
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

    bars = price_result.bars
    warnings.extend(price_result.warnings)
    planning_values = (
        [args.morning_plan_time]
        if args.planning_mode == "fixed_morning"
        else (args.refresh_time or args.planning_time or ["10:00", "19:00"])
    )
    planning_times = tuple(_parse_hhmm(value) for value in planning_values)
    selections, planning_issues = select_planning_cycles(
        range_snapshots=range_snapshots,
        strike_rows=strike_rows,
        bars=bars,
        session_date_from=session_date_from,
        session_date_to=session_date_to,
        planning_times=planning_times,
        timezone=args.timezone,
        basis_tolerance_seconds=args.basis_tolerance_seconds,
        planning_mode=args.planning_mode,
        day_end_time=_parse_hhmmss(args.day_end_time),
        require_complete_window=args.planning_mode == "fixed_morning",
        require_one_sd=args.planning_mode == "fixed_morning",
        mapping_mode=XauMappingMode(args.mapping_mode),
        source_alignment_tolerance_seconds=(
            args.source_alignment_tolerance_seconds
        ),
        snapshot_freshness_tolerance_seconds=(
            args.snapshot_freshness_tolerance_seconds
        ),
    )
    plans = (
        build_predefined_baseline_plans(selections, args.baseline_config)
        if args.baseline_config
        else _build_custom_plans(selections, args)
    )
    if args.use_data_lake:
        coverage, integrity = build_coverage_and_integrity_audit(
            vol2vol_root=Path(args.vol2vol_data_root),
            price_result=price_result,
            timezone=args.timezone,
            basis_tolerance_seconds=args.basis_tolerance_seconds,
        )
    else:
        coverage = _empty_coverage(range_snapshots, bars)
        integrity = _empty_integrity()
    integrity.update(
        {
            "future_snapshot_used_count": planning_issues["future_snapshot_used_count"],
            "plans_missing_basis_count": planning_issues["plans_missing_basis_count"],
            "plans_missing_sd_count": planning_issues["plans_missing_sd_count"],
        }
    )
    coverage.update(
        {
            "planning_mode": args.planning_mode,
            "mapping_mode": args.mapping_mode,
            "planning_selection_issue_counts": planning_issues,
            "fully_testable_morning_sessions": (
                len({item.session_date for item in selections})
                if args.planning_mode == "fixed_morning"
                else None
            ),
        }
    )
    blockers = integrity_blocks_backtest(integrity)
    if blockers:
        audit_dir = persist_audit_report(
            output_root=(
                Path(args.output_root) if args.output_root else get_settings().data_reports_path
            ),
            coverage=coverage,
            integrity=integrity,
        )
        parser.error(f"Backtest blocked by integrity gates ({', '.join(blockers)}); {audit_dir}")
    outcomes = []
    if bars:
        spread_scenarios = args.spread_points or (
            [0.0, 0.3, 0.5, 1.0] if args.baseline_config else [0.0]
        )
        for spread in spread_scenarios:
            outcomes.extend(
                simulate_plans(
                    plans,
                    bars,
                    entry_touch_policy=args.entry_touch_policy,
                    same_bar_policy=args.same_bar_policy,
                    cost_points=spread + args.slippage_points,
                    time_exit_policy=XauTimeExitPolicy(args.time_exit_policy),
                )
            )
    else:
        warnings.append("No price bars supplied; Vol2Vol data preparation ran without simulation.")
    _update_outcome_integrity(integrity, plans, outcomes)
    post_simulation_blockers = integrity_blocks_backtest(integrity)
    if post_simulation_blockers:
        audit_dir = persist_audit_report(
            output_root=(
                Path(args.output_root) if args.output_root else get_settings().data_reports_path
            ),
            coverage=coverage,
            integrity=integrity,
        )
        parser.error(
            "Backtest blocked after simulation by integrity gates "
            f"({', '.join(post_simulation_blockers)}); {audit_dir}"
        )
    run_id = new_walkforward_run_id()
    stats_outcomes = _base_cost_outcomes(outcomes)
    stats = build_walkforward_stats(
        run_id=run_id,
        plans=plans,
        outcomes=stats_outcomes,
        session_date_from=session_date_from,
        session_date_to=session_date_to,
    )
    report_store = XauVol2VolHistoryWalkforwardReportStore(
        reports_dir=Path(args.output_root) if args.output_root else None
    )
    conservative = build_conservative_statistics(
        outcomes,
        bootstrap_seed=args.bootstrap_seed,
    )
    daily_paths = (
        build_daily_sd_paths(selections, bars)
        if args.planning_mode == "fixed_morning"
        else []
    )
    opportunities, opportunity_stats = build_opportunity_map(
        daily_paths,
        plans,
        outcomes,
    )
    comparison_report = _summarize_comparison_report(
        Path(args.comparison_report) if args.comparison_report else None
    )
    collection_manifest = _load_optional_json(
        Path(args.vol2vol_data_root) / "catalog" / "collection_manifest.json"
    )
    expected_report_dir = report_store.report_dir(run_id)
    review_handoff = _build_review_handoff(
        report_dir=expected_report_dir,
        coverage=coverage,
        integrity=integrity,
        stats=stats,
        conservative=conservative,
        plans=plans,
        planning_mode=args.planning_mode,
        opportunity_stats=opportunity_stats,
        comparison_report=comparison_report,
    )
    report_dir = report_store.persist_run(
        stats=stats,
        range_snapshots=range_snapshots,
        strike_rows=strike_rows,
        plans=plans,
        outcomes=outcomes,
        raw_manifest={
            "source_mode": "data_lake" if args.use_data_lake else args.history_source_mode,
            "source_paths": [str(path) for path in load_result.source_paths],
            "warnings": warnings,
            "research_only": True,
            "signal_allowed": False,
        },
        additional_artifacts={
            "collection_manifest.json": collection_manifest,
            "coverage_audit.json": coverage,
            "integrity_report.json": integrity,
            "development_stats.json": conservative["development_stats"],
            "holdout_stats.json": conservative["holdout_stats"],
            "config_comparison.json": conservative["config_comparison"],
            "daily_path_analysis.json": [
                item.model_dump(mode="json") for item in daily_paths
            ],
            "opportunity_map.json": [
                item.model_dump(mode="json") for item in opportunities
            ],
            "opportunity_stats.json": opportunity_stats,
            "comparison_report.json": comparison_report,
        },
        review_handoff_markdown=review_handoff,
        overwrite=args.overwrite,
    )
    summary = {
        "run_id": run_id,
        "report_dir": report_dir.as_posix(),
        "plan_count": len(plans),
        "outcome_count": len(outcomes),
        "target_hit_count": stats.target_hit_count,
        "stop_hit_count": stats.stop_hit_count,
        "valid_session_count": coverage.get("collected_valid_session_count", 0),
        "overlap_session_count": coverage.get("overlap_session_count", 0),
        "fill_count": stats.triggered_count,
        "holdout_fill_count": _holdout_fill_count(conservative["holdout_stats"]),
        "planning_mode": args.planning_mode,
        "mapping_mode": args.mapping_mode,
        "testable_morning_sessions": opportunity_stats["testable_morning_sessions"],
        "sessions_reaching_either_2sd": opportunity_stats[
            "sessions_reaching_either_2sd"
        ],
        "sessions_reaching_either_3sd": opportunity_stats[
            "sessions_reaching_either_3sd"
        ],
        "unique_2sd_opportunities": opportunity_stats[
            "unique_2sd_opportunity_count"
        ],
        "unique_3sd_opportunities": opportunity_stats[
            "unique_3sd_opportunity_count"
        ],
        "configuration_fill_count": opportunity_stats["configuration_fill_count"],
        "evidence_status": opportunity_stats["evidence_status"],
        "comparison_report": comparison_report,
        "integrity": integrity,
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


def _enrich_range_snapshots_with_bars(
    snapshots: list[XauVol2VolRangeDeskSnapshot],
    bars: list[XauPriceBar],
) -> list[XauVol2VolRangeDeskSnapshot]:
    enriched: list[XauVol2VolRangeDeskSnapshot] = []
    for snapshot in snapshots:
        if snapshot.cfd_open is not None or snapshot.future_open is None:
            enriched.append(snapshot)
            continue
        bar = latest_bar_at_or_before(bars, snapshot.observed_at)
        if bar is None:
            enriched.append(snapshot)
            continue
        cfd_open = bar.close
        diff = snapshot.future_open - cfd_open
        enriched.append(snapshot.model_copy(update={"cfd_open": cfd_open, "diff": diff}))
    return enriched


def _has_sd_plan_inputs(snapshot: XauVol2VolRangeDeskSnapshot) -> bool:
    return any(
        value is not None
        for value in (
            snapshot.cfd_buy_1sd,
            snapshot.cfd_buy_2sd,
            snapshot.cfd_buy_3sd,
            snapshot.cfd_sell_1sd,
            snapshot.cfd_sell_2sd,
            snapshot.cfd_sell_3sd,
            snapshot.future_buy_1sd,
            snapshot.future_buy_2sd,
            snapshot.future_buy_3sd,
            snapshot.future_sell_1sd,
            snapshot.future_sell_2sd,
            snapshot.future_sell_3sd,
        )
    )


def _parse_hhmm(value: str) -> time:
    hour, minute = [int(part) for part in value.split(":", maxsplit=1)]
    return time(hour=hour, minute=minute)


def _parse_hhmmss(value: str) -> time:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        return time(hour=parts[0], minute=parts[1])
    if len(parts) == 3:
        return time(hour=parts[0], minute=parts[1], second=parts[2])
    raise ValueError("time must use HH:MM or HH:MM:SS")


def _load_price_inputs(args: argparse.Namespace) -> XauPriceBarFolderLoadResult:
    if args.price_bars_folder:
        return load_traded_bars_folder(Path(args.price_bars_folder), timezone=args.timezone)
    if args.price_bars_path:
        path = Path(args.price_bars_path)
        return XauPriceBarFolderLoadResult(
            bars=load_traded_bars(path, timezone=args.timezone),
            source_paths=[path],
        )
    return XauPriceBarFolderLoadResult()


def _build_custom_plans(
    selections: list[XauPlanningSelection],
    args: argparse.Namespace,
) -> list[XauSdMeanReversionPlan]:
    plans: list[XauSdMeanReversionPlan] = []
    entry_sds = _entry_sds(args.entry_sd, args.include_one_sd)
    for selection in selections:
        generated = build_sd_mean_reversion_plans(
            range_snapshot=selection.range_snapshot,
            strike_rows=selection.strike_rows,
            config=XauRangePlanBuildConfig(
                cycle_label=selection.cycle_label,
                entry_sds=tuple(entry_sds),
                tp_modes=(
                    tuple(XauTpMode(item) for item in args.tp_mode)
                    if args.tp_mode
                    else XauRangePlanBuildConfig().tp_modes
                ),
                sl_modes=(
                    tuple(XauSlMode(item) for item in args.sl_mode)
                    if args.sl_mode
                    else XauRangePlanBuildConfig().sl_modes
                ),
                wormhole_threshold_total=args.wormhole_threshold_total,
            ),
        )
        for plan in generated:
            plans.append(
                plan.model_copy(
                    update={
                        "selected_vol2vol_snapshot_time": selection.range_snapshot.observed_at,
                        "selected_xau_price_time": selection.selected_xau_price_time,
                        "basis_alignment_seconds": selection.basis_alignment_seconds,
                        "plan_created_at": selection.planning_at,
                        "simulation_window_start": selection.simulation_window_start,
                        "simulation_window_end": selection.simulation_window_end,
                        **planning_plan_metadata(selection),
                    }
                )
            )
    return plans


def _update_outcome_integrity(
    integrity: dict,
    plans: list[XauSdMeanReversionPlan],
    outcomes: list,
) -> None:
    plan_by_id = {item.plan_id: item for item in plans}
    integrity_outcomes = _base_cost_outcomes(outcomes)
    integrity["trigger_before_plan_count"] = sum(
        bool(
            outcome.triggered_at
            and plan_by_id.get(outcome.plan_id)
            and plan_by_id[outcome.plan_id].plan_created_at
            and outcome.triggered_at < plan_by_id[outcome.plan_id].plan_created_at
        )
        for outcome in integrity_outcomes
    )
    integrity["future_snapshot_used_count"] = sum(
        bool(
            plan.selected_vol2vol_snapshot_time
            and plan.plan_created_at
            and plan.selected_vol2vol_snapshot_time > plan.plan_created_at
        )
        for plan in plans
    )
    integrity["plans_without_bars_in_window_count"] = sum(
        outcome.window_alignment_status.value == "no_bars_in_window"
        for outcome in integrity_outcomes
    )
    integrity["same_bar_ambiguous_count"] = sum(
        outcome.same_bar_ambiguous for outcome in integrity_outcomes
    )
    integrity["unavailable_outcomes_count"] = sum(
        outcome.status == XauWalkforwardTradeStatus.UNAVAILABLE
        for outcome in integrity_outcomes
    )


def _empty_coverage(
    snapshots: list[XauVol2VolRangeDeskSnapshot],
    bars: list[XauPriceBar],
) -> dict:
    dates = sorted({item.session_date for item in snapshots})
    return {
        "advertised_vol2vol_session_count": len(dates),
        "collected_valid_session_count": len(dates),
        "earliest_valid_vol2vol_date": dates[0].isoformat() if dates else None,
        "latest_valid_vol2vol_date": dates[-1].isoformat() if dates else None,
        "xau_candle_row_count": len(bars),
        "overlap_session_count": len(dates),
        "research_only": True,
        "signal_allowed": False,
    }


def _empty_integrity() -> dict:
    return {
        "requested_returned_date_mismatch_count": 0,
        "duplicate_snapshot_count": 0,
        "duplicate_candle_timestamp_count": 0,
        "out_of_order_timestamp_count": 0,
        "trigger_before_plan_count": 0,
        "future_snapshot_used_count": 0,
        "plans_missing_basis_count": 0,
        "plans_missing_sd_count": 0,
        "plans_without_bars_in_window_count": 0,
        "same_bar_ambiguous_count": 0,
        "unavailable_outcomes_count": 0,
        "research_only": True,
        "signal_allowed": False,
    }


def _load_optional_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_optional_json_list(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _holdout_fill_count(holdout_stats: dict) -> int:
    return sum(int(item.get("fill_count") or 0) for item in holdout_stats.get("groups", []))


def _summarize_comparison_report(report_dir: Path | None) -> dict:
    if report_dir is None:
        return {
            "report_dir": None,
            "available": False,
            "research_only": True,
            "signal_allowed": False,
        }
    plans_payload = _load_optional_json_list(report_dir / "plans.json")
    outcomes_payload = _load_optional_json_list(report_dir / "outcomes.json")
    costs = [float(item.get("cost_points") or 0) for item in outcomes_payload]
    minimum_cost = min(costs, default=0.0)
    filled_statuses = {
        "target_hit",
        "stop_hit",
        "expired",
        "time_exit_profit",
        "time_exit_loss",
        "ambiguous",
    }
    base_fills = [
        item
        for item in outcomes_payload
        if float(item.get("cost_points") or 0) == minimum_cost
        and item.get("status") in filled_statuses
    ]
    opportunity_keys = {
        (
            item.get("session_date"),
            item.get("cycle_label"),
            item.get("side"),
            item.get("entry_sd"),
            round(float(item.get("entry_level") or 0), 4),
        )
        for item in base_fills
    }
    return {
        "report_dir": report_dir.resolve().as_posix(),
        "available": bool(plans_payload or outcomes_payload),
        "planning_mode": "existing_1000_1900",
        "testable_sessions": len({item.get("session_date") for item in plans_payload}),
        "unique_market_opportunities": len(opportunity_keys),
        "configuration_fills": len(base_fills),
        "cost_scenario_filled_rows": sum(
            item.get("status") in filled_statuses for item in outcomes_payload
        ),
        "research_only": True,
        "signal_allowed": False,
    }


def _base_cost_outcomes(outcomes: list) -> list:
    if not outcomes:
        return []
    minimum_cost = min(item.cost_points for item in outcomes)
    return [item for item in outcomes if item.cost_points == minimum_cost]


def _build_review_handoff(
    *,
    report_dir: Path,
    coverage: dict,
    integrity: dict,
    stats,
    conservative: dict,
    plans: list[XauSdMeanReversionPlan],
    planning_mode: str,
    opportunity_stats: dict,
    comparison_report: dict,
) -> str:
    holdout_fills = _holdout_fill_count(conservative["holdout_stats"])
    comparison = conservative["config_comparison"].get("groups", [])
    tested_dates = sorted({plan.session_date for plan in plans})
    resolved_report_dir = report_dir.resolve()
    lines = [
        "# XAU Vol2Vol Fixed-Morning Walk-Forward Review",
        "",
        "Research-only. Not a buy/sell signal.",
        "",
        "## Coverage",
        f"- Advertised sessions: `{coverage.get('advertised_vol2vol_session_count')}`",
        f"- Valid sessions: `{coverage.get('collected_valid_session_count')}`",
        f"- Date range: `{coverage.get('earliest_valid_vol2vol_date')}` to "
        f"`{coverage.get('latest_valid_vol2vol_date')}`",
        f"- XAU candles: `{coverage.get('xau_candle_row_count')}`",
        f"- Overlap sessions: `{coverage.get('overlap_session_count')}`",
        f"- Independently tested sessions: `{len(tested_dates)}`",
        f"- Planning mode: `{planning_mode}`",
        f"- Fully testable morning sessions: "
        f"`{opportunity_stats['testable_morning_sessions']}`",
        f"- Tested date range: `{tested_dates[0] if tested_dates else None}` to "
        f"`{tested_dates[-1] if tested_dates else None}`",
        "",
        "## Integrity",
        f"- Requested/returned mismatches: "
        f"`{integrity.get('requested_returned_date_mismatch_count')}`",
        f"- Future snapshots used: `{integrity.get('future_snapshot_used_count')}`",
        f"- Triggers before plans: `{integrity.get('trigger_before_plan_count')}`",
        f"- Missing basis plans: `{integrity.get('plans_missing_basis_count')}`",
        f"- Missing SD plans: `{integrity.get('plans_missing_sd_count')}`",
        "",
        "## Results",
        f"- Plans: `{stats.plan_count}`",
        f"- Sessions reaching either 2SD: "
        f"`{opportunity_stats['sessions_reaching_either_2sd']}`",
        f"- Sessions reaching either 3SD: "
        f"`{opportunity_stats['sessions_reaching_either_3sd']}`",
        f"- Unique 2SD opportunities: "
        f"`{opportunity_stats['unique_2sd_opportunity_count']}`",
        f"- Unique 3SD opportunities: "
        f"`{opportunity_stats['unique_3sd_opportunity_count']}`",
        f"- Filled market opportunities: "
        f"`{opportunity_stats['filled_opportunity_count']}`",
        f"- Configuration fills: `{opportunity_stats['configuration_fill_count']}`",
        f"- Cost-scenario filled rows: "
        f"`{opportunity_stats['cost_scenario_filled_row_count']}`",
        f"- Cost-scenario outcome rows: `{sum(item['outcome_count'] for item in comparison)}`",
        f"- Holdout fills across grouped scenarios: `{holdout_fills}`",
        f"- Net expectancy points: `{stats.net_expectancy_points}`",
        f"- Maximum cumulative drawdown points: "
        f"`{stats.maximum_cumulative_drawdown_points}`",
        f"- Evidence status: `{opportunity_stats['evidence_status']}`",
        "",
        "## Former 10:00/19:00 Comparison",
        f"- Report: `{comparison_report.get('report_dir')}`",
        f"- Testable sessions: `{comparison_report.get('testable_sessions')}`",
        f"- Unique market opportunities: "
        f"`{comparison_report.get('unique_market_opportunities')}`",
        f"- Configuration fills: `{comparison_report.get('configuration_fills')}`",
        "- Planning modes are separate experiments; their counts are not combined.",
        "",
        "## Baseline Comparison",
    ]
    for item in comparison:
        if item["fill_count"] == 0:
            continue
        lines.append(
            "- `{baseline} cost={cost} side={side} cycle={cycle}` fills=`{fills}` "
            "net_expectancy=`{expectancy}` provisional=`{provisional}`".format(
                baseline=item["baseline_config"],
                cost=item["cost_points"],
                side=item["side"],
                cycle=item["cycle_label"],
                fills=item["fill_count"],
                expectancy=item["net_expectancy_points"],
                provisional=item["provisional"],
            )
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "- Retained Vol2Vol sessions are a small rolling sample.",
            "- Snapshot count is not independent trade count.",
            "- No result establishes a durable edge or live readiness.",
            "- Monthly OI and intraday flow are labels only in this baseline.",
            "",
            "## Artifacts",
            f"- Review: `{(resolved_report_dir / 'review_handoff.md').as_posix()}`",
            f"- Stats: `{(resolved_report_dir / 'stats.json').as_posix()}`",
            f"- Outcomes: `{(resolved_report_dir / 'outcomes.json').as_posix()}`",
            f"- Daily paths: "
            f"`{(resolved_report_dir / 'daily_path_analysis.json').as_posix()}`",
            f"- Opportunities: "
            f"`{(resolved_report_dir / 'opportunity_map.json').as_posix()}`",
            f"- Integrity: `{(resolved_report_dir / 'integrity_report.json').as_posix()}`",
            "",
            "signal_allowed=false",
            "research_only=true",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
