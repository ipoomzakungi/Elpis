from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from src.xau_ft2_candidate.integrity_runner import (
    Ft2IntegrityRunConfig,
    run_integrity_study,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rerun FT2_RAW_V1 with 034D timestamp and fill integrity.",
    )
    parser.add_argument("--session-date-from", default="2026-05-31")
    parser.add_argument("--session-date-to", default="2026-07-27")
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--vol2vol-root", default="data/imports/vol2vol")
    parser.add_argument(
        "--price-bars-folder",
        default="data/imports/xau/dukascopy/xauusd/m1",
    )
    parser.add_argument("--candidate-policy", default="config/xau_ft2_raw_candidate_v1.json")
    parser.add_argument("--integrity-policy", default="config/xau_ft2_integrity_v1.json")
    parser.add_argument("--output-root", default="data/reports/xau_ft2_integrity")
    parser.add_argument("--supersedes-run-dir", required=True)
    parser.add_argument("--timezone", default="Asia/Bangkok")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = run_integrity_study(
        Ft2IntegrityRunConfig(
            vol2vol_root=Path(args.vol2vol_root),
            price_bars_folder=Path(args.price_bars_folder),
            candidate_policy_path=Path(args.candidate_policy),
            integrity_policy_path=Path(args.integrity_policy),
            output_root=Path(args.output_root),
            supersedes_run_dir=Path(args.supersedes_run_dir),
            session_date_from=date.fromisoformat(args.session_date_from),
            session_date_to=date.fromisoformat(args.session_date_to),
            as_of_date=date.fromisoformat(args.as_of_date),
            timezone=args.timezone,
        )
    )
    print(
        json.dumps(
            {
                "run_dir": run_dir.as_posix(),
                "review_handoff": (run_dir / "review_handoff.md").as_posix(),
                "research_only": True,
                "signal_allowed": False,
                "order_submission_allowed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
