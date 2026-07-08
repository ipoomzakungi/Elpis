from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.models.xau_market_context import (
    XauBasisStatus,
    XauCandleReactionState,
    XauPriceBar,
)
from src.models.xau_quikstrike_fusion import (
    XauFusionContextStatus,
    XauQuikStrikeFusionReport,
)
from src.models.xau_systematic_research import (
    XauAlignedSourceState,
    XauSystematicBasisState,
    XauSystematicCmeState,
    XauSystematicCycleRequest,
    XauSystematicMappedStructure,
    XauSystematicPriceState,
    XauSystematicReadinessFlags,
    XauSystematicRegimeStates,
    XauSystematicSessionState,
    XauSystematicVolatilityState,
)
from src.xau_market_context.basis_mapper import build_basis_snapshot
from src.xau_market_context.candle_state import buffer_points, classify_candle_state
from src.xau_market_context.price_loader import latest_bar_at_or_before
from src.xau_market_context.price_provider import extract_gc_reference_from_fusion
from src.xau_market_context.session_calendar import build_session_opens
from src.xau_market_context.volatility import build_volatility_snapshot
from src.xau_systematic_research.source_manifest import (
    no_trade_reasons_for_readiness,
    readiness_flags,
    readiness_from_state,
)


class XauSystematicAlignmentEngine:
    def align(
        self,
        *,
        request: XauSystematicCycleRequest,
        cycle_id: str,
        created_at: datetime,
        fusion_report: XauQuikStrikeFusionReport | None,
        fusion_report_path,
        price_bars: list[XauPriceBar],
        bars_path,
        current_timestamp: datetime | None = None,
        gc_futures_price: float | None = None,
        gc_futures_timestamp: datetime | None = None,
        cme_partial: bool = False,
    ) -> XauAlignedSourceState:
        timezone = ZoneInfo(request.timezone)
        bars = sorted(price_bars, key=lambda item: item.timestamp)
        current = _current_timestamp(bars, current_timestamp, timezone)
        session_date = request.session_date or current.astimezone(timezone).date()
        latest_bar = latest_bar_at_or_before(bars, current) if bars else None
        latest_price = latest_bar.close if latest_bar else None
        latest_price_timestamp = latest_bar.timestamp if latest_bar else None
        resolved_gc_price, resolved_gc_timestamp = _resolve_gc_reference(
            fusion_report=fusion_report,
            fusion_report_path=fusion_report_path,
            explicit_price=gc_futures_price,
            explicit_timestamp=gc_futures_timestamp,
        )
        basis = build_basis_snapshot(
            xauusd_spot_price=latest_price,
            gc_futures_price=resolved_gc_price,
            spot_timestamp=latest_price_timestamp,
            futures_timestamp=resolved_gc_timestamp,
            max_alignment_seconds=request.max_basis_alignment_seconds,
        )
        session_opens, active_session = build_session_opens(
            bars=bars,
            current_timestamp=current,
            traded_price=latest_price,
            session_date=session_date,
            target_timezone=request.timezone,
        )
        volatility = build_volatility_snapshot(
            bars=bars,
            current_timestamp=current,
            active_session=active_session,
        )
        top_walls = _top_futures_walls(fusion_report, limit=10)
        mapped_walls = _mapped_walls(
            top_walls,
            basis_points=basis.basis_points,
            basis_status=basis.status,
            allow_stale_basis=request.allow_stale_basis,
            latest_price=latest_price,
        )
        nearest = _nearest_wall(mapped_walls)
        candle_states = _candle_states(
            mapped_walls=mapped_walls,
            bars=bars,
            current_timestamp=current,
            atr_5m=volatility.atr_5m,
        )
        cme_age_minutes = _age_minutes(current, fusion_report.created_at if fusion_report else None)
        price_age_minutes = _age_minutes(current, latest_price_timestamp)
        cme_is_stale = (
            cme_age_minutes is not None and cme_age_minutes > request.max_cme_age_minutes
        )
        price_is_stale = (
            price_age_minutes is not None and price_age_minutes > request.max_price_age_minutes
        )
        wall_distance_points = nearest.get("distance_points") if nearest else None
        wall_distance_atr = (
            wall_distance_points / volatility.atr_5m
            if wall_distance_points is not None and volatility.atr_5m
            else None
        )
        state = XauAlignedSourceState(
            cycle_id=cycle_id,
            created_at=created_at,
            session_date=session_date,
            cycle_label=request.cycle_label,
            cme=_cme_state(fusion_report, cme_age_minutes),
            price=XauSystematicPriceState(
                traded_symbol=request.traded_symbol,
                provider=request.price_provider,
                bars_path=bars_path,
                latest_price=latest_price,
                latest_price_timestamp=latest_price_timestamp,
                price_age_minutes=price_age_minutes,
            ),
            basis=XauSystematicBasisState(
                gc_futures_price=resolved_gc_price,
                xauusd_spot_price=latest_price,
                basis_points=basis.basis_points,
                basis_status=basis.status,
                alignment_seconds=basis.timestamp_alignment_seconds,
            ),
            session=XauSystematicSessionState(
                active_session=active_session.session_name.value if active_session else None,
                session_open=active_session.open_price if active_session else None,
                open_distance_points=(
                    active_session.open_distance_points if active_session else None
                ),
                open_side=active_session.open_side if active_session else None,
            ),
            volatility=XauSystematicVolatilityState(
                atr_5m=volatility.atr_5m,
                atr_15m=volatility.atr_15m,
                atr_1h=volatility.atr_1h,
                realized_vol_30m=volatility.realized_vol_30m,
                realized_vol_session=volatility.realized_vol_session,
                status=volatility.status,
            ),
            mapped_structure=XauSystematicMappedStructure(
                top_mapped_walls=mapped_walls,
                nearest_mapped_wall=nearest,
                mapped_sd_bands=_mapped_sd_bands(
                    fusion_report,
                    basis_points=basis.basis_points,
                    basis_status=basis.status,
                    allow_stale_basis=request.allow_stale_basis,
                ),
                wall_distance_points=wall_distance_points,
                wall_distance_atr=wall_distance_atr,
            ),
            states=XauSystematicRegimeStates(
                oi_state="structural_only" if fusion_report else "unavailable",
                iv_state=_iv_state(fusion_report),
                volume_state=_volume_state(fusion_report, cme_is_stale=cme_is_stale),
                candle_state=_primary_candle_state(candle_states),
                regime_state="research_context_only",
            ),
            readiness=XauSystematicReadinessFlags(
                blocked=False,
                partial=True,
                ready_for_shadow_review=False,
            ),
            no_trade_reasons=[],
        )
        readiness = readiness_from_state(
            state,
            cme_is_stale=cme_is_stale or cme_partial,
            price_is_stale=price_is_stale,
            allow_stale_basis=request.allow_stale_basis,
        )
        return state.model_copy(
            update={
                "readiness": XauSystematicReadinessFlags(**readiness_flags(readiness)),
                "no_trade_reasons": no_trade_reasons_for_readiness(state, readiness),
            }
        )


def map_cme_level_to_spot_equivalent(
    *,
    cme_level: float,
    gc_futures_price: float,
    xauusd_spot_price: float,
) -> float:
    basis_points = gc_futures_price - xauusd_spot_price
    return cme_level - basis_points


def _cme_state(
    fusion_report: XauQuikStrikeFusionReport | None,
    cme_age_minutes: float | None,
) -> XauSystematicCmeState:
    if fusion_report is None:
        return XauSystematicCmeState(cme_age_minutes=cme_age_minutes)
    coverage = fusion_report.coverage
    return XauSystematicCmeState(
        vol2vol_report_id=fusion_report.vol2vol_source.report_id,
        matrix_report_id=fusion_report.matrix_source.report_id,
        fusion_report_id=fusion_report.report_id,
        cme_created_at=fusion_report.created_at,
        cme_age_minutes=cme_age_minutes,
        row_counts={
            "vol2vol": fusion_report.vol2vol_source.row_count,
            "matrix": fusion_report.matrix_source.row_count,
            "fused": fusion_report.fused_row_count,
        },
        strike_count=coverage.strike_count if coverage else 0,
        expiration_count=coverage.expiration_count if coverage else 0,
        unavailable_cell_count=_unavailable_cell_count(fusion_report),
    )


def _top_futures_walls(
    fusion_report: XauQuikStrikeFusionReport | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if fusion_report is None:
        return []
    score_by_strike: dict[float, float] = defaultdict(float)
    value_types: dict[float, set[str]] = defaultdict(set)
    for row in fusion_report.fused_rows:
        strike = row.match_key.strike
        for source_value in (row.matrix_value, row.vol2vol_value):
            if source_value is None:
                continue
            value_type = (source_value.value_type or row.match_key.value_type).lower()
            if value_type in {"open_interest", "oi", "oi_change", "volume", "intraday_volume"}:
                value_types[strike].add(value_type)
                if source_value.value is not None:
                    score_by_strike[strike] += abs(source_value.value)
    if not score_by_strike:
        return []
    ranked = sorted(score_by_strike, key=lambda strike: (-score_by_strike[strike], strike))
    return [
        {
            "futures_level": strike,
            "score": score_by_strike[strike],
            "value_types": sorted(value_types[strike]),
        }
        for strike in ranked[:limit]
    ]


def _mapped_walls(
    walls: list[dict[str, Any]],
    *,
    basis_points: float | None,
    basis_status: XauBasisStatus,
    allow_stale_basis: bool,
    latest_price: float | None,
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    mapping_available = basis_points is not None and (
        basis_status == XauBasisStatus.ALIGNED
        or (basis_status == XauBasisStatus.STALE and allow_stale_basis)
    )
    for wall in walls:
        futures_level = wall["futures_level"]
        mapped_level = futures_level - basis_points if mapping_available else None
        distance = (
            abs(mapped_level - latest_price)
            if mapped_level is not None and latest_price is not None
            else None
        )
        mapped.append(
            {
                **wall,
                "mapped_level": mapped_level,
                "basis_points": basis_points,
                "mapping_status": "available" if mapped_level is not None else "unavailable",
                "distance_points": distance,
            }
        )
    return mapped


def _nearest_wall(mapped_walls: list[dict[str, Any]]) -> dict[str, Any] | None:
    available = [wall for wall in mapped_walls if wall.get("distance_points") is not None]
    if not available:
        return None
    return min(available, key=lambda wall: wall["distance_points"])


def _mapped_sd_bands(
    fusion_report: XauQuikStrikeFusionReport | None,
    *,
    basis_points: float | None,
    basis_status: XauBasisStatus,
    allow_stale_basis: bool,
) -> list[dict[str, Any]]:
    snapshot = fusion_report.expected_range_snapshot if fusion_report else None
    if snapshot is None:
        return []
    mapping_available = basis_points is not None and (
        basis_status == XauBasisStatus.ALIGNED
        or (basis_status == XauBasisStatus.STALE and allow_stale_basis)
    )
    bands = []
    for label, lower, upper in (
        ("1sd", snapshot.lower_1sd, snapshot.upper_1sd),
        ("2sd", snapshot.lower_2sd, snapshot.upper_2sd),
        ("3sd", snapshot.lower_3sd, snapshot.upper_3sd),
    ):
        if lower is None and upper is None:
            continue
        bands.append(
            {
                "band": label,
                "futures_lower": lower,
                "futures_upper": upper,
                "mapped_lower": lower - basis_points if lower and mapping_available else None,
                "mapped_upper": upper - basis_points if upper and mapping_available else None,
                "mapping_status": "available" if mapping_available else "unavailable",
            }
        )
    return bands


def _candle_states(
    *,
    mapped_walls: list[dict[str, Any]],
    bars: list[XauPriceBar],
    current_timestamp: datetime,
    atr_5m: float | None,
) -> list[XauCandleReactionState]:
    if not bars:
        return []
    last_bar = latest_bar_at_or_before(bars, current_timestamp)
    if last_bar is None:
        return []
    available_levels = [
        wall["mapped_level"] for wall in mapped_walls if wall.get("mapped_level") is not None
    ]
    selected = sorted(available_levels, key=lambda level: abs(level - last_bar.close))[:3]
    resolved_buffer = buffer_points(configured_min_buffer=2.0, atr_5m=atr_5m)
    return [
        classify_candle_state(level=level, candle=last_bar, buffer=resolved_buffer).state
        for level in selected
    ]


def _primary_candle_state(candle_states: list[XauCandleReactionState]) -> str:
    if not candle_states:
        return "unavailable"
    first = candle_states[0]
    return "unavailable" if first == XauCandleReactionState.UNAVAILABLE else first.value


def _iv_state(fusion_report: XauQuikStrikeFusionReport | None) -> str:
    if fusion_report is None:
        return "unavailable"
    if fusion_report.expected_range_snapshot is not None:
        return "available"
    context = fusion_report.context_summary
    if context and context.iv_range_status == XauFusionContextStatus.AVAILABLE:
        return "available"
    if context and context.iv_range_status == XauFusionContextStatus.PARTIAL:
        return "partial"
    return "unavailable"


def _volume_state(
    fusion_report: XauQuikStrikeFusionReport | None,
    *,
    cme_is_stale: bool,
) -> str:
    if fusion_report is None:
        return "unavailable"
    has_volume_or_oi_change = any(
        row.match_key.value_type.lower() in {"volume", "intraday_volume", "oi_change"}
        for row in fusion_report.fused_rows
    )
    if not has_volume_or_oi_change:
        return "unavailable"
    return "stale" if cme_is_stale else "available"


def _resolve_gc_reference(
    *,
    fusion_report: XauQuikStrikeFusionReport | None,
    fusion_report_path,
    explicit_price: float | None,
    explicit_timestamp: datetime | None,
) -> tuple[float | None, datetime | None]:
    if explicit_price is not None:
        return explicit_price, explicit_timestamp
    if fusion_report_path is not None:
        resolved = extract_gc_reference_from_fusion(fusion_report_path)
        if resolved.price is not None:
            return resolved.price, resolved.timestamp
    if fusion_report is None:
        return None, None
    values = [
        source_value.future_reference_price
        for row in fusion_report.fused_rows
        for source_value in (row.matrix_value, row.vol2vol_value)
        if source_value is not None and source_value.future_reference_price is not None
    ]
    return (values[0], fusion_report.created_at) if values else (None, None)


def _unavailable_cell_count(fusion_report: XauQuikStrikeFusionReport) -> int:
    count = 0
    for row in fusion_report.fused_rows:
        for source_value in (row.matrix_value, row.vol2vol_value):
            if source_value is None or source_value.value is None:
                count += 1
    return count


def _current_timestamp(
    bars: list[XauPriceBar],
    explicit_timestamp: datetime | None,
    timezone: ZoneInfo,
) -> datetime:
    if explicit_timestamp is not None:
        if explicit_timestamp.tzinfo:
            return explicit_timestamp
        return explicit_timestamp.replace(tzinfo=timezone)
    if bars:
        return bars[-1].timestamp
    return datetime.now(timezone)


def _age_minutes(current: datetime, timestamp: datetime | None) -> float | None:
    if timestamp is None:
        return None
    current_utc = current.astimezone(UTC) if current.tzinfo else current.replace(tzinfo=UTC)
    timestamp_utc = timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    return abs((current_utc - timestamp_utc).total_seconds()) / 60
