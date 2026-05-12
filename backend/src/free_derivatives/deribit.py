"""Deribit public options fixture/request planning and normalization."""

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.free_derivatives.processing import (
    DERIBIT_CRYPTO_OPTIONS_LIMITATION,
    DERIBIT_MISSING_IV_OI_LIMITATION,
)
from src.models.free_derivatives import (
    DeribitOptionInstrument,
    DeribitOptionsRequest,
    DeribitOptionSummarySnapshot,
    DeribitOptionType,
    FreeDerivativesBaseModel,
)

DERIBIT_INSTRUMENT_PATTERN = re.compile(
    r"^(?P<underlying>[A-Z0-9_-]+)-(?P<day>\d{1,2})(?P<month>[A-Z]{3})(?P<year>\d{2})-"
    r"(?P<strike>\d+(?:\.\d+)?)-(?P<option_type>[CP])$"
)
MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


class DeribitRequestPlanItem(FreeDerivativesBaseModel):
    underlying: str
    include_expired: bool
    snapshot_timestamp: datetime | None = None
    fixture_instruments_path: Path | None = None
    fixture_summary_path: Path | None = None
    requested_item: str


def create_deribit_request_plan(
    request: DeribitOptionsRequest,
) -> list[DeribitRequestPlanItem]:
    """Build deterministic Deribit public options plan items without live calls."""

    scope = "include_expired" if request.include_expired else "active"
    return [
        DeribitRequestPlanItem(
            underlying=underlying,
            include_expired=request.include_expired,
            snapshot_timestamp=request.snapshot_timestamp,
            fixture_instruments_path=request.fixture_instruments_path,
            fixture_summary_path=request.fixture_summary_path,
            requested_item=f"{underlying}:options:{scope}",
        )
        for underlying in request.underlyings
    ]


def load_deribit_fixture_rows(path: Path) -> list[dict[str, Any]]:
    """Load Deribit public fixture rows from direct or public result wrappers."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = _unwrap_result_rows(payload)
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Deribit fixture rows must be JSON objects")
        normalized_rows.append(row)
    return normalized_rows


def parse_deribit_instrument_name(instrument_name: str) -> DeribitOptionInstrument:
    """Parse a Deribit option instrument name into normalized contract terms."""

    normalized = instrument_name.strip().upper()
    match = DERIBIT_INSTRUMENT_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError("safe Deribit option instrument name is required")
    month = MONTHS.get(match.group("month"))
    if month is None:
        raise ValueError(f"Unsupported Deribit instrument month: {match.group('month')}")
    option_type = (
        DeribitOptionType.CALL
        if match.group("option_type") == "C"
        else DeribitOptionType.PUT
    )
    return DeribitOptionInstrument(
        instrument_name=normalized,
        underlying=match.group("underlying"),
        expiry=date(2000 + int(match.group("year")), month, int(match.group("day"))),
        strike=float(match.group("strike")),
        option_type=option_type,
        is_active=True,
        raw_payload={"instrument_name": normalized},
        limitations=[DERIBIT_CRYPTO_OPTIONS_LIMITATION],
    )


def normalize_deribit_instruments(
    rows: list[dict[str, Any]],
    *,
    requested_underlyings: list[str],
    include_expired: bool,
) -> list[DeribitOptionInstrument]:
    """Normalize public Deribit instruments and skip unsupported underlyings visibly."""

    requested = {underlying.strip().upper() for underlying in requested_underlyings}
    instruments: list[DeribitOptionInstrument] = []
    for row in rows:
        instrument_name = _string_value(row.get("instrument_name"))
        parsed = parse_deribit_instrument_name(instrument_name)
        if parsed.underlying not in requested:
            continue
        is_active = _is_active_instrument(row)
        if not include_expired and not is_active:
            continue
        instruments.append(
            parsed.model_copy(
                update={
                    "is_active": is_active,
                    "raw_payload": row,
                    "limitations": [DERIBIT_CRYPTO_OPTIONS_LIMITATION],
                }
            )
        )
    return sorted(instruments, key=lambda item: item.instrument_name)


def normalize_deribit_summary_snapshots(
    rows: list[dict[str, Any]],
    *,
    requested_underlyings: list[str],
    snapshot_timestamp: datetime | None = None,
) -> list[DeribitOptionSummarySnapshot]:
    """Normalize public Deribit book-summary/ticker rows into option snapshots."""

    timestamp = snapshot_timestamp or datetime.now(UTC)
    requested = {underlying.strip().upper() for underlying in requested_underlyings}
    snapshots: list[DeribitOptionSummarySnapshot] = []
    for row in rows:
        parsed = parse_deribit_instrument_name(_string_value(row.get("instrument_name")))
        if parsed.underlying not in requested:
            continue
        greeks = row.get("greeks") if isinstance(row.get("greeks"), dict) else {}
        open_interest = _optional_float(row.get("open_interest"))
        mark_iv = _optional_float(row.get("mark_iv"))
        bid_iv = _optional_float(row.get("bid_iv"))
        ask_iv = _optional_float(row.get("ask_iv"))
        limitations = [DERIBIT_CRYPTO_OPTIONS_LIMITATION]
        if any(value is None for value in (open_interest, mark_iv, bid_iv, ask_iv)):
            limitations.append(DERIBIT_MISSING_IV_OI_LIMITATION)
        snapshots.append(
            DeribitOptionSummarySnapshot(
                snapshot_timestamp=timestamp,
                instrument_name=parsed.instrument_name,
                underlying=parsed.underlying,
                expiry=parsed.expiry,
                strike=parsed.strike,
                option_type=parsed.option_type,
                open_interest=open_interest,
                mark_iv=mark_iv,
                bid_iv=bid_iv,
                ask_iv=ask_iv,
                underlying_price=_optional_float(row.get("underlying_price")),
                volume=_optional_float(row.get("volume")),
                delta=_optional_float(greeks.get("delta")),
                gamma=_optional_float(greeks.get("gamma")),
                vega=_optional_float(greeks.get("vega")),
                theta=_optional_float(greeks.get("theta")),
                raw_payload=row,
                limitations=limitations,
            )
        )
    return sorted(snapshots, key=lambda item: item.instrument_name)


def load_deribit_instruments(request: DeribitOptionsRequest) -> list[DeribitOptionInstrument]:
    """Load normalized Deribit instruments from local public fixtures."""

    if request.fixture_instruments_path is None:
        return []
    rows = load_deribit_fixture_rows(request.fixture_instruments_path)
    return normalize_deribit_instruments(
        rows,
        requested_underlyings=request.underlyings,
        include_expired=request.include_expired,
    )


def load_deribit_summary_snapshots(
    request: DeribitOptionsRequest,
) -> list[DeribitOptionSummarySnapshot]:
    """Load normalized Deribit option summaries from local public fixtures."""

    if request.fixture_summary_path is None:
        return []
    rows = load_deribit_fixture_rows(request.fixture_summary_path)
    return normalize_deribit_summary_snapshots(
        rows,
        requested_underlyings=request.underlyings,
        snapshot_timestamp=request.snapshot_timestamp,
    )


def _unwrap_result_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        result = payload.get("result", payload)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("instruments", "book_summary", "summary", "data"):
                value = result.get(key)
                if isinstance(value, list):
                    return value
    raise ValueError("Deribit fixture must contain a public result row list")


def _is_active_instrument(row: dict[str, Any]) -> bool:
    if "is_active" in row:
        return bool(row["is_active"])
    if "expired" in row:
        return not bool(row["expired"])
    if "is_expired" in row:
        return not bool(row["is_expired"])
    return True


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if normalized in {"", ".", "NA", "N/A", "null"}:
            return None
        return float(normalized)
    return float(value)


def _string_value(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Deribit public row must include instrument_name")
    return value
