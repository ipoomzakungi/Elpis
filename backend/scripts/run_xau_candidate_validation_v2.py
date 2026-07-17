from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import XauPriceBar
from src.models.xau_vol2vol_history_walkforward import XauMappingMode
from src.xau_options_research.ambiguity_resolver import (
    load_tick_rows,
    resolve_ambiguous_outcome,
)
from src.xau_options_research.candidate_validation_reporting import (
    build_daily_summary,
    build_validation_summary,
)
from src.xau_options_research.candidate_validation_runner import (
    ENGINE_REVISION,
    complete_price_coverage,
    engine_revision_hash,
    hash_price_bars,
    load_frozen_manifest,
    run_frozen_candidates,
    validate_completed_session,
)
from src.xau_options_research.candidate_validation_store import (
    CandidateValidationStore,
    DuplicateValidationSessionError,
)
from src.xau_options_research.event_builder import build_raw_events
from src.xau_options_research.event_deduplication import deduplicate_events
from src.xau_options_research.feature_panel import build_checkpoint_rows
from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_raw_path,
    evaluate_daily_session_eligibility,
)
from src.xau_vol2vol_history_walkforward.history_normalizer import normalize_payload
from src.xau_vol2vol_history_walkforward.oi_flow_audit import StrikeSnapshotIndex
from src.xau_vol2vol_history_walkforward.planning import select_planning_cycles
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append one completed session to frozen XAU candidate validation v2."
    )
    parser.add_argument("--session-date", required=True)
    parser.add_argument(
        "--candidate-registry",
        default="config/xau_options_candidate_validation_v2.json",
    )
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument("--price-bars-folder", default="data/imports/xau/dukascopy/xauusd/m1")
    parser.add_argument(
        "--journal-root", default="data/reports/xau_candidate_validation/v2"
    )
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--resolve-ambiguous-with-ticks", action="store_true")
    parser.add_argument("--tick-data-file")
    parser.add_argument(
        "--fixture-json",
        help="Synthetic post-cutoff fixture. Requires --dry-run and never appends journals.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    requested_date = date.fromisoformat(args.session_date)
    manifest = load_frozen_manifest(Path(args.candidate_registry))
    if args.fixture_json:
        if not args.dry_run:
            raise ValueError("--fixture-json requires --dry-run")
        payload = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
        result = _run_fixture(
            payload, requested_date, manifest, journal_root=Path(args.journal_root)
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    result = _run_real_session(args, requested_date, manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"ACCEPTED", "DRY_RUN_ACCEPTED"} else 2


def _run_real_session(
    args: argparse.Namespace,
    requested_date: date,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    root = Path(args.vol2vol_data_root)
    eligibility = evaluate_daily_session_eligibility(
        root=root,
        session_date=requested_date,
        current_date=date.today(),
    )
    raw_path = daily_raw_path(root, requested_date)
    payload: dict[str, Any] = {}
    if raw_path.exists():
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    returned_date = str(payload.get("sessionDate") or "")[:10]
    price_result = load_traded_bars_folder(
        Path(args.price_bars_folder), timezone=args.timezone
    )
    zone = ZoneInfo(args.timezone)
    coverage = complete_price_coverage(
        price_result.bars, session_date=requested_date, timezone=zone
    )
    gate = validate_completed_session(
        requested_date=requested_date,
        returned_date=returned_date,
        source_status=eligibility.source_session_status,
        price_coverage_complete=coverage,
        manifest=manifest,
    )
    if not gate.accepted:
        return _rejection(
            requested_date,
            gate.reason,
            eligibility.reasons,
            manifest,
        )

    strikes, ranges, warnings = normalize_payload(payload, default_session_date=requested_date)
    selections = []
    selection_issues: dict[str, dict[str, int]] = {}
    for mode, planning_times in (
        ("fixed_morning", (time(7, 0),)),
        ("rolling_30m", _rolling_times()),
    ):
        selected, issues = select_planning_cycles(
            range_snapshots=ranges,
            strike_rows=strikes,
            bars=price_result.bars,
            session_date_from=requested_date,
            session_date_to=requested_date,
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
    checkpoints = build_checkpoint_rows(
        selections,
        price_result.bars,
        StrikeSnapshotIndex(strikes),
        timezone=args.timezone,
        range_snapshots=ranges,
        monthly_strikes=[],
    )
    raw_events = build_raw_events(checkpoints, price_result.bars, timezone=args.timezone)
    _, episodes = deduplicate_events(raw_events, price_result.bars)
    run = run_frozen_candidates(
        manifest=manifest,
        episode_events=episodes,
        bars=price_result.bars,
    )
    opportunities, outcomes = _prepare_records(run, requested_date)
    resolutions = _resolve_ambiguities(outcomes, args)
    session_record = {
        "session_id": f"validation-v2:{requested_date.isoformat()}",
        "session_date": requested_date.isoformat(),
        "ingested_at": datetime.now(UTC).isoformat(),
        "vol2vol_sha256": eligibility.payload_sha256,
        "price_data_sha256": hash_price_bars(price_result.bars, requested_date, zone),
        "candidate_hashes": _candidate_hashes(manifest),
        "engine_revision": ENGINE_REVISION,
        "engine_revision_hash": engine_revision_hash(),
        "returned_session_date": returned_date,
        "source_session_status": eligibility.source_session_status,
        "price_coverage_complete": coverage,
        "checkpoint_count": len(checkpoints),
        "episode_count": len(episodes),
        "selection_issues": selection_issues,
        "normalization_warnings": warnings,
    }
    daily_summary = build_daily_summary(
        requested_date.isoformat(),
        outcomes,
        c3_eligibility_count=run["c3_descriptive_eligibility_count"],
        bo0_monitor_count=run["bo0_monitor_observation_count"],
    )
    store = CandidateValidationStore(Path(args.journal_root), manifest["registry_hash"])
    if not args.dry_run:
        try:
            store.append_session_bundle(
                session=session_record,
                opportunities=opportunities,
                outcomes=outcomes,
                resolutions=resolutions,
                daily_summary=daily_summary,
            )
        except DuplicateValidationSessionError:
            return _rejection(requested_date, "DUPLICATE_SESSION", [], manifest)
    all_outcomes = outcomes if args.dry_run else store.read("outcomes")
    accepted_sessions = (
        []
        if args.dry_run
        else [row["session_date"] for row in store.read("sessions")]
    )
    summary = build_validation_summary(
        all_outcomes, accepted_session_dates=accepted_sessions
    )
    checkpoint = _append_review_checkpoint(store, summary, manifest, args.dry_run)
    report_dir = _write_report(
        Path(args.journal_root),
        requested_date,
        manifest,
        session_record,
        summary,
        daily_summary,
        dry_run=args.dry_run,
    )
    return {
        "status": "DRY_RUN_ACCEPTED" if args.dry_run else "ACCEPTED",
        "session_date": requested_date.isoformat(),
        "real_accepted_session_count": summary["real_accepted_session_count"],
        "synthetic_fixture_session_count": summary[
            "synthetic_fixture_session_count"
        ],
        "rejected_session_count": summary["rejected_session_count"],
        "manifest_hash": manifest["registry_hash"],
        "candidate_hashes": _candidate_hashes(manifest),
        "c1_opportunity_count": sum(row["candidate_id"] == "C1" for row in opportunities),
        "c2_opportunity_count": sum(row["candidate_id"] == "C2" for row in opportunities),
        "ambiguity_count": sum(
            row["resolved_status"] == "same_bar_ambiguous" for row in outcomes
        ),
        "review_checkpoint_appended": checkpoint,
        "report_path": (report_dir / "review_handoff.md").resolve().as_posix(),
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _run_fixture(
    payload: dict[str, Any],
    requested_date: date,
    manifest: dict[str, Any],
    *,
    journal_root: Path,
) -> dict[str, Any]:
    gate = validate_completed_session(
        requested_date=requested_date,
        returned_date=payload["returned_session_date"],
        source_status=payload["source_status"],
        price_coverage_complete=payload["price_coverage_complete"],
        manifest=manifest,
    )
    if not gate.accepted:
        return _rejection(requested_date, gate.reason, [], manifest)
    bars = [XauPriceBar.model_validate(row) for row in payload["bars"]]
    run = run_frozen_candidates(
        manifest=manifest,
        episode_events=payload["episode_events"],
        bars=bars,
    )
    opportunities, outcomes = _prepare_records(run, requested_date)
    summary = build_validation_summary(
        outcomes,
        accepted_session_dates=[],
        synthetic_fixture_session_count=1,
    )
    daily_summary = build_daily_summary(
        requested_date.isoformat(),
        outcomes,
        c3_eligibility_count=run["c3_descriptive_eligibility_count"],
        bo0_monitor_count=run["bo0_monitor_observation_count"],
    )
    session_record = {
        "session_date": requested_date.isoformat(),
        "source_session_status": "synthetic_fixture",
        "engine_revision": ENGINE_REVISION,
        "candidate_hashes": _candidate_hashes(manifest),
    }
    report_dir = _write_report(
        journal_root,
        requested_date,
        manifest,
        session_record,
        summary,
        daily_summary,
        dry_run=True,
    )
    return {
        "status": "DRY_RUN_ACCEPTED",
        "session_date": requested_date.isoformat(),
        "real_accepted_session_count": 0,
        "synthetic_fixture_session_count": 1,
        "rejected_session_count": 0,
        "manifest_hash": manifest["registry_hash"],
        "candidate_hashes": _candidate_hashes(manifest),
        "c1_opportunity_count": sum(row["candidate_id"] == "C1" for row in opportunities),
        "c2_opportunity_count": sum(row["candidate_id"] == "C2" for row in opportunities),
        "ambiguity_count": sum(
            row["resolved_status"] == "same_bar_ambiguous" for row in outcomes
        ),
        "journal_append_count": 0,
        "report_path": (report_dir / "review_handoff.md").resolve().as_posix(),
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _prepare_records(
    run: dict[str, Any], requested_date: date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    opportunities = run["opportunities"]
    zone_by_key = {
        (row["candidate_id"], row["episode_id"]): row["entry_zone"]
        for row in opportunities
    }
    outcomes = []
    for row in run["outcomes"]:
        outcomes.append(
            {
                **row,
                "outcome_id": f"{row['candidate_id']}:{row['episode_id']}",
                "entry_zone": zone_by_key[(row["candidate_id"], row["episode_id"])],
                "session_date": requested_date.isoformat(),
            }
        )
    return opportunities, outcomes


def _resolve_ambiguities(
    outcomes: list[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    if not args.resolve_ambiguous_with_ticks:
        return []
    source = Path(args.tick_data_file) if args.tick_data_file else None
    ticks = load_tick_rows(source) if source else []
    resolutions = []
    for index, outcome in enumerate(outcomes):
        if outcome["original_m1_status"] != "same_bar_ambiguous":
            continue
        resolved, record = resolve_ambiguous_outcome(
            outcome, tick_rows=ticks, resolution_source=source
        )
        outcomes[index] = resolved
        resolutions.append(record)
    return resolutions


def _append_review_checkpoint(
    store: CandidateValidationStore,
    summary: dict[str, Any],
    manifest: dict[str, Any],
    dry_run: bool,
) -> bool:
    count = summary["validation_session_count"]
    if dry_run or count not in manifest["review_schedule_sessions"]:
        return False
    if store.has_review_checkpoint(count):
        return False
    store.append(
        "review_checkpoints",
        {
            "checkpoint_id": f"validation-v2:{count}",
            "session_count": count,
            "summary": summary,
        },
    )
    return True


def _write_report(
    journal_root: Path,
    session_date: date,
    manifest: dict[str, Any],
    session: dict[str, Any],
    summary: dict[str, Any],
    daily_summary: dict[str, Any],
    *,
    dry_run: bool,
) -> Path:
    run_id = f"{session_date.isoformat()}_{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
    report_dir = journal_root / "runs" / run_id
    report_dir.mkdir(parents=True, exist_ok=False)
    integrity = {
        "manifest_hash_valid": True,
        "pre_cutoff_row_count": 0,
        "candidate_ids": ["C1", "C2"],
        "c3_outcome_count": daily_summary["c3_outcome_count"],
        "bo0_candidate_outcome_count": daily_summary["bo0_candidate_outcome_count"],
        "dry_run": dry_run,
        "real_accepted_session_count": summary["real_accepted_session_count"],
        "synthetic_fixture_session_count": summary[
            "synthetic_fixture_session_count"
        ],
        "rejected_session_count": summary["rejected_session_count"],
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }
    (report_dir / "validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    (report_dir / "integrity_report.json").write_text(
        json.dumps(integrity, indent=2, sort_keys=True), encoding="utf-8"
    )
    handoff = _handoff(
        manifest, session, summary, daily_summary, report_dir, dry_run=dry_run
    )
    (report_dir / "review_handoff.md").write_text(handoff, encoding="utf-8")
    return report_dir


def _handoff(
    manifest: dict[str, Any],
    session: dict[str, Any],
    summary: dict[str, Any],
    daily: dict[str, Any],
    report_dir: Path,
    *,
    dry_run: bool,
) -> str:
    observation = (
        "synthetic_dry_run"
        if session["source_session_status"] == "synthetic_fixture"
        else "completed_session_dry_run"
        if dry_run
        else "historical_validation"
    )
    lines = [
        "# XAU Candidate Validation v2",
        "",
        f"- Session: `{session['session_date']}`",
        f"- Observation: `{observation}`",
        f"- Source session status: `{session['source_session_status']}`",
        f"- Real accepted sessions: {summary['real_accepted_session_count']}",
        f"- Synthetic fixture sessions: {summary['synthetic_fixture_session_count']}",
        f"- Rejected sessions: {summary['rejected_session_count']}",
        f"- Manifest hash: `{manifest['registry_hash']}`",
        f"- Validation start: `{manifest['validation_start_date']}`",
        "- Evidence status: `insufficient_sample`",
        f"- C3 descriptive eligibility: {daily['c3_descriptive_eligibility_count']}",
        f"- BO0 monitor observations: {daily['bo0_monitor_observation_count']}",
        "- C3 outcomes: 0",
        "- BO0 candidate outcomes: 0",
        "",
        "## Frozen Candidates",
        "",
    ]
    for row in summary["candidates"]:
        lines.extend(
            [
                f"### {row['candidate_id']}",
                "",
                f"- Validation sessions: {row['validation_session_count']}",
                f"- Sessions with opportunities: {row['sessions_with_opportunities']}",
                f"- Opportunities: {row['independent_opportunity_count']}",
                f"- Priced: {row['priced_outcome_count']}",
                f"- Ambiguous: {row['ambiguous_outcome_count']}",
                f"- Net mean points: {row['net_mean_points']}",
                f"- Evidence: `{row['evidence_status']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Guardrails",
            "",
            "`research_only=true`, `signal_allowed=false`, "
            "`order_submission_allowed=false`.",
            "",
            f"Artifacts: `{report_dir.resolve().as_posix()}`",
            "",
        ]
    )
    return "\n".join(lines)


def _rejection(
    session_date: date,
    reason: str,
    details: list[str],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "REJECTED",
        "session_date": session_date.isoformat(),
        "real_accepted_session_count": 0,
        "synthetic_fixture_session_count": 0,
        "rejected_session_count": 1,
        "reason": reason,
        "details": details,
        "manifest_hash": manifest["registry_hash"],
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def _candidate_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        row["candidate_id"]: row["candidate_hash"]
        for row in manifest["candidates"]
        if row["candidate_id"] in {"C1", "C2"}
    }


def _rolling_times() -> tuple[time, ...]:
    current = datetime.combine(date(2000, 1, 1), time(7, 0))
    end = datetime.combine(date(2000, 1, 1), time(23, 30))
    values = []
    while current <= end:
        values.append(current.time())
        current += timedelta(minutes=30)
    return tuple(values)


if __name__ == "__main__":
    raise SystemExit(main())
