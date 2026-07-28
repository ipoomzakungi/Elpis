from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from src.xau_first_touch_study.runner import FirstTouchStudyConfig, run_study


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the research-only XAU Vol2Vol literal SD first-touch study.",
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
        "--registry",
        default="config/xau_vol2vol_first_touch_study_v1.json",
    )
    parser.add_argument(
        "--output-root",
        default="data/reports/xau_first_touch_study",
    )
    parser.add_argument("--timezone", default="Asia/Bangkok")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = run_study(
        FirstTouchStudyConfig(
            vol2vol_root=Path(args.vol2vol_root),
            price_bars_folder=Path(args.price_bars_folder),
            registry_path=Path(args.registry),
            output_root=Path(args.output_root),
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
