import pytest

from src.quikstrike.local_browser import (
    LocalBrowserExtractionNotImplementedError,
    QuikStrikeLocalBrowserAdapter,
    validate_sanitized_browser_context,
)


def test_local_browser_adapter_reports_manual_ready_for_gold_vol2vol_context():
    adapter = QuikStrikeLocalBrowserAdapter(
        {"surface": "QUIKOPTIONS VOL2VOL", "product": "Gold (OG|GC)"}
    )

    readiness = adapter.readiness()

    assert readiness.ready is True
    assert readiness.status == "manual_ready"
    assert "Gold" in readiness.message
    assert any("No browser cookies" in limitation for limitation in readiness.limitations)


def test_local_browser_adapter_reports_manual_navigation_required():
    adapter = QuikStrikeLocalBrowserAdapter({"surface": "Other", "product": "Corn"})

    readiness = adapter.readiness()

    assert readiness.ready is False
    assert readiness.status == "manual_navigation_required"
    assert "navigate" in readiness.message


def test_local_browser_adapter_rejects_secret_session_inputs():
    forbidden_payloads = [
        {"cookies": "not allowed"},
        {"headers": {"Authorization": "not allowed"}},
        {"viewstate": "__VIEWSTATE"},
        {"har": {"entries": []}},
        {"screenshot": "image.png"},
    ]

    for payload in forbidden_payloads:
        with pytest.raises(ValueError, match="secret/session fields"):
            validate_sanitized_browser_context(payload)


def test_local_browser_adapter_real_collection_is_not_implemented():
    adapter = QuikStrikeLocalBrowserAdapter()

    with pytest.raises(LocalBrowserExtractionNotImplementedError, match="not implemented"):
        adapter.collect_current_page_payload()
