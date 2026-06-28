from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from src.models.xau import XauDailyStructuralMap
from src.models.xau_daily_structural_map import XauDailyStructuralMapReportMetadata
from src.models.xau_daily_workbench import (
    XauDailyWorkbenchMissingInput,
    XauDailyWorkbenchMissingInputSeverity,
    XauDailyWorkbenchProviderState,
    XauDailyWorkbenchProviderStatus,
    XauDailyWorkbenchProviderType,
    XauDailyWorkbenchRunRequest,
    XauDailyWorkbenchSourceQuality,
    missing_input,
    provider_status,
)
from src.xau_daily_structural_map.bundle_adapter import (
    generate_xau_daily_structural_map_from_bundle,
)
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_daily_structural_map.sample_run import stable_xau_daily_structural_map_id

REPORT_JSON_FILENAME = "04_xau_vol_oi_report_report.json"
WALLS_PARQUET_FILENAME = "04_xau_vol_oi_report_walls.parquet"
ZONES_PARQUET_FILENAME = "04_xau_vol_oi_report_zones.parquet"
FUSED_ROWS_FILENAME = "03_xau_quikstrike_fusion_fused_rows.json"


@dataclass(frozen=True)
class CmeDataSourceResult:
    daily_map: XauDailyStructuralMap | None
    metadata: XauDailyStructuralMapReportMetadata | None
    artifact_paths: dict[str, str]
    provider_status: XauDailyWorkbenchProviderStatus
    missing_inputs: list[XauDailyWorkbenchMissingInput]
    no_signal_reasons: list[str]
    limitations: list[str]


@dataclass(frozen=True)
class PriceResult:
    price: float | None
    provider_status: XauDailyWorkbenchProviderStatus
    missing_inputs: list[XauDailyWorkbenchMissingInput]
    no_signal_reasons: list[str]


class CmeDataSource(Protocol):
    def load_or_fetch_bundle(
        self,
        request: XauDailyWorkbenchRunRequest,
    ) -> CmeDataSourceResult:
        """Load or fetch one CME/XAU data bundle as a structural map."""

    def get_status(self) -> XauDailyWorkbenchProviderStatus:
        """Return current source status without exposing credentials or sessions."""


class FuturesPriceProvider(Protocol):
    def get_gc_reference_price(
        self,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        """Return a GC/futures reference price."""


class TradedPriceProvider(Protocol):
    def get_traded_reference_price(
        self,
        traded_instrument: str,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        """Return the traded chart reference price."""


class SessionOpenProvider(Protocol):
    def get_session_open_price(
        self,
        traded_instrument: str,
        session_date: date | None,
    ) -> PriceResult:
        """Return the session open reference."""


class LocalBundleCmeDataSource:
    def __init__(
        self,
        map_store: XauDailyStructuralMapReportStore,
        *,
        source_quality: XauDailyWorkbenchSourceQuality = (
            XauDailyWorkbenchSourceQuality.LOCAL_BUNDLE
        ),
        provider_name: str = "LocalBundleCmeDataSource",
    ) -> None:
        self.map_store = map_store
        self.source_quality = source_quality
        self.provider_name = provider_name
        self._last_status = _status(
            provider_name=provider_name,
            status=XauDailyWorkbenchProviderState.UNAVAILABLE,
            source_quality=source_quality,
            message="Local bundle source has not run yet.",
        )

    def load_or_fetch_bundle(
        self,
        request: XauDailyWorkbenchRunRequest,
    ) -> CmeDataSourceResult:
        missing_inputs: list[XauDailyWorkbenchMissingInput] = []
        if request.input_dir is None:
            missing_inputs.append(_missing("input_dir", "Local bundle input_dir is required."))
        if request.session_date is None:
            missing_inputs.append(
                _missing("session_date", "Local bundle session_date is required.")
            )
        if request.expiration_code is None:
            missing_inputs.append(
                _missing("expiration_code", "Local bundle expiration_code is required.")
            )
        if missing_inputs:
            return self._blocked(
                missing_inputs,
                "Local bundle source requires input_dir, session_date, and expiration_code.",
            )

        input_dir = request.input_dir.resolve()
        if not input_dir.exists():
            return self._blocked(
                [_missing("input_dir", f"Local bundle input directory was not found: {input_dir}")],
                f"Local bundle input directory was not found: {input_dir}",
            )
        if not input_dir.is_dir():
            return self._blocked(
                [_missing("input_dir", f"Local bundle input path is not a directory: {input_dir}")],
                f"Local bundle input path is not a directory: {input_dir}",
            )

        report_path = input_dir / REPORT_JSON_FILENAME
        if not report_path.exists():
            return self._blocked(
                [
                    _missing(
                        REPORT_JSON_FILENAME,
                        f"Missing required XAU Vol-OI report JSON: {report_path}",
                    )
                ],
                f"Missing required XAU Vol-OI report JSON: {report_path}",
            )

        map_id = request.map_id or stable_xau_daily_structural_map_id(
            session_date=request.session_date,
            expiration_code=request.expiration_code,
        )
        result = generate_xau_daily_structural_map_from_bundle(
            map_id=map_id,
            session_date=request.session_date,
            xau_vol_oi_report_path=report_path,
            walls_path=_optional_path(input_dir / WALLS_PARQUET_FILENAME),
            fused_rows_path=_optional_path(input_dir / FUSED_ROWS_FILENAME),
            traded_instrument=request.traded_instrument,
            traded_reference_price=request.traded_reference_price,
            gc_reference_price=request.gc_reference_price,
            manual_basis=request.manual_basis,
            session_open_price=request.session_open_price,
            session_open_source=request.session_open_source,
            output_root=self.map_store.reports_dir,
            overwrite_allowed=request.overwrite_allowed,
        )
        self._last_status = _status(
            provider_name=self.provider_name,
            status=XauDailyWorkbenchProviderState.AVAILABLE,
            source_quality=self.source_quality,
            message="Local XAU bundle loaded and persisted as a daily structural map.",
            limitations=result.daily_map.limitations,
        )
        return CmeDataSourceResult(
            daily_map=result.daily_map,
            metadata=result.metadata,
            artifact_paths={
                artifact.artifact_type.value: artifact.path for artifact in result.artifacts
            },
            provider_status=self._last_status,
            missing_inputs=[],
            no_signal_reasons=result.daily_map.no_signal_reasons,
            limitations=result.daily_map.limitations,
        )

    def get_status(self) -> XauDailyWorkbenchProviderStatus:
        return self._last_status

    def _blocked(
        self,
        missing_inputs: list[XauDailyWorkbenchMissingInput],
        message: str,
    ) -> CmeDataSourceResult:
        self._last_status = _status(
            provider_name=self.provider_name,
            status=XauDailyWorkbenchProviderState.UNAVAILABLE,
            source_quality=self.source_quality,
            message=message,
            limitations=["No structural map can be built until the local CME bundle exists."],
        )
        return CmeDataSourceResult(
            daily_map=None,
            metadata=None,
            artifact_paths={},
            provider_status=self._last_status,
            missing_inputs=missing_inputs,
            no_signal_reasons=[message],
            limitations=self._last_status.limitations,
        )


class FixtureCmeDataSource(LocalBundleCmeDataSource):
    def __init__(self, map_store: XauDailyStructuralMapReportStore) -> None:
        super().__init__(
            map_store,
            source_quality=XauDailyWorkbenchSourceQuality.FIXTURE,
            provider_name="FixtureCmeDataSource",
        )


class LatestExistingXauArtifactSource:
    def __init__(self, map_store: XauDailyStructuralMapReportStore) -> None:
        self.map_store = map_store
        self._last_status = _status(
            provider_name="LatestExistingXauArtifactSource",
            status=XauDailyWorkbenchProviderState.UNAVAILABLE,
            source_quality=XauDailyWorkbenchSourceQuality.LATEST_EXISTING,
            message="Latest existing source has not run yet.",
        )

    def load_or_fetch_bundle(
        self,
        request: XauDailyWorkbenchRunRequest,
    ) -> CmeDataSourceResult:
        latest = _latest_existing_map(self.map_store, request)
        if latest is None:
            message = "No existing XAU daily structural map matched the requested filters."
            self._last_status = _status(
                provider_name="LatestExistingXauArtifactSource",
                status=XauDailyWorkbenchProviderState.UNAVAILABLE,
                source_quality=XauDailyWorkbenchSourceQuality.LATEST_EXISTING,
                message=message,
            )
            return CmeDataSourceResult(
                daily_map=None,
                metadata=None,
                artifact_paths={},
                provider_status=self._last_status,
                missing_inputs=[_missing("xau_daily_structural_map", message)],
                no_signal_reasons=[message],
                limitations=[],
            )

        daily_map, metadata = latest
        self._last_status = _status(
            provider_name="LatestExistingXauArtifactSource",
            status=XauDailyWorkbenchProviderState.AVAILABLE,
            source_quality=XauDailyWorkbenchSourceQuality.LATEST_EXISTING,
            message="Loaded latest matching XAU daily structural map.",
            limitations=daily_map.limitations,
        )
        return CmeDataSourceResult(
            daily_map=daily_map,
            metadata=metadata,
            artifact_paths={
                artifact.artifact_type.value: artifact.path
                for artifact in metadata.artifacts
            },
            provider_status=self._last_status,
            missing_inputs=[],
            no_signal_reasons=daily_map.no_signal_reasons,
            limitations=daily_map.limitations,
        )

    def get_status(self) -> XauDailyWorkbenchProviderStatus:
        return self._last_status


class ApiOnlyCmeSource:
    def __init__(self) -> None:
        self._last_status = _status(
            provider_name="ApiOnlyCmeSource",
            status=XauDailyWorkbenchProviderState.UNAVAILABLE,
            source_quality=XauDailyWorkbenchSourceQuality.OFFICIAL,
            message="API-only CME source is not configured.",
        )

    def load_or_fetch_bundle(
        self,
        request: XauDailyWorkbenchRunRequest,
    ) -> CmeDataSourceResult:
        message = "API-only CME source is not configured for this local workbench slice."
        self._last_status = _status(
            provider_name="ApiOnlyCmeSource",
            status=XauDailyWorkbenchProviderState.UNAVAILABLE,
            source_quality=XauDailyWorkbenchSourceQuality.OFFICIAL,
            message=message,
            limitations=["No credentials or session material are required or read by tests."],
        )
        return CmeDataSourceResult(
            daily_map=None,
            metadata=None,
            artifact_paths={},
            provider_status=self._last_status,
            missing_inputs=[_missing("cme_source.api_only", message)],
            no_signal_reasons=[message],
            limitations=self._last_status.limitations,
        )

    def get_status(self) -> XauDailyWorkbenchProviderStatus:
        return self._last_status


class ManualPriceProvider:
    """Uses request-supplied reference prices and marks them as manual overrides."""

    def __init__(self, request: XauDailyWorkbenchRunRequest) -> None:
        self.request = request

    def get_gc_reference_price(
        self,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        return _price_result(
            provider_name="ManualFuturesPriceProvider",
            provider_type=XauDailyWorkbenchProviderType.FUTURES_PRICE,
            price=self.request.gc_reference_price,
            input_name="gc_reference_price",
            available_message="GC reference price supplied by request.",
            missing_message="GC reference price was not supplied by request.",
            source_quality=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
        )

    def get_traded_reference_price(
        self,
        traded_instrument: str,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        return _price_result(
            provider_name="ManualTradedPriceProvider",
            provider_type=XauDailyWorkbenchProviderType.TRADED_PRICE,
            price=self.request.traded_reference_price,
            input_name="traded_reference_price",
            available_message="Traded reference price supplied by request.",
            missing_message="Traded reference price was not supplied by request.",
            source_quality=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
        )

    def get_session_open_price(
        self,
        traded_instrument: str,
        session_date: date | None,
    ) -> PriceResult:
        return _price_result(
            provider_name="ManualSessionOpenProvider",
            provider_type=XauDailyWorkbenchProviderType.SESSION_OPEN,
            price=self.request.session_open_price,
            input_name="session_open_price",
            available_message="Session open price supplied by request.",
            missing_message="Session open price was not supplied by request.",
            source_quality=XauDailyWorkbenchSourceQuality.MANUAL_OVERRIDE,
        )


class StaticFixturePriceProvider:
    """Deterministic price provider for tests; no network access."""

    def __init__(
        self,
        *,
        gc_reference_price: float | None = None,
        traded_reference_price: float | None = None,
        session_open_price: float | None = None,
    ) -> None:
        self.gc_price = gc_reference_price
        self.traded_price = traded_reference_price
        self.open_price = session_open_price

    def get_gc_reference_price(
        self,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        return _price_result(
            provider_name="StaticFixtureFuturesPriceProvider",
            provider_type=XauDailyWorkbenchProviderType.FUTURES_PRICE,
            price=self.gc_price,
            input_name="gc_reference_price",
            available_message="Fixture GC reference price supplied.",
            missing_message="Fixture GC reference price is unavailable.",
            source_quality=XauDailyWorkbenchSourceQuality.FIXTURE,
        )

    def get_traded_reference_price(
        self,
        traded_instrument: str,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        return _price_result(
            provider_name="StaticFixtureTradedPriceProvider",
            provider_type=XauDailyWorkbenchProviderType.TRADED_PRICE,
            price=self.traded_price,
            input_name="traded_reference_price",
            available_message="Fixture traded reference price supplied.",
            missing_message="Fixture traded reference price is unavailable.",
            source_quality=XauDailyWorkbenchSourceQuality.FIXTURE,
        )

    def get_session_open_price(
        self,
        traded_instrument: str,
        session_date: date | None,
    ) -> PriceResult:
        return _price_result(
            provider_name="StaticFixtureSessionOpenProvider",
            provider_type=XauDailyWorkbenchProviderType.SESSION_OPEN,
            price=self.open_price,
            input_name="session_open_price",
            available_message="Fixture session open price supplied.",
            missing_message="Fixture session open price is unavailable.",
            source_quality=XauDailyWorkbenchSourceQuality.FIXTURE,
        )


class YahooResearchPriceProvider:
    """Optional research fallback; tests must not require network or yfinance."""

    def get_gc_reference_price(
        self,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        return self._unavailable("gc_reference_price", "Yahoo GC fallback is not configured.")

    def get_traded_reference_price(
        self,
        traded_instrument: str,
        session_date: date | None,
        timestamp: datetime | None = None,
    ) -> PriceResult:
        try:
            import yfinance  # noqa: F401
        except ImportError:
            return self._unavailable(
                "traded_reference_price",
                "yfinance is not installed; Yahoo research fallback unavailable.",
            )
        return self._unavailable(
            "traded_reference_price",
            "Yahoo research fallback is intentionally not used by tests or default runs.",
        )

    def get_session_open_price(
        self,
        traded_instrument: str,
        session_date: date | None,
    ) -> PriceResult:
        return self._unavailable(
            "session_open_price",
            "Yahoo session-open fallback is not configured for XAU workbench.",
        )

    def _unavailable(self, input_name: str, message: str) -> PriceResult:
        return PriceResult(
            price=None,
            provider_status=_status(
                provider_name="YahooResearchPriceProvider",
                provider_type=XauDailyWorkbenchProviderType.TRADED_PRICE,
                status=XauDailyWorkbenchProviderState.UNAVAILABLE,
                source_quality=XauDailyWorkbenchSourceQuality.RESEARCH_FALLBACK,
                message=message,
                limitations=[
                    "Yahoo is a research fallback only and is not broker-exact XAU data."
                ],
            ),
            missing_inputs=[
                missing_input(
                    input_name,
                    message,
                    severity=XauDailyWorkbenchMissingInputSeverity.WARNING,
                )
            ],
            no_signal_reasons=[message],
        )


def _latest_existing_map(
    map_store: XauDailyStructuralMapReportStore,
    request: XauDailyWorkbenchRunRequest,
) -> tuple[XauDailyStructuralMap, XauDailyStructuralMapReportMetadata] | None:
    root = map_store.report_root()
    if not root.exists():
        return None
    matches: list[tuple[XauDailyStructuralMap, XauDailyStructuralMapReportMetadata]] = []
    for metadata_path in root.glob("*/metadata.json"):
        map_id = metadata_path.parent.name
        try:
            daily_map = map_store.read_map(map_id)
            metadata = map_store.read_metadata(map_id)
        except (OSError, ValueError):
            continue
        if request.session_date is not None and daily_map.session_date != request.session_date:
            continue
        if (
            request.expiration_code is not None
            and daily_map.expiration_code != request.expiration_code
        ):
            continue
        if (
            request.traded_instrument
            and daily_map.traded_instrument.lower() != request.traded_instrument.lower()
        ):
            continue
        matches.append((daily_map, metadata))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0].created_at)


def _price_result(
    *,
    provider_name: str,
    provider_type: XauDailyWorkbenchProviderType,
    price: float | None,
    input_name: str,
    available_message: str,
    missing_message: str,
    source_quality: XauDailyWorkbenchSourceQuality,
) -> PriceResult:
    if price is not None:
        return PriceResult(
            price=price,
            provider_status=_status(
                provider_name=provider_name,
                provider_type=provider_type,
                status=XauDailyWorkbenchProviderState.AVAILABLE,
                source_quality=source_quality,
                message=available_message,
                limitations=["Reference price is local research context, not execution data."],
            ),
            missing_inputs=[],
            no_signal_reasons=[],
        )
    return PriceResult(
        price=None,
        provider_status=_status(
            provider_name=provider_name,
            provider_type=provider_type,
            status=XauDailyWorkbenchProviderState.UNAVAILABLE,
            source_quality=source_quality,
            message=missing_message,
            limitations=["Missing price context keeps candidate readiness blocked if required."],
        ),
        missing_inputs=[
            missing_input(
                input_name,
                missing_message,
                severity=XauDailyWorkbenchMissingInputSeverity.WARNING,
            )
        ],
        no_signal_reasons=[missing_message],
    )


def _status(
    *,
    provider_name: str,
    status: XauDailyWorkbenchProviderState,
    source_quality: XauDailyWorkbenchSourceQuality,
    message: str,
    provider_type: XauDailyWorkbenchProviderType = (
        XauDailyWorkbenchProviderType.CME_DATA_SOURCE
    ),
    limitations: list[str] | None = None,
) -> XauDailyWorkbenchProviderStatus:
    return provider_status(
        provider_name=provider_name,
        provider_type=provider_type,
        status=status,
        source_quality=source_quality,
        message=message,
        limitations=limitations,
    )


def _missing(input_name: str, message: str) -> XauDailyWorkbenchMissingInput:
    return missing_input(
        input_name,
        message,
        severity=XauDailyWorkbenchMissingInputSeverity.BLOCKING,
    )


def _optional_path(path: Path) -> Path | None:
    return path if path.exists() else None


__all__ = [
    "ApiOnlyCmeSource",
    "CmeDataSource",
    "CmeDataSourceResult",
    "FUSED_ROWS_FILENAME",
    "FixtureCmeDataSource",
    "FuturesPriceProvider",
    "LatestExistingXauArtifactSource",
    "LocalBundleCmeDataSource",
    "ManualPriceProvider",
    "PriceResult",
    "REPORT_JSON_FILENAME",
    "SessionOpenProvider",
    "StaticFixturePriceProvider",
    "TradedPriceProvider",
    "WALLS_PARQUET_FILENAME",
    "YahooResearchPriceProvider",
    "ZONES_PARQUET_FILENAME",
]
