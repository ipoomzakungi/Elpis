from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.xau_walk_forward_research import (
    XauWalkForwardSdSnapshot,
    XauWalkForwardSdSource,
)
from src.quikstrike.report_store import QuikStrikeReportStore

RANGE_LABEL_NOT_NUMERIC_LIMITATION = (
    "Vol2Vol range_label/sigma_label is classification context only and is not numeric SD."
)


def resolve_sd_snapshot(
    *,
    timestamp: datetime,
    cme_source: str,
    reports_dir: Path | None = None,
    expiration_code: str | None = None,
    future_reference_price: float | None = None,
) -> XauWalkForwardSdSnapshot:
    if cme_source == "fixture":
        reference = future_reference_price or 4500.0
        return fixture_sd_snapshot(timestamp=timestamp, reference_price=reference)
    if cme_source != "latest_existing":
        return unavailable_sd_snapshot(
            timestamp=timestamp,
            reason=f"cme_source={cme_source} is not implemented in Feature 025.",
        )

    store = QuikStrikeReportStore(reports_dir=reports_dir)
    for summary in store.list_reports().extractions:
        path = store.report_dir(summary.extraction_id) / "range_bands.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = sd_snapshot_from_range_bands_payload(
            payload,
            timestamp=timestamp,
            expiration_code=expiration_code,
        )
        if snapshot.sd_source != XauWalkForwardSdSource.UNAVAILABLE:
            return snapshot
    return unavailable_sd_snapshot(
        timestamp=timestamp,
        reason="No latest Vol2Vol range_bands.json with native numeric SD was found.",
    )


def fixture_sd_snapshot(
    *,
    timestamp: datetime,
    reference_price: float = 4500.0,
    one_sd: float = 25.0,
) -> XauWalkForwardSdSnapshot:
    return _snapshot_from_moves(
        timestamp=timestamp,
        reference_price=reference_price,
        one_sd=one_sd,
        two_sd=one_sd * 2,
        three_sd=one_sd * 3,
        dte=0.68,
        expiration_code="FIXTURE",
        source_report_id="fixture_range_bands",
        source_view="fixture",
        sd_source=XauWalkForwardSdSource.FIXTURE,
        limitations=["Fixture SD values are for tests and local smoke validation only."],
    )


def unavailable_sd_snapshot(*, timestamp: datetime, reason: str) -> XauWalkForwardSdSnapshot:
    return XauWalkForwardSdSnapshot(
        timestamp=timestamp,
        sd_source=XauWalkForwardSdSource.UNAVAILABLE,
        limitations=[reason, RANGE_LABEL_NOT_NUMERIC_LIMITATION],
    )


def sd_snapshot_from_range_bands_payload(
    payload: dict[str, Any],
    *,
    timestamp: datetime,
    expiration_code: str | None = None,
    preferred_view: str | None = None,
) -> XauWalkForwardSdSnapshot:
    views = payload.get("views", [])
    matching_views = [
        view
        for view in views
        if (expiration_code is None or view.get("expiration_code") == expiration_code)
        and (preferred_view is None or view.get("view_type") == preferred_view)
    ]
    for view in matching_views or views:
        bands = view.get("cumulative_bands") or []
        by_sigma = {
            float(band["sigma"]): band
            for band in bands
            if isinstance(band, dict)
            and band.get("sigma") is not None
            and band.get("cme_numeric_sd") is not None
        }
        if {1.0, 2.0, 3.0}.issubset(by_sigma):
            reference = _number(view.get("future_reference_price"))
            if reference is None:
                return unavailable_sd_snapshot(
                    timestamp=timestamp,
                    reason="range_bands.json has SD bands but no future reference price.",
                )
            return _snapshot_from_bands(
                timestamp=timestamp,
                reference_price=reference,
                one=by_sigma[1.0],
                two=by_sigma[2.0],
                three=by_sigma[3.0],
                dte=_number(view.get("dte")),
                expiration_code=view.get("expiration_code"),
                source_report_id=payload.get("extraction_id"),
                source_view=view.get("view_type"),
            )
    return unavailable_sd_snapshot(
        timestamp=timestamp,
        reason="range_bands.json did not expose numeric 1SD/2SD/3SD cumulative bands.",
    )


def _snapshot_from_bands(
    *,
    timestamp: datetime,
    reference_price: float,
    one: dict[str, Any],
    two: dict[str, Any],
    three: dict[str, Any],
    dte: float | None,
    expiration_code: str | None,
    source_report_id: str | None,
    source_view: str | None,
) -> XauWalkForwardSdSnapshot:
    one_sd = float(one["cme_numeric_sd"])
    two_sd = float(two["cme_numeric_sd"])
    three_sd = float(three["cme_numeric_sd"])
    lower_2_5 = _interpolate(float(two["lower_strike"]), float(three["lower_strike"]))
    upper_2_5 = _interpolate(float(two["upper_strike"]), float(three["upper_strike"]))
    lower_3_5 = reference_price - (three_sd + (three_sd - two_sd) / 2)
    upper_3_5 = reference_price + (three_sd + (three_sd - two_sd) / 2)
    return XauWalkForwardSdSnapshot(
        timestamp=timestamp,
        expiration_code=expiration_code,
        dte=dte,
        future_reference_price=reference_price,
        native_1sd=one_sd,
        native_2sd=two_sd,
        native_3sd=three_sd,
        native_3_5sd=three_sd + (three_sd - two_sd) / 2,
        lower_1sd=float(one["lower_strike"]),
        upper_1sd=float(one["upper_strike"]),
        lower_2sd=float(two["lower_strike"]),
        upper_2sd=float(two["upper_strike"]),
        lower_2_5sd=lower_2_5,
        upper_2_5sd=upper_2_5,
        lower_3sd=float(three["lower_strike"]),
        upper_3sd=float(three["upper_strike"]),
        lower_3_5sd=lower_3_5,
        upper_3_5sd=upper_3_5,
        sd_source=XauWalkForwardSdSource.CME_NATIVE,
        source_report_id=source_report_id,
        source_view=source_view,
        limitations=["Native SD captured from sanitized QuikStrike range_bands.json."],
    )


def _snapshot_from_moves(
    *,
    timestamp: datetime,
    reference_price: float,
    one_sd: float,
    two_sd: float,
    three_sd: float,
    dte: float | None,
    expiration_code: str | None,
    source_report_id: str | None,
    source_view: str | None,
    sd_source: XauWalkForwardSdSource,
    limitations: list[str],
) -> XauWalkForwardSdSnapshot:
    return XauWalkForwardSdSnapshot(
        timestamp=timestamp,
        expiration_code=expiration_code,
        dte=dte,
        future_reference_price=reference_price,
        native_1sd=one_sd,
        native_2sd=two_sd,
        native_3sd=three_sd,
        native_3_5sd=three_sd + (three_sd - two_sd) / 2,
        lower_1sd=reference_price - one_sd,
        upper_1sd=reference_price + one_sd,
        lower_2sd=reference_price - two_sd,
        upper_2sd=reference_price + two_sd,
        lower_2_5sd=reference_price - (two_sd + (three_sd - two_sd) / 2),
        upper_2_5sd=reference_price + (two_sd + (three_sd - two_sd) / 2),
        lower_3sd=reference_price - three_sd,
        upper_3sd=reference_price + three_sd,
        lower_3_5sd=reference_price - (three_sd + (three_sd - two_sd) / 2),
        upper_3_5sd=reference_price + (three_sd + (three_sd - two_sd) / 2),
        sd_source=sd_source,
        source_report_id=source_report_id,
        source_view=source_view,
        limitations=limitations,
    )


def _interpolate(first: float, second: float) -> float:
    return first + (second - first) / 2


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "RANGE_LABEL_NOT_NUMERIC_LIMITATION",
    "fixture_sd_snapshot",
    "resolve_sd_snapshot",
    "sd_snapshot_from_range_bands_payload",
    "unavailable_sd_snapshot",
]
