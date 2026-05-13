import pytest

from src.quikstrike_matrix.local_browser import (
    QuikStrikeMatrixLocalBrowserAdapter,
    QuikStrikeMatrixLocalBrowserNotImplementedError,
)


def test_local_browser_adapter_reports_safe_readiness():
    adapter = QuikStrikeMatrixLocalBrowserAdapter()
    readiness = adapter.readiness(surface="Open Interest Matrix", product="Gold (OG|GC)")

    assert readiness.ready is True
    assert readiness.status == "manual_ready"
    assert "user-controlled" in readiness.message.lower()
    assert "No browser cookies" in readiness.limitations[0]


def test_local_browser_adapter_rejects_secret_material():
    with pytest.raises(ValueError, match="secret/session fields"):
        QuikStrikeMatrixLocalBrowserAdapter({"cookies": "blocked"})


def test_local_browser_collection_is_placeholder_only():
    adapter = QuikStrikeMatrixLocalBrowserAdapter()

    with pytest.raises(QuikStrikeMatrixLocalBrowserNotImplementedError):
        adapter.collect_current_table_payload()
