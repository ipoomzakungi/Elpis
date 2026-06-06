from datetime import date
from pathlib import Path

from src.models.xau_daily_workbench import (
    XauDailyWorkbenchCmeSource,
    XauDailyWorkbenchProviderState,
    XauDailyWorkbenchRunRequest,
    XauDailyWorkbenchSourceQuality,
)
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_daily_workbench.providers import (
    ApiOnlyCmeSource,
    FixtureCmeDataSource,
    LocalBundleCmeDataSource,
    ManualPriceProvider,
    StaticFixturePriceProvider,
    YahooResearchPriceProvider,
)
from tests.unit.test_xau_daily_workbench_service import _write_temp_bundle


def test_local_bundle_provider_returns_clean_missing_report_status(tmp_path: Path) -> None:
    input_dir = tmp_path / "empty_bundle"
    input_dir.mkdir()
    provider = LocalBundleCmeDataSource(
        XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    )

    result = provider.load_or_fetch_bundle(
        XauDailyWorkbenchRunRequest(
            session_date=date(2026, 6, 2),
            expiration_code="OG1M6",
            traded_instrument="XAUUSD",
            cme_source=XauDailyWorkbenchCmeSource.LOCAL_BUNDLE,
            input_dir=input_dir,
            research_only_acknowledged=True,
        )
    )

    assert result.daily_map is None
    assert result.provider_status.status == XauDailyWorkbenchProviderState.UNAVAILABLE
    assert result.missing_inputs[0].input_name == "04_xau_vol_oi_report_report.json"


def test_fixture_cme_source_loads_fixture_bundle(tmp_path: Path) -> None:
    input_dir = _write_temp_bundle(tmp_path)
    provider = FixtureCmeDataSource(
        XauDailyStructuralMapReportStore(reports_dir=tmp_path / "data" / "reports")
    )

    result = provider.load_or_fetch_bundle(
        XauDailyWorkbenchRunRequest(
            session_date=date(2026, 6, 2),
            expiration_code="OG1M6",
            traded_instrument="XAUUSD",
            cme_source=XauDailyWorkbenchCmeSource.FIXTURE,
            input_dir=input_dir,
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
            map_id="test_fixture_provider_map",
            research_only_acknowledged=True,
        )
    )

    assert result.daily_map is not None
    assert result.provider_status.source_quality == XauDailyWorkbenchSourceQuality.FIXTURE
    assert result.daily_map.signal_allowed is False


def test_manual_price_provider_marks_manual_override() -> None:
    provider = ManualPriceProvider(
        XauDailyWorkbenchRunRequest(
            session_date=date(2026, 6, 2),
            expiration_code="OG1M6",
            traded_instrument="XAUUSD",
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
            research_only_acknowledged=True,
        )
    )

    gc_result = provider.get_gc_reference_price(date(2026, 6, 2))

    assert gc_result.price == 4549.2
    assert gc_result.provider_status.source_quality == (
        XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE
    )


def test_static_fixture_price_provider_is_deterministic() -> None:
    provider = StaticFixturePriceProvider(
        gc_reference_price=4549.2,
        traded_reference_price=4536.7,
        session_open_price=4538.0,
    )

    assert provider.get_gc_reference_price(date(2026, 6, 2)).price == 4549.2
    assert provider.get_traded_reference_price("XAUUSD", date(2026, 6, 2)).price == 4536.7
    assert provider.get_session_open_price("XAUUSD", date(2026, 6, 2)).price == 4538.0


def test_yahoo_research_fallback_returns_unavailable_without_network() -> None:
    provider = YahooResearchPriceProvider()

    result = provider.get_session_open_price("XAUUSD", date(2026, 6, 2))

    assert result.price is None
    assert result.provider_status.status == XauDailyWorkbenchProviderState.UNAVAILABLE
    assert result.provider_status.source_quality == (
        XauDailyWorkbenchSourceQuality.RESEARCH_FALLBACK
    )


def test_api_only_source_is_cleanly_unavailable() -> None:
    result = ApiOnlyCmeSource().load_or_fetch_bundle(
        XauDailyWorkbenchRunRequest(
            cme_source=XauDailyWorkbenchCmeSource.API_ONLY,
            traded_instrument="XAUUSD",
            research_only_acknowledged=True,
        )
    )

    assert result.daily_map is None
    assert result.provider_status.status == XauDailyWorkbenchProviderState.UNAVAILABLE
    assert result.missing_inputs[0].input_name == "cme_source.api_only"
