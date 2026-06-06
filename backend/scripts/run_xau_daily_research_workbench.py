from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.models.xau_daily_workbench import (  # noqa: E402
    XauDailyWorkbenchCmeSource,
    XauDailyWorkbenchRunRequest,
)
from src.xau_daily_workbench.service import run_xau_daily_research_workbench  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the research-only XAU daily workbench."
    )
    parser.add_argument("--session-date", type=_parse_date)
    parser.add_argument("--expiration-code")
    parser.add_argument("--traded-instrument", default="XAUUSD")
    parser.add_argument(
        "--cme-source",
        choices=[source.value for source in XauDailyWorkbenchCmeSource],
        default=XauDailyWorkbenchCmeSource.LATEST_EXISTING.value,
    )
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--gc-reference-price", type=float)
    parser.add_argument("--traded-reference-price", type=float)
    parser.add_argument("--manual-basis", type=float)
    parser.add_argument("--session-open-price", type=float)
    parser.add_argument("--confirmation-state", default="unavailable")
    parser.add_argument("--iv-state", default="unavailable")
    parser.add_argument("--flow-state", default="unavailable")
    parser.add_argument("--output-root", type=Path, default=BACKEND_ROOT / "data" / "reports")
    parser.add_argument("--map-id")
    parser.add_argument("--no-candidates", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        result = run_xau_daily_research_workbench(
            XauDailyWorkbenchRunRequest(
                session_date=args.session_date,
                expiration_code=args.expiration_code,
                traded_instrument=args.traded_instrument,
                cme_source=args.cme_source,
                input_dir=args.input_dir,
                gc_reference_price=args.gc_reference_price,
                traded_reference_price=args.traded_reference_price,
                manual_basis=args.manual_basis,
                session_open_price=args.session_open_price,
                confirmation_state=args.confirmation_state,
                iv_state=args.iv_state,
                flow_state=args.flow_state,
                output_root=args.output_root,
                map_id=args.map_id,
                run_candidates=not args.no_candidates,
                overwrite_allowed=args.overwrite,
                research_only_acknowledged=True,
            )
        )
    except (ValidationError, ValueError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(_summary(result.model_dump(mode="json")), indent=2, sort_keys=True))
    return 0


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload["readiness"],
        "run_id": payload["run_id"],
        "map_id": payload.get("map_id"),
        "candidate_set_id": payload.get("candidate_set_id"),
        "readiness": payload["readiness"],
        "artifact_paths": payload.get("artifact_paths", {}),
        "map_artifact_paths": payload.get("map_artifact_paths", {}),
        "candidate_artifact_paths": payload.get("candidate_artifact_paths", {}),
        "no_signal_reasons": payload.get("no_signal_reasons", []),
        "missing_inputs": payload.get("missing_inputs", []),
        "signal_allowed": payload["signal_allowed"],
        "research_only": payload["research_only"],
    }


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


if __name__ == "__main__":
    raise SystemExit(main())
