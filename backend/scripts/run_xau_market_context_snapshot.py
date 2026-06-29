from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from src.models.xau_price_provider import XauPriceProviderKind, XauResolvedPrice
from src.xau_market_context.context_builder import (
    XauMarketContextBuilder,
    XauMarketContextBuilderRequest,
)
from src.xau_market_context.latest_artifact import (
    find_latest_fusion_report,
    find_latest_price_bars,
)
from src.xau_market_context.price_loader import load_price_bars
from src.xau_market_context.price_provider import (
    build_resolved_market_inputs,
    extract_gc_reference_from_fusion,
    manual_price,
    resolve_latest_price_from_bars,
    should_pass_gc_price_to_builder,
    unavailable_price,
)
from src.xau_market_context.yfinance_provider import (
    fetch_yfinance_bars,
    fetch_yfinance_price,
    save_yfinance_bars,
)


def build_parser() -> argparse.ArgumentParser:
    backend_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Build a research-only XAU market context snapshot from local files.",
    )
    parser.add_argument("--fusion-report-id")
    parser.add_argument("--fusion-report-path")
    parser.add_argument("--use-latest-fusion", action="store_true")
    parser.add_argument(
        "--latest-fusion-root",
        default=str(backend_root / "data" / "reports" / "xau_quikstrike_fusion"),
    )
    parser.add_argument("--price-bars-path")
    parser.add_argument(
        "--price-bars-provider",
        choices=["local_bars", "latest_local_import", "yfinance"],
        default="local_bars",
    )
    parser.add_argument(
        "--auto-price-provider",
        choices=["manual", "local_bars", "latest_local_import", "yfinance"],
        default="local_bars",
    )
    parser.add_argument(
        "--latest-import-root",
        default=str(backend_root / "data" / "imports"),
    )
    parser.add_argument("--traded-symbol", default="XAUUSD")
    parser.add_argument("--spot-symbol", default="XAUUSD=X")
    parser.add_argument("--gc-symbol", default="GC=F")
    parser.add_argument("--yfinance-interval", default="1m")
    parser.add_argument("--yfinance-period", default="1d")
    parser.add_argument("--xauusd-spot-price", type=float)
    parser.add_argument("--gc-futures-price", type=float)
    parser.add_argument("--current-timestamp")
    parser.add_argument("--session-date")
    parser.add_argument("--timezone", default="Asia/Bangkok")
    parser.add_argument("--max-basis-alignment-seconds", type=float, default=120.0)
    parser.add_argument("--allow-stale-basis", action="store_true")
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

    explicit_timestamp = (
        datetime.fromisoformat(args.current_timestamp) if args.current_timestamp else None
    )
    fusion_path = _resolve_fusion_path(args)
    price_bars_path = _resolve_price_bars_path(args)
    yfinance_bars = []
    if price_bars_path is None and args.price_bars_provider == "yfinance":
        yfinance_bars = fetch_yfinance_bars(
            symbol=args.spot_symbol,
            interval=args.yfinance_interval,
            period=args.yfinance_period,
            timezone=args.timezone,
        )
        price_bars_path = save_yfinance_bars(
            bars=yfinance_bars,
            output_dir=Path(args.latest_import_root) / "yfinance",
            symbol=args.spot_symbol,
            interval=args.yfinance_interval,
        )

    bars = (
        load_price_bars(
            price_bars_path,
            default_symbol=args.traded_symbol,
            default_timezone=args.timezone,
        )
        if price_bars_path is not None
        else yfinance_bars
    )
    current_timestamp = explicit_timestamp or (bars[-1].timestamp if bars else None)
    traded_price = _resolve_traded_price(
        args=args,
        price_bars_path=price_bars_path,
        current_timestamp=current_timestamp,
    )
    gc_price = _resolve_gc_price(
        args=args,
        fusion_path=fusion_path,
        traded_price=traded_price,
        current_timestamp=current_timestamp,
    )
    resolved_inputs = build_resolved_market_inputs(
        traded_price=traded_price,
        gc_futures_price=gc_price,
        current_timestamp=current_timestamp,
        price_bars_path=price_bars_path,
        fusion_report_path=fusion_path,
        max_basis_alignment_seconds=args.max_basis_alignment_seconds,
        allow_stale_basis=args.allow_stale_basis,
    )
    pass_gc = should_pass_gc_price_to_builder(
        resolved_inputs,
        max_basis_alignment_seconds=args.max_basis_alignment_seconds,
        allow_stale_basis=args.allow_stale_basis,
    )
    builder = XauMarketContextBuilder()
    snapshot = builder.build(
        XauMarketContextBuilderRequest(
            price_bars=bars,
            traded_symbol=args.traded_symbol,
            fusion_report_id=args.fusion_report_id,
            fusion_report_path=fusion_path,
            xauusd_spot_price=traded_price.price,
            xauusd_spot_timestamp=traded_price.timestamp,
            gc_futures_price=gc_price.price if pass_gc else None,
            gc_futures_timestamp=gc_price.timestamp if pass_gc else None,
            current_timestamp=current_timestamp,
            session_date=date.fromisoformat(args.session_date) if args.session_date else None,
            timezone=args.timezone,
            max_basis_alignment_seconds=args.max_basis_alignment_seconds,
            wall_buffer_points=args.wall_buffer_points,
            output_root=Path(args.output_root) if args.output_root else None,
            overwrite=args.overwrite,
        )
    )
    context_path = _context_path(snapshot.snapshot_id, args.output_root)
    summary = {
        "snapshot_id": snapshot.snapshot_id,
        "context_path": context_path.as_posix(),
        "resolved_inputs": resolved_inputs.model_dump(mode="json"),
        "basis_points": snapshot.basis.basis_points,
        "basis_status": snapshot.basis.status.value,
        "basis_alignment_seconds": resolved_inputs.basis_alignment_seconds,
        "active_session": (
            snapshot.active_session.session_name.value if snapshot.active_session else None
        ),
        "current_timestamp": current_timestamp.isoformat() if current_timestamp else None,
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


def _resolve_fusion_path(args: argparse.Namespace) -> Path | None:
    if args.fusion_report_path:
        return Path(args.fusion_report_path)
    if args.use_latest_fusion and not args.fusion_report_id:
        return find_latest_fusion_report(Path(args.latest_fusion_root))
    if args.fusion_report_id:
        return Path(args.latest_fusion_root) / args.fusion_report_id
    return None


def _resolve_price_bars_path(args: argparse.Namespace) -> Path | None:
    if args.price_bars_path:
        return Path(args.price_bars_path)
    if args.price_bars_provider == "latest_local_import":
        return find_latest_price_bars(Path(args.latest_import_root), args.traded_symbol)
    return None


def _resolve_traded_price(
    *,
    args: argparse.Namespace,
    price_bars_path: Path | None,
    current_timestamp: datetime | None,
) -> XauResolvedPrice:
    if args.xauusd_spot_price is not None:
        return manual_price(
            symbol=args.traded_symbol,
            price=args.xauusd_spot_price,
            timestamp=current_timestamp,
        )
    if args.auto_price_provider == "yfinance":
        return fetch_yfinance_price(
            symbol=args.spot_symbol,
            interval=args.yfinance_interval,
            period=args.yfinance_period,
            timezone=args.timezone,
        )
    if price_bars_path is None:
        return unavailable_price(
            symbol=args.traded_symbol,
            warning="No traded-side price bars path was resolved.",
        )
    provider = (
        XauPriceProviderKind.LATEST_LOCAL_IMPORT
        if args.auto_price_provider == "latest_local_import"
        else XauPriceProviderKind.LOCAL_BARS
    )
    return resolve_latest_price_from_bars(
        price_bars_path,
        symbol=args.traded_symbol,
        timezone=args.timezone,
        current_timestamp=current_timestamp,
        provider=provider,
    )


def _resolve_gc_price(
    *,
    args: argparse.Namespace,
    fusion_path: Path | None,
    traded_price: XauResolvedPrice,
    current_timestamp: datetime | None,
) -> XauResolvedPrice:
    if args.gc_futures_price is not None:
        return manual_price(
            symbol="GC",
            price=args.gc_futures_price,
            timestamp=current_timestamp,
        )
    fusion_price = (
        extract_gc_reference_from_fusion(fusion_path)
        if fusion_path is not None
        else unavailable_price(symbol="GC", warning="No fusion path was resolved.")
    )
    if args.auto_price_provider != "yfinance":
        return fusion_price
    yfinance_price = fetch_yfinance_price(
        symbol=args.gc_symbol,
        interval=args.yfinance_interval,
        period=args.yfinance_period,
        timezone=args.timezone,
    )
    if yfinance_price.price is None:
        return fusion_price
    if fusion_price.price is None:
        return yfinance_price
    fusion_gap = _alignment_to_traded(traded_price, fusion_price)
    yfinance_gap = _alignment_to_traded(traded_price, yfinance_price)
    if fusion_gap is None or (yfinance_gap is not None and yfinance_gap <= fusion_gap):
        return yfinance_price
    return fusion_price


def _alignment_to_traded(
    traded_price: XauResolvedPrice,
    other_price: XauResolvedPrice,
) -> float | None:
    if traded_price.timestamp is None or other_price.timestamp is None:
        return None
    return abs((traded_price.timestamp - other_price.timestamp).total_seconds())


def _context_path(snapshot_id: str, output_root: str | None) -> Path:
    root = Path(output_root) if output_root else Path("data") / "reports"
    return root / "xau_market_context" / snapshot_id / "context.json"


if __name__ == "__main__":
    raise SystemExit(main())
