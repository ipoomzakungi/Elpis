from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from src.models.xau_vol2vol_history_walkforward import XauMappingMode
from src.xau_options_research.event_builder import build_raw_events
from src.xau_options_research.event_deduplication import deduplicate_events
from src.xau_options_research.event_study import build_event_study
from src.xau_options_research.experiment_registry import load_experiment_registry
from src.xau_options_research.feature_panel import build_checkpoint_rows
from src.xau_options_research.labels import label_events
from src.xau_options_research.negative_controls import build_negative_controls
from src.xau_options_research.report_store import XauOptionsResearchReportStore
from src.xau_options_research.strategy_simulator import run_preregistered_strategies
from src.xau_options_research.validation import build_validation_report, evidence_status
from src.xau_vol2vol_history_walkforward.data_lake import load_vol2vol_data_lake
from src.xau_vol2vol_history_walkforward.history_normalizer import normalize_payload
from src.xau_vol2vol_history_walkforward.oi_flow_audit import StrikeSnapshotIndex
from src.xau_vol2vol_history_walkforward.planning import select_planning_cycles
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the preregistered historical XAU intraday options research lab."
    )
    parser.add_argument("--session-date-from", default="2026-05-31")
    parser.add_argument("--session-date-to", default=date.today().isoformat())
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument("--price-bars-folder", default="data/imports/xau/dukascopy/xauusd/m1")
    parser.add_argument("--registry", default="config/xau_options_research_experiments_v1.json")
    parser.add_argument("--output-root", default="data/reports/xau_options_research")
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--bootstrap-iterations", type=int, default=500)
    parser.add_argument("--seed", type=int, default=32)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    date_from = date.fromisoformat(args.session_date_from)
    date_to = date.fromisoformat(args.session_date_to)
    registry = load_experiment_registry(Path(args.registry))
    load_result = load_vol2vol_data_lake(
        root=Path(args.vol2vol_data_root),
        session_date_from=date_from,
        session_date_to=date_to,
    )
    ranges = []
    strikes = []
    normalization_warnings = []
    for payload in load_result.payloads:
        normalized_strikes, normalized_ranges, warnings = normalize_payload(payload)
        strikes.extend(normalized_strikes)
        ranges.extend(normalized_ranges)
        normalization_warnings.extend(warnings)
    monthly_strikes = []
    monthly_path = Path(args.vol2vol_data_root) / "monthly_oi_20260708.json"
    if monthly_path.exists():
        monthly_payload = json.loads(monthly_path.read_text(encoding="utf-8"))
        monthly_strikes, _, monthly_warnings = normalize_payload(monthly_payload)
        normalization_warnings.extend(monthly_warnings)
    price_result = load_traded_bars_folder(Path(args.price_bars_folder), timezone=args.timezone)
    selections = []
    selection_issues: dict[str, dict[str, int]] = {}
    for mode, planning_times in (
        ("fixed_morning", (time(7, 0),)),
        ("rolling_30m", _rolling_times(time(7, 0), time(23, 30))),
    ):
        selected, issues = select_planning_cycles(
            range_snapshots=ranges,
            strike_rows=strikes,
            bars=price_result.bars,
            session_date_from=date_from,
            session_date_to=date_to,
            planning_times=planning_times,
            timezone=args.timezone,
            planning_mode=mode,
            day_end_time=time(23, 59, 59),
            require_complete_window=mode == "fixed_morning",
            require_one_sd=True,
            mapping_mode=XauMappingMode.SAME_TIME_BASIS,
            source_alignment_tolerance_seconds=300,
            snapshot_freshness_tolerance_seconds=1800,
            bar_interval_minutes=1,
            join_by_observed_trading_date=True,
        )
        selections.extend(selected)
        selection_issues[mode] = issues
    strike_index = StrikeSnapshotIndex(strikes)
    checkpoints = build_checkpoint_rows(
        selections,
        price_result.bars,
        strike_index,
        timezone=args.timezone,
        range_snapshots=ranges,
        monthly_strikes=monthly_strikes,
    )
    raw_events = build_raw_events(checkpoints, price_result.bars, timezone=args.timezone)
    annotated_events, episodes = deduplicate_events(raw_events, price_result.bars)
    labels = label_events(episodes, price_result.bars)
    event_study = build_event_study(
        labels,
        seed=args.seed,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    strategy_results = run_preregistered_strategies(episodes, price_result.bars)
    negative_controls = build_negative_controls(episodes, price_result.bars, seed=args.seed)
    valid_sessions = sorted({row["session_date"] for row in checkpoints})
    validation, holdout, trials = build_validation_report(
        strategy_results,
        valid_sessions,
        development_fraction=float(registry["development_fraction"]),
        seed=args.seed,
        bootstrap_iterations=args.bootstrap_iterations,
    )
    integrity = {
        "future_feature_violation_count": sum(
            bool(row["future_feature_violation"]) for row in checkpoints
        ),
        "event_before_feature_count": sum(
            datetime.fromisoformat(row["feature_timestamp"])
            > datetime.fromisoformat(row["event_timestamp"])
            for row in annotated_events
        ),
        "signal_allowed_violation_count": sum(
            row.get("signal_allowed") is not False
            for row in checkpoints + annotated_events + labels
        ),
    }
    integrity_count = sum(integrity.values())
    holdout_sessions = set(validation["holdout_sessions"])
    holdout_episodes = sum(row["session_date"] in holdout_sessions for row in episodes)
    statistical_support = _statistical_support(
        strategy_results,
        validation,
        holdout,
        negative_controls,
    )
    status = evidence_status(
        unique_episodes=len(episodes),
        holdout_episodes=holdout_episodes,
        sessions_with_events=len({row["session_date"] for row in episodes}),
        integrity_violations=integrity_count,
        statistical_support=statistical_support,
    )
    coverage = _feature_coverage(checkpoints, valid_sessions, selection_issues, integrity)
    run_id = f"xau_options_research_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    manifest = {
        "run_id": run_id,
        "registry_version": registry["registry_version"],
        "registry_hash": registry["registry_hash"],
        "experiments": registry["experiments"],
        "session_date_from": date_from.isoformat(),
        "session_date_to": date_to.isoformat(),
        "valid_sessions": valid_sessions,
        "warnings": load_result.warnings + price_result.warnings + normalization_warnings,
        "research_only": True,
        "signal_allowed": False,
    }
    handoff = _review_handoff(
        run_id=run_id,
        valid_sessions=valid_sessions,
        checkpoints=checkpoints,
        raw_events=annotated_events,
        episodes=episodes,
        labels=labels,
        validation=validation,
        holdout=holdout,
        strategy_results=strategy_results,
        negative_controls=negative_controls,
        coverage=coverage,
        integrity=integrity,
        trial_registry=trials,
        statistical_support=statistical_support,
        evidence=status,
        output_root=Path(args.output_root),
    )
    report_dir = XauOptionsResearchReportStore(Path(args.output_root)).persist(
        run_id=run_id,
        manifest=manifest,
        checkpoints=checkpoints,
        raw_events=annotated_events,
        episode_events=episodes,
        labels=labels,
        feature_coverage=coverage,
        event_study=event_study,
        strategy_results=strategy_results,
        negative_controls=negative_controls,
        validation_report=validation,
        holdout_report=holdout,
        trial_registry=trials,
        review_handoff=handoff,
        evidence_status=status,
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "report_dir": report_dir.resolve().as_posix(),
                "valid_session_count": len(valid_sessions),
                "checkpoint_count": len(checkpoints),
                "raw_event_count": len(annotated_events),
                "unique_episode_count": len(episodes),
                "development_session_count": validation["development_session_count"],
                "holdout_session_count": validation["holdout_session_count"],
                "evidence_status": status,
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


def _feature_coverage(
    rows: list[dict[str, Any]],
    valid_sessions: list[str],
    selection_issues: dict[str, dict[str, int]],
    integrity: dict[str, int],
) -> dict[str, Any]:
    fields = (
        "atm_iv",
        "oi_nearest_wall",
        "oi_change",
        "volume_nearest_wall",
        "volume_change",
        "basis_drift",
        "monthly_oi_confluence",
    )
    return {
        "valid_sessions": valid_sessions,
        "valid_session_count": len(valid_sessions),
        "checkpoint_count": len(rows),
        "field_coverage": {
            field: {
                "available_count": sum(row.get(field) is not None for row in rows),
                "missing_count": sum(row.get(field) is None for row in rows),
            }
            for field in fields
        },
        "selection_issues": selection_issues,
        "integrity": integrity,
        "nulls_preserved": True,
        "research_only": True,
        "signal_allowed": False,
    }


def _statistical_support(
    strategy_results: dict[str, Any],
    validation: dict[str, Any],
    holdout: dict[str, Any],
    negative_controls: dict[str, Any],
) -> bool:
    options_ids = {"MR1", "MR2", "MR3", "BO1", "PIN0"}
    positive_incremental = any(
        row["experiment_id"] in options_ids
        and row["matched_episode_count"] >= 15
        and row["mean_incremental_net_points"] is not None
        and row["mean_incremental_net_points"] > 0
        for row in strategy_results["incremental_value"]
    )
    positive_ci = any(
        row["experiment_id"] in options_ids
        and row["net_expectancy_ci95"] is not None
        and row["net_expectancy_ci95"][0] >= 0
        for row in validation["session_clustered_bootstrap"]
    )
    positive_holdout = any(
        row["experiment_id"] in options_ids
        and row["independent_session_count"] >= 3
        and row["net_expectancy_points"] is not None
        and row["net_expectancy_points"] > 0
        for row in holdout["summaries"]
    )
    controls_available = bool(negative_controls["controls"])
    return positive_incremental and positive_ci and positive_holdout and controls_available


def _review_handoff(**context: Any) -> str:
    strategy = context["strategy_results"]
    baseline = [
        row
        for row in strategy["summaries"]
        if row["spread_points"] == 1.0 and row["slippage_points_per_side"] == 0.0
    ]
    lines = [
        "# XAU Intraday Options Research Lab Review Handoff",
        "",
        "Retrospective historical research only. Not true-forward evidence.",
        "",
        f"- Valid sessions: `{len(context['valid_sessions'])}`",
        f"- Checkpoint rows: `{len(context['checkpoints'])}`",
        f"- Raw events: `{len(context['raw_events'])}`",
        f"- Unique episodes: `{len(context['episodes'])}`",
        f"- Development sessions: `{context['validation']['development_session_count']}`",
        f"- Holdout sessions: `{context['validation']['holdout_session_count']}`",
        f"- Labeled episodes: `{len(context['labels'])}`",
        f"- Integrity violations: `{sum(context['integrity'].values())}`",
        f"- Evidence status: `{context['evidence']}`",
        f"- Statistical support gate: `{context['statistical_support']}`",
        "- Episodes are deduplicated excursions; sessions remain the resampling unit.",
        "",
        "## Feature Coverage",
        "",
    ]
    for field, counts in context["coverage"]["field_coverage"].items():
        lines.append(
            f"- `{field}`: available=`{counts['available_count']}`, "
            f"missing=`{counts['missing_count']}`"
        )
    lines.extend(
        [
        "",
        "## Baseline Cost Results",
        "",
        ]
    )
    reported = set()
    for row in baseline:
        reported.add(row["experiment_id"])
        lines.append(
            f"- `{row['experiment_id']} / {row['planning_mode']} / TP {row['target_sd']}SD`: "
            f"episodes=`{row['unique_episode_count']}`, expectancy=`{row['net_expectancy_points']}`"
        )
    for experiment_id in ("MR0", "MR1", "MR2", "MR3", "BO0", "BO1", "PIN0"):
        if experiment_id not in reported:
            lines.append(f"- `{experiment_id}`: no qualifying observations")
    lines.extend(["", "## Matched Incremental Value", ""])
    for row in strategy["incremental_value"]:
        lines.append(
            f"- `{row['experiment_id']}` vs `{row['matched_control']}`: "
            f"matched=`{row['matched_episode_count']}`, "
            f"incremental=`{row['mean_incremental_net_points']}`"
        )
    lines.extend(["", "## Cost Sensitivity", "", *_cost_sensitivity_lines(strategy)])
    lines.extend(
        [
            "",
            "## Session Bootstrap Confidence Intervals",
            "",
            *_confidence_lines(context["validation"]),
            "",
            "## Multiple Testing",
            "",
            f"- Tracked trials: `{context['trial_registry']['trial_count']}`",
            "- Effective independent experiment families: "
            f"`{context['trial_registry']['effective_independent_experiment_families']}`",
            "- Raw p-values and Benjamini-Hochberg q-values are in `trial_registry.json`.",
        ]
    )
    control_names = [row["control"] for row in context["negative_controls"]["controls"]]
    lines.extend(
        [
            "",
            "## Controls and Safeguards",
            "",
            f"- Negative-control seed: `{context['negative_controls']['deterministic_seed']}`",
            f"- Negative controls executed: `{', '.join(control_names)}`",
            "- Cost grid: spreads 0.3/0.5/1.0/1.5; slippage 0.0/0.2/0.5 per side.",
            "- Cost scenarios do not multiply independent episode counts.",
            "- Holdout was not used for threshold selection.",
            "- No best strategy is selected.",
            "",
            "## Artifacts",
            "",
            *_artifact_lines(context),
            "",
            "research_only=true",
            "signal_allowed=false",
        ]
    )
    return "\n".join(lines) + "\n"


def _artifact_lines(context: dict[str, Any]) -> list[str]:
    root = context["output_root"] / context["run_id"]
    return [
        f"- `{(root / name).resolve().as_posix()}`"
        for name in (
            "experiment_manifest.json",
            "feature_panel.parquet",
            "checkpoint_rows.parquet",
            "event_rows.parquet",
            "event_labels.parquet",
            "feature_coverage.json",
            "event_study.json",
            "event_study.md",
            "strategy_results.json",
            "strategy_results.md",
            "negative_controls.json",
            "validation_report.json",
            "holdout_report.json",
            "trial_registry.json",
            "review_handoff.md",
            "metadata.json",
        )
    ]


def _cost_sensitivity_lines(strategy: dict[str, Any]) -> list[str]:
    grouped: dict[tuple[str, str, float], list[float]] = {}
    for row in strategy["summaries"]:
        expectancy = row.get("net_expectancy_points")
        if expectancy is None:
            continue
        key = (row["experiment_id"], row["planning_mode"], row["target_sd"])
        grouped.setdefault(key, []).append(float(expectancy))
    return [
        f"- `{key[0]} / {key[1]} / TP {key[2]}SD`: "
        f"expectancy range=`{min(values)}` to `{max(values)}` points"
        for key, values in sorted(grouped.items())
    ]


def _confidence_lines(validation: dict[str, Any]) -> list[str]:
    return [
        f"- `{row['experiment_id']} / TP {row['target_sd']}SD`: "
        f"sessions=`{row['session_count']}`, CI95=`{row['net_expectancy_ci95']}`"
        for row in validation["session_clustered_bootstrap"]
    ]


if __name__ == "__main__":
    raise SystemExit(main())
