from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.xau_vol2vol_history_walkforward.browser_collector import (
    Vol2VolBrowserCollectionConfig,
    collect_browser_history,
)
from src.xau_vol2vol_history_walkforward.data_lake import daily_raw_path
from src.xau_vol2vol_history_walkforward.forward_operations import (
    FORWARD_ENGINE_ERRATUM,
    FORWARD_ENGINE_REVISION,
    ForwardOperationalState,
    ForwardReadinessResult,
    evaluate_forward_readiness,
    observe_forward_plan,
)
from src.xau_vol2vol_history_walkforward.history_normalizer import (
    load_json_payload,
    normalize_payload,
)
from src.xau_vol2vol_history_walkforward.matched_validation import (
    AppendOnlyJournal,
    validate_protocol,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one research-only XAU protocol-v1 daily operation stage.",
    )
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--stage", choices=("prepare", "monitor", "finalize"), required=True)
    parser.add_argument(
        "--planning-mode",
        choices=("fixed_morning", "rolling_30m"),
        default="fixed_morning",
    )
    parser.add_argument("--checkpoint", help="HH:MM checkpoint; required for rolling_30m")
    parser.add_argument("--collect-browser", action="store_true")
    parser.add_argument("--refresh-price", action="store_true")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--vol2vol-data-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--price-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    parser.add_argument(
        "--protocol-path",
        default="config/xau_forward_research_protocol_v1.json",
    )
    parser.add_argument(
        "--journal-root",
        default="data/reports/xau_forward_protocol/v1",
    )
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument(
        "--observation-mode",
        choices=(
            "true_forward",
            "retrospective_replay",
            "historical_backtest",
            "dry_run",
        ),
    )
    parser.add_argument("--workflow-attempt-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_date = date.fromisoformat(args.session_date)
    zone = ZoneInfo(args.timezone)
    checkpoint = _planning_time(args.planning_mode, args.checkpoint)
    planning_at = datetime.combine(session_date, checkpoint, tzinfo=zone)
    protocol = _read(Path(args.protocol_path))
    hash_value = validate_protocol(protocol)
    recorded_at = datetime.now(zone)
    journal = AppendOnlyJournal(
        Path(args.journal_root), protocol["protocol_version"], hash_value
    )
    successful_prepare = journal.latest_successful_prepare(
        session_date=session_date.isoformat(),
        planning_mode=args.planning_mode,
    )
    observation_mode = _observation_mode(
        explicit=args.observation_mode,
        stage=args.stage,
        successful_prepare=successful_prepare,
        session_date=session_date,
        planning_at=planning_at,
        recorded_at=recorded_at,
    )
    workflow_attempt_id = (
        args.workflow_attempt_id
        or (
            successful_prepare.get("workflow_attempt_id")
            if args.stage != "prepare" and successful_prepare
            else None
        )
        or _new_workflow_attempt_id(
            session_date, args.planning_mode, observation_mode, recorded_at
        )
    )
    data_root = Path(args.vol2vol_data_root)
    collection_error = None
    if args.collect_browser and args.stage == "prepare":
        try:
            collect_browser_history(
                Vol2VolBrowserCollectionConfig(
                    cdp_url=args.cdp_url,
                    base_url="https://www.vol2vol.com",
                    output_root=data_root,
                    session_date=session_date,
                    refresh=True,
                    include_current_incomplete_session=True,
                    timezone=args.timezone,
                )
            )
        except (OSError, RuntimeError, ValueError) as exc:
            collection_error = " ".join(str(exc).split())[:300]
    price_refresh_error = None
    if args.refresh_price:
        command = [
            sys.executable,
            str(Path(__file__).with_name("fetch_xau_dukascopy_range.py")),
            "--date-from",
            (session_date - timedelta(days=1)).isoformat(),
            "--date-to",
            (session_date + timedelta(days=1)).isoformat(),
            "--chunk-days",
            "1",
            "--timeout-seconds",
            "60",
            "--max-retries",
            "3",
            "--transport",
            "realtime-json",
            "--output-root",
            str(Path(args.price_bars_folder).parents[1]),
            "--append",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if completed.returncode != 0:
                price_refresh_error = " ".join(
                    (completed.stderr or completed.stdout).split()
                )[:300]
        except subprocess.TimeoutExpired:
            price_refresh_error = "Dukascopy refresh exceeded the 180-second limit."
    raw_path = daily_raw_path(data_root, session_date)
    strike_rows = []
    range_rows = []
    if raw_path.exists():
        strike_rows, range_rows, _ = normalize_payload(
            load_json_payload(raw_path), default_session_date=session_date
        )
    price_result = load_traded_bars_folder(Path(args.price_bars_folder), timezone=args.timezone)
    readiness = evaluate_forward_readiness(
        session_date=session_date,
        planning_at=planning_at,
        range_rows=range_rows,
        strike_rows=strike_rows,
        bars=price_result.bars,
        planning_mode=args.planning_mode,
        source_gap_limit_seconds=protocol["data_freshness_limits_seconds"][
            "price_source_alignment"
        ],
        snapshot_freshness_limit_seconds=protocol["data_freshness_limits_seconds"][
            "plan_options_snapshot"
        ],
    )
    if (
        args.stage != "prepare"
        and args.workflow_attempt_id is None
        and successful_prepare is None
    ):
        readiness = ForwardReadinessResult(
            ForwardOperationalState.DATA_BLOCKED,
            ["No successful prepare workflow exists for this session and planning mode."],
        )
    data_as_of = _data_as_of(
        readiness.plan,
        price_result.bars,
        planning_at=planning_at,
        stage=args.stage,
    )
    written = {"plans": 0, "opportunities": 0, "confirmations": 0, "outcomes": 0}
    if readiness.state == ForwardOperationalState.PLAN_READY and readiness.plan:
        logical_plan_record_id = (
            f"{session_date}:plan:{args.planning_mode}:{planning_at.isoformat()}"
        )
        plan_record_id = (
            f"{logical_plan_record_id}:attempt:{workflow_attempt_id}"
        )
        if not journal.contains("plans", plan_record_id):
            supersedes = journal.latest_record_id("plans", logical_plan_record_id)
            journal.append(
                "plans",
                {
                    "record_id": plan_record_id,
                    "logical_record_key": logical_plan_record_id,
                    "finalized": True,
                    **readiness.plan,
                    "stage_created": args.stage,
                    "workflow_attempt_id": workflow_attempt_id,
                    "observation_mode": observation_mode,
                    "recorded_at": recorded_at.isoformat(),
                    "data_as_of": data_as_of,
                    "engine_revision": FORWARD_ENGINE_REVISION,
                    "engine_erratum": FORWARD_ENGINE_ERRATUM,
                    **(
                        {"supersedes_record_id": supersedes}
                        if supersedes is not None
                        else {}
                    ),
                    "order_submission_allowed": False,
                },
            )
            written["plans"] += 1
        if args.stage in {"monitor", "finalize"}:
            observations = observe_forward_plan(
                readiness.plan,
                price_result.bars,
                finalize=args.stage == "finalize",
            )
            for stream in ("opportunities", "confirmations", "outcomes"):
                for row in observations[stream]:
                    key = row.get("record_key") or row["opportunity_id"]
                    logical_record_id = f"{session_date}:{stream}:{key}"
                    record_id = (
                        f"{logical_record_id}:attempt:{workflow_attempt_id}"
                    )
                    if journal.contains(stream, record_id):
                        continue
                    supersedes = journal.latest_record_id(stream, logical_record_id)
                    journal.append(
                        stream,
                        {
                            "record_id": record_id,
                            "logical_record_key": logical_record_id,
                            "finalized": True,
                            "session_date": session_date.isoformat(),
                            "planning_mode": args.planning_mode,
                            "plan_record_id": plan_record_id,
                            **row,
                            "workflow_attempt_id": workflow_attempt_id,
                            "observation_mode": observation_mode,
                            "recorded_at": recorded_at.isoformat(),
                            "data_as_of": data_as_of,
                            "engine_revision": FORWARD_ENGINE_REVISION,
                            "engine_erratum": FORWARD_ENGINE_ERRATUM,
                            **(
                                {"supersedes_record_id": supersedes}
                                if supersedes is not None
                                else {}
                            ),
                            "order_submission_allowed": False,
                        },
                    )
                    written[stream] += 1
    status_record = {
        "record_id": (
            f"{session_date}:daily:{args.stage}:{args.planning_mode}:"
            f"{recorded_at.isoformat()}"
        ),
        "finalized": True,
        "session_date": session_date.isoformat(),
        "stage": args.stage,
        "planning_mode": args.planning_mode,
        "planning_at": planning_at.isoformat(),
        "workflow_attempt_id": workflow_attempt_id,
        "observation_mode": observation_mode,
        "recorded_at": recorded_at.isoformat(),
        "data_as_of": data_as_of,
        "dry_run": observation_mode == "dry_run",
        "engine_revision": FORWARD_ENGINE_REVISION,
        "engine_erratum": FORWARD_ENGINE_ERRATUM,
        "operational_state": readiness.state.value,
        "reasons": readiness.reasons,
        "collection_error": collection_error,
        "price_refresh_error": price_refresh_error,
        "records_written": written,
        "raw_vol2vol_path": raw_path.resolve().as_posix(),
        "price_bar_count": len(price_result.bars),
        "order_submission_allowed": False,
    }
    journal.append("daily_summary", status_record)
    print(
        json.dumps(
            {
                **status_record,
                "journal_root": Path(args.journal_root).resolve().as_posix(),
                "protocol_hash": hash_value,
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if readiness.state == ForwardOperationalState.PLAN_READY else 2


def _planning_time(planning_mode: str, checkpoint: str | None) -> time:
    if planning_mode == "fixed_morning":
        return time(7, 0)
    if checkpoint is None:
        raise ValueError("--checkpoint is required for rolling_30m")
    hour, minute = (int(part) for part in checkpoint.split(":"))
    if minute not in {0, 30}:
        raise ValueError("rolling checkpoint must be on a 30-minute boundary")
    return time(hour, minute)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _observation_mode(
    *,
    explicit: str | None,
    stage: str,
    successful_prepare: dict | None,
    session_date: date,
    planning_at: datetime,
    recorded_at: datetime,
) -> str:
    if explicit is not None:
        return explicit
    if stage != "prepare" and successful_prepare is not None:
        return str(successful_prepare["observation_mode"])
    if session_date < recorded_at.date():
        return "retrospective_replay"
    if session_date > recorded_at.date():
        return "historical_backtest"
    if planning_at <= recorded_at <= planning_at + timedelta(minutes=30):
        return "true_forward"
    return "retrospective_replay"


def _new_workflow_attempt_id(
    session_date: date,
    planning_mode: str,
    observation_mode: str,
    recorded_at: datetime,
) -> str:
    timestamp = recorded_at.strftime("%Y%m%dT%H%M%S%f%z")
    return f"{session_date}:{planning_mode}:{observation_mode}:{timestamp}"


def _data_as_of(plan, bars, *, planning_at: datetime, stage: str) -> str | None:
    if stage == "prepare" and plan:
        candidates = [
            datetime.fromisoformat(plan[key])
            for key in ("vol2vol_snapshot_time", "xau_source_time")
            if plan.get(key)
        ]
        return max(candidates).isoformat() if candidates else None
    window = [
        bar.timestamp
        for bar in bars
        if bar.timestamp.astimezone(planning_at.tzinfo).date() == planning_at.date()
        and bar.timestamp > planning_at
    ]
    return max(window).isoformat() if window else None


if __name__ == "__main__":
    raise SystemExit(main())
