from src.models.free_derivatives import FreeDerivativesSource

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
        return [GVZ_PROXY_LIMITATION, PUBLIC_ONLY_LIMITATION, ARTIFACT_SCOPE_LIMITATION]
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
        DERIBIT_CRYPTO_OPTIONS_LIMITATION,
        PUBLIC_ONLY_LIMITATION,
        ARTIFACT_SCOPE_LIMITATION,
        FREE_DERIVATIVES_NO_REPLACEMENT_LIMITATION,
    ]
    return list(dict.fromkeys(values))

