"""Expected-range context parity helpers for XAU QuikStrike research."""

from __future__ import annotations

from math import sqrt
from typing import Any

from src.models.xau import (
    XauExpectedRange,
    XauExpectedRangeExtractionQuality,
    XauExpectedRangeSnapshot,
    XauExpectedRangeSource,
    XauExpectedRangeSourceStatus,
    XauVolatilitySource,
)

CME_NATIVE_RANGE_SOURCE = XauExpectedRangeSource.CME_NATIVE
DERIVED_RANGE_SOURCE = XauExpectedRangeSource.DERIVED_FROM_IV
UNAVAILABLE_RANGE_SOURCE = XauExpectedRangeSource.UNAVAILABLE
DERIVED_RANGE_LIMITATION = (
    "CME-native numeric SD bands were unavailable; expected range was derived "
    "from report-level IV, futures reference price, and fractional DTE."
)
RANGE_LABEL_LIMITATION = (
    "Vol2Vol range_label is classification context only and is not a numeric SD band."
)
PER_STRIKE_IV_LIMITATION = (
    "Per-strike vol_settle is not treated as report-level IV for SD-band parity."
)


def build_expected_range_snapshot(
    *,
    source_report_id: str,
    source_view: str,
    capture_timestamp: Any,
    product: str,
    option_product_code: str,
    official_release_ts: Any | None = None,
    source_status: XauExpectedRangeSourceStatus = XauExpectedRangeSourceStatus.UNKNOWN,
    futures_symbol: str | None = None,
    expiration_code: str | None = None,
    expiry_date: Any | None = None,
    reference_futures_price: float | None = None,
    report_level_iv: float | None = None,
    vol_settle: float | None = None,
    fractional_dte: float | None = None,
    cme_numeric_1sd: float | None = None,
    cme_numeric_2sd: float | None = None,
    cme_numeric_3sd: float | None = None,
    upper_1sd: float | None = None,
    lower_1sd: float | None = None,
    upper_2sd: float | None = None,
    lower_2sd: float | None = None,
    upper_3sd: float | None = None,
    lower_3sd: float | None = None,
    range_label: str | None = None,
    limitations: list[str] | None = None,
) -> XauExpectedRangeSnapshot:
    """Build a CME-native, IV-derived, or unavailable expected-range snapshot."""

    base = {
        "source_report_id": source_report_id,
        "source_view": source_view,
        "capture_timestamp": capture_timestamp,
        "official_release_ts": official_release_ts,
        "source_status": source_status,
        "product": product,
        "option_product_code": option_product_code,
        "futures_symbol": futures_symbol,
        "expiration_code": expiration_code,
        "expiry_date": expiry_date,
        "reference_futures_price": reference_futures_price,
        "report_level_iv": report_level_iv,
        "vol_settle": vol_settle,
        "fractional_dte": fractional_dte,
    }
    native_values = {
        "cme_numeric_1sd": cme_numeric_1sd,
        "cme_numeric_2sd": cme_numeric_2sd,
        "cme_numeric_3sd": cme_numeric_3sd,
        "upper_1sd": upper_1sd,
        "lower_1sd": lower_1sd,
        "upper_2sd": upper_2sd,
        "lower_2sd": lower_2sd,
        "upper_3sd": upper_3sd,
        "lower_3sd": lower_3sd,
    }
    if _native_bands_complete(native_values):
        return XauExpectedRangeSnapshot(
            **base,
            **native_values,
            range_source=CME_NATIVE_RANGE_SOURCE,
            extraction_quality=XauExpectedRangeExtractionQuality.COMPLETE,
            limitations=list(limitations or []),
        )

    derived = _derive_bands(
        reference_futures_price=reference_futures_price,
        report_level_iv=report_level_iv,
        fractional_dte=fractional_dte,
    )
    if derived is not None:
        return XauExpectedRangeSnapshot(
            **base,
            **derived,
            range_source=DERIVED_RANGE_SOURCE,
            extraction_quality=XauExpectedRangeExtractionQuality.COMPLETE,
            limitations=[*(limitations or []), DERIVED_RANGE_LIMITATION],
        )

    unavailable_limitations = list(limitations or [])
    if range_label:
        unavailable_limitations.append(RANGE_LABEL_LIMITATION)
    if vol_settle is not None and report_level_iv is None:
        unavailable_limitations.append(PER_STRIKE_IV_LIMITATION)
    if not unavailable_limitations:
        unavailable_limitations.append(
            "Expected range is unavailable because CME-native bands or report-level "
            "IV inputs are missing."
        )
    return XauExpectedRangeSnapshot(
        **base,
        range_source=UNAVAILABLE_RANGE_SOURCE,
        extraction_quality=XauExpectedRangeExtractionQuality.UNAVAILABLE,
        limitations=unavailable_limitations,
    )


def expected_range_from_snapshot(snapshot: XauExpectedRangeSnapshot) -> XauExpectedRange:
    """Convert an expected-range snapshot into the existing XAU report range shape."""

    if snapshot.range_source == XauExpectedRangeSource.UNAVAILABLE:
        return XauExpectedRange(
            source=XauVolatilitySource.UNAVAILABLE,
            range_source=snapshot.range_source,
            extraction_quality=snapshot.extraction_quality,
            reference_price=snapshot.reference_futures_price,
            report_level_iv=snapshot.report_level_iv,
            fractional_dte=snapshot.fractional_dte,
            unavailable_reason=" ".join(snapshot.limitations),
            notes=list(snapshot.limitations),
        )
    source = (
        XauVolatilitySource.CME_NATIVE
        if snapshot.range_source == XauExpectedRangeSource.CME_NATIVE
        else XauVolatilitySource.DERIVED_FROM_IV
    )
    return XauExpectedRange(
        source=source,
        range_source=snapshot.range_source,
        extraction_quality=snapshot.extraction_quality,
        reference_price=snapshot.reference_futures_price,
        report_level_iv=snapshot.report_level_iv,
        fractional_dte=snapshot.fractional_dte,
        expected_move=snapshot.cme_numeric_1sd,
        cme_numeric_1sd=snapshot.cme_numeric_1sd,
        cme_numeric_2sd=snapshot.cme_numeric_2sd,
        cme_numeric_3sd=snapshot.cme_numeric_3sd,
        lower_1sd=snapshot.lower_1sd,
        upper_1sd=snapshot.upper_1sd,
        lower_2sd=snapshot.lower_2sd,
        upper_2sd=snapshot.upper_2sd,
        lower_3sd=snapshot.lower_3sd,
        upper_3sd=snapshot.upper_3sd,
        days_to_expiry=(
            int(snapshot.fractional_dte) if snapshot.fractional_dte is not None else None
        ),
        notes=list(snapshot.limitations),
    )


def _native_bands_complete(values: dict[str, float | None]) -> bool:
    return all(value is not None for value in values.values())


def _derive_bands(
    *,
    reference_futures_price: float | None,
    report_level_iv: float | None,
    fractional_dte: float | None,
) -> dict[str, float] | None:
    if (
        reference_futures_price is None
        or report_level_iv is None
        or fractional_dte is None
        or fractional_dte < 0
    ):
        return None
    sd1 = reference_futures_price * report_level_iv * sqrt(fractional_dte / 365.0)
    sd2 = 2.0 * sd1
    sd3 = 3.0 * sd1
    return {
        "cme_numeric_1sd": sd1,
        "cme_numeric_2sd": sd2,
        "cme_numeric_3sd": sd3,
        "upper_1sd": reference_futures_price + sd1,
        "lower_1sd": reference_futures_price - sd1,
        "upper_2sd": reference_futures_price + sd2,
        "lower_2sd": reference_futures_price - sd2,
        "upper_3sd": reference_futures_price + sd3,
        "lower_3sd": reference_futures_price - sd3,
    }
