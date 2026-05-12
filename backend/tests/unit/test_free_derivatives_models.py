from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.free_derivatives import (
    CftcCotReportCategory,
    DeribitOptionsRequest,
    FreeDerivativesBootstrapRequest,
    FreeDerivativesReportFormat,
    FreeDerivativesSource,
    validate_filesystem_safe_id,
)


def test_free_derivatives_enums_have_expected_public_sources():
    assert FreeDerivativesSource.CFTC_COT == "cftc_cot"
    assert FreeDerivativesSource.GVZ == "gvz"
    assert FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS == "deribit_public_options"
    assert FreeDerivativesReportFormat.BOTH == "both"


def test_bootstrap_request_requires_research_only_acknowledgement():
    with pytest.raises(ValidationError, match="research_only_acknowledged must be true"):
        FreeDerivativesBootstrapRequest(research_only_acknowledged=False)


def test_bootstrap_request_rejects_all_sources_disabled():
    with pytest.raises(ValidationError, match="at least one free derivatives source"):
        FreeDerivativesBootstrapRequest(
            include_cftc=False,
            include_gvz=False,
            include_deribit=False,
            research_only_acknowledged=True,
        )


def test_bootstrap_request_rejects_extra_and_credential_fields():
    with pytest.raises(ValidationError):
        FreeDerivativesBootstrapRequest(
            research_only_acknowledged=True,
            unexpected="value",
        )

    with pytest.raises(ValidationError, match="credential or execution fields"):
        FreeDerivativesBootstrapRequest(
            research_only_acknowledged=True,
            cftc={"api_key": "not-allowed"},
        )


def test_bootstrap_request_validates_safe_ids_urls_and_paths():
    request = FreeDerivativesBootstrapRequest(
        run_label="fixture_smoke",
        research_only_acknowledged=True,
        cftc={
            "years": [2025, 2025, 2026],
            "categories": [CftcCotReportCategory.FUTURES_ONLY],
            "source_urls": ["https://www.cftc.gov/files/report.csv"],
            "local_fixture_paths": [Path("backend/tests/fixtures/free_derivatives/cftc.csv")],
        },
        gvz={
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 1, 31),
        },
    )

    assert request.run_label == "fixture_smoke"
    assert request.cftc.years == [2025, 2026]
    assert request.cftc.source_urls == ["https://www.cftc.gov/files/report.csv"]

    with pytest.raises(ValidationError, match="filesystem-safe"):
        FreeDerivativesBootstrapRequest(
            run_label="../bad",
            research_only_acknowledged=True,
        )
    with pytest.raises(ValidationError, match="must not include credentials"):
        FreeDerivativesBootstrapRequest(
            research_only_acknowledged=True,
            cftc={"source_urls": ["https://user:pass@example.com/file.csv"]},
        )
    with pytest.raises(ValidationError, match="parent traversal"):
        FreeDerivativesBootstrapRequest(
            research_only_acknowledged=True,
            cftc={"local_fixture_paths": ["../outside.csv"]},
        )


def test_deribit_request_normalizes_and_deduplicates_underlyings():
    request = DeribitOptionsRequest(underlyings=["btc", "ETH", "btc"])

    assert request.underlyings == ["BTC", "ETH"]

    with pytest.raises(ValidationError, match="safe uppercase symbols"):
        DeribitOptionsRequest(underlyings=["BTC/../../BAD"])


def test_deribit_request_rejects_private_account_order_and_auth_fields():
    forbidden_payloads = [
        {"account_id": "not-allowed"},
        {"order_id": "not-allowed"},
        {"private_endpoint": "/private/get_positions"},
        {"authentication": "not-allowed"},
    ]

    for payload in forbidden_payloads:
        with pytest.raises(ValidationError, match="credential or execution fields"):
            DeribitOptionsRequest(**payload)


def test_validate_filesystem_safe_id_rejects_unsafe_values():
    assert validate_filesystem_safe_id("free_derivatives_20260512") == (
        "free_derivatives_20260512"
    )
    for value in ("", "../outside", "nested/run", "bad id"):
        with pytest.raises(ValueError):
            validate_filesystem_safe_id(value)
