"""Preflight helpers for research execution workflows."""

import re
from collections.abc import Iterable
from pathlib import Path

import polars as pl

from src.config import get_settings
from src.models.research_execution import (
    CryptoResearchWorkflowConfig,
    ProxyResearchWorkflowConfig,
    ResearchExecutionPreflightResult,
    ResearchExecutionWorkflowStatus,
    ResearchExecutionWorkflowType,
    XauVolOiWorkflowConfig,
    normalize_capability,
)
from src.xau.imports import validate_options_oi_file

REQUIRED_COLUMNS_BY_CAPABILITY: dict[str, set[str]] = {
    "ohlcv": {"timestamp", "open", "high", "low", "close", "volume"},
    "regime": {"regime", "range_high", "range_low", "range_mid", "atr"},
    "open_interest": {"open_interest", "oi_change_pct"},
    "funding": {"funding_rate"},
    "volume_confirmation": {"volume_ratio"},
}

YAHOO_UNSUPPORTED_CAPABILITIES = {
    "open_interest",
    "funding",
    "iv",
    "gold_options_oi",
    "futures_oi",
    "xauusd_spot_execution",
}


def preflight_crypto_processed_features(
    config: CryptoResearchWorkflowConfig,
) -> list[ResearchExecutionPreflightResult]:
    """Check processed crypto feature readiness without downloading data."""

    return [
        _preflight_processed_asset(
            workflow_type=ResearchExecutionWorkflowType.CRYPTO_MULTI_ASSET,
            symbol=symbol,
            timeframe=config.timeframe,
            provider="binance",
            processed_feature_root=config.processed_feature_root,
            required_capabilities=config.required_capabilities,
        )
        for symbol in config.enabled_assets()
    ]


def preflight_proxy_ohlcv_assets(
    config: ProxyResearchWorkflowConfig,
) -> list[ResearchExecutionPreflightResult]:
    """Check processed OHLCV proxy readiness and label unsupported capabilities."""

    unsupported = _unsupported_proxy_capabilities(config.required_capabilities, config.provider)
    results = []
    for symbol in config.assets if config.enabled else []:
        result = _preflight_processed_asset(
            workflow_type=ResearchExecutionWorkflowType.PROXY_OHLCV,
            symbol=symbol,
            timeframe=config.timeframe,
            provider=config.provider,
            processed_feature_root=config.processed_feature_root,
            required_capabilities=[
                capability
                for capability in config.required_capabilities
                if capability not in unsupported
            ]
            or ["ohlcv"],
            unsupported_capabilities=unsupported,
            limitations=_proxy_limitations(symbol, config.provider),
        )
        results.append(result)
    return results


def preflight_xau_options_file(
    config: XauVolOiWorkflowConfig,
) -> ResearchExecutionPreflightResult:
    """Check local XAU options OI readiness without substituting data."""

    if not config.enabled:
        return ResearchExecutionPreflightResult(
            workflow_type=ResearchExecutionWorkflowType.XAU_VOL_OI,
            status=ResearchExecutionWorkflowStatus.SKIPPED,
            asset="XAU",
            source_identity="local_options_oi",
            ready=False,
            limitations=["XAU Vol-OI workflow is disabled."],
        )

    if config.options_oi_file_path is None:
        return _blocked_xau_result(
            None,
            ["XAU options OI file path is required to run the XAU Vol-OI workflow."],
        )

    settings = get_settings()
    report = validate_options_oi_file(
        config.options_oi_file_path,
        base_dir=settings.data_raw_path,
    )
    if not report.is_valid:
        return _blocked_xau_result(
            Path(config.options_oi_file_path),
            [*report.errors, *report.instructions],
        )

    return ResearchExecutionPreflightResult(
        workflow_type=ResearchExecutionWorkflowType.XAU_VOL_OI,
        status=ResearchExecutionWorkflowStatus.COMPLETED,
        asset="XAU",
        source_identity="local_options_oi",
        ready=True,
        feature_path=report.file_path,
        row_count=report.accepted_row_count,
        missing_data_actions=[],
        warnings=report.warnings,
        limitations=[
            "XAU options OI evidence comes from a local CSV/Parquet import, not Yahoo Finance.",
            "Research annotations are not buy/sell signals or live-readiness claims.",
        ],
    )


def crypto_missing_data_instructions(symbol: str, timeframe: str, feature_path: Path) -> list[str]:
    return [
        f"Download {symbol} {timeframe} public market data before research execution.",
        f"Run feature processing for {symbol} {timeframe} to create processed features.",
        f"Expected processed feature file: {feature_path.as_posix()}",
    ]


def proxy_missing_data_instructions(symbol: str, timeframe: str, feature_path: Path) -> list[str]:
    return [
        f"Download or import OHLCV data for {symbol} {timeframe} before research execution.",
        f"Run feature processing for {symbol} {timeframe} as an OHLCV-only proxy asset.",
        f"Expected processed feature file: {feature_path.as_posix()}",
    ]


def xau_missing_data_instructions(file_path: Path | None) -> list[str]:
    expected = file_path.as_posix() if file_path is not None else "data/raw/xau/options_oi.csv"
    return [
        "Provide a readable local CSV or Parquet gold options OI file.",
        ("Required columns: date or timestamp, expiry, strike, option_type, and open_interest."),
        f"Expected local options OI file: {expected}",
    ]


def _preflight_processed_asset(
    *,
    workflow_type: ResearchExecutionWorkflowType,
    symbol: str,
    timeframe: str,
    provider: str,
    processed_feature_root: Path | None,
    required_capabilities: list[str],
    unsupported_capabilities: list[str] | None = None,
    limitations: list[str] | None = None,
) -> ResearchExecutionPreflightResult:
    unsupported = unsupported_capabilities or []
    notes = limitations or []
    try:
        feature_path = resolve_processed_feature_path(symbol, timeframe, processed_feature_root)
    except ValueError as exc:
        return ResearchExecutionPreflightResult(
            workflow_type=workflow_type,
            status=ResearchExecutionWorkflowStatus.BLOCKED,
            asset=symbol,
            source_identity=provider,
            ready=False,
            missing_data_actions=[str(exc)],
            unsupported_capabilities=unsupported,
            limitations=notes,
        )

    if not feature_path.exists():
        instruction_factory = (
            proxy_missing_data_instructions
            if workflow_type == ResearchExecutionWorkflowType.PROXY_OHLCV
            else crypto_missing_data_instructions
        )
        return ResearchExecutionPreflightResult(
            workflow_type=workflow_type,
            status=ResearchExecutionWorkflowStatus.BLOCKED,
            asset=symbol,
            source_identity=provider,
            ready=False,
            feature_path=feature_path.as_posix(),
            missing_data_actions=instruction_factory(symbol, timeframe, feature_path),
            unsupported_capabilities=unsupported,
            warnings=_unsupported_warnings(unsupported),
            limitations=notes,
        )

    try:
        frame = pl.read_parquet(feature_path)
    except Exception as exc:  # pragma: no cover - exact parquet errors vary by backend
        return ResearchExecutionPreflightResult(
            workflow_type=workflow_type,
            status=ResearchExecutionWorkflowStatus.BLOCKED,
            asset=symbol,
            source_identity=provider,
            ready=False,
            feature_path=feature_path.as_posix(),
            missing_data_actions=[
                f"Processed feature file could not be read: {feature_path.as_posix()}",
                f"Reprocess {symbol} {timeframe} before research execution.",
            ],
            unsupported_capabilities=unsupported,
            warnings=[f"Processed feature file could not be read: {exc}"],
            limitations=notes,
        )

    missing_columns = _missing_columns(frame.columns, required_capabilities)
    if frame.is_empty():
        missing_columns.append("<non-empty rows>")

    if missing_columns:
        return ResearchExecutionPreflightResult(
            workflow_type=workflow_type,
            status=ResearchExecutionWorkflowStatus.BLOCKED,
            asset=symbol,
            source_identity=provider,
            ready=False,
            feature_path=feature_path.as_posix(),
            row_count=frame.height,
            date_start=_first_timestamp(frame),
            date_end=_last_timestamp(frame),
            missing_data_actions=[
                f"Reprocess {symbol} {timeframe} features with required columns.",
                f"Missing columns: {', '.join(missing_columns)}",
            ],
            unsupported_capabilities=unsupported,
            warnings=_unsupported_warnings(unsupported),
            limitations=notes,
        )

    return ResearchExecutionPreflightResult(
        workflow_type=workflow_type,
        status=ResearchExecutionWorkflowStatus.COMPLETED,
        asset=symbol,
        source_identity=provider,
        ready=True,
        feature_path=feature_path.as_posix(),
        row_count=frame.height,
        date_start=_first_timestamp(frame),
        date_end=_last_timestamp(frame),
        unsupported_capabilities=unsupported,
        warnings=_unsupported_warnings(unsupported),
        limitations=notes,
    )


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


def _missing_columns(columns: Iterable[str], capabilities: list[str]) -> list[str]:
    column_set = set(columns)
    required = set()
    for capability in capabilities:
        required.update(REQUIRED_COLUMNS_BY_CAPABILITY.get(normalize_capability(capability), set()))
    return sorted(required - column_set)


def _unsupported_proxy_capabilities(capabilities: list[str], provider: str) -> list[str]:
    if provider.strip().lower() not in {"yahoo_finance", "yahoo"}:
        return []
    unsupported: list[str] = []
    for capability in capabilities:
        normalized = normalize_capability(capability)
        if normalized in YAHOO_UNSUPPORTED_CAPABILITIES and normalized not in unsupported:
            unsupported.append(normalized)
    return unsupported


def _proxy_limitations(symbol: str, provider: str) -> list[str]:
    notes = []
    if provider.strip().lower() in {"yahoo_finance", "yahoo"}:
        notes.append(
            "Yahoo Finance proxy assets are OHLCV-only in this workflow; OI, funding, "
            "gold options OI, futures OI, IV, and XAUUSD spot execution data are unsupported."
        )
    if symbol.upper() in {"GC=F", "GLD"}:
        notes.append(
            "GC=F and GLD are gold OHLCV proxies only, not CME gold options OI, "
            "gold futures OI, IV, or XAUUSD spot execution sources."
        )
    return notes


def _unsupported_warnings(capabilities: list[str]) -> list[str]:
    if not capabilities:
        return []
    return [f"Unsupported requested capabilities were labeled: {', '.join(capabilities)}"]


def _blocked_xau_result(
    file_path: Path | None,
    additional_instructions: list[str],
) -> ResearchExecutionPreflightResult:
    return ResearchExecutionPreflightResult(
        workflow_type=ResearchExecutionWorkflowType.XAU_VOL_OI,
        status=ResearchExecutionWorkflowStatus.BLOCKED,
        asset="XAU",
        source_identity="local_options_oi",
        ready=False,
        feature_path=file_path.as_posix() if file_path is not None else None,
        missing_data_actions=[*additional_instructions, *xau_missing_data_instructions(file_path)],
        limitations=[
            "XAU Vol-OI requires a local gold options OI CSV or Parquet import.",
            "Yahoo GC=F and GLD are OHLCV proxies only and are not gold options OI sources.",
        ],
    )


def _safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._=-]+", "_", value.lower()).strip("_")
    if not normalized:
        raise ValueError("processed feature filename part cannot be empty")
    return normalized


def _first_timestamp(frame: pl.DataFrame):
    if frame.is_empty() or "timestamp" not in frame.columns:
        return None
    return frame.sort("timestamp")["timestamp"][0]


def _last_timestamp(frame: pl.DataFrame):
    if frame.is_empty() or "timestamp" not in frame.columns:
        return None
    return frame.sort("timestamp")["timestamp"][-1]
