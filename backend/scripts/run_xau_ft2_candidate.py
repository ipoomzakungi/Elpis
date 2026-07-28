from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from src.models.xau_ft2_candidate import XauFt2BrokerQuote
from src.xau_ft2_candidate.external_importer import (
    validate_external_study_file,
    write_external_import,
)
from src.xau_ft2_candidate.runner import (
    Ft2CandidateRunConfig,
    run_candidate_study,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen research-only FT2_RAW_V1 candidate workflow.",
    )
    parser.add_argument("--session-date-from", default="2026-05-31")
    parser.add_argument("--session-date-to", default=date.today().isoformat())
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--vol2vol-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--price-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    parser.add_argument("--policy", default="config/xau_ft2_raw_candidate_v1.json")
    parser.add_argument("--output-root", default="data/reports/xau_ft2_candidate")
    parser.add_argument(
        "--journal-root",
        default="data/reports/xau_ft2_candidate/v1",
    )
    parser.add_argument("--broker-quote-file")
    parser.add_argument("--external-study-file")
    parser.add_argument("--timezone", default="Asia/Bangkok")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = run_candidate_study(
        Ft2CandidateRunConfig(
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
    external_path = None
    if args.external_study_file:
        external_path = write_external_import(
            run_dir,
            validate_external_study_file(Path(args.external_study_file)),
        )
    print(
        json.dumps(
            {
                "run_dir": run_dir.as_posix(),
                "review_handoff": (run_dir / "review_handoff.md").as_posix(),
                "coverage_audit": (
                    run_dir / "strict_dte_coverage_audit.json"
                ).as_posix(),
                "external_import": external_path.as_posix() if external_path else None,
                "research_only": True,
                "signal_allowed": False,
                "order_submission_allowed": False,
            },
            indent=2,
        )
    )
    return 0


def _load_broker_quote(path_value: str | None) -> XauFt2BrokerQuote | None:
    if not path_value:
        return None
    with Path(path_value).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Broker quote CSV is empty")
    row = rows[-1]
    return XauFt2BrokerQuote(
        timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
        symbol=row["symbol"],
        bid=float(row["bid"]),
        ask=float(row["ask"]),
    )


if __name__ == "__main__":
    raise SystemExit(main())
