from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from src.models.xau_systematic_research import (
    XauSystematicCmeSourceMode,
    XauSystematicCycleRequest,
    XauSystematicPriceProvider,
)
from src.xau_systematic_research.orchestrator import XauSystematicResearchOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the research-only XAU systematic source-alignment cycle.",
    )
    parser.add_argument("--cycle-label")
    parser.add_argument("--cycle-time", choices=["10:00", "19:00", "manual"])
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--session-date")
    parser.add_argument(
        "--cme-source-mode",
        choices=[mode.value for mode in XauSystematicCmeSourceMode],
        default=XauSystematicCmeSourceMode.LATEST_EXISTING.value,
    )
    parser.add_argument("--vol2vol-report-id")
    parser.add_argument("--matrix-report-id")
    parser.add_argument("--fusion-report-id")
    parser.add_argument("--no-latest-fusion", action="store_true")
    parser.add_argument("--traded-symbol", default="XAUUSD")
    parser.add_argument(
        "--price-provider",
        choices=[provider.value for provider in XauSystematicPriceProvider],
        default=XauSystematicPriceProvider.LATEST_LOCAL_IMPORT.value,
    )
    parser.add_argument("--price-bars-path")
    parser.add_argument("--dukascopy-node-command-template")
    parser.add_argument("--dukascopy-symbol", default="xauusd")
    parser.add_argument("--dukascopy-timeframe", default="m1")
    parser.add_argument("--dukascopy-from")
    parser.add_argument("--dukascopy-to")
    parser.add_argument("--spot-symbol", default="XAUUSD=X")
    parser.add_argument("--gc-symbol", default="GC=F")
    parser.add_argument("--max-cme-age-minutes", type=int, default=180)
    parser.add_argument("--max-price-age-minutes", type=int, default=15)
    parser.add_argument("--max-basis-alignment-seconds", type=int, default=120)
    parser.add_argument("--allow-stale-basis", action="store_true")
    parser.add_argument("--output-root")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    request = XauSystematicCycleRequest(
        cycle_label=args.cycle_label,
        cycle_time=args.cycle_time,
        timezone=args.timezone,
        session_date=date.fromisoformat(args.session_date) if args.session_date else None,
        cme_source_mode=XauSystematicCmeSourceMode(args.cme_source_mode),
        vol2vol_report_id=args.vol2vol_report_id,
        matrix_report_id=args.matrix_report_id,
        fusion_report_id=args.fusion_report_id,
        use_latest_fusion=not args.no_latest_fusion,
        traded_symbol=args.traded_symbol,
        price_provider=XauSystematicPriceProvider(args.price_provider),
        price_bars_path=Path(args.price_bars_path) if args.price_bars_path else None,
        dukascopy_node_command_template=args.dukascopy_node_command_template,
        dukascopy_symbol=args.dukascopy_symbol,
        dukascopy_timeframe=args.dukascopy_timeframe,
        dukascopy_from=_parse_datetime(args.dukascopy_from),
        dukascopy_to=_parse_datetime(args.dukascopy_to),
        spot_symbol=args.spot_symbol,
        gc_symbol=args.gc_symbol,
        max_cme_age_minutes=args.max_cme_age_minutes,
        max_price_age_minutes=args.max_price_age_minutes,
        max_basis_alignment_seconds=args.max_basis_alignment_seconds,
        allow_stale_basis=args.allow_stale_basis,
        output_root=Path(args.output_root) if args.output_root else None,
        overwrite=args.overwrite,
        research_only_acknowledged=True,
    )
    result = XauSystematicResearchOrchestrator(reports_dir=request.output_root).run(request)
    print(
        json.dumps(
            {
                "cycle_id": result.cycle_id,
                "output_dir": result.output_dir.as_posix(),
                "readiness": result.readiness.value,
                "signal_allowed": False,
                "research_only": True,
                "artifacts": {
                    key: value.as_posix() for key, value in sorted(result.artifacts.items())
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


if __name__ == "__main__":
    raise SystemExit(main())
