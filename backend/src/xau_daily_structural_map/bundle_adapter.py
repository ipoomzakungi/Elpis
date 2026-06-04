from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import ValidationError

from src.models.xau import (
    XauExpectedRangeSnapshot,
    XauFreshnessFactorStatus,
    XauOiWall,
    XauWallType,
)
from src.models.xau_daily_structural_map import XauDailyStructuralMapReportResult
from src.models.xau_quikstrike_fusion import XauFusionBasisState, XauFusionContextStatus
from src.xau_daily_structural_map.sample_run import generate_xau_daily_structural_map_report
from src.xau_quikstrike_fusion.basis import calculate_basis_state
from src.xau_quikstrike_fusion.expected_range import build_expected_range_snapshot

LOCAL_BUNDLE_LIMITATION = (
    "Local imported options data must be independently verified before research use."
)
NO_WALL_ROWS_LIMITATION = "No wall rows were available from bundle artifacts."
RANGE_LABEL_SOURCE_VIEW = "local_bundle_range_label"


def generate_xau_daily_structural_map_from_bundle(
    *,
    map_id: str,
    session_date: date,
    xau_vol_oi_report_path: Path,
    walls_path: Path | None = None,
    fused_rows_path: Path | None = None,
    traded_instrument: str,
    traded_reference_price: float | None,
    gc_reference_price: float | None,
    manual_basis: float | None,
    session_open_price: float | None,
    session_open_source: str | None,
    output_root: Path | None = None,
    overwrite_allowed: bool = False,
) -> XauDailyStructuralMapReportResult:
    """Generate and persist a research-only daily map from local XAU bundle files."""

    report_payload = _load_json_mapping(xau_vol_oi_report_path)
    core_report = _core_report_payload(report_payload)
    fused_context = _load_fused_context(fused_rows_path)
    expected_range_snapshot = _extract_expected_range_snapshot(
        report_payload=report_payload,
        core_report=core_report,
        fused_context=fused_context,
        report_path=xau_vol_oi_report_path,
    )
    walls, oi_change_by_id, volume_by_id, wall_limitations = _load_bundle_walls(
        walls_path=walls_path,
        report_payload=report_payload,
        core_report=core_report,
        session_date=session_date,
        expected_range_snapshot=expected_range_snapshot,
    )
    basis_state = _basis_state_from_bundle_inputs(
        manual_basis=manual_basis,
        expected_range_snapshot=expected_range_snapshot,
        traded_reference_price=traded_reference_price,
        gc_reference_price=gc_reference_price,
    )
    source_report_ids = _source_report_ids(
        core_report=core_report,
        xau_vol_oi_report_path=xau_vol_oi_report_path,
        fused_rows_path=fused_rows_path,
    )
    metadata = _context_metadata(
        core_report=core_report,
        expected_range_snapshot=expected_range_snapshot,
        walls=walls,
    )
    limitations = _dedupe(
        [
            LOCAL_BUNDLE_LIMITATION,
            *_text_list(_get(core_report, "limitations")),
            *_text_list(_get(report_payload, "limitations")),
            *wall_limitations,
        ]
    )

    return generate_xau_daily_structural_map_report(
        map_id=map_id,
        session_date=session_date,
        source_product=metadata["source_product"],
        traded_instrument=traded_instrument,
        traded_reference_price=traded_reference_price,
        expected_range_snapshot=expected_range_snapshot,
        basis_state=basis_state,
        walls=walls,
        session_open_price=session_open_price,
        session_open_source=session_open_source,
        expiration_code=metadata["expiration_code"],
        option_product_code=metadata["option_product_code"],
        futures_symbol=metadata["futures_symbol"],
        expiry_date=metadata["expiry_date"],
        source_report_ids=source_report_ids,
        source_kind="operational",
        output_dir=output_root,
        overwrite_allowed=overwrite_allowed,
        wall_oi_change_by_id=oi_change_by_id,
        wall_volume_by_id=volume_by_id,
        limitations=limitations,
    )


def _load_json_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("XAU bundle report JSON must be an object")
    return payload


def _core_report_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = payload.get("report")
    if isinstance(nested, Mapping):
        return nested
    return payload


def _load_fused_context(fused_rows_path: Path | None) -> dict[str, Any]:
    if fused_rows_path is None or not Path(fused_rows_path).exists():
        return {}
    payload = json.loads(Path(fused_rows_path).read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        return {}

    context: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        flat_row = _flatten_fused_row(row)
        for source_key, target_key in (
            ("range_label", "range_label"),
            ("vol_settle", "vol_settle"),
            ("future_reference_price", "reference_futures_price"),
            ("underlying_futures_price", "reference_futures_price"),
            ("dte", "fractional_dte"),
            ("expiration_code", "expiration_code"),
            ("expiration", "expiry_date"),
        ):
            value = _get(flat_row, source_key)
            if value is not None and target_key not in context:
                context[target_key] = value
    return context


def _flatten_fused_row(row: Mapping[str, Any]) -> dict[str, Any]:
    flattened = dict(row)
    for key in ("vol2vol_value", "matrix_value", "match_key"):
        value = row.get(key)
        if isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                flattened.setdefault(str(nested_key), nested_value)
    return flattened


def _extract_expected_range_snapshot(
    *,
    report_payload: Mapping[str, Any],
    core_report: Mapping[str, Any],
    fused_context: Mapping[str, Any],
    report_path: Path,
) -> XauExpectedRangeSnapshot | None:
    snapshot_payload = _first_mapping(
        _get(core_report, "expected_range_snapshot"),
        _get(report_payload, "expected_range_snapshot"),
    )
    if snapshot_payload is not None:
        snapshot = _snapshot_from_mapping(snapshot_payload)
        if snapshot is not None:
            return snapshot

    expected_range = _first_mapping(
        _get(core_report, "expected_range"),
        _get(report_payload, "expected_range"),
    )
    context = _merge_mappings(expected_range or {}, core_report, report_payload, fused_context)
    if expected_range is None and not _has_expected_range_context(context):
        return None
    return _build_snapshot_from_context(context, report_path=report_path)


def _snapshot_from_mapping(payload: Mapping[str, Any]) -> XauExpectedRangeSnapshot | None:
    filtered = _filter_model_fields(payload, XauExpectedRangeSnapshot)
    try:
        return XauExpectedRangeSnapshot.model_validate(filtered)
    except ValidationError:
        return _build_snapshot_from_context(filtered, report_path=Path("xau_vol_oi_report"))


def _build_snapshot_from_context(
    context: Mapping[str, Any],
    *,
    report_path: Path,
) -> XauExpectedRangeSnapshot:
    reference_futures_price = _float_from_context(
        context,
        "reference_futures_price",
        "reference_price",
        "future_reference_price",
        "underlying_futures_price",
    )
    report_level_iv = _float_from_context(context, "report_level_iv")
    vol_settle = _float_from_context(context, "vol_settle", "implied_volatility")
    fractional_dte = _float_from_context(context, "fractional_dte", "dte")
    range_label = _text_or_none(_get(context, "range_label"))
    source_report_id = _safe_source_id(
        _get(context, "source_report_id", "report_id"),
        fallback=report_path.stem,
    )
    source_view = _text_or_none(_get(context, "source_view")) or (
        RANGE_LABEL_SOURCE_VIEW if range_label else "xau_vol_oi_report"
    )
    return build_expected_range_snapshot(
        source_report_id=source_report_id,
        source_view=source_view,
        capture_timestamp=_datetime_or_default(
            _get(context, "capture_timestamp", "created_at"),
            datetime.now(UTC),
        ),
        official_release_ts=_datetime_or_none(_get(context, "official_release_ts")),
        product=_text_or_none(_get(context, "product", "source_product")) or "Gold",
        option_product_code=(
            _text_or_none(_get(context, "option_product_code")) or "OG|GC"
        ),
        futures_symbol=_text_or_none(_get(context, "futures_symbol")) or "GC",
        expiration_code=_text_or_none(_get(context, "expiration_code")),
        expiry_date=_date_or_none(_get(context, "expiry_date", "expiration")),
        reference_futures_price=reference_futures_price,
        report_level_iv=report_level_iv,
        vol_settle=vol_settle,
        fractional_dte=fractional_dte,
        cme_numeric_1sd=_float_from_context(
            context,
            "cme_numeric_1sd",
            "expected_move",
        ),
        cme_numeric_2sd=_float_from_context(context, "cme_numeric_2sd"),
        cme_numeric_3sd=_float_from_context(context, "cme_numeric_3sd"),
        upper_1sd=_float_from_context(context, "upper_1sd"),
        lower_1sd=_float_from_context(context, "lower_1sd"),
        upper_2sd=_float_from_context(context, "upper_2sd"),
        lower_2sd=_float_from_context(context, "lower_2sd"),
        upper_3sd=_float_from_context(context, "upper_3sd"),
        lower_3sd=_float_from_context(context, "lower_3sd"),
        range_label=range_label,
        limitations=[
            *_text_list(_get(context, "limitations")),
            *_text_list(_get(context, "unavailable_reason")),
        ],
    )


def _has_expected_range_context(context: Mapping[str, Any]) -> bool:
    fields = (
        "range_label",
        "reference_futures_price",
        "reference_price",
        "report_level_iv",
        "fractional_dte",
        "dte",
        "cme_numeric_1sd",
        "upper_1sd",
        "lower_1sd",
        "vol_settle",
    )
    return any(_get(context, field) is not None for field in fields)


def _basis_state_from_bundle_inputs(
    *,
    manual_basis: float | None,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    traded_reference_price: float | None,
    gc_reference_price: float | None,
) -> XauFusionBasisState:
    if manual_basis is None:
        return calculate_basis_state(
            xauusd_spot_reference=traded_reference_price,
            gc_futures_reference=gc_reference_price,
        )

    resolved_gc_reference = gc_reference_price or (
        expected_range_snapshot.reference_futures_price if expected_range_snapshot else None
    )
    resolved_traded_reference = traded_reference_price
    if resolved_gc_reference is None and resolved_traded_reference is not None:
        resolved_gc_reference = resolved_traded_reference + manual_basis
    if resolved_traded_reference is None and resolved_gc_reference is not None:
        resolved_traded_reference = resolved_gc_reference - manual_basis
    if resolved_gc_reference is None or resolved_traded_reference is None:
        return XauFusionBasisState(
            status=XauFusionContextStatus.UNAVAILABLE,
            calculation_note=(
                "Manual basis was supplied, but a futures or traded reference was missing; "
                "spot-equivalent strike levels were not computed."
            ),
            warnings=["Basis mapping unavailable."],
        )
    return XauFusionBasisState(
        status=XauFusionContextStatus.AVAILABLE,
        xauusd_spot_reference=resolved_traded_reference,
        gc_futures_reference=resolved_gc_reference,
        basis_points=manual_basis,
        calculation_note="Manual basis supplied for local bundle structural-map research.",
    )


def _load_bundle_walls(
    *,
    walls_path: Path | None,
    report_payload: Mapping[str, Any],
    core_report: Mapping[str, Any],
    session_date: date,
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
) -> tuple[list[XauOiWall], dict[str, float | None], dict[str, float | None], list[str]]:
    raw_rows = _load_wall_rows_from_path(walls_path)
    if not raw_rows:
        raw_rows = _embedded_wall_rows(report_payload, core_report)

    limitations: list[str] = []
    if not raw_rows:
        limitations.append(NO_WALL_ROWS_LIMITATION)
        return [], {}, {}, limitations

    default_expiry = (
        expected_range_snapshot.expiry_date
        if expected_range_snapshot and expected_range_snapshot.expiry_date
        else session_date
    )
    total_by_expiry = _total_open_interest_by_expiry(raw_rows, default_expiry)
    walls: list[XauOiWall] = []
    oi_change_by_id: dict[str, float | None] = {}
    volume_by_id: dict[str, float | None] = {}
    for index, row in enumerate(raw_rows):
        if not isinstance(row, Mapping):
            continue
        wall = _wall_from_row(
            row,
            index=index,
            default_expiry=default_expiry,
            total_by_expiry=total_by_expiry,
            limitations=limitations,
        )
        walls.append(wall)
        oi_change_by_id[wall.wall_id] = _optional_float(_get(row, "oi_change"))
        volume_by_id[wall.wall_id] = _optional_float(_get(row, "volume"))
    if not walls:
        limitations.append(NO_WALL_ROWS_LIMITATION)
    return walls, oi_change_by_id, volume_by_id, _dedupe(limitations)


def _load_wall_rows_from_path(walls_path: Path | None) -> list[Mapping[str, Any]]:
    if walls_path is None:
        return []
    path = Path(walls_path)
    if not path.exists():
        return []
    if path.suffix.lower() == ".parquet":
        return pl.read_parquet(path).to_dicts()
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("walls") if isinstance(payload, Mapping) else payload
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    raise ValueError("walls_path must point to a parquet or JSON wall artifact")


def _embedded_wall_rows(
    report_payload: Mapping[str, Any],
    core_report: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    for candidate in (
        _get(report_payload, "walls"),
        _get(core_report, "walls"),
        _get(report_payload, "wall_rows"),
        _get(core_report, "wall_rows"),
    ):
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, Mapping)]
    return []


def _wall_from_row(
    row: Mapping[str, Any],
    *,
    index: int,
    default_expiry: date,
    total_by_expiry: Mapping[str, float],
    limitations: list[str],
) -> XauOiWall:
    expiry = _date_or_none(_get(row, "expiry", "expiration", "expiry_date")) or default_expiry
    expiry_key = expiry.isoformat()
    open_interest = _optional_float(_get(row, "open_interest")) or 0.0
    total_oi = _optional_float(_get(row, "total_expiry_open_interest"))
    if total_oi is None or total_oi <= 0:
        total_oi = total_by_expiry.get(expiry_key) or max(open_interest, 1.0)
    oi_share = _optional_float(_get(row, "oi_share"))
    if oi_share is None:
        oi_share = min(open_interest / total_oi, 1.0) if total_oi > 0 else 0.0
    wall_id = _text_or_none(_get(row, "wall_id", "id")) or _fallback_wall_id(row, index)
    wall_limitations = _text_list(_get(row, "limitations"))
    return XauOiWall(
        wall_id=wall_id,
        expiry=expiry,
        strike=_required_positive_float(_get(row, "strike"), "wall strike"),
        option_type=_wall_type(_get(row, "option_type", "wall_type")),
        open_interest=open_interest,
        total_expiry_open_interest=total_oi,
        oi_share=oi_share,
        expiry_weight=_optional_float(_get(row, "expiry_weight")) or 1.0,
        freshness_factor=_optional_float(_get(row, "freshness_factor")) or 1.0,
        wall_score=_optional_float(_get(row, "wall_score", "score")) or 0.0,
        freshness_status=_freshness_status(_get(row, "freshness_status", "freshness_state")),
        notes=_text_list(_get(row, "notes")),
        limitations=wall_limitations,
    )


def _fallback_wall_id(row: Mapping[str, Any], index: int) -> str:
    strike = _optional_float(_get(row, "strike")) or 0.0
    wall_type = _wall_type(_get(row, "option_type", "wall_type")).value
    return f"wall_{index}_{int(strike) if strike.is_integer() else strike}_{wall_type}"


def _total_open_interest_by_expiry(
    rows: Sequence[Mapping[str, Any]],
    default_expiry: date,
) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        expiry = _date_or_none(_get(row, "expiry", "expiration", "expiry_date")) or default_expiry
        open_interest = _optional_float(_get(row, "open_interest")) or 0.0
        totals[expiry.isoformat()] = totals.get(expiry.isoformat(), 0.0) + open_interest
    return totals


def _context_metadata(
    *,
    core_report: Mapping[str, Any],
    expected_range_snapshot: XauExpectedRangeSnapshot | None,
    walls: Sequence[XauOiWall],
) -> dict[str, Any]:
    first_wall = walls[0] if walls else None
    return {
        "source_product": (
            (expected_range_snapshot.product if expected_range_snapshot else None)
            or _text_or_none(_get(core_report, "source_product", "product"))
            or "Gold"
        ),
        "option_product_code": (
            (
                expected_range_snapshot.option_product_code
                if expected_range_snapshot
                else None
            )
            or _text_or_none(_get(core_report, "option_product_code"))
            or "OG|GC"
        ),
        "futures_symbol": (
            (expected_range_snapshot.futures_symbol if expected_range_snapshot else None)
            or _text_or_none(_get(core_report, "futures_symbol"))
            or "GC"
        ),
        "expiration_code": (
            (expected_range_snapshot.expiration_code if expected_range_snapshot else None)
            or _text_or_none(_get(core_report, "expiration_code"))
            or _text_or_none(_get(core_report, "expiry_code"))
        ),
        "expiry_date": (
            (expected_range_snapshot.expiry_date if expected_range_snapshot else None)
            or (first_wall.expiry if first_wall else None)
            or _date_or_none(_get(core_report, "expiry_date", "expiration"))
        ),
    }


def _source_report_ids(
    *,
    core_report: Mapping[str, Any],
    xau_vol_oi_report_path: Path,
    fused_rows_path: Path | None,
) -> list[str]:
    ids = [
        _safe_source_id(_get(core_report, "report_id"), fallback=xau_vol_oi_report_path.stem),
        _safe_source_id(xau_vol_oi_report_path.stem),
    ]
    if fused_rows_path is not None:
        ids.append(_safe_source_id(Path(fused_rows_path).stem))
    return _dedupe([source_id for source_id in ids if source_id])


def _merge_mappings(*mappings: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            if value is not None and key not in merged:
                merged[str(key)] = value
    return merged


def _first_mapping(*values: Any) -> Mapping[str, Any] | None:
    for value in values:
        if isinstance(value, Mapping):
            return value
    return None


def _filter_model_fields(payload: Mapping[str, Any], model: Any) -> dict[str, Any]:
    fields = set(model.model_fields)
    return {str(key): value for key, value in payload.items() if str(key) in fields}


def _float_from_context(context: Mapping[str, Any], *keys: str) -> float | None:
    return _optional_float(_get(context, *keys))


def _get(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    lower_lookup = {str(key).lower(): value for key, value in mapping.items()}
    for key in keys:
        lowered = key.lower()
        if lowered in lower_lookup:
            return lower_lookup[lowered]
    return None


def _required_positive_float(value: Any, field_name: str) -> float:
    resolved = _optional_float(value)
    if resolved is None or resolved <= 0:
        raise ValueError(f"{field_name} must be positive")
    return resolved


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _date_or_none(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return date.fromisoformat(cleaned[:10])
        except ValueError:
            try:
                return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).date()
            except ValueError:
                return None
    return None


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _datetime_or_default(value: Any, default: datetime) -> datetime:
    return _datetime_or_none(value) or default


def _wall_type(value: Any) -> XauWallType:
    normalized = _text_or_none(value)
    if normalized is None:
        return XauWallType.UNKNOWN
    lowered = normalized.lower()
    if lowered in {"c", "call", "calls", "call_wall"}:
        return XauWallType.CALL
    if lowered in {"p", "put", "puts", "put_wall"}:
        return XauWallType.PUT
    if lowered in {"mixed", "both"}:
        return XauWallType.MIXED
    return XauWallType.UNKNOWN


def _freshness_status(value: Any) -> XauFreshnessFactorStatus:
    normalized = _text_or_none(value)
    if normalized is None:
        return XauFreshnessFactorStatus.UNAVAILABLE
    lowered = normalized.lower()
    if lowered in {"confirmed", "fresh"}:
        return XauFreshnessFactorStatus.CONFIRMED
    if lowered == "stale":
        return XauFreshnessFactorStatus.STALE
    if lowered in {"neutral", "unknown"}:
        return XauFreshnessFactorStatus.NEUTRAL
    return XauFreshnessFactorStatus.UNAVAILABLE


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = _text_or_none(value)
        return [item] if item else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [item for item in (_text_or_none(entry) for entry in value) if item]
    return []


def _safe_source_id(value: Any, fallback: str | None = None) -> str:
    raw = _text_or_none(value) or fallback or "unknown_source"
    safe = "".join(
        character if character.isalnum() or character in "_-" else "_" for character in raw
    )
    return safe.strip("_") or "unknown_source"


def _dedupe(values: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _text_or_none(value)
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


__all__ = ["generate_xau_daily_structural_map_from_bundle"]
