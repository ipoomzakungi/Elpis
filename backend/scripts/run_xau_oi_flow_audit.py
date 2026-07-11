from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from src.xau_vol2vol_history_walkforward.data_lake import load_vol2vol_data_lake
from src.xau_vol2vol_history_walkforward.history_normalizer import (
    load_json_payload,
    normalize_payload,
)
from src.xau_vol2vol_history_walkforward.oi_flow_audit import (
    StrikeSnapshotIndex,
    build_conditional_variants,
    build_coverage,
    build_descriptive_stratification,
    build_opportunity_features,
    load_quikstrike_rows,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Attach timestamp-safe OI/flow context to XAU SD opportunities.",
    )
    parser.add_argument("--session-date-from", required=True)
    parser.add_argument("--session-date-to", required=True)
    parser.add_argument("--sd-audit-path", required=True)
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--monthly-oi-path",
        default="data/imports/vol2vol/monthly_oi_20260708.json",
    )
    parser.add_argument(
        "--quikstrike-folder",
        default="data/processed/quikstrike_matrix",
    )
    parser.add_argument("--output-root", default="data/reports/xau_oi_flow_audit")
    parser.add_argument(
        "--price-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    date_from = date.fromisoformat(args.session_date_from)
    date_to = date.fromisoformat(args.session_date_to)
    audit = json.loads(Path(args.sd_audit_path).read_text(encoding="utf-8"))
    loaded = load_vol2vol_data_lake(
        root=Path(args.vol2vol_data_root),
        session_date_from=date_from,
        session_date_to=date_to,
    )
    daily_rows = []
    normalization_warnings = []
    for payload in loaded.payloads:
        rows, _, warnings = normalize_payload(payload)
        daily_rows.extend(rows)
        normalization_warnings.extend(warnings)
    monthly_rows = []
    monthly_path = Path(args.monthly_oi_path)
    if monthly_path.exists():
        monthly_rows, _, warnings = normalize_payload(load_json_payload(monthly_path))
        normalization_warnings.extend(warnings)
    quikstrike_rows = load_quikstrike_rows(Path(args.quikstrike_folder))
    daily_index = StrikeSnapshotIndex(daily_rows)
    features = build_opportunity_features(
        audit["result_sets"],
        daily_index,
        monthly_index=StrikeSnapshotIndex(monthly_rows) if monthly_rows else None,
        quikstrike_rows=quikstrike_rows,
    )
    coverage = build_coverage(features)
    exit_backtest = audit["preregistered_exit_backtest"]
    stratification = build_descriptive_stratification(features, exit_backtest)
    price_result = load_traded_bars_folder(Path(args.price_bars_folder))
    variants = build_conditional_variants(
        features,
        exit_backtest,
        bars=price_result.bars,
        daily_index=daily_index,
    )
    integrity = _integrity(features)
    run_id = f"xau_oi_flow_audit_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    report_dir = Path(args.output_root) / run_id
    report_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "session_date_from": date_from.isoformat(),
        "session_date_to": date_to.isoformat(),
        "price_source": "dukascopy_xauusd_spot_bid_m1",
        "sd_audit_path": Path(args.sd_audit_path).resolve().as_posix(),
        "vol2vol_session_count": len(loaded.payloads),
        "daily_strike_row_count": len(daily_rows),
        "monthly_strike_row_count": len(monthly_rows),
        "quikstrike_row_count": len(quikstrike_rows),
        "normalization_warning_count": len(normalization_warnings),
        "evidence_status": "insufficient_sample",
        "research_only": True,
        "signal_allowed": False,
    }
    _write(report_dir / "oi_flow_coverage.json", coverage)
    _write(report_dir / "opportunity_features.json", features)
    _write(report_dir / "descriptive_stratification.json", stratification)
    _write(report_dir / "conditional_variant_results.json", variants)
    _write(report_dir / "integrity_report.json", integrity)
    _write(report_dir / "metadata.json", metadata)
    coverage_md = _coverage_markdown(coverage)
    stratification_md = _stratification_markdown(stratification)
    variants_md = _variants_markdown(variants)
    (report_dir / "oi_flow_coverage.md").write_text(coverage_md, encoding="utf-8")
    (report_dir / "descriptive_stratification.md").write_text(
        stratification_md, encoding="utf-8"
    )
    (report_dir / "conditional_variant_results.md").write_text(
        variants_md, encoding="utf-8"
    )
    handoff = _handoff(report_dir, metadata, coverage, variants, integrity)
    (report_dir / "review_handoff.md").write_text(handoff, encoding="utf-8")
    primary = {
        row["planning_mode"]: row
        for row in coverage["summaries"]
        if row["mapping_mode"] == "same_time_basis"
    }
    print(
        json.dumps(
            {
                "run_id": run_id,
                "report_dir": report_dir.resolve().as_posix(),
                "fixed_morning_unique_opportunities": primary.get(
                    "fixed_morning", {}
                ).get("unique_opportunity_count", 0),
                "rolling_30m_unique_opportunities": primary.get("rolling_30m", {}).get(
                    "unique_opportunity_count", 0
                ),
                "coverage_gate_passed": variants["coverage_gate_passed"],
                "evidence_status": "insufficient_sample",
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _integrity(features):
    future = []
    series = []
    for row in features:
        for state_name in ("plan_state", "touch_state"):
            state = row[state_name]
            if state["future_feature_violation"]:
                future.append(row["opportunity_id"])
            for kind in ("oi", "volume"):
                value = state[kind]
                if value and value["selected_series"] != row["selected_series"]:
                    series.append(row["opportunity_id"])
    return {
        "future_feature_lookahead_count": len(set(future)),
        "series_mismatch_count": len(set(series)),
        "cost_scenarios_multiply_opportunities": False,
        "all_outputs_research_only": True,
        "all_outputs_signal_allowed_false": True,
        "integrity_status": "passed" if not future and not series else "failed",
        "research_only": True,
        "signal_allowed": False,
    }


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _coverage_markdown(coverage):
    lines = ["# OI and Flow Coverage", "", "Research-only.", ""]
    for row in coverage["summaries"]:
        lines.extend(
            [
                f"## {row['planning_mode']} / {row['mapping_mode']}",
                f"- Unique opportunities: `{row['unique_opportunity_count']}`",
                f"- Plan OI: `{row['plan_time_oi_percentage']}%`",
                f"- Plan volume: `{row['plan_time_volume_percentage']}%`",
                f"- Touch OI: `{row['touch_time_oi_percentage']}%`",
                f"- Touch volume: `{row['touch_time_volume_percentage']}%`",
                f"- Monthly OI: `{row['monthly_oi_percentage']}%`",
                f"- QuikStrike OI Change: `{row['quikstrike_oi_change_percentage']}%`",
                f"- Lookahead violations: `{row['future_feature_lookahead_count']}`",
                "",
            ]
        )
    return "\n".join(lines)


def _stratification_markdown(result):
    return "\n".join(
        [
            "# Descriptive OI/Flow Stratification",
            "",
            "No group is selected as best. See the JSON artifact for all strata.",
            "",
            f"- Group rows: `{len(result['summaries'])}`",
            "- Evidence status: `insufficient_sample`",
            "",
        ]
    )


def _variants_markdown(result):
    lines = [
        "# Conditional Variant Results",
        "",
        f"- Coverage gate passed: `{result['coverage_gate_passed']}`",
        f"- Evidence status: `{result['evidence_status']}`",
    ]
    for row in result["variants"]:
        lines.append(
            f"- `{row['variant']}`: status=`{row['status']}`, "
            f"opportunities=`{row['unique_opportunity_count']}`, "
            f"expectancy=`{row.get('net_expectancy_after_one_point')}`, "
            f"change_vs_F0=`{row.get('expectancy_change_vs_f0')}`"
        )
    return "\n".join(lines) + "\n"


def _handoff(report_dir, metadata, coverage, variants, integrity):
    primary = [
        row for row in coverage["summaries"] if row["mapping_mode"] == "same_time_basis"
    ]
    lines = [
        "# XAU Opportunity OI/Flow Review Handoff",
        "",
        f"- Price source: `{metadata['price_source']}`",
        f"- Vol2Vol sessions: `{metadata['vol2vol_session_count']}`",
        f"- Daily strike rows: `{metadata['daily_strike_row_count']}`",
        f"- Monthly OI strike rows: `{metadata['monthly_strike_row_count']}`",
        f"- QuikStrike rows: `{metadata['quikstrike_row_count']}`",
    ]
    for row in primary:
        lines.append(
            f"- `{row['planning_mode']}` opportunities=`{row['unique_opportunity_count']}`, "
            f"plan_oi=`{row['plan_time_oi_percentage']}%`, "
            f"touch_oi=`{row['touch_time_oi_percentage']}%`, "
            f"plan_volume=`{row['plan_time_volume_percentage']}%`, "
            f"touch_volume=`{row['touch_time_volume_percentage']}%`, "
            f"monthly=`{row['monthly_oi_percentage']}%`, "
            f"quikstrike=`{row['quikstrike_oi_change_percentage']}%`"
        )
    lines.extend(
        [
            f"- Conditional gate passed: `{variants['coverage_gate_passed']}`",
            f"- Integrity status: `{integrity['integrity_status']}`",
            "- Evidence status: `insufficient_sample`",
            "- Strategies A-D and F0 remain unchanged controls.",
            "- Monthly OI and QuikStrike remain optional overlays.",
            "- Yahoo GC=F is not used as the execution series.",
            "- Variant headline counts combine fixed and rolling experiments; "
            "planning-mode/strategy/side groups remain separate in JSON.",
            "",
            "## Conditional Variants",
        ]
    )
    for row in variants["variants"]:
        lines.append(
            f"- `{row['variant']}` opportunities=`{row['unique_opportunity_count']}`, "
            f"targets=`{row.get('target_hit_count')}`, stops=`{row.get('stop_hit_count')}`, "
            f"time_exits=`{row.get('time_exit_count')}`, expectancy_1pt="
            f"`{row.get('net_expectancy_after_one_point')}`, delta_vs_F0="
            f"`{row.get('expectancy_change_vs_f0')}`"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
        ]
    )
    for name in (
        "oi_flow_coverage.json",
        "oi_flow_coverage.md",
        "opportunity_features.json",
        "descriptive_stratification.json",
        "descriptive_stratification.md",
        "conditional_variant_results.json",
        "conditional_variant_results.md",
        "integrity_report.json",
        "metadata.json",
        "review_handoff.md",
    ):
        lines.append(f"- `{(report_dir.resolve() / name).as_posix()}`")
    lines.extend(["", "research_only=true", "signal_allowed=false", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
