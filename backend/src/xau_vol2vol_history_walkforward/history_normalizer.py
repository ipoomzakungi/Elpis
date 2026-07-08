from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.models.xau_vol2vol_history_walkforward import (
    XauVol2VolRangeDeskSnapshot,
    XauVol2VolStrikeSnapshot,
)

_OBSERVED_KEYS = ("observedAt", "observed_at", "timestamp", "time", "createdAt")
_SESSION_DATE_KEYS = ("sessionDate", "session_date", "date")
_SERIES_KEYS = ("series", "contract", "expirationCode")
_STRIKE_KEYS = ("strike", "Strike")
_CALL_KEYS = ("call", "Call", "callVolume", "callOi")
_PUT_KEYS = ("put", "Put", "putVolume", "putOi")
_TOTAL_KEYS = ("total", "Total")
_VOL_KEYS = ("volSettle", "vol_settle", "vol")
_CALL_CHANGE_KEYS = ("callChange", "call_change")
_PUT_CHANGE_KEYS = ("putChange", "put_change")
_TOTAL_CHANGE_KEYS = ("totalChange", "total_change")


def load_json_payload(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_payload(payload: Any, *, default_session_date: date | None = None) -> tuple[
    list[XauVol2VolStrikeSnapshot],
    list[XauVol2VolRangeDeskSnapshot],
    list[str],
]:
    warnings: list[str] = []
    snapshots = _find_snapshot_mappings(payload)
    if not snapshots:
        warnings.append("No Vol2Vol snapshot array was found in the payload.")
    strike_rows: list[XauVol2VolStrikeSnapshot] = []
    range_rows: list[XauVol2VolRangeDeskSnapshot] = []
    warned_session_date_fallback = False
    for snapshot in snapshots:
        observed_at = _parse_datetime(_first(snapshot, _OBSERVED_KEYS))
        if observed_at is None:
            warnings.append("Snapshot missing observed timestamp; skipped.")
            continue
        session_date = _parse_date(_first(snapshot, _SESSION_DATE_KEYS)) or default_session_date
        if session_date is None:
            session_date = observed_at.date()
            if not warned_session_date_fallback:
                warnings.append("Snapshot missing sessionDate; observedAt date was used.")
                warned_session_date_fallback = True
        snapshot_kind = _detect_kind(snapshot)
        range_rows.append(_range_snapshot(snapshot, observed_at, session_date, snapshot_kind))
        rows = _first(snapshot, ("rows", "data", "strikes"))
        if not isinstance(rows, list):
            warnings.append(f"Snapshot {snapshot.get('id', '<unknown>')} has no strike rows.")
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            strike = _to_float(_first(row, _STRIKE_KEYS))
            if strike is None:
                warnings.append("Strike row missing strike; skipped.")
                continue
            strike_rows.append(
                XauVol2VolStrikeSnapshot(
                    session_date=session_date,
                    observed_at=observed_at,
                    series=_optional_text(_first(snapshot, _SERIES_KEYS)),
                    snapshot_kind=snapshot_kind,
                    strike=strike,
                    call=_to_float(_first(row, _CALL_KEYS)),
                    put=_to_float(_first(row, _PUT_KEYS)),
                    total=_to_float(_first(row, _TOTAL_KEYS)),
                    vol_settle=_to_float(_first(row, _VOL_KEYS)),
                    call_change=_to_float(_first(row, _CALL_CHANGE_KEYS)),
                    put_change=_to_float(_first(row, _PUT_CHANGE_KEYS)),
                    total_change=_to_float(_first(row, _TOTAL_CHANGE_KEYS)),
                    source=_source_label(snapshot),
                    warnings=[],
                )
            )
    return strike_rows, range_rows, warnings


def write_normalized_artifacts(
    *,
    output_dir: Path,
    strike_rows: list[XauVol2VolStrikeSnapshot],
    range_rows: list[XauVol2VolRangeDeskSnapshot],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "normalized_history.json").write_text(
        json.dumps(
            {
                "strike_snapshots": [row.model_dump(mode="json") for row in strike_rows],
                "range_snapshots": [row.model_dump(mode="json") for row in range_rows],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with (output_dir / "normalized_history.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "session_date",
                "observed_at",
                "series",
                "snapshot_kind",
                "strike",
                "call",
                "put",
                "total",
                "vol_settle",
                "call_change",
                "put_change",
                "total_change",
                "source",
            ],
        )
        writer.writeheader()
        for row in strike_rows:
            payload = row.model_dump(mode="json")
            payload["warnings"] = "; ".join(row.warnings)
            writer.writerow({key: payload.get(key) for key in writer.fieldnames})


def latest_range_by_session(
    range_rows: Iterable[XauVol2VolRangeDeskSnapshot],
) -> dict[date, XauVol2VolRangeDeskSnapshot]:
    latest: dict[date, XauVol2VolRangeDeskSnapshot] = {}
    for row in sorted(range_rows, key=lambda item: item.observed_at):
        latest[row.session_date] = row
    return latest


def latest_strikes_by_session(
    strike_rows: Iterable[XauVol2VolStrikeSnapshot],
) -> dict[date, list[XauVol2VolStrikeSnapshot]]:
    latest_observed: dict[tuple[date, str], datetime] = {}
    for row in strike_rows:
        key = (row.session_date, row.snapshot_kind)
        if key not in latest_observed or row.observed_at > latest_observed[key]:
            latest_observed[key] = row.observed_at
    selected: dict[date, list[XauVol2VolStrikeSnapshot]] = {}
    for row in strike_rows:
        if latest_observed.get((row.session_date, row.snapshot_kind)) == row.observed_at:
            selected.setdefault(row.session_date, []).append(row)
    return selected


def _find_snapshot_mappings(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("snapshots", "history", "data"):
            value = payload.get(key)
            if isinstance(value, list) and any(isinstance(item, Mapping) for item in value):
                return [dict(item) for item in value if isinstance(item, Mapping)]
        if _looks_like_snapshot(payload):
            return [dict(payload)]
        for value in payload.values():
            nested = _find_snapshot_mappings(value)
            if nested:
                return nested
    if isinstance(payload, list):
        if any(isinstance(item, Mapping) and _looks_like_snapshot(item) for item in payload):
            return [dict(item) for item in payload if isinstance(item, Mapping)]
        for item in payload:
            nested = _find_snapshot_mappings(item)
            if nested:
                return nested
    return []


def _range_snapshot(
    snapshot: Mapping[str, Any],
    observed_at: datetime,
    session_date: date,
    snapshot_kind: str,
) -> XauVol2VolRangeDeskSnapshot:
    current_price = _to_float(_first(snapshot, ("future_open", "currentPrice", "futurePrice")))
    dte = _to_float(_first(snapshot, ("dte", "daysToExpiry")))
    ranges = _first(snapshot, ("ranges",))
    future_buy: dict[int, float] = {}
    future_sell: dict[int, float] = {}
    if isinstance(ranges, list) and current_price is not None:
        for item in ranges:
            if not isinstance(item, Mapping):
                continue
            sd = int(_to_float(_first(item, ("sd",))) or 0)
            if sd <= 0:
                continue
            down = _to_float(_first(item, ("down", "fix")))
            up = _to_float(_first(item, ("up", "fix")))
            if down is not None:
                future_buy[sd] = current_price - down
            if up is not None:
                future_sell[sd] = current_price + up
    return XauVol2VolRangeDeskSnapshot(
        session_date=session_date,
        observed_at=observed_at,
        series=_optional_text(_first(snapshot, _SERIES_KEYS)),
        dte=dte,
        future_open=current_price,
        cfd_open=_to_float(_first(snapshot, ("cfd_open", "cfdPrice", "cfd"))),
        diff=_to_float(_first(snapshot, ("diff", "diff_points", "basis"))),
        vol_now=_to_float(_first(snapshot, ("vol_now", "atmVol", "volNow"))),
        vol_chg=_to_float(_first(snapshot, ("vol_chg", "volChange"))),
        future_chg=_to_float(_first(snapshot, ("future_chg", "futureChange"))),
        expected_move=_to_float(_first(snapshot, ("expected_move", "expectedMove"))),
        sd_step_1=_sd_step(current_price, future_buy.get(1), future_sell.get(1)),
        sd_step_2=_sd_step(current_price, future_buy.get(2), future_sell.get(2)),
        sd_step_3=_sd_step(current_price, future_buy.get(3), future_sell.get(3)),
        cfd_buy_1sd=_to_float(_first(snapshot, ("cfd_buy_1sd", "cfdLower1Sd"))),
        cfd_buy_2sd=_to_float(_first(snapshot, ("cfd_buy_2sd", "cfdLower2Sd"))),
        cfd_buy_3sd=_to_float(_first(snapshot, ("cfd_buy_3sd", "cfdLower3Sd"))),
        cfd_sell_1sd=_to_float(_first(snapshot, ("cfd_sell_1sd", "cfdUpper1Sd"))),
        cfd_sell_2sd=_to_float(_first(snapshot, ("cfd_sell_2sd", "cfdUpper2Sd"))),
        cfd_sell_3sd=_to_float(_first(snapshot, ("cfd_sell_3sd", "cfdUpper3Sd"))),
        future_buy_1sd=future_buy.get(1) or _to_float(_first(snapshot, ("future_buy_1sd",))),
        future_buy_2sd=future_buy.get(2) or _to_float(_first(snapshot, ("future_buy_2sd",))),
        future_buy_3sd=future_buy.get(3) or _to_float(_first(snapshot, ("future_buy_3sd",))),
        future_sell_1sd=future_sell.get(1) or _to_float(_first(snapshot, ("future_sell_1sd",))),
        future_sell_2sd=future_sell.get(2) or _to_float(_first(snapshot, ("future_sell_2sd",))),
        future_sell_3sd=future_sell.get(3) or _to_float(_first(snapshot, ("future_sell_3sd",))),
        warnings=[f"normalized from snapshot kind {snapshot_kind}"],
    )


def _detect_kind(snapshot: Mapping[str, Any]) -> str:
    text = " ".join(
        str(_first(snapshot, ("kind", "title", "snapshot_kind")) or "").lower().split()
    )
    if "monthly" in text:
        return "monthly_open_interest"
    if "open" in text and "interest" in text:
        return "open_interest"
    if "intraday" in text or "volume" in text:
        return "intraday_volume"
    return text or "unknown"


def _looks_like_snapshot(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in _OBSERVED_KEYS) and (
        "rows" in value or "currentPrice" in value or "kind" in value
    )


def _first(row: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    lower = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        value = lower.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return " ".join(str(value).split()) or None


def _source_label(snapshot: Mapping[str, Any]) -> str:
    source = snapshot.get("source")
    if isinstance(source, Mapping):
        return str(source.get("label") or "Vol2Vol")
    return str(source or "Vol2Vol")


def _sd_step(current_price: float | None, lower: float | None, upper: float | None) -> float | None:
    candidates: list[float] = []
    if current_price is not None and lower is not None:
        candidates.append(abs(current_price - lower))
    if current_price is not None and upper is not None:
        candidates.append(abs(upper - current_price))
    if not candidates:
        return None
    return sum(candidates) / len(candidates)
