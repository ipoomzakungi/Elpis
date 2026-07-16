from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from src.xau_options_research.audit_report_store import XauOptionsFeatureAuditReportStore
from src.xau_options_research.candidate_validation import (
    build_candidate_manifest,
    build_validation_v2_status,
    load_candidate_registry,
)
from src.xau_options_research.clustered_inference import build_clustered_inference_audit
from src.xau_options_research.event_independence import (
    build_event_independence_audit,
    candidate_summaries,
)
from src.xau_options_research.feature_validity import build_feature_semantics_audit
from src.xau_options_research.matched_controls import build_matched_negative_control_report
from src.xau_vol2vol_history_walkforward.data_lake import load_vol2vol_data_lake
from src.xau_vol2vol_history_walkforward.history_normalizer import normalize_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit Feature 032 semantics, independence, inference, and candidates."
    )
    parser.add_argument("--source-report")
    parser.add_argument("--source-root", default="data/reports/xau_options_research")
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--candidate-registry", default="config/xau_options_candidate_validation_v2.json"
    )
    parser.add_argument("--output-root", default="data/reports/xau_options_feature_audit")
    parser.add_argument("--permutations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=32)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = (
        Path(args.source_report) if args.source_report else _latest_complete(Path(args.source_root))
    )
    manifest = _read_json(source / "experiment_manifest.json")
    checkpoints = pl.read_parquet(source / "feature_panel.parquet").to_dicts()
    raw_events = pl.read_parquet(source / "event_rows.parquet").to_dicts()
    episodes = pl.read_parquet(source / "event_labels.parquet").to_dicts()
    strategy = _read_json(source / "strategy_results.json")
    load_result = load_vol2vol_data_lake(
        root=Path(args.vol2vol_data_root),
        session_date_from=date.fromisoformat(manifest["session_date_from"]),
        session_date_to=date.fromisoformat(manifest["session_date_to"]),
    )
    strikes = []
    ranges = []
    for payload in load_result.payloads:
        normalized_strikes, normalized_ranges, _ = normalize_payload(payload)
        strikes.extend(normalized_strikes)
        ranges.extend(normalized_ranges)
    feature_audit = build_feature_semantics_audit(checkpoints, ranges, strikes)
    independence, revised = build_event_independence_audit(raw_events, episodes, strategy)
    inference = build_clustered_inference_audit(
        revised["outcomes"], seed=args.seed, iterations=args.permutations
    )
    controls = build_matched_negative_control_report(
        revised["outcomes"], episodes, seed=args.seed, permutations=args.permutations
    )
    registry = load_candidate_registry(Path(args.candidate_registry))
    candidate_manifest = build_candidate_manifest(registry, controls)
    validation_v2 = build_validation_v2_status(revised["outcomes"], candidate_manifest)
    revised_results = {
        **revised,
        "candidate_summaries": candidate_summaries(revised["outcomes"]),
        "validation_v2": validation_v2,
        "evidence_status": "insufficient_sample",
    }
    integrity = {
        "source_report": source.resolve().as_posix(),
        "source_future_feature_violation_count": sum(
            bool(row.get("future_feature_violation")) for row in checkpoints
        ),
        "matched_control_count_violation_count": sum(
            not row["matched_counts_equal"] for row in controls["oi_matched_controls"]
        ),
        "validation_v2_pre_cutoff_row_count": validation_v2["pre_cutoff_row_count"],
        "inference_consistency_violation_count": inference["inference_consistency_violation_count"],
        "research_only": True,
        "signal_allowed": False,
    }
    run_id = f"xau_options_feature_audit_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    payloads = {
        "feature_semantics_audit": feature_audit,
        "event_independence_audit": independence,
        "clustered_inference_audit": inference,
        "matched_negative_control_report": controls,
        "candidate_manifest_v2": candidate_manifest,
        "revised_strategy_results": revised_results,
        "integrity_report": integrity,
    }
    handoff = _review_handoff(run_id, Path(args.output_root), payloads)
    report_dir = XauOptionsFeatureAuditReportStore(Path(args.output_root)).persist(
        run_id=run_id, payloads=payloads, handoff=handoff
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "report_dir": report_dir.resolve().as_posix(),
                "oi_change_status": feature_audit["oi_change_status"],
                "intraday_volume_semantics": feature_audit["intraday_volume"]["semantics"],
                "non_overlapping_opportunity_count": independence[
                    "non_overlapping_tradable_opportunity_count"
                ],
                "mr2_beats_controls": controls["mr2_beats_controls"],
                "inference_consistency_violations": inference[
                    "inference_consistency_violation_count"
                ],
                "evidence_status": "insufficient_sample",
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _latest_complete(root: Path) -> Path:
    candidates = [
        path
        for path in root.glob("xau_options_research_*")
        if (path / "experiment_manifest.json").exists()
        and (path / "strategy_results.json").exists()
        and (path / "event_labels.parquet").exists()
    ]
    if not candidates:
        raise FileNotFoundError(f"No complete Feature 032 report under {root}")
    return max(candidates, key=lambda path: path.name)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _review_handoff(
    run_id: str,
    output_root: Path,
    payloads: dict[str, dict[str, Any]],
) -> str:
    feature = payloads["feature_semantics_audit"]
    independence = payloads["event_independence_audit"]
    inference = payloads["clustered_inference_audit"]
    controls = payloads["matched_negative_control_report"]
    candidates = payloads["candidate_manifest_v2"]
    revised = payloads["revised_strategy_results"]
    root = (output_root / run_id).resolve()
    lines = [
        "# Feature 032A Review Handoff",
        "",
        "Historical feature-validity audit only. Not true-forward or execution evidence.",
        "",
        f"- OI Change status: `{feature['oi_change_status']}`",
        f"- Intraday volume semantics: `{feature['intraday_volume']['semantics']}`",
        "- IV actual update count: "
        f"`{feature['iv_update_semantics']['actual_value_update_count']}`",
        "- IV median actual update interval minutes: "
        f"`{feature['iv_update_semantics']['median_actual_update_interval_minutes']}`",
        "- OI Change repeated-value percentage: "
        f"`{feature['source_oi_change_update_semantics']['repeated_value_percentage']}`",
        "- Volume negative/reset transitions excluded: "
        f"`{feature['intraday_volume']['negative_reset_count']}`",
        f"- Informative feature count: `{feature['informative_feature_count']}`",
        f"- Raw events: `{independence['raw_event_count']}`",
        f"- Continuous excursions: `{independence['continuous_excursion_count']}`",
        "- Non-overlapping opportunities: "
        f"`{independence['non_overlapping_tradable_opportunity_count']}`",
        "- Inference consistency violations: "
        f"`{inference['inference_consistency_violation_count']}`",
        f"- MR2 beats matched controls: `{controls['mr2_beats_controls']}`",
        f"- Validation-v2 cutoff: `{candidates['data_cutoff']}`",
        f"- Validation-v2 starts: `{candidates['validation_start_date']}`",
        "- Evidence status: `insufficient_sample`",
        "",
        "## Revised Candidates",
        "",
    ]
    for row in revised["candidate_summaries"]:
        opportunity_count = row["non_overlapping_opportunity_count"]
        expectancy = row["net_expectancy_points"]
        trial = _candidate_trial(row, inference)
        lines.append(
            f"- `{row['candidate_id']}` opportunities=`{opportunity_count}` "
            f"priced=`{row['priced_opportunity_count']}` "
            f"sessions=`{row['independent_session_count']}` "
            f"priced_sessions=`{row['priced_independent_session_count']}` "
            f"ambiguous=`{row['same_bar_ambiguous_count']}` expectancy=`{expectancy}` "
            f"CI95=`{trial.get('session_clustered_ci95')}` "
            f"q=`{trial.get('bh_q_value')}`"
        )
    fixed_mr2 = next(
        (
            row
            for row in controls["oi_matched_controls"]
            if row["planning_mode"] == "fixed_morning" and row["target_sd"] == 0.5
        ),
        None,
    )
    lines.extend(["", "## Matched OI Control", ""])
    if fixed_mr2:
        lines.extend(
            [
                f"- Real OI expectancy: `{fixed_mr2['real_oi']['expectancy_points']}`",
                f"- Control discrimination: `{fixed_mr2['control_discrimination_status']}`",
                f"- Distinct control selections: `{fixed_mr2['distinct_control_selection_count']}`",
                f"- Matched counts equal: `{fixed_mr2['matched_counts_equal']}`",
                "- Result: the current sample cannot distinguish real OI from controls.",
            ]
        )
    lines.extend(["", "## Frozen Candidate Hashes", ""])
    for row in candidates["candidates"]:
        lines.append(
            f"- `{row['candidate_id']}` enabled=`{row['enabled_for_validation_v2']}` "
            f"hash=`{row['candidate_hash']}`"
        )
    lines.extend(["", "## Artifacts", ""])
    names = [
        "feature_semantics_audit.json",
        "feature_semantics_audit.md",
        "event_independence_audit.json",
        "event_independence_audit.md",
        "clustered_inference_audit.json",
        "clustered_inference_audit.md",
        "matched_negative_control_report.json",
        "matched_negative_control_report.md",
        "candidate_manifest_v2.json",
        "candidate_manifest_v2.md",
        "revised_strategy_results.json",
        "integrity_report.json",
        "review_handoff.md",
        "metadata.json",
    ]
    lines.extend(f"- `{(root / name).as_posix()}`" for name in names)
    lines.extend(["", "research_only=true", "signal_allowed=false"])
    return "\n".join(lines) + "\n"


def _candidate_trial(
    candidate: dict[str, Any],
    inference: dict[str, Any],
) -> dict[str, Any]:
    return next(
        (
            row
            for row in inference["trials"]
            if row["experiment_id"] == candidate["experiment_id"]
            and row["planning_mode"] == candidate["planning_mode"]
            and row["target_sd"] == candidate["target_sd"]
            and row["spread_points"] == 1.0
            and row["slippage_points_per_side"] == 0.0
        ),
        {},
    )


if __name__ == "__main__":
    raise SystemExit(main())
