from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau_market_context import (
    XauBasisStatus,
    XauCandleReactionState,
    XauMappedLevel,
    XauMappedLevelStatus,
    XauMarketContextReadiness,
    XauMarketContextSnapshot,
    XauPriceBar,
    XauVolatilityStatus,
)
from src.models.xau_quikstrike_fusion import XauQuikStrikeFusionReport
from src.xau_market_context.basis_mapper import (
    build_basis_snapshot,
    map_futures_levels,
)
from src.xau_market_context.candle_state import buffer_points, classify_candle_state
from src.xau_market_context.price_loader import latest_bar_at_or_before
from src.xau_market_context.report_store import (
    XauMarketContextReportStore,
    new_market_context_snapshot_id,
)
from src.xau_market_context.session_calendar import build_session_opens
from src.xau_market_context.volatility import build_volatility_snapshot


@dataclass(frozen=True)
class XauMarketContextBuilderRequest:
    price_bars: list[XauPriceBar]
    traded_symbol: str = "XAUUSD"
    cme_product: str = "GC/OG"
    fusion_report_id: str | None = None
    fusion_report_path: Path | None = None
    xauusd_spot_price: float | None = None
    gc_futures_price: float | None = None
    current_timestamp: datetime | None = None
    session_date: date | None = None
    timezone: str = "Asia/Bangkok"
    max_basis_alignment_seconds: float = 120.0
    wall_buffer_points: float = 2.0
    output_root: Path | None = None
    overwrite: bool = False


class XauMarketContextBuilder:
    def __init__(
        self,
        *,
        reports_dir: Path | None = None,
        fusion_reports_dir: Path | None = None,
    ) -> None:
        self.reports_dir = reports_dir
        self.fusion_reports_dir = fusion_reports_dir

    def build(self, request: XauMarketContextBuilderRequest) -> XauMarketContextSnapshot:
        timezone = ZoneInfo(request.timezone)
        bars = sorted(request.price_bars, key=lambda item: item.timestamp)
        current_timestamp = _current_timestamp(bars, request.current_timestamp, timezone)
        session_date = request.session_date or current_timestamp.astimezone(timezone).date()
        latest_bar = latest_bar_at_or_before(bars, current_timestamp) if bars else None
        spot_price = request.xauusd_spot_price or (latest_bar.close if latest_bar else None)
        fusion_report = _read_fusion_report(
            report_id=request.fusion_report_id,
            report_path=request.fusion_report_path,
            reports_dir=self.fusion_reports_dir,
        )
        gc_price, gc_timestamp = _gc_reference(
            explicit_price=request.gc_futures_price,
            fusion_report=fusion_report,
            current_timestamp=current_timestamp,
        )
        basis = build_basis_snapshot(
            xauusd_spot_price=spot_price,
            gc_futures_price=gc_price,
            spot_timestamp=current_timestamp if spot_price is not None else None,
            futures_timestamp=gc_timestamp,
            max_alignment_seconds=request.max_basis_alignment_seconds,
        )
        session_opens, active_session = build_session_opens(
            bars=bars,
            current_timestamp=current_timestamp,
            traded_price=spot_price,
            session_date=session_date,
            target_timezone=request.timezone,
        )
        volatility = build_volatility_snapshot(
            bars=bars,
            current_timestamp=current_timestamp,
            active_session=active_session,
        )
        source_levels = _source_levels(fusion_report=fusion_report, spot_price=spot_price)
        mapped_levels = map_futures_levels(
            source_levels,
            basis=basis,
            source="xau_quikstrike_fusion",
        )
        nearest = _nearest_mapped_wall(mapped_levels, spot_price)
        candle_states = _candle_states(
            mapped_levels=mapped_levels,
            bars=bars,
            current_timestamp=current_timestamp,
            configured_buffer=request.wall_buffer_points,
            atr_5m=volatility.atr_5m,
        )
        missing_context = _missing_context(
            bars=bars,
            basis_status=basis.status,
            active_session=active_session,
            volatility=volatility,
            candle_states=candle_states,
            fusion_report=fusion_report,
        )
        readiness = _readiness(
            bars=bars,
            basis_status=basis.status,
            active_session=active_session,
            volatility=volatility,
            candle_states=candle_states,
        )
        snapshot = XauMarketContextSnapshot(
            snapshot_id=new_market_context_snapshot_id(session_date),
            created_at=datetime.now(UTC),
            session_date=session_date,
            traded_symbol=request.traded_symbol,
            cme_product=request.cme_product,
            fusion_report_id=fusion_report.report_id if fusion_report else request.fusion_report_id,
            xauusd_spot_price=spot_price,
            gc_futures_price=gc_price,
            basis=basis,
            active_session=active_session,
            session_opens=session_opens,
            volatility=volatility,
            mapped_levels=mapped_levels,
            nearest_mapped_wall=nearest,
            candle_states=candle_states,
            missing_context=missing_context,
            readiness=readiness,
            limitations=[
                "XAU Market Context Snapshot is research-only and never enables signals.",
                "CME/QuikStrike futures levels require basis adjustment before use "
                "on XAUUSD/GO charts.",
                "Traded-side prices and candles are local inputs; this feature "
                "performs no internet fetch.",
                "OI walls are structural map levels only; candle and volatility "
                "context are required.",
            ],
        )
        store = XauMarketContextReportStore(reports_dir=request.output_root or self.reports_dir)
        return store.persist_snapshot(snapshot, overwrite=request.overwrite)


def _current_timestamp(
    bars: list[XauPriceBar],
    explicit_timestamp: datetime | None,
    timezone: ZoneInfo,
) -> datetime:
    if explicit_timestamp is not None:
        if explicit_timestamp.tzinfo is None:
            return explicit_timestamp.replace(tzinfo=timezone)
        return explicit_timestamp.astimezone(timezone)
    if bars:
        return bars[-1].timestamp.astimezone(timezone)
    return datetime.now(timezone)


def _read_fusion_report(
    *,
    report_id: str | None,
    report_path: Path | None,
    reports_dir: Path | None,
) -> XauQuikStrikeFusionReport | None:
    if report_path is not None:
        path = report_path / "report.json" if report_path.is_dir() else report_path
        if not path.exists():
            raise FileNotFoundError(path)
        return XauQuikStrikeFusionReport.model_validate_json(path.read_text(encoding="utf-8"))
    if report_id is not None:
        path = _fusion_report_root(reports_dir) / report_id / "report.json"
        if not path.exists():
            raise FileNotFoundError(report_id)
        return XauQuikStrikeFusionReport.model_validate_json(path.read_text(encoding="utf-8"))
    root = _fusion_report_root(reports_dir)
    if not root.exists():
        return None
    candidates = sorted(
        root.glob("*/report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return XauQuikStrikeFusionReport.model_validate_json(candidates[0].read_text(encoding="utf-8"))


def _fusion_report_root(reports_dir: Path | None) -> Path:
    if reports_dir is not None:
        return reports_dir / "xau_quikstrike_fusion"
    repo_root = Path(__file__).resolve().parents[3]
    backend_root = repo_root / "backend"
    backend_reports = backend_root / "data" / "reports" / "xau_quikstrike_fusion"
    if backend_reports.exists():
        return backend_reports
    return Path("data") / "reports" / "xau_quikstrike_fusion"


def _gc_reference(
    *,
    explicit_price: float | None,
    fusion_report: XauQuikStrikeFusionReport | None,
    current_timestamp: datetime,
) -> tuple[float | None, datetime | None]:
    if explicit_price is not None:
        return explicit_price, current_timestamp
    if fusion_report is None:
        return None, None
    values: list[float] = []
    for row in fusion_report.fused_rows:
        for source_value in (row.matrix_value, row.vol2vol_value):
            if source_value is not None and source_value.future_reference_price is not None:
                values.append(source_value.future_reference_price)
    if not values:
        return None, None
    counts = Counter(round(value, 4) for value in values)
    selected = counts.most_common(1)[0][0]
    return selected, fusion_report.created_at


def _source_levels(
    *,
    fusion_report: XauQuikStrikeFusionReport | None,
    spot_price: float | None,
    limit: int = 25,
) -> list[float]:
    if fusion_report is None:
        return []
    score_by_strike: dict[float, float] = defaultdict(float)
    all_strikes: set[float] = set()
    for row in fusion_report.fused_rows:
        strike = row.match_key.strike
        all_strikes.add(strike)
        value_type = row.match_key.value_type.lower()
        if value_type in {"open_interest", "oi", "oi_change", "volume", "intraday_volume"}:
            score_by_strike[strike] += _row_numeric_value(row)
    if score_by_strike:
        ranked = sorted(score_by_strike, key=lambda strike: (-score_by_strike[strike], strike))
    else:
        ranked = sorted(
            all_strikes,
            key=lambda strike: abs(strike - spot_price) if spot_price else strike,
        )
    if spot_price is not None:
        near = sorted(all_strikes, key=lambda strike: abs(strike - spot_price))[:10]
        ranked = _dedupe_float([*near, *ranked])
    return ranked[:limit]


def _row_numeric_value(row) -> float:
    values = []
    for source_value in (row.matrix_value, row.vol2vol_value):
        if source_value is not None and source_value.value is not None:
            values.append(abs(source_value.value))
    return max(values) if values else 0.0


def _nearest_mapped_wall(
    mapped_levels: list[XauMappedLevel],
    spot_price: float | None,
) -> XauMappedLevel | None:
    available = [
        item
        for item in mapped_levels
        if item.mapping_status == XauMappedLevelStatus.AVAILABLE and item.mapped_level is not None
    ]
    if not available or spot_price is None:
        return None
    return min(available, key=lambda item: abs((item.mapped_level or 0.0) - spot_price))


def _candle_states(
    *,
    mapped_levels: list[XauMappedLevel],
    bars: list[XauPriceBar],
    current_timestamp: datetime,
    configured_buffer: float,
    atr_5m: float | None,
) -> list:
    if not bars:
        return []
    last_bar = latest_bar_at_or_before(bars, current_timestamp)
    if last_bar is None:
        return []
    next_bar = next((bar for bar in bars if bar.timestamp > last_bar.timestamp), None)
    available_levels = [
        item.mapped_level
        for item in mapped_levels
        if item.mapping_status == XauMappedLevelStatus.AVAILABLE and item.mapped_level is not None
    ]
    if not available_levels:
        return []
    selected = sorted(available_levels, key=lambda level: abs(level - last_bar.close))[:5]
    resolved_buffer = buffer_points(configured_min_buffer=configured_buffer, atr_5m=atr_5m)
    return [
        classify_candle_state(
            level=level,
            candle=last_bar,
            next_bar=next_bar,
            buffer=resolved_buffer,
        )
        for level in selected
    ]


def _missing_context(
    *,
    bars: list[XauPriceBar],
    basis_status: XauBasisStatus,
    active_session,
    volatility,
    candle_states,
    fusion_report: XauQuikStrikeFusionReport | None,
) -> list[str]:
    missing: list[str] = []
    if not bars:
        missing.append("price_bars")
    if basis_status != XauBasisStatus.ALIGNED:
        missing.append("basis")
    if active_session is None or active_session.open_price is None:
        missing.append("session_open")
    if volatility.status == XauVolatilityStatus.UNAVAILABLE:
        missing.append("realized_volatility")
    if not _has_atr(volatility):
        missing.append("atr")
    if not candle_states or all(
        state.state == XauCandleReactionState.UNAVAILABLE for state in candle_states
    ):
        missing.append("candle_acceptance")
    if fusion_report is None:
        missing.append("fusion_context")
    elif fusion_report.context_summary is not None:
        missing.extend(
            item.context_key
            for item in fusion_report.context_summary.missing_context
            if item.status.value != "available"
        )
    return _dedupe_text(missing)


def _readiness(
    *,
    bars: list[XauPriceBar],
    basis_status: XauBasisStatus,
    active_session,
    volatility,
    candle_states,
) -> XauMarketContextReadiness:
    if not bars or basis_status == XauBasisStatus.UNAVAILABLE:
        return XauMarketContextReadiness.BLOCKED
    complete = (
        basis_status == XauBasisStatus.ALIGNED
        and active_session is not None
        and active_session.open_price is not None
        and volatility.status in {XauVolatilityStatus.AVAILABLE, XauVolatilityStatus.PARTIAL}
        and _has_atr(volatility)
        and bool(candle_states)
    )
    return XauMarketContextReadiness.COMPLETE if complete else XauMarketContextReadiness.PARTIAL


def _has_atr(volatility) -> bool:
    return any(
        value is not None
        for value in (volatility.atr_5m, volatility.atr_15m, volatility.atr_1h)
    )


def _dedupe_float(values: list[float]) -> list[float]:
    seen: set[float] = set()
    result: list[float] = []
    for value in values:
        normalized = round(value, 8)
        if normalized not in seen:
            result.append(value)
            seen.add(normalized)
    return result


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
