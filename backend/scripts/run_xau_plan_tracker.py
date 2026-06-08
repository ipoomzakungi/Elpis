from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.models.xau_price_plan_tracker import XauPlanTrackerRequest
from src.xau_price_plan_tracker.service import XauPlanTrackerService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run research-only XAU plan tracker from local bars or Dukascopy CLI."
    )
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--planning-time", action="append", dest="planning_times")
    parser.add_argument("--price-bars-path")
    parser.add_argument("--dukas-cli-path")
    parser.add_argument("--dukas-command-template")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--entry-sd", type=float, default=2.0)
    parser.add_argument("--target-sd", type=float, default=1.0)
    parser.add_argument("--stop-sd", type=float, default=2.5)
    parser.add_argument("--recovery-entry-sd", type=float, default=3.0)
    parser.add_argument("--recovery-target-sd", type=float, default=2.0)
    parser.add_argument("--run-until-time", default="21:50")
    parser.add_argument("--output-root")
    parser.add_argument("--cme-source", default="latest_existing")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    request = XauPlanTrackerRequest(
        session_date=date.fromisoformat(args.session_date),
        planning_times=args.planning_times or ["10:10", "18:10"],
        price_bars_path=Path(args.price_bars_path) if args.price_bars_path else None,
        dukas_cli_path=Path(args.dukas_cli_path) if args.dukas_cli_path else None,
        command_template=args.dukas_command_template,
        symbol=args.symbol,
        timeframe=args.timeframe,
        entry_sd=args.entry_sd,
        target_sd=args.target_sd,
        stop_sd=args.stop_sd,
        recovery_entry_sd=args.recovery_entry_sd,
        recovery_target_sd=args.recovery_target_sd,
        run_until_time=args.run_until_time,
        output_root=Path(args.output_root) if args.output_root else None,
        cme_source=args.cme_source,
        overwrite=args.overwrite,
        research_only_acknowledged=True,
    )
    result = XauPlanTrackerService().run(request)
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
