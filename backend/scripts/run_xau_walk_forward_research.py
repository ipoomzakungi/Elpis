from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models.xau_walk_forward_research import (  # noqa: E402
    XauResearchOrderPlanConfig,
    XauResearchRiskConfig,
    XauWalkForwardCmeSource,
    XauWalkForwardPriceSource,
    XauWalkForwardRunRequest,
    XauWalkForwardScheduleConfig,
)
from src.xau_walk_forward.service import XauWalkForwardResearchService  # noqa: E402


def main() -> None:
    args = _parser().parse_args()
    planning_only = args.mode == "planning-only"
    request = XauWalkForwardRunRequest(
        session_date=date.fromisoformat(args.session_date),
        expiration_code=args.expiration_code,
        schedule_config=XauWalkForwardScheduleConfig(
            planning_times=args.planning_time,
            capture_start_time=args.capture_start_time,
            capture_end_time=args.capture_end_time,
            capture_interval_minutes=args.capture_interval_minutes,
            include_planning_times_only=planning_only,
        ),
        order_plan_config=XauResearchOrderPlanConfig(
            entry_sd_abs=args.entry_sd,
            target_sd_abs=args.target_sd,
            stop_sd_abs=args.stop_sd,
            recovery_entry_sd_abs=args.recovery_entry_sd,
            recovery_target_sd_abs=args.recovery_target_sd,
            max_recovery_steps=args.max_recovery_steps,
        ),
        risk_config=XauResearchRiskConfig(
            point_value_per_size_unit=args.point_value_per_size_unit,
            max_size=args.max_size,
            leverage=args.leverage,
            recovery_enabled=args.point_value_per_size_unit is not None,
        ),
        cme_source=XauWalkForwardCmeSource(args.cme_source),
        price_source=XauWalkForwardPriceSource(args.price_source),
        future_reference_price=args.future_reference_price,
        traded_reference_price=args.traded_reference_price,
        input_dir=args.input_dir,
        price_bars_path=args.price_bars_path,
        run_outcome_simulation=args.run_outcome_simulation,
        output_root=args.output_root,
        overwrite_allowed=args.overwrite,
        research_only_acknowledged=True,
    )
    service = XauWalkForwardResearchService()
    result = service.run(request)
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a research-only XAU walk-forward Range Desk capture.",
    )
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--expiration-code")
    parser.add_argument(
        "--mode",
        choices=["planning-only", "walk-forward"],
        default="planning-only",
    )
    parser.add_argument("--planning-time", action="append", default=["10:10", "19:10"])
    parser.add_argument("--capture-start-time", default="10:10")
    parser.add_argument("--capture-end-time", default="21:50")
    parser.add_argument("--capture-interval-minutes", type=int, default=10)
    parser.add_argument(
        "--cme-source",
        choices=[item.value for item in XauWalkForwardCmeSource],
        default=XauWalkForwardCmeSource.LATEST_EXISTING.value,
    )
    parser.add_argument(
        "--price-source",
        choices=[item.value for item in XauWalkForwardPriceSource if item.value != "unavailable"],
        default=XauWalkForwardPriceSource.MANUAL.value,
    )
    parser.add_argument("--future-reference-price", type=float)
    parser.add_argument("--traded-reference-price", type=float)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--price-bars-path", type=Path)
    parser.add_argument("--entry-sd", type=float, default=2.0)
    parser.add_argument("--target-sd", type=float, default=1.0)
    parser.add_argument("--stop-sd", type=float, default=2.5)
    parser.add_argument("--recovery-entry-sd", type=float, default=3.0)
    parser.add_argument("--recovery-target-sd", type=float, default=2.0)
    parser.add_argument("--max-recovery-steps", type=int, default=1)
    parser.add_argument("--point-value-per-size-unit", type=float)
    parser.add_argument("--max-size", type=float)
    parser.add_argument("--leverage", type=float)
    parser.add_argument("--run-outcome-simulation", action="store_true")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


if __name__ == "__main__":
    main()
