from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from src.models.xau_tiered_manual_signal import XauBrokerQuote
from src.xau_tiered_manual_signal.runner import TieredStudyConfig, run_tiered_study


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the research-only tiered XAU first-touch matrix and current manual alert."
        ),
    )
    parser.add_argument("--session-date-from", default="2026-05-31")
    parser.add_argument("--session-date-to", default=date.today().isoformat())
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--vol2vol-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--price-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    parser.add_argument(
        "--policy",
        default="config/xau_tiered_first_touch_manual_signal_v1.json",
    )
    parser.add_argument(
        "--output-root",
        default="data/reports/xau_tiered_first_touch_study",
    )
    parser.add_argument(
        "--journal-root",
        default="data/reports/xau_manual_signals",
    )
    parser.add_argument(
        "--broker-quote-file",
        help="Optional CSV containing timestamp,symbol,bid,ask; the last row is used.",
    )
    parser.add_argument("--timezone", default="Asia/Bangkok")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = run_tiered_study(
        TieredStudyConfig(
            vol2vol_root=Path(args.vol2vol_root),
            price_bars_folder=Path(args.price_bars_folder),
            policy_path=Path(args.policy),
            output_root=Path(args.output_root),
            journal_root=Path(args.journal_root),
            session_date_from=date.fromisoformat(args.session_date_from),
            session_date_to=date.fromisoformat(args.session_date_to),
            as_of_date=date.fromisoformat(args.as_of_date),
            timezone=args.timezone,
            broker_quote=_load_broker_quote(args.broker_quote_file),
        )
    )
    print(
        json.dumps(
            {
                "run_dir": run_dir.as_posix(),
                "review_handoff": (run_dir / "review_handoff.md").as_posix(),
                "current_plan": (run_dir / "current_plan.json").as_posix(),
                "research_only": True,
                "signal_allowed": False,
                "order_submission_allowed": False,
            },
            indent=2,
        )
    )
    return 0


def _load_broker_quote(path_value: str | None) -> XauBrokerQuote | None:
    if not path_value:
        return None
    path = Path(path_value)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Broker quote CSV is empty: {path}")
    row = rows[-1]
    return XauBrokerQuote(
        timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
        symbol=row["symbol"],
        bid=float(row["bid"]),
        ask=float(row["ask"]),
    )


if __name__ == "__main__":
    raise SystemExit(main())
