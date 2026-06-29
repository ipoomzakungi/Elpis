from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.xau_price_provider import (
    XauPriceProviderKind,
    XauPriceProviderQuality,
    XauResolvedMarketInputs,
    XauResolvedPrice,
)
from src.xau_market_context.price_loader import latest_bar_at_or_before, load_price_bars


def unavailable_price(
    *,
    symbol: str,
    provider: XauPriceProviderKind = XauPriceProviderKind.UNAVAILABLE,
    warning: str,
    limitation: str | None = None,
) -> XauResolvedPrice:
    return XauResolvedPrice(
        symbol=symbol,
        price=None,
        timestamp=None,
        provider=provider,
        provider_quality=XauPriceProviderQuality.UNAVAILABLE,
        warnings=[warning],
        limitations=[limitation or warning],
    )


def manual_price(
    *,
    symbol: str,
    price: float | None,
    timestamp: datetime | None,
) -> XauResolvedPrice:
    if price is None:
        return unavailable_price(
            symbol=symbol,
            provider=XauPriceProviderKind.MANUAL,
            warning=f"Manual {symbol} price was not supplied.",
        )
    return XauResolvedPrice(
        symbol=symbol,
        price=price,
        timestamp=timestamp,
        provider=XauPriceProviderKind.MANUAL,
        provider_quality=XauPriceProviderQuality.MANUAL_FALLBACK,
        warnings=[] if timestamp is not None else ["Manual price timestamp is unavailable."],
        limitations=["Manual prices are local research inputs and are not execution-grade."],
    )


def resolve_latest_price_from_bars(
    path: Path,
    *,
    symbol: str,
    timezone: str = "Asia/Bangkok",
    current_timestamp: datetime | None = None,
    provider: XauPriceProviderKind = XauPriceProviderKind.LOCAL_BARS,
) -> XauResolvedPrice:
    try:
        bars = load_price_bars(path, default_symbol=symbol, default_timezone=timezone)
    except (OSError, ValueError) as exc:
        return unavailable_price(
            symbol=symbol,
            provider=provider,
            warning=f"Could not load local price bars: {exc}",
            limitation="Local traded-side bars are required for automated spot context.",
        )
    if not bars:
        return unavailable_price(
            symbol=symbol,
            provider=provider,
            warning="Local price bars file contained no bars.",
        )
    bar = latest_bar_at_or_before(bars, current_timestamp) if current_timestamp else bars[-1]
    if bar is None:
        return unavailable_price(
            symbol=symbol,
            provider=provider,
            warning="No local price bar was available at or before current_timestamp.",
        )
    return XauResolvedPrice(
        symbol=symbol,
        price=bar.close,
        timestamp=bar.timestamp,
        provider=provider,
        provider_quality=XauPriceProviderQuality.RESEARCH_GOOD,
        source_path=path.as_posix(),
        warnings=[],
        limitations=["Local bars are research-good traded-side context, not execution data."],
    )


def extract_gc_reference_from_fusion(fusion_path: Path) -> XauResolvedPrice:
    report_dir = fusion_path if fusion_path.is_dir() else fusion_path.parent
    rows_path = report_dir / "fused_rows.json"
    if not rows_path.exists() and fusion_path.is_file():
        rows_path = fusion_path
    try:
        rows_payload = json.loads(rows_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return unavailable_price(
            symbol="GC",
            provider=XauPriceProviderKind.LATEST_FUSION,
            warning=f"Could not read fusion GC reference: {exc}",
        )
    if not isinstance(rows_payload, list):
        return unavailable_price(
            symbol="GC",
            provider=XauPriceProviderKind.LATEST_FUSION,
            warning="Fusion fused_rows.json is not a list.",
        )

    values: list[float] = []
    values_by_dte: list[tuple[float, float]] = []
    for row in rows_payload:
        if not isinstance(row, dict):
            continue
        for source_key in ("matrix_value", "vol2vol_value"):
            source_value = row.get(source_key)
            if not isinstance(source_value, dict):
                continue
            price = _optional_float(source_value.get("future_reference_price"))
            if price is None:
                continue
            values.append(price)
            dte = _optional_float(source_value.get("dte"))
            if dte is not None:
                values_by_dte.append((dte, price))
    if not values:
        return unavailable_price(
            symbol="GC",
            provider=XauPriceProviderKind.LATEST_FUSION,
            warning="No future_reference_price was found in fusion rows.",
        )

    selected = _select_gc_price(values=values, values_by_dte=values_by_dte)
    timestamp = _fusion_timestamp(report_dir)
    return XauResolvedPrice(
        symbol="GC",
        price=selected,
        timestamp=timestamp,
        provider=XauPriceProviderKind.LATEST_FUSION,
        provider_quality=(
            XauPriceProviderQuality.RESEARCH_GOOD
            if timestamp is not None
            else XauPriceProviderQuality.RESEARCH_FALLBACK
        ),
        source_path=report_dir.as_posix(),
        warnings=[] if timestamp is not None else ["Fusion GC timestamp is unavailable."],
        limitations=[
            "Fusion GC reference is research context from local QuikStrike artifacts."
        ],
    )


def basis_alignment_seconds(
    traded_price: XauResolvedPrice,
    gc_futures_price: XauResolvedPrice,
) -> float | None:
    if traded_price.timestamp is None or gc_futures_price.timestamp is None:
        return None
    return abs((traded_price.timestamp - gc_futures_price.timestamp).total_seconds())


def build_resolved_market_inputs(
    *,
    traded_price: XauResolvedPrice,
    gc_futures_price: XauResolvedPrice,
    current_timestamp: datetime | None,
    price_bars_path: Path | None,
    fusion_report_path: Path | None,
    max_basis_alignment_seconds: float,
    allow_stale_basis: bool = False,
) -> XauResolvedMarketInputs:
    alignment = basis_alignment_seconds(traded_price, gc_futures_price)
    missing: list[str] = []
    warnings = [*traded_price.warnings, *gc_futures_price.warnings]
    limitations = [*traded_price.limitations, *gc_futures_price.limitations]
    if traded_price.price is None:
        missing.append("traded_price")
    if gc_futures_price.price is None:
        missing.append("gc_futures_price")
    if current_timestamp is None:
        missing.append("current_timestamp")
    if alignment is None and traded_price.price is not None and gc_futures_price.price is not None:
        warnings.append("basis timestamp alignment is unknown")
        if not allow_stale_basis:
            missing.append("basis_alignment")
    elif alignment is not None and alignment > max_basis_alignment_seconds:
        warnings.append(
            "basis timestamp alignment exceeds max tolerance; basis should be stale/partial."
        )
        if not allow_stale_basis:
            missing.append("basis_alignment")

    return XauResolvedMarketInputs(
        traded_price=traded_price,
        gc_futures_price=gc_futures_price,
        current_timestamp=current_timestamp,
        price_bars_path=price_bars_path,
        fusion_report_id=fusion_report_path.name if fusion_report_path else None,
        fusion_report_path=fusion_report_path,
        basis_alignment_seconds=alignment,
        missing_inputs=_dedupe(missing),
        warnings=_dedupe(warnings),
        limitations=_dedupe(limitations),
    )


def should_pass_gc_price_to_builder(
    inputs: XauResolvedMarketInputs,
    *,
    max_basis_alignment_seconds: float,
    allow_stale_basis: bool,
) -> bool:
    if inputs.gc_futures_price.price is None or inputs.traded_price.price is None:
        return False
    if allow_stale_basis:
        return True
    alignment = inputs.basis_alignment_seconds
    return alignment is not None and alignment <= max_basis_alignment_seconds


def _select_gc_price(*, values: list[float], values_by_dte: list[tuple[float, float]]) -> float:
    if values_by_dte:
        near_dte = min(values_by_dte, key=lambda item: (item[0], item[1]))
        return near_dte[1]
    counts = Counter(round(value, 4) for value in values)
    return counts.most_common(1)[0][0]


def _fusion_timestamp(report_dir: Path) -> datetime | None:
    for filename in ("metadata.json", "report.json"):
        path = report_dir / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        parsed = _created_at(payload)
        if parsed is not None:
            return parsed
    return None


def _created_at(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    for key in ("created_at", "completed_at", "capture_time", "timestamp"):
        value = payload.get(key)
        if value:
            parsed = _parse_datetime(value)
            if parsed is not None:
                return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result

