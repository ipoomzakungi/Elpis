from src.free_derivatives.processing import (
    ARTIFACT_SCOPE_LIMITATION,
    CFTC_WEEKLY_POSITIONING_LIMITATION,
    DERIBIT_CRYPTO_OPTIONS_LIMITATION,
    GVZ_PROXY_LIMITATION,
    PUBLIC_ONLY_LIMITATION,
    source_limitations,
)
from src.models.free_derivatives import FreeDerivativesSource


def test_foundational_limitation_labels_describe_source_boundaries():
    assert "weekly broad positioning" in CFTC_WEEKLY_POSITIONING_LIMITATION.lower()
    assert "not strike-level options open interest" in CFTC_WEEKLY_POSITIONING_LIMITATION
    assert "GLD-options-derived volatility proxy" in GVZ_PROXY_LIMITATION
    assert "not a CME gold options" in GVZ_PROXY_LIMITATION
    assert "crypto options data only" in DERIBIT_CRYPTO_OPTIONS_LIMITATION
    assert "not gold or XAU data" in DERIBIT_CRYPTO_OPTIONS_LIMITATION
    assert "public/no-key" in PUBLIC_ONLY_LIMITATION
    assert "must remain untracked" in ARTIFACT_SCOPE_LIMITATION


def test_source_limitations_include_public_and_artifact_scope_labels():
    for source in FreeDerivativesSource:
        limitations = source_limitations(source)

        assert PUBLIC_ONLY_LIMITATION in limitations
        assert ARTIFACT_SCOPE_LIMITATION in limitations


def test_cftc_limitations_state_weekly_context_and_no_wall_level_replacement():
    limitations = source_limitations(FreeDerivativesSource.CFTC_COT)
    joined = " ".join(limitations).lower()

    assert "weekly broad positioning context" in joined
    assert "not strike-level options open interest" in joined
    assert "not intraday wall data" in joined
