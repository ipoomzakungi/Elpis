from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from src.models.xau_plan_tracker_statistics import XauPlanTrackerStatsRequest
from src.models.xau_price_plan_tracker import XauResearchOrderSide, XauTrackedOrderStatus
from src.xau_plan_tracker_statistics.service import XauPlanTrackerStatisticsService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate research-only XAU plan-tracker outcomes.",
    )
    parser.add_argument("--session-date-from")
    parser.add_argument("--session-date-to")
    parser.add_argument("--planning-time", action="append", dest="planning_times")
    parser.add_argument(
        "--side",
        action="append",
        choices=[side.value for side in XauResearchOrderSide],
    )
    parser.add_argument(
        "--status",
        action="append",
        choices=[status.value for status in XauTrackedOrderStatus],
    )
    parser.add_argument("--include-unavailable-orders", action="store_true")
    parser.add_argument("--max-runs", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    service = XauPlanTrackerStatisticsService(
        reports_dir=Path(args.output_root) if args.output_root else None,
    )

    request = XauPlanTrackerStatsRequest(
        session_date_from=date.fromisoformat(args.session_date_from)
        if args.session_date_from
        else None,
        session_date_to=date.fromisoformat(args.session_date_to)
        if args.session_date_to
        else None,
        planning_times=args.planning_times or [],
        sides=[XauResearchOrderSide(value) for value in args.side] if args.side else [],
        statuses=[
            XauTrackedOrderStatus(value) for value in args.status
        ]
        if args.status
        else [],
        include_unavailable_orders=args.include_unavailable_orders,
        max_runs=args.max_runs,
    )

    if args.run_id:
        result = service.run_for_run(run_id=args.run_id, request=request)
    else:
        result = service.run(request)

    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
