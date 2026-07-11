from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from src.xau_vol2vol_history_walkforward.matched_validation import (
    AppendOnlyJournal,
    validate_protocol,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append a research-only XAU forward protocol dry-run cycle.",
    )
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--oi-audit-dir", required=True)
    parser.add_argument(
        "--protocol-path",
        default="config/xau_forward_research_protocol_v1.json",
    )
    parser.add_argument(
        "--journal-root",
        default="data/reports/xau_forward_protocol/v1",
    )
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_date = date.fromisoformat(args.session_date)
    protocol = _read(Path(args.protocol_path))
    hash_value = validate_protocol(protocol)
    audit_dir = Path(args.oi_audit_dir)
    features = _read(audit_dir / "opportunity_features.json")
    conditional = _read(audit_dir / "conditional_variant_results.json")
    journal = AppendOnlyJournal(
        Path(args.journal_root),
        protocol["protocol_version"],
        hash_value,
    )
    selected = [
        row
        for row in features
        if row["session_date"] == session_date.isoformat()
        and row["mapping_mode"] == protocol["mapping_mode"]
    ]
    confirmation_by_id = {
        row["opportunity_id"]: row for row in conditional["confirmation_records"]
    }
    written = defaultdict_int()
    written_plan_ids = set()
    for feature in selected:
        plan_id = f"{session_date}:plan:{feature['planning_mode']}:{feature['planning_at']}"
        if plan_id not in written_plan_ids:
            journal.append(
                "plans",
                {
                    "record_id": plan_id,
                    "finalized": True,
                    "session_date": session_date.isoformat(),
                    "source_timestamps": {
                        "plan_oi": feature["plan_oi_snapshot_time"],
                        "plan_volume": feature["plan_volume_snapshot_time"],
                    },
                    "series": feature["selected_series"],
                    "xau_reference": feature["xau_reference"],
                    "future_reference": feature["future_reference"],
                    "basis_points": feature["basis_diff_used"],
                    "mapping_mode": feature["mapping_mode"],
                    "plan_feature_state": feature["plan_state"],
                    "dry_run": True,
                    "order_submission_allowed": False,
                },
            )
            written_plan_ids.add(plan_id)
            written["plans"] += 1
        journal.append(
            "opportunities",
            {
                "record_id": f"{session_date}:opportunity:{feature['opportunity_id']}",
                "finalized": True,
                "session_date": session_date.isoformat(),
                "opportunity_id": feature["opportunity_id"],
                "plan_record_id": plan_id,
                "side": feature["side"],
                "entry_definition": feature["entry_definition"],
                "mapped_entry_level": feature["entry_level"],
                "mapped_oi_wall": (
                    feature["plan_state"]["oi"].get("mapped_xauusd_strike")
                    if feature["plan_state"]["oi"]
                    else None
                ),
                "plan_state": feature["plan_state"],
                "touch_state": feature["touch_state"],
                "dry_run": True,
                "order_submission_allowed": False,
            },
        )
        written["opportunities"] += 1
        confirmation = confirmation_by_id.get(feature["opportunity_id"])
        if confirmation:
            journal.append(
                "confirmations",
                {
                    "record_id": f"{session_date}:confirmation:{feature['opportunity_id']}",
                    "finalized": True,
                    "session_date": session_date.isoformat(),
                    **confirmation,
                    "dry_run": True,
                    "order_submission_allowed": False,
                },
            )
            written["confirmations"] += 1
    journal.append(
        "daily_summary",
        {
            "record_id": f"{session_date}:daily_summary:{datetime.now(UTC).isoformat()}",
            "finalized": True,
            "session_date": session_date.isoformat(),
            "plan_count": written["plans"],
            "opportunity_count": written["opportunities"],
            "confirmation_count": written["confirmations"],
            "outcome_count": 0,
            "dry_run": True,
            "order_submission_allowed": False,
        },
    )
    written["daily_summary"] += 1
    print(
        json.dumps(
            {
                "session_date": session_date.isoformat(),
                "journal_root": Path(args.journal_root).resolve().as_posix(),
                "records_written": written,
                "protocol_hash": hash_value,
                "dry_run": True,
                "order_submission_allowed": False,
                "research_only": True,
                "signal_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def defaultdict_int() -> dict[str, int]:
    return {
        "plans": 0,
        "opportunities": 0,
        "confirmations": 0,
        "outcomes": 0,
        "daily_summary": 0,
    }


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
