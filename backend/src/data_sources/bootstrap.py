"""Free public/local data bootstrapper for data-source onboarding."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import yfinance as yf

from src.config import get_settings
from src.data_sources.capabilities import YAHOO_UNSUPPORTED_CAPABILITIES
from src.data_sources.missing_data import xau_options_oi_schema_action
from src.data_sources.preflight import DataSourcePreflightService
from src.data_sources.report_store import DataSourceBootstrapReportStore
from src.models.data_sources import (
    DataSourceBootstrapArtifact,
    DataSourceBootstrapAssetSummary,
    DataSourceBootstrapPlanItem,
    DataSourceBootstrapProvider,
    DataSourceBootstrapRequest,
    DataSourceBootstrapRunResult,
    DataSourceMissingDataAction,
    DataSourcePreflightRequest,
    DataSourceProviderType,
    FirstEvidenceRunStatus,
)
from src.providers.yahoo_finance_provider import YahooFinanceProvider
from src.services.binance_client import BinanceClient
from src.services.feature_engine import FeatureEngine

BINANCE_LIMITED_DERIVATIVES_NOTE = (
    "Binance public OI/funding history can be limited or shallow; deeper historical "
    "derivatives research may require exported vendor data."
)
YAHOO_OHLCV_ONLY_LIMITATION = (
    "Yahoo Finance is OHLCV-only and is not a source for OI, funding, IV, gold "
    "options OI, futures OI, or XAUUSD execution data."
)
XAU_LOCAL_IMPORT_LIMITATION = (
    "XAU options OI remains a local CSV/Parquet import workflow under data/raw/xau."
)
BOOTSTRAP_RESEARCH_WARNING = (
    "Public data bootstrap is research-only; it does not use paid vendor APIs, "
    "private trading keys, broker integrations, wallet keys, or order execution."
)
INTERVAL_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


@dataclass(frozen=True)
class _DownloadedFrames:
    ohlcv: pl.DataFrame
    open_interest: pl.DataFrame | None = None
    funding_rate: pl.DataFrame | None = None


class YahooPublicOhlcvClient:
    """Small yfinance wrapper used by the public bootstrap service."""

    def __init__(self, ticker_factory: Any | None = None):
        self.ticker_factory = ticker_factory or yf.Ticker

    async def download_ohlcv(self, symbol: str, timeframe: str, days: int) -> pl.DataFrame:
        provider = YahooFinanceProvider(ticker_factory=self.ticker_factory)
        request = type(
            "YahooBootstrapRequest",
            (),
            {"symbol": symbol, "timeframe": timeframe, "days": days},
        )()
        return await provider.fetch_ohlcv(request)


class PublicDataBootstrapService:
    """Download public/no-key data and write ignored raw/processed artifacts."""

    def __init__(
        self,
        *,
        binance_client: Any | None = None,
        yahoo_client: Any | None = None,
        report_store: DataSourceBootstrapReportStore | None = None,
    ):
        self.settings = get_settings()
        self.binance_client = binance_client or BinanceClient()
        self.yahoo_client = yahoo_client or YahooPublicOhlcvClient()
        self.report_store = report_store or DataSourceBootstrapReportStore()

    async def run(self, request: DataSourceBootstrapRequest) -> DataSourceBootstrapRunResult:
        run_id = _bootstrap_run_id()
        summaries: list[DataSourceBootstrapAssetSummary] = []
        if request.include_binance:
            for symbol in [*request.binance_symbols, *request.optional_binance_symbols]:
                for timeframe in request.binance_timeframes:
                    summaries.append(
                        await self._bootstrap_binance_symbol(
                            symbol=symbol,
                            timeframe=timeframe,
                            request=request,
                        )
                    )

        if request.include_yahoo:
            for symbol in request.yahoo_symbols:
                for timeframe in request.yahoo_timeframes:
                    summaries.append(
                        await self._bootstrap_yahoo_symbol(
                            symbol=symbol,
                            timeframe=timeframe,
                            request=request,
                        )
                    )

        missing_actions: list[DataSourceMissingDataAction] = []
        limitations = [XAU_LOCAL_IMPORT_LIMITATION]
        if request.include_xau_local_instructions:
            missing_actions.append(xau_options_oi_schema_action())

        preflight = None
        if request.run_preflight_after and summaries:
            preflight = DataSourcePreflightService().run(
                _preflight_request_from_bootstrap(request, summaries)
            )
            missing_actions = _dedupe_actions(
                [*missing_actions, *preflight.missing_data_actions]
            )

        result = DataSourceBootstrapRunResult(
            bootstrap_run_id=run_id,
            status=_bootstrap_status(summaries),
            created_at=datetime.now(UTC),
            raw_root=self.settings.data_raw_path.resolve(),
            processed_root=self.settings.data_processed_path.resolve(),
            asset_summaries=summaries,
            preflight_result=preflight,
            missing_data_actions=missing_actions,
            research_only_warnings=[BOOTSTRAP_RESEARCH_WARNING],
            limitations=limitations,
        )
        self.report_store.write_bootstrap_run(result)
        await self._close_owned_clients()
        return result

    async def _bootstrap_binance_symbol(
        self,
        *,
        symbol: str,
        timeframe: str,
        request: DataSourceBootstrapRequest,
    ) -> DataSourceBootstrapAssetSummary:
        artifacts: list[DataSourceBootstrapArtifact] = []
        warnings: list[str] = []
        limitations = [
            "Binance public endpoints only; no private account or order endpoints are used.",
            BINANCE_LIMITED_DERIVATIVES_NOTE,
        ]
        try:
            frames = await self._download_binance_frames(symbol, timeframe, request)
            if frames.ohlcv.is_empty():
                return _blocked_summary(
                    provider_type=DataSourceProviderType.BINANCE_PUBLIC,
                    symbol=symbol,
                    timeframe=timeframe,
                    warning=f"No public Binance OHLCV rows returned for {symbol} {timeframe}.",
                    limitations=limitations,
                )

            artifacts.append(
                _write_raw_artifact(
                    frame=frames.ohlcv,
                    raw_root=self.settings.data_raw_path,
                    provider=DataSourceBootstrapProvider.BINANCE_PUBLIC,
                    provider_type=DataSourceProviderType.BINANCE_PUBLIC,
                    symbol=symbol,
                    timeframe=timeframe,
                    data_type="ohlcv",
                    limitations=[],
                )
            )
            if frames.open_interest is not None and not frames.open_interest.is_empty():
                artifacts.append(
                    _write_raw_artifact(
                        frame=frames.open_interest,
                        raw_root=self.settings.data_raw_path,
                        provider=DataSourceBootstrapProvider.BINANCE_PUBLIC,
                        provider_type=DataSourceProviderType.BINANCE_PUBLIC,
                        symbol=symbol,
                        timeframe=timeframe,
                        data_type="open_interest",
                        limitations=binance_derivative_limitations(
                            data_type="open_interest",
                            row_count=frames.open_interest.height,
                            start_timestamp=_first_timestamp(frames.open_interest),
                            end_timestamp=_last_timestamp(frames.open_interest),
                            requested_days=request.days,
                        ),
                    )
                )
            elif request.include_binance_open_interest:
                warnings.append("Binance public open interest returned no rows.")

            if frames.funding_rate is not None and not frames.funding_rate.is_empty():
                artifacts.append(
                    _write_raw_artifact(
                        frame=frames.funding_rate,
                        raw_root=self.settings.data_raw_path,
                        provider=DataSourceBootstrapProvider.BINANCE_PUBLIC,
                        provider_type=DataSourceProviderType.BINANCE_PUBLIC,
                        symbol=symbol,
                        timeframe=timeframe,
                        data_type="funding_rate",
                        limitations=binance_derivative_limitations(
                            data_type="funding_rate",
                            row_count=frames.funding_rate.height,
                            start_timestamp=_first_timestamp(frames.funding_rate),
                            end_timestamp=_last_timestamp(frames.funding_rate),
                            requested_days=request.days,
                        ),
                    )
                )
            elif request.include_binance_funding:
                warnings.append("Binance public funding returned no rows.")

            features = _compute_processed_features(
                frames.ohlcv,
                open_interest=frames.open_interest,
                funding_rate=frames.funding_rate,
            )
            processed_path = _write_processed_features(
                features,
                processed_root=self.settings.data_processed_path,
                symbol=symbol,
                timeframe=timeframe,
            )
            return DataSourceBootstrapAssetSummary(
                provider_type=DataSourceProviderType.BINANCE_PUBLIC,
                symbol=symbol,
                timeframe=timeframe,
                status=FirstEvidenceRunStatus.COMPLETED,
                raw_artifacts=artifacts,
                processed_feature_path=processed_path,
                row_count=features.height,
                start_timestamp=_first_timestamp(features),
                end_timestamp=_last_timestamp(features),
                warnings=warnings,
                limitations=limitations,
            )
        except Exception as exc:
            return _blocked_summary(
                provider_type=DataSourceProviderType.BINANCE_PUBLIC,
                symbol=symbol,
                timeframe=timeframe,
                warning=f"Public Binance bootstrap failed for {symbol} {timeframe}: {exc}",
                limitations=limitations,
            )

    async def _download_binance_frames(
        self,
        symbol: str,
        timeframe: str,
        request: DataSourceBootstrapRequest,
    ) -> _DownloadedFrames:
        ohlcv = await self.binance_client.download_ohlcv(
            symbol=symbol,
            interval=timeframe,
            days=request.days,
        )
        open_interest = None
        if request.include_binance_open_interest:
            open_interest = await self.binance_client.download_open_interest(
                symbol=symbol,
                period=timeframe,
                days=request.days,
            )
        funding_rate = None
        if request.include_binance_funding:
            funding_rate = await self.binance_client.download_funding_rate(
                symbol=symbol,
                days=request.days,
            )
        return _DownloadedFrames(
            ohlcv=ohlcv,
            open_interest=open_interest,
            funding_rate=funding_rate,
        )

    async def _bootstrap_yahoo_symbol(
        self,
        *,
        symbol: str,
        timeframe: str,
        request: DataSourceBootstrapRequest,
    ) -> DataSourceBootstrapAssetSummary:
        limitations = [YAHOO_OHLCV_ONLY_LIMITATION]
        if symbol.upper() in {"GC=F", "GLD"}:
            limitations.append(
                "GC=F and GLD are OHLCV proxies only, not gold options OI, "
                "futures OI, IV, or XAUUSD execution sources."
            )
        try:
            ohlcv = await self.yahoo_client.download_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                days=request.days,
            )
            if ohlcv.is_empty():
                return _blocked_summary(
                    provider_type=DataSourceProviderType.YAHOO_FINANCE,
                    symbol=symbol,
                    timeframe=timeframe,
                    warning=f"No Yahoo Finance OHLCV rows returned for {symbol} {timeframe}.",
                    limitations=limitations,
                    unsupported_capabilities=YAHOO_UNSUPPORTED_CAPABILITIES,
                )
            artifact = _write_raw_artifact(
                frame=ohlcv,
                raw_root=self.settings.data_raw_path,
                provider=DataSourceBootstrapProvider.YAHOO_FINANCE,
                provider_type=DataSourceProviderType.YAHOO_FINANCE,
                symbol=symbol,
                timeframe=timeframe,
                data_type="ohlcv",
                limitations=limitations,
            )
            features = _compute_processed_features(ohlcv)
            processed_path = _write_processed_features(
                features,
                processed_root=self.settings.data_processed_path,
                symbol=symbol,
                timeframe=timeframe,
            )
            return DataSourceBootstrapAssetSummary(
                provider_type=DataSourceProviderType.YAHOO_FINANCE,
                symbol=symbol,
                timeframe=timeframe,
                status=FirstEvidenceRunStatus.COMPLETED,
                raw_artifacts=[artifact],
                processed_feature_path=processed_path,
                row_count=features.height,
                start_timestamp=_first_timestamp(features),
                end_timestamp=_last_timestamp(features),
                unsupported_capabilities=YAHOO_UNSUPPORTED_CAPABILITIES,
                limitations=limitations,
            )
        except Exception as exc:
            return _blocked_summary(
                provider_type=DataSourceProviderType.YAHOO_FINANCE,
                symbol=symbol,
                timeframe=timeframe,
                warning=f"Yahoo Finance OHLCV bootstrap failed for {symbol} {timeframe}: {exc}",
                limitations=limitations,
                unsupported_capabilities=YAHOO_UNSUPPORTED_CAPABILITIES,
            )

    async def _close_owned_clients(self) -> None:
        close = getattr(self.binance_client, "close", None)
        if close is not None:
            await close()


def build_public_bootstrap_plan(
    request: DataSourceBootstrapRequest,
) -> list[DataSourceBootstrapPlanItem]:
    plan: list[DataSourceBootstrapPlanItem] = []
    if request.include_binance:
        data_types = ["ohlcv"]
        if request.include_binance_open_interest:
            data_types.append("open_interest")
        if request.include_binance_funding:
            data_types.append("funding_rate")
        for symbol in [*request.binance_symbols, *request.optional_binance_symbols]:
            for timeframe in request.binance_timeframes:
                plan.append(
                    DataSourceBootstrapPlanItem(
                        provider=DataSourceBootstrapProvider.BINANCE_PUBLIC,
                        symbol=symbol,
                        timeframe=timeframe,
                        data_types=data_types,
                        limitations=[
                            "Public Binance market and derivatives endpoints only.",
                            BINANCE_LIMITED_DERIVATIVES_NOTE,
                        ],
                    )
                )
    if request.include_yahoo:
        for symbol in request.yahoo_symbols:
            for timeframe in request.yahoo_timeframes:
                plan.append(
                    DataSourceBootstrapPlanItem(
                        provider=DataSourceBootstrapProvider.YAHOO_FINANCE,
                        symbol=symbol,
                        timeframe=timeframe,
                        data_types=["ohlcv"],
                        unsupported_capabilities=YAHOO_UNSUPPORTED_CAPABILITIES,
                        limitations=[YAHOO_OHLCV_ONLY_LIMITATION],
                    )
                )
    return plan


def binance_request_windows(
    start: datetime,
    end: datetime,
    *,
    timeframe: str,
    limit: int,
) -> list[tuple[int, int]]:
    if start >= end:
        return []
    interval_ms = INTERVAL_MS[timeframe]
    span_ms = interval_ms * limit
    end_ms = _to_epoch_ms(end)
    current_start = _to_epoch_ms(start)
    windows: list[tuple[int, int]] = []
    while current_start < end_ms:
        current_end = min(current_start + span_ms, end_ms)
        windows.append((current_start, current_end))
        current_start = current_end + 1
    return windows


def binance_derivative_limitations(
    *,
    data_type: str,
    row_count: int,
    start_timestamp: datetime | None,
    end_timestamp: datetime | None,
    requested_days: int,
) -> list[str]:
    limitations = [BINANCE_LIMITED_DERIVATIVES_NOTE]
    if row_count == 0:
        limitations.append(f"Binance public {data_type} returned no rows.")
    if start_timestamp is None or end_timestamp is None:
        limitations.append(f"Binance public {data_type} date range is unavailable.")
        return limitations
    covered_days = max((end_timestamp - start_timestamp).total_seconds() / 86400, 0)
    if covered_days < max(requested_days * 0.5, 1):
        limitations.append(
            f"Binance public {data_type} history is shallow for the requested window."
        )
    return limitations


def provider_raw_path(
    *,
    raw_root: Path,
    provider: DataSourceBootstrapProvider,
    symbol: str,
    timeframe: str,
    data_type: str,
) -> Path:
    provider_folder = (
        "binance" if provider == DataSourceBootstrapProvider.BINANCE_PUBLIC else "yahoo"
    )
    filename = (
        f"{_safe_filename_part(symbol)}_{_safe_filename_part(timeframe)}_"
        f"{_safe_filename_part(data_type)}.parquet"
    )
    path = (raw_root.resolve() / provider_folder / filename).resolve()
    if raw_root.resolve() not in path.parents:
        raise ValueError("unsafe raw output path")
    return path


def _write_raw_artifact(
    *,
    frame: pl.DataFrame,
    raw_root: Path,
    provider: DataSourceBootstrapProvider,
    provider_type: DataSourceProviderType,
    symbol: str,
    timeframe: str,
    data_type: str,
    limitations: list[str],
) -> DataSourceBootstrapArtifact:
    path = provider_raw_path(
        raw_root=raw_root,
        provider=provider,
        symbol=symbol,
        timeframe=timeframe,
        data_type=data_type,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)
    return DataSourceBootstrapArtifact(
        provider_type=provider_type,
        data_type=data_type,
        path=path,
        row_count=frame.height,
        start_timestamp=_first_timestamp(frame),
        end_timestamp=_last_timestamp(frame),
        limitations=limitations,
    )


def _write_processed_features(
    frame: pl.DataFrame,
    *,
    processed_root: Path,
    symbol: str,
    timeframe: str,
) -> Path:
    path = (
        processed_root.resolve()
        / f"{_safe_filename_part(symbol)}_{_safe_filename_part(timeframe)}_features.parquet"
    ).resolve()
    if processed_root.resolve() not in path.parents:
        raise ValueError("unsafe processed output path")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)
    return path


def _compute_processed_features(
    ohlcv: pl.DataFrame,
    *,
    open_interest: pl.DataFrame | None = None,
    funding_rate: pl.DataFrame | None = None,
) -> pl.DataFrame:
    engine = FeatureEngine()
    merged = engine.merge_data(ohlcv, open_interest, funding_rate)
    features = engine.compute_atr(merged, period=engine.settings.atr_period)
    features = engine.compute_range_levels(features, period=engine.settings.range_period)
    features = engine.compute_volume_ratio(features, period=engine.settings.volume_ratio_period)
    if engine._has_non_null_values(features, "open_interest"):
        features = engine.compute_oi_change(features)
    if engine._has_non_null_values(features, "funding_rate"):
        features = engine.compute_funding_features(features)
    return engine._drop_required_feature_nulls(features)


def _preflight_request_from_bootstrap(
    request: DataSourceBootstrapRequest,
    summaries: list[DataSourceBootstrapAssetSummary],
) -> DataSourcePreflightRequest:
    crypto_assets = [
        summary.symbol
        for summary in summaries
        if summary.provider_type == DataSourceProviderType.BINANCE_PUBLIC
        and summary.status == FirstEvidenceRunStatus.COMPLETED
    ]
    proxy_assets = [
        summary.symbol
        for summary in summaries
        if summary.provider_type == DataSourceProviderType.YAHOO_FINANCE
        and summary.status == FirstEvidenceRunStatus.COMPLETED
    ]
    requested_capabilities = ["ohlcv"]
    if request.include_binance_open_interest:
        requested_capabilities.append("open_interest")
    if request.include_binance_funding:
        requested_capabilities.append("funding")
    return DataSourcePreflightRequest(
        crypto_assets=_dedupe_strings(crypto_assets),
        crypto_timeframe=request.binance_timeframes[0] if request.binance_timeframes else "15m",
        proxy_assets=_dedupe_strings(proxy_assets),
        proxy_timeframe=request.yahoo_timeframes[0] if request.yahoo_timeframes else "1d",
        requested_capabilities=requested_capabilities,
        research_only_acknowledged=True,
    )


def _bootstrap_status(
    summaries: list[DataSourceBootstrapAssetSummary],
) -> FirstEvidenceRunStatus:
    if not summaries:
        return FirstEvidenceRunStatus.BLOCKED
    completed = [
        summary for summary in summaries if summary.status == FirstEvidenceRunStatus.COMPLETED
    ]
    if len(completed) == len(summaries):
        return FirstEvidenceRunStatus.COMPLETED
    if completed:
        return FirstEvidenceRunStatus.PARTIAL
    return FirstEvidenceRunStatus.BLOCKED


def _blocked_summary(
    *,
    provider_type: DataSourceProviderType,
    symbol: str,
    timeframe: str,
    warning: str,
    limitations: list[str],
    unsupported_capabilities: list[str] | None = None,
) -> DataSourceBootstrapAssetSummary:
    return DataSourceBootstrapAssetSummary(
        provider_type=provider_type,
        symbol=symbol,
        timeframe=timeframe,
        status=FirstEvidenceRunStatus.BLOCKED,
        unsupported_capabilities=unsupported_capabilities or [],
        warnings=[warning],
        limitations=limitations,
    )


def _first_timestamp(frame: pl.DataFrame) -> datetime | None:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return None
    return frame["timestamp"].min()


def _last_timestamp(frame: pl.DataFrame) -> datetime | None:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return None
    return frame["timestamp"].max()


def _to_epoch_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def _safe_filename_part(value: str) -> str:
    raw = value.strip()
    if not raw or "/" in raw or "\\" in raw or ".." in Path(raw).parts:
        raise ValueError(f"unsafe filename value: {value}")
    normalized = re.sub(r"[^a-z0-9._=-]+", "_", raw.lower()).strip("_")
    if not normalized or normalized in {".", ".."}:
        raise ValueError(f"unsafe filename value: {value}")
    return normalized


def _bootstrap_run_id() -> str:
    return "bootstrap_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")


def _dedupe_actions(
    actions: Iterable[DataSourceMissingDataAction],
) -> list[DataSourceMissingDataAction]:
    seen: set[str] = set()
    deduped: list[DataSourceMissingDataAction] = []
    for action in actions:
        if action.action_id in seen:
            continue
        seen.add(action.action_id)
        deduped.append(action)
    return deduped


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
