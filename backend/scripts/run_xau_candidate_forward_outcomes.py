from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from src.models.xau_candidate_outcome import (
    XauCandidateOutcomeRunRequest,
    XauCandidateOutcomeWindow,
)
from src.xau_candidate_outcomes.service import run_xau_candidate_forward_outcomes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run research-only XAU candidate forward outcomes from local artifacts.",
    )
    parser.add_argument("--candidate-set-path", required=True)
    parser.add_argument("--price-bars-path", required=True)
    parser.add_argument(
        "--window",
        action="append",
        choices=[window.value for window in XauCandidateOutcomeWindow],
        dest="windows",
    )
    parser.add_argument("--output-root")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--open-column", default="open")
    parser.add_argument("--high-column", default="high")
    parser.add_argument("--low-column", default="low")
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--volume-column", default="volume")
    parser.add_argument("--timezone", default="UTC")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    request = XauCandidateOutcomeRunRequest(
        candidate_set_path=Path(args.candidate_set_path),
        price_bars_path=Path(args.price_bars_path),
        windows=[XauCandidateOutcomeWindow(value) for value in args.windows]
        if args.windows
        else [
            XauCandidateOutcomeWindow.THIRTY_MINUTES,
            XauCandidateOutcomeWindow.ONE_HOUR,
            XauCandidateOutcomeWindow.FOUR_HOURS,
            XauCandidateOutcomeWindow.SESSION_CLOSE,
            XauCandidateOutcomeWindow.NEXT_DAY,
        ],
        output_root=Path(args.output_root) if args.output_root else None,
        overwrite_allowed=args.overwrite,
        timestamp_column=args.timestamp_column,
        open_column=args.open_column,
        high_column=args.high_column,
        low_column=args.low_column,
        close_column=args.close_column,
        volume_column=args.volume_column,
        timezone=args.timezone,
        research_only_acknowledged=True,
    )
    result = run_xau_candidate_forward_outcomes(request)
    print(
        json.dumps(
            _summary(result),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _summary(result: BaseModel) -> dict:
    payload = result.model_dump(mode="json")
    return {
        "status": payload["readiness"],
        "outcome_run_id": payload["outcome_run_id"],
        "candidate_set_id": payload["candidate_set_id"],
        "map_id": payload["map_id"],
        "candidate_count": payload["candidate_count"],
        "outcome_count": payload["outcome_count"],
        "unavailable_count": payload["unavailable_count"],
        "artifact_paths": payload["artifact_paths"],
        "no_signal_reasons": payload["no_signal_reasons"],
        "limitations": payload["limitations"],
        "signal_allowed": payload["signal_allowed"],
        "research_only": payload["research_only"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
