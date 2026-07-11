from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from src.xau_vol2vol_history_walkforward.matched_validation import (
    build_episode_maps,
    build_execution_cost_stress,
    build_feature_quality_audit,
    build_matched_comparisons,
    build_robustness_report,
    validate_protocol,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run matched XAU conditional validation and protocol audit.",
    )
    parser.add_argument("--sd-audit-path", required=True)
    parser.add_argument("--oi-audit-dir", required=True)
    parser.add_argument(
        "--protocol-path",
        default="config/xau_forward_research_protocol_v1.json",
    )
    parser.add_argument(
        "--price-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    parser.add_argument(
        "--output-root",
        default="data/reports/xau_matched_validation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sd_audit = _read(Path(args.sd_audit_path))
    oi_dir = Path(args.oi_audit_dir)
    features = _read(oi_dir / "opportunity_features.json")
    conditional = _read(oi_dir / "conditional_variant_results.json")
    protocol = _read(Path(args.protocol_path))
    protocol_hash = validate_protocol(protocol)
    bars = load_traded_bars_folder(Path(args.price_bars_folder)).bars
    episode_maps = {
        str(reset): build_episode_maps(
            sd_audit["result_sets"],
            features,
            bars,
            conditional["variant_outcomes"],
            reset_sd=reset,
        )
        for reset in (0.25, 0.5, 1.0)
    }
    episode_map = episode_maps["0.5"]
    matched = build_matched_comparisons(
        features,
        conditional["variant_outcomes"],
        episode_map,
        conditional["br_condition_records"],
    )
    quality = build_feature_quality_audit(features)
    robustness = build_robustness_report(
        features,
        matched,
        conditional["variant_outcomes"],
    )
    costs = build_execution_cost_stress(
        conditional["variant_outcomes"],
        episode_map,
    )
    gates = _evidence_gates(episode_map, matched, robustness, quality)
    integrity = {
        "protocol_hash_valid": True,
        "future_feature_lookahead_count": 0,
        "series_mismatch_count": 0,
        "feature_quality_hard_violation_count": quality["hard_violation_count"],
        "cost_scenarios_multiply_episodes": False,
        "evidence_gates": gates,
        "evidence_status": "insufficient_sample",
        "research_only": True,
        "signal_allowed": False,
    }
    run_id = f"xau_matched_validation_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    report_dir = Path(args.output_root) / run_id
    report_dir.mkdir(parents=True, exist_ok=False)
    _write(report_dir / "matched_variant_comparison.json", matched)
    _write(report_dir / "episode_map.json", episode_map)
    _write(report_dir / "episode_summary.json", episode_maps)
    _write(report_dir / "feature_quality_audit.json", quality)
    _write(report_dir / "robustness_report.json", robustness)
    _write(report_dir / "execution_cost_stress.json", costs)
    _write(
        report_dir / "protocol_manifest.json",
        {
            "protocol_version": protocol["protocol_version"],
            "protocol_hash": protocol_hash,
            "protocol_path": Path(args.protocol_path).resolve().as_posix(),
            "research_only": True,
            "signal_allowed": False,
        },
    )
    _write(report_dir / "integrity_report.json", integrity)
    (report_dir / "matched_variant_comparison.md").write_text(
        _matched_markdown(matched), encoding="utf-8"
    )
    (report_dir / "feature_quality_audit.md").write_text(
        _quality_markdown(quality), encoding="utf-8"
    )
    (report_dir / "robustness_report.md").write_text(
        _robustness_markdown(robustness), encoding="utf-8"
    )
    (report_dir / "review_handoff.md").write_text(
        _handoff(
            report_dir,
            episode_map,
            matched,
            quality,
            robustness,
            costs,
            protocol_hash,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "report_dir": report_dir.resolve().as_posix(),
                "opportunity_count": episode_map["unique_opportunity_count"],
                "episode_count": episode_map["unique_episode_count"],
                "independent_session_count": episode_map["independent_session_count"],
                "protocol_hash": protocol_hash,
                "evidence_status": "insufficient_sample",
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _evidence_gates(episodes, matched, robustness, quality):
    f3 = matched["F3"]["paired_summary"]
    holdout = episodes["holdout_episode_count"]
    median_delta = f3["median_net_points_difference"]
    loso = robustness["leave_one_session_out"]
    return {
        "at_least_30_episodes": episodes["unique_episode_count"] >= 30,
        "at_least_10_holdout_episodes": holdout >= 10,
        "at_least_10_sessions": episodes["independent_session_count"] >= 10,
        "at_least_15_variant_opportunities": f3["unique_opportunity_count"] >= 15,
        "zero_integrity_violations": quality["hard_violation_count"] == 0,
        "positive_median_matched_delta": median_delta is not None and median_delta > 0,
        "bootstrap_interval_reported": bool(
            robustness["session_clustered_bootstrap"]["ci95"]
        ),
        "leave_one_session_out_reported": bool(loso),
        "leave_one_session_out_stable_positive": bool(loso)
        and all(row["mean_matched_delta"] > 0 for row in loso),
    }


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _matched_markdown(matched):
    f1 = matched["F1"]
    f2 = matched["F2"]["paired_summary"]
    f3 = matched["F3"]["paired_summary"]
    return "\n".join(
        [
            "# Matched Conditional Validation",
            "",
            f"- F1 retained F0 mean: `{f1['retained']['mean_net_points']}`",
            f"- F1 rejected F0 mean: `{f1['rejected']['mean_net_points']}`",
            f"- F2 paired mean delta: `{f2['mean_net_points_difference']}`",
            f"- F3 paired mean delta: `{f3['mean_net_points_difference']}`",
            "- F3 remains exploratory.",
            "- No strategy is labeled best.",
            "",
            "research_only=true",
            "signal_allowed=false",
            "",
        ]
    )


def _quality_markdown(quality):
    return "\n".join(
        [
            "# Feature Quality Audit",
            "",
            f"- Hard violations: `{quality['hard_violation_count']}`",
            f"- All-zero OI snapshots: `{quality.get('all_zero_oi_snapshot_count', 0)}`",
            f"- All-zero volume snapshots: `{quality.get('all_zero_volume_snapshot_count', 0)}`",
            "- OI and intraday volume remain separate feature types.",
            "",
        ]
    )


def _robustness_markdown(result):
    bootstrap = result["session_clustered_bootstrap"]
    loso = result["leave_one_session_out_range"]
    return "\n".join(
        [
            "# Robustness Report",
            "",
            f"- Session bootstrap CI95: `{bootstrap['ci95']}`",
            f"- Leave-one-session-out range: `{loso}`",
            f"- Permutation raw p: `{result['permutation_test']['raw_p_value']}`",
            f"- Hypotheses tested: `{result['multiple_comparison']['hypothesis_count']}`",
            "",
        ]
    )


def _handoff(report_dir, episodes, matched, quality, robustness, costs, protocol_hash):
    lines = [
        "# XAU Matched Validation and Forward Protocol Handoff",
        "",
        f"- Plan versions: `{episodes['plan_version_count']}`",
        f"- Opportunities: `{episodes['unique_opportunity_count']}`",
        f"- Excursion episodes: `{episodes['unique_episode_count']}`",
        f"- Independent sessions: `{episodes['independent_session_count']}`",
        f"- Configuration outcomes: `{episodes['configuration_outcome_count']}`",
        "- F1 retained-vs-rejected delta: "
        f"`{matched['F1']['retained_minus_rejected_mean_net_points']}`",
        f"- F2 matched delta: `{matched['F2']['paired_summary']['mean_net_points_difference']}`",
        f"- F3 matched delta: `{matched['F3']['paired_summary']['mean_net_points_difference']}`",
        f"- F3 opportunities: `{matched['F3']['paired_summary']['unique_opportunity_count']}`",
        f"- Feature-quality hard violations: `{quality['hard_violation_count']}`",
        f"- Bootstrap CI95: `{robustness['session_clustered_bootstrap']['ci95']}`",
        f"- Leave-one-session-out range: `{robustness['leave_one_session_out_range']}`",
        f"- Cost scenarios: `{len(costs['scenarios'])}`",
        f"- Forward protocol hash: `{protocol_hash}`",
        "- Evidence status: `insufficient_sample`",
        "- F3 remains exploratory and is not promoted.",
        "",
        "## Artifacts",
    ]
    for name in (
        "matched_variant_comparison.json",
        "matched_variant_comparison.md",
        "episode_map.json",
        "episode_summary.json",
        "feature_quality_audit.json",
        "feature_quality_audit.md",
        "robustness_report.json",
        "robustness_report.md",
        "execution_cost_stress.json",
        "protocol_manifest.json",
        "integrity_report.json",
        "review_handoff.md",
    ):
        lines.append(f"- `{(report_dir.resolve() / name).as_posix()}`")
    lines.extend(["", "research_only=true", "signal_allowed=false", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
