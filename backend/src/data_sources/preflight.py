"""Local-only data-source preflight checks for the first evidence workflow."""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import polars as pl

from src.config import get_settings
from src.data_sources.capabilities import (
    FORBIDDEN_CAPABILITIES,
    unsupported_capabilities_for_provider,
)
from src.data_sources.missing_data import (
    crypto_processed_features_action,
    proxy_ohlcv_action,
    xau_options_oi_schema_action,
)
from src.data_sources.readiness import (
    OPTIONAL_PROVIDER_ENV_VARS,
    data_source_readiness,
    provider_statuses,
)
from src.models.data_sources import (
    DataSourceMissingDataAction,
    DataSourcePreflightAssetResult,
    DataSourcePreflightRequest,
    DataSourcePreflightResult,
    DataSourceProviderStatus,
    DataSourceProviderType,
    DataSourceReadinessStatus,
    FirstEvidenceRunStatus,
)
from src.xau.imports import validate_options_oi_file

REQUIRED_COLUMNS_BY_CAPABILITY: dict[str, set[str]] = {
    "ohlcv": {"timestamp", "open", "high", "low", "close", "volume"},
    "open_interest": {"open_interest", "oi_change_pct"},
    "funding": {"funding_rate"},
    "volume_confirmation": {"volume_ratio"},
    "regime": {"regime", "range_high", "range_low", "range_mid", "atr"},
}

CRYPTO_LIMITATION = (
    "Binance public data is suitable for v0 research preflight, but official historical "
    "OI can be limited; deeper OI history may require vendor data."
)
PROXY_LIMITATION = (
    "Yahoo Finance proxy assets are OHLCV-only; OI, funding, gold options OI, futures "
    "OI, IV, and XAUUSD execution data are unsupported."
)
GOLD_PROXY_LIMITATION = (
    "GC=F and GLD are gold OHLCV proxies only, not CME gold options OI, futures OI, "
    "IV, or XAUUSD spot execution sources."
)
XAU_LIMITATION = (
    "XAU Vol-OI preflight requires a local gold options OI CSV or Parquet import; "
    "Yahoo GC=F and GLD are OHLCV proxies only."
)
PREFLIGHT_RESEARCH_WARNING = (
    "Data-source preflight is research-only and does not run external downloads, "
    "paper trading, live trading, broker integration, or order execution."
)
SYNTHETIC_DATA_LIMITATION = (
    "Synthetic data is allowed only in automated tests and smoke validation, not final "
    "real research evidence runs."
)


class DataSourcePreflightService:
    """Run local filesystem and configuration readiness checks only."""

    def preview(
        self,
        request: DataSourcePreflightRequest,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> DataSourcePreflightResult:
        return self.run(request, environ=environ)

    def run(
        self,
        request: DataSourcePreflightRequest,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> DataSourcePreflightResult:
        readiness = data_source_readiness(environ=environ)
        crypto_results = [
            _preflight_processed_asset(
                symbol=symbol,
                timeframe=request.crypto_timeframe,
                provider_type=DataSourceProviderType.BINANCE_PUBLIC,
                processed_feature_root=request.processed_feature_root,
                required_capabilities=_crypto_required_capabilities(
                    request.requested_capabilities
                ),
                missing_action=crypto_processed_features_action(symbol, request.crypto_timeframe),
                limitations=[CRYPTO_LIMITATION],
            )
            for symbol in [*request.crypto_assets, *request.optional_crypto_assets]
        ]
        proxy_results = [
            _preflight_proxy_asset(
                symbol=symbol,
                timeframe=request.proxy_timeframe,
                processed_feature_root=request.processed_feature_root,
                requested_capabilities=request.requested_capabilities,
            )
            for symbol in request.proxy_assets
        ]
        xau_result = _preflight_xau_options_file(request.xau_options_oi_file_path)
        optional_vendor_results = _optional_vendor_results(request, environ=environ)
        missing_actions = _dedupe_actions(
            [
                action
                for result in [*crypto_results, *proxy_results, xau_result]
                for action in result.missing_data_actions
            ]
            + [
                action
                for status in optional_vendor_results
                for action in status.missing_actions
            ]
        )
        unsupported = _dedupe_strings(
            [
                capability
                for result in proxy_results
                for capability in result.unsupported_capabilities
            ]
            + _forbidden_requested_capabilities(request.requested_capabilities)
        )
        warnings = [PREFLIGHT_RESEARCH_WARNING]
        if unsupported:
            warnings.append(
                "Unsupported requested capabilities were labeled: "
                + ", ".join(unsupported)
            )

        return DataSourcePreflightResult(
            status=_preflight_status([*crypto_results, *proxy_results, xau_result]),
            readiness=readiness,
            crypto_results=crypto_results,
            proxy_results=proxy_results,
            xau_result=xau_result,
            optional_vendor_results=optional_vendor_results,
            unsupported_capabilities=unsupported,
            missing_data_actions=missing_actions,
            warnings=warnings,
            limitations=[SYNTHETIC_DATA_LIMITATION],
        )


def run_data_source_preflight(
    request: DataSourcePreflightRequest,
    *,
    environ: Mapping[str, str] | None = None,
) -> DataSourcePreflightResult:
    return DataSourcePreflightService().run(request, environ=environ)


def resolve_processed_feature_path(
    symbol: str,
    timeframe: str,
    processed_feature_root: Path | None = None,
) -> Path:
    settings = get_settings()
    allowed_root = settings.data_processed_path.resolve()
    root = (processed_feature_root or settings.data_processed_path).resolve()
    if root != allowed_root and allowed_root not in root.parents:
        raise ValueError("processed feature paths must stay inside data/processed")
    return root / f"{_safe_filename_part(symbol)}_{_safe_filename_part(timeframe)}_features.parquet"


def _preflight_proxy_asset(
    *,
    symbol: str,
    timeframe: str,
    processed_feature_root: Path | None,
    requested_capabilities: list[str],
) -> DataSourcePreflightAssetResult:
    unsupported = unsupported_capabilities_for_provider(
        DataSourceProviderType.YAHOO_FINANCE,
        requested_capabilities,
    )
    limitations = [PROXY_LIMITATION]
    if symbol.upper() in {"GC=F", "GLD"}:
        limitations.append(GOLD_PROXY_LIMITATION)
    result = _preflight_processed_asset(
        symbol=symbol,
        timeframe=timeframe,
        provider_type=DataSourceProviderType.YAHOO_FINANCE,
        processed_feature_root=processed_feature_root,
        required_capabilities=["ohlcv"],
        missing_action=proxy_ohlcv_action(symbol, timeframe),
        unsupported_capabilities=unsupported,
        limitations=limitations,
    )
    if unsupported:
        result.warnings.append(
            "Unsupported requested capabilities were labeled for Yahoo Finance: "
            + ", ".join(unsupported)
        )
    return result


def _preflight_processed_asset(
    *,
    symbol: str,
    timeframe: str,
    provider_type: DataSourceProviderType,
    processed_feature_root: Path | None,
    required_capabilities: list[str],
    missing_action: DataSourceMissingDataAction,
    unsupported_capabilities: list[str] | None = None,
    limitations: list[str] | None = None,
) -> DataSourcePreflightAssetResult:
    unsupported = unsupported_capabilities or []
    notes = limitations or []
    try:
        feature_path = resolve_processed_feature_path(symbol, timeframe, processed_feature_root)
    except ValueError as exc:
        return DataSourcePreflightAssetResult(
            asset=symbol,
            provider_type=provider_type,
            status=DataSourceReadinessStatus.BLOCKED,
            missing_data_actions=[
                missing_action.model_copy(
                    update={"instructions": [*missing_action.instructions, str(exc)]}
                )
            ],
            unsupported_capabilities=unsupported,
            limitations=notes,
        )

    if not feature_path.exists():
        return DataSourcePreflightAssetResult(
            asset=symbol,
            provider_type=provider_type,
            status=DataSourceReadinessStatus.BLOCKED,
            feature_path=feature_path.as_posix(),
            missing_data_actions=[missing_action],
            unsupported_capabilities=unsupported,
            limitations=notes,
        )

    try:
        frame = pl.read_parquet(feature_path)
    except Exception as exc:  # pragma: no cover - exact parquet errors vary by backend
        return DataSourcePreflightAssetResult(
            asset=symbol,
            provider_type=provider_type,
            status=DataSourceReadinessStatus.BLOCKED,
            feature_path=feature_path.as_posix(),
            missing_data_actions=[
                missing_action.model_copy(
                    update={
                        "instructions": [
                            f"Processed feature file could not be read: {feature_path.as_posix()}",
                            f"Reprocess {symbol} {timeframe} before evidence execution.",
                        ]
                    }
                )
            ],
            unsupported_capabilities=unsupported,
            warnings=[f"Processed feature file could not be read: {exc}"],
            limitations=notes,
        )

    missing_columns = _missing_processed_columns(frame.columns, required_capabilities)
    if frame.is_empty():
        missing_columns.append("<non-empty rows>")
    if missing_columns:
        return DataSourcePreflightAssetResult(
            asset=symbol,
            provider_type=provider_type,
            status=DataSourceReadinessStatus.BLOCKED,
            feature_path=feature_path.as_posix(),
            row_count=frame.height,
            missing_data_actions=[
                missing_action.model_copy(
                    update={
                        "instructions": [
                            *missing_action.instructions,
                            "Reprocess the feature file with the required columns.",
                            f"Missing columns: {', '.join(missing_columns)}",
                        ]
                    }
                )
            ],
            unsupported_capabilities=unsupported,
            limitations=notes,
        )

    return DataSourcePreflightAssetResult(
        asset=symbol,
        provider_type=provider_type,
        status=DataSourceReadinessStatus.READY,
        feature_path=feature_path.as_posix(),
        row_count=frame.height,
        unsupported_capabilities=unsupported,
        limitations=notes,
    )


def _preflight_xau_options_file(file_path: Path | None) -> DataSourcePreflightAssetResult:
    if file_path is None:
        action = xau_options_oi_schema_action()
        return DataSourcePreflightAssetResult(
            asset="XAU",
            provider_type=DataSourceProviderType.LOCAL_FILE,
            status=DataSourceReadinessStatus.BLOCKED,
            missing_data_actions=[action],
            limitations=[XAU_LIMITATION],
        )

    settings = get_settings()
    report = validate_options_oi_file(file_path, base_dir=settings.data_raw_path)
    if not report.is_valid:
        action = xau_options_oi_schema_action(file_path)
        return DataSourcePreflightAssetResult(
            asset="XAU",
            provider_type=DataSourceProviderType.LOCAL_FILE,
            status=DataSourceReadinessStatus.BLOCKED,
            feature_path=Path(file_path).as_posix(),
            missing_data_actions=[action],
            warnings=[*report.errors, *report.instructions],
            limitations=[XAU_LIMITATION],
        )

    return DataSourcePreflightAssetResult(
        asset="XAU",
        provider_type=DataSourceProviderType.LOCAL_FILE,
        status=DataSourceReadinessStatus.READY,
        feature_path=report.file_path,
        row_count=report.accepted_row_count,
        warnings=report.warnings,
        limitations=[
            "XAU options OI comes from a local CSV/Parquet import, not Yahoo Finance.",
            "Research annotations are not trading signals or live-readiness claims.",
        ],
    )


def _optional_vendor_results(
    request: DataSourcePreflightRequest,
    *,
    environ: Mapping[str, str] | None,
) -> list[DataSourceProviderStatus]:
    requested = set(request.require_optional_vendors) or set(OPTIONAL_PROVIDER_ENV_VARS)
    statuses = provider_statuses(environ=environ)
    return [status for status in statuses if status.provider_type in requested]


def _crypto_required_capabilities(requested_capabilities: Iterable[str]) -> list[str]:
    capabilities = ["ohlcv"]
    for requested in requested_capabilities:
        normalized = _normalize_capability(requested)
        if normalized in {"open_interest", "funding"} and normalized not in capabilities:
            capabilities.append(normalized)
    return capabilities


def _missing_processed_columns(
    columns: Iterable[str],
    required_capabilities: Iterable[str],
) -> list[str]:
    column_set = set(columns)
    required: set[str] = set()
    for capability in required_capabilities:
        required.update(
            REQUIRED_COLUMNS_BY_CAPABILITY.get(_normalize_capability(capability), set())
        )
    return sorted(required - column_set)


def _preflight_status(
    required_results: list[DataSourcePreflightAssetResult],
) -> FirstEvidenceRunStatus:
    blocked = [
        result
        for result in required_results
        if result.status == DataSourceReadinessStatus.BLOCKED
    ]
    ready = [
        result
        for result in required_results
        if result.status == DataSourceReadinessStatus.READY
    ]
    if blocked and ready:
        return FirstEvidenceRunStatus.PARTIAL
    if blocked:
        return FirstEvidenceRunStatus.BLOCKED
    return FirstEvidenceRunStatus.COMPLETED


def _forbidden_requested_capabilities(capabilities: Iterable[str]) -> list[str]:
    forbidden = {_normalize_capability(capability) for capability in FORBIDDEN_CAPABILITIES}
    return [
        normalized
        for capability in capabilities
        if (normalized := _normalize_capability(capability)) in forbidden
    ]


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


def _safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._=-]+", "_", value.lower()).strip("_")
    if not normalized:
        raise ValueError("processed feature filename part cannot be empty")
    return normalized


def _normalize_capability(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "oi": "open_interest",
        "crypto_oi": "open_interest",
        "funding_rate": "funding",
        "live": "live_trading",
        "execution": "real_order_execution",
        "private_key": "private_trading_keys",
    }
    compact = "".join(character for character in normalized if character.isalnum())
    return aliases.get(normalized) or aliases.get(compact) or normalized
