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
    ForwardOperationalState,
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_date = date.fromisoformat(args.session_date)
    zone = ZoneInfo(args.timezone)
    checkpoint = _planning_time(args.planning_mode, args.checkpoint)
    planning_at = datetime.combine(session_date, checkpoint, tzinfo=zone)
    protocol = _read(Path(args.protocol_path))
    hash_value = validate_protocol(protocol)
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
    journal = AppendOnlyJournal(
        Path(args.journal_root), protocol["protocol_version"], hash_value
    )
    written = {"plans": 0, "opportunities": 0, "confirmations": 0, "outcomes": 0}
    if readiness.state == ForwardOperationalState.PLAN_READY and readiness.plan:
        plan_record_id = (
            f"{session_date}:plan:{args.planning_mode}:{planning_at.isoformat()}"
        )
        if not journal.contains("plans", plan_record_id):
            journal.append(
                "plans",
                {
                    "record_id": plan_record_id,
                    "finalized": True,
                    **readiness.plan,
                    "stage_created": args.stage,
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
                    record_id = f"{session_date}:{stream}:{key}"
                    if journal.contains(stream, record_id):
                        continue
                    journal.append(
                        stream,
                        {
                            "record_id": record_id,
                            "finalized": True,
                            "session_date": session_date.isoformat(),
                            "plan_record_id": plan_record_id,
                            **row,
                            "order_submission_allowed": False,
                        },
                    )
                    written[stream] += 1
    status_record = {
        "record_id": (
            f"{session_date}:daily:{args.stage}:{args.planning_mode}:"
            f"{datetime.now(zone).isoformat()}"
        ),
        "finalized": True,
        "session_date": session_date.isoformat(),
        "stage": args.stage,
        "planning_mode": args.planning_mode,
        "planning_at": planning_at.isoformat(),
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


if __name__ == "__main__":
    raise SystemExit(main())
