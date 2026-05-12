from datetime import date, timedelta

from src.models.free_derivatives import (
    CftcCotGoldRecord,
    CftcGoldPositioningSummary,
    FreeDerivativesSource,
    GvzDailyCloseRecord,
    GvzGapSummary,
)

CFTC_WEEKLY_POSITIONING_LIMITATION = (
    "Weekly broad positioning context only; not strike-level options open interest "
    "and not intraday wall data."
)
CFTC_CATEGORY_LIMITATION = (
    "Futures-only and futures-and-options combined reports must remain separately labeled."
)
GVZ_PROXY_LIMITATION = (
    "GVZ is a GLD-options-derived volatility proxy, not a CME gold options "
    "implied-volatility surface."
)
GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION = (
    "GVZ is not strike-level options open interest and cannot replace local XAU "
    "options OI."
)
DERIBIT_CRYPTO_OPTIONS_LIMITATION = (
    "Deribit public options data is crypto options data only, not gold or XAU data."
)
PUBLIC_ONLY_LIMITATION = (
    "This run uses public/no-key market-data access only and does not use private "
    "account, broker, wallet, order, or paid vendor credentials."
)
ARTIFACT_SCOPE_LIMITATION = (
    "Generated raw, processed, and report outputs are local research artifacts and "
    "must remain untracked."
)
FREE_DERIVATIVES_RESEARCH_ONLY_WARNING = (
    "Free derivatives bootstrap is research-only and uses public/no-key or local "
    "fixture inputs only."
)
FREE_DERIVATIVES_NO_REPLACEMENT_LIMITATION = (
    "CFTC COT, GVZ, and Deribit public options do not replace local XAU "
    "strike-level options OI."
)


def source_limitations(source: FreeDerivativesSource) -> list[str]:
    """Return foundational source limitation labels for free derivatives data."""

    if source == FreeDerivativesSource.CFTC_COT:
        return [
            CFTC_WEEKLY_POSITIONING_LIMITATION,
            CFTC_CATEGORY_LIMITATION,
            PUBLIC_ONLY_LIMITATION,
            ARTIFACT_SCOPE_LIMITATION,
        ]
    if source == FreeDerivativesSource.GVZ:
        return [
            GVZ_PROXY_LIMITATION,
            GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION,
            PUBLIC_ONLY_LIMITATION,
            ARTIFACT_SCOPE_LIMITATION,
        ]
    if source == FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS:
        return [
            DERIBIT_CRYPTO_OPTIONS_LIMITATION,
            PUBLIC_ONLY_LIMITATION,
            ARTIFACT_SCOPE_LIMITATION,
        ]
    raise ValueError(f"Unsupported free derivatives source: {source}")


def foundational_limitations() -> list[str]:
    """Return de-duplicated feature-level limitation labels."""

    values = [
        CFTC_WEEKLY_POSITIONING_LIMITATION,
        CFTC_CATEGORY_LIMITATION,
        GVZ_PROXY_LIMITATION,
        GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION,
        DERIBIT_CRYPTO_OPTIONS_LIMITATION,
        PUBLIC_ONLY_LIMITATION,
        ARTIFACT_SCOPE_LIMITATION,
        FREE_DERIVATIVES_NO_REPLACEMENT_LIMITATION,
    ]
    return list(dict.fromkeys(values))


def build_cftc_gold_positioning_summary(
    records: list[CftcCotGoldRecord],
) -> list[CftcGoldPositioningSummary]:
    """Create weekly broad gold positioning summaries with category labels preserved."""

    records_by_group: dict[tuple[str, str, str], list[CftcCotGoldRecord]] = {}
    for record in records:
        key = (record.report_category.value, record.market_name, record.exchange_name)
        records_by_group.setdefault(key, []).append(record)

    summaries: list[CftcGoldPositioningSummary] = []
    for group_records in records_by_group.values():
        previous_noncommercial_net: float | None = None
        previous_open_interest: float | None = None
        for record in sorted(group_records, key=lambda item: item.report_date):
            noncommercial_net = _net(record.noncommercial_long, record.noncommercial_short)
            summary = CftcGoldPositioningSummary(
                report_date=record.report_date,
                report_category=record.report_category,
                market_name=record.market_name,
                exchange_name=record.exchange_name,
                open_interest=record.open_interest,
                noncommercial_net=noncommercial_net,
                commercial_net=_net(record.commercial_long, record.commercial_short),
                total_reportable_net=_net(
                    record.total_reportable_long,
                    record.total_reportable_short,
                ),
                nonreportable_net=_net(
                    record.nonreportable_long,
                    record.nonreportable_short,
                ),
                week_over_week_noncommercial_net_change=_difference(
                    noncommercial_net,
                    previous_noncommercial_net,
                ),
                week_over_week_open_interest_change=_difference(
                    record.open_interest,
                    previous_open_interest,
                ),
                limitations=[CFTC_WEEKLY_POSITIONING_LIMITATION, CFTC_CATEGORY_LIMITATION],
            )
            summaries.append(summary)
            previous_noncommercial_net = noncommercial_net
            previous_open_interest = record.open_interest
    return sorted(
        summaries,
        key=lambda item: (item.report_category.value, item.market_name, item.report_date),
    )


def build_gvz_gap_summary(
    records: list[GvzDailyCloseRecord],
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> GvzGapSummary:
    """Summarize missing GVZ daily close observations without fabricating values."""

    if not records and (start_date is None or end_date is None):
        raise ValueError("GVZ gap summary needs records or an explicit date window")
    observed_dates = {record.date for record in records if not record.is_missing}
    all_record_dates = {record.date for record in records}
    window_start = start_date or min(all_record_dates)
    window_end = end_date or max(all_record_dates)
    missing_dates = [
        current_date
        for current_date in _inclusive_dates(window_start, window_end)
        if current_date not in observed_dates
    ]
    return GvzGapSummary(
        start_date=window_start,
        end_date=window_end,
        observed_row_count=len(observed_dates),
        missing_date_count=len(missing_dates),
        missing_dates=missing_dates,
        limitations=[GVZ_PROXY_LIMITATION, GVZ_NOT_STRIKE_LEVEL_OI_LIMITATION],
    )


def _net(long_value: float | None, short_value: float | None) -> float | None:
    if long_value is None or short_value is None:
        return None
    return long_value - short_value


def _difference(value: float | None, previous: float | None) -> float | None:
    if value is None or previous is None:
        return None
    return value - previous


def _inclusive_dates(start_date: date, end_date: date):
    current_date = start_date
    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)
