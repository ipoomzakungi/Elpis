from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from src.xau_market_context.context_builder import (
    XauMarketContextBuilder,
    XauMarketContextBuilderRequest,
)
from src.xau_market_context.price_loader import load_price_bars


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a research-only XAU market context snapshot from local files.",
    )
    parser.add_argument("--fusion-report-id")
    parser.add_argument("--fusion-report-path")
    parser.add_argument("--price-bars-path", required=True)
    parser.add_argument("--traded-symbol", default="XAUUSD")
    parser.add_argument("--xauusd-spot-price", type=float)
    parser.add_argument("--gc-futures-price", type=float)
    parser.add_argument("--current-timestamp")
    parser.add_argument("--session-date")
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--max-basis-alignment-seconds", type=float, default=120.0)
    parser.add_argument("--wall-buffer-points", type=float, default=2.0)
    parser.add_argument("--output-root")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    bars = load_price_bars(
        Path(args.price_bars_path),
        default_symbol=args.traded_symbol,
        default_timezone=args.timezone,
    )
    builder = XauMarketContextBuilder()
    snapshot = builder.build(
        XauMarketContextBuilderRequest(
            price_bars=bars,
            traded_symbol=args.traded_symbol,
            fusion_report_id=args.fusion_report_id,
            fusion_report_path=Path(args.fusion_report_path)
            if args.fusion_report_path
            else None,
            xauusd_spot_price=args.xauusd_spot_price,
            gc_futures_price=args.gc_futures_price,
            current_timestamp=datetime.fromisoformat(args.current_timestamp)
            if args.current_timestamp
            else None,
            session_date=date.fromisoformat(args.session_date) if args.session_date else None,
            timezone=args.timezone,
            max_basis_alignment_seconds=args.max_basis_alignment_seconds,
            wall_buffer_points=args.wall_buffer_points,
            output_root=Path(args.output_root) if args.output_root else None,
            overwrite=args.overwrite,
        )
    )
    summary = {
        "snapshot_id": snapshot.snapshot_id,
        "basis_points": snapshot.basis.basis_points,
        "basis_status": snapshot.basis.status.value,
        "active_session": (
            snapshot.active_session.session_name.value if snapshot.active_session else None
        ),
        "session_open": (
            snapshot.active_session.open_price if snapshot.active_session else None
        ),
        "atr_5m": snapshot.volatility.atr_5m,
        "atr_15m": snapshot.volatility.atr_15m,
        "realized_vol_30m": snapshot.volatility.realized_vol_30m,
        "nearest_mapped_wall": (
            snapshot.nearest_mapped_wall.model_dump(mode="json")
            if snapshot.nearest_mapped_wall
            else None
        ),
        "candle_state": snapshot.candle_states[0].state.value
        if snapshot.candle_states
        else None,
        "readiness": snapshot.readiness.value,
        "missing_context": snapshot.missing_context,
        "signal_allowed": snapshot.signal_allowed,
        "research_only": snapshot.research_only,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

