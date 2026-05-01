"""Processed-feature and capability preflight for multi-asset research."""

import re
from pathlib import Path
from typing import Any

import polars as pl

from src.config import get_settings
from src.models.research import (
    ResearchAssetClass,
    ResearchAssetConfig,
    ResearchCapabilitySnapshot,
    ResearchFeatureGroup,
    ResearchPreflightResult,
    ResearchPreflightStatus,
)
from src.providers.errors import ProviderNotFoundError
from src.providers.registry import create_default_provider_registry


class ResearchPreflightNotImplementedError(NotImplementedError):
    """Raised until story implementation adds concrete preflight behavior."""


REQUIRED_COLUMNS_BY_GROUP: dict[ResearchFeatureGroup, set[str]] = {
    ResearchFeatureGroup.OHLCV: {"timestamp", "open", "high", "low", "close", "volume"},
    ResearchFeatureGroup.REGIME: {"regime", "range_high", "range_low", "range_mid", "atr"},
    ResearchFeatureGroup.OPEN_INTEREST: {"open_interest", "oi_change_pct"},
    ResearchFeatureGroup.FUNDING: {"funding_rate"},
    ResearchFeatureGroup.VOLUME_CONFIRMATION: {"volume_ratio"},
}


def preflight_research_asset(asset: ResearchAssetConfig) -> ResearchPreflightResult:
    """Preflight one research asset without substituting synthetic data."""
    feature_path = resolve_processed_feature_path(asset)
    capability = _base_capability_snapshot(asset)

    if not feature_path.exists():
        return ResearchPreflightResult(
            symbol=asset.symbol,
            provider=asset.provider,
            status=ResearchPreflightStatus.MISSING_DATA,
            feature_path=feature_path.as_posix(),
            capability_snapshot=capability,
            instructions=missing_data_instructions(asset, feature_path),
            warnings=capability.limitation_notes,
        )

    try:
        frame = pl.read_parquet(feature_path)
    except Exception as exc:  # pragma: no cover - concrete error type varies by backend
        return ResearchPreflightResult(
            symbol=asset.symbol,
            provider=asset.provider,
            status=ResearchPreflightStatus.INCOMPLETE_FEATURES,
            feature_path=feature_path.as_posix(),
            capability_snapshot=capability,
            instructions=[
                f"Processed feature file exists but could not be read: {feature_path.as_posix()}",
                f"Reprocess {asset.symbol} {asset.timeframe} features before research.",
            ],
            warnings=[f"Processed feature file could not be read: {exc}"],
        )

    capability = _capability_from_columns(asset, frame.columns)
    unsupported_groups = _unsupported_requested_groups(asset, capability)
    if unsupported_groups:
        requested = ", ".join(group.value for group in unsupported_groups)
        return ResearchPreflightResult(
            symbol=asset.symbol,
            provider=asset.provider,
            status=ResearchPreflightStatus.UNSUPPORTED_CAPABILITY,
            feature_path=feature_path.as_posix(),
            row_count=frame.height,
            first_timestamp=_first_timestamp(frame),
            last_timestamp=_last_timestamp(frame),
            capability_snapshot=capability,
            missing_columns=sorted(_columns_for_groups(unsupported_groups) - set(frame.columns)),
            instructions=[
                (
                    f"Requested {requested} research is unsupported for provider "
                    f"{asset.provider} asset {asset.symbol}."
                ),
                (
                    "Use OHLCV/regime-only research requirements for this source or "
                    "choose a provider with validated OI/funding data."
                ),
            ],
            warnings=[
                *capability.limitation_notes,
                f"Unsupported requested capability groups: {requested}",
            ],
        )

    missing_columns = sorted(_required_columns(asset.required_feature_groups) - set(frame.columns))
    if frame.is_empty():
        missing_columns.append("<non-empty rows>")

    if missing_columns:
        return ResearchPreflightResult(
            symbol=asset.symbol,
            provider=asset.provider,
            status=ResearchPreflightStatus.INCOMPLETE_FEATURES,
            feature_path=feature_path.as_posix(),
            row_count=frame.height,
            first_timestamp=_first_timestamp(frame),
            last_timestamp=_last_timestamp(frame),
            capability_snapshot=capability,
            missing_columns=missing_columns,
            instructions=[
                f"Reprocess {asset.symbol} {asset.timeframe} features with the required columns.",
                f"Missing columns: {', '.join(missing_columns)}",
            ],
            warnings=capability.limitation_notes,
        )

    return ResearchPreflightResult(
        symbol=asset.symbol,
        provider=asset.provider,
        status=ResearchPreflightStatus.READY,
        feature_path=feature_path.as_posix(),
        row_count=frame.height,
        first_timestamp=_first_timestamp(frame),
        last_timestamp=_last_timestamp(frame),
        capability_snapshot=capability,
        warnings=capability.limitation_notes,
    )


def preflight_research_assets(
    assets: list[ResearchAssetConfig],
) -> list[ResearchPreflightResult]:
    return [preflight_research_asset(asset) for asset in assets if asset.enabled]


def resolve_processed_feature_path(asset: ResearchAssetConfig) -> Path:
    settings = get_settings()
    settings.data_processed_path.mkdir(parents=True, exist_ok=True)
    processed_root = settings.data_processed_path.resolve()
    if asset.feature_path is not None:
        path = Path(asset.feature_path)
    else:
        path = settings.data_processed_path / (
            f"{_safe_filename_part(asset.symbol)}_{_safe_filename_part(asset.timeframe)}"
            "_features.parquet"
        )
    resolved = path.resolve()
    if processed_root != resolved and processed_root not in resolved.parents:
        raise ValueError(
            "processed feature path must stay inside the configured data/processed directory"
        )
    return resolved


def missing_data_instructions(asset: ResearchAssetConfig, feature_path: Path) -> list[str]:
    return [
        (
            f"Download {asset.symbol} {asset.timeframe} data for provider {asset.provider} "
            "using POST /api/v1/data/download."
        ),
        (
            f"Run feature processing for {asset.symbol} {asset.timeframe} using "
            "POST /api/v1/process before starting multi-asset research."
        ),
        f"Expected processed feature file: {feature_path.as_posix()}",
    ]


def _safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._=-]+", "_", value.lower()).strip("_")
    if not normalized:
        raise ValueError("processed feature filename part cannot be empty")
    return normalized


def _required_columns(groups: list[ResearchFeatureGroup]) -> set[str]:
    return _columns_for_groups(groups)


def _columns_for_groups(groups: list[ResearchFeatureGroup]) -> set[str]:
    required: set[str] = set()
    for group in groups:
        required.update(REQUIRED_COLUMNS_BY_GROUP[group])
    return required


def _base_capability_snapshot(asset: ResearchAssetConfig) -> ResearchCapabilitySnapshot:
    normalized = asset.provider.lower()
    try:
        provider_info = create_default_provider_registry().get_provider_info(normalized)
        notes = list(provider_info.limitations)
        supports_ohlcv = provider_info.supports_ohlcv
        supports_open_interest = provider_info.supports_open_interest
        supports_funding_rate = provider_info.supports_funding_rate
    except ProviderNotFoundError:
        notes = ["Unknown provider; capabilities are inferred only from processed columns."]
        supports_ohlcv = True
        supports_open_interest = False
        supports_funding_rate = False

    if normalized == "yahoo_finance":
        notes.append("Yahoo Finance assets are OHLCV-only in v0; OI and funding are not supported.")
    if normalized == "local_file":
        notes.append("Local-file capabilities depend on validated processed feature columns.")
    notes.extend(_asset_limitation_notes(asset))

    return ResearchCapabilitySnapshot(
        provider=normalized,
        supports_ohlcv=supports_ohlcv,
        supports_open_interest=supports_open_interest,
        supports_funding_rate=supports_funding_rate,
        limitation_notes=_dedupe_notes(notes),
    )


def _capability_from_columns(
    asset: ResearchAssetConfig,
    columns: list[str],
) -> ResearchCapabilitySnapshot:
    base = _base_capability_snapshot(asset)
    column_set = set(columns)
    detected_open_interest = REQUIRED_COLUMNS_BY_GROUP[ResearchFeatureGroup.OPEN_INTEREST].issubset(
        column_set
    )
    detected_funding_rate = REQUIRED_COLUMNS_BY_GROUP[ResearchFeatureGroup.FUNDING].issubset(
        column_set
    )
    supports_open_interest = base.supports_open_interest
    supports_funding_rate = base.supports_funding_rate
    if asset.provider == "local_file":
        supports_open_interest = detected_open_interest
        supports_funding_rate = detected_funding_rate

    return base.model_copy(
        update={
            "detected_ohlcv": REQUIRED_COLUMNS_BY_GROUP[ResearchFeatureGroup.OHLCV].issubset(
                column_set
            ),
            "detected_regime": REQUIRED_COLUMNS_BY_GROUP[ResearchFeatureGroup.REGIME].issubset(
                column_set
            ),
            "supports_open_interest": supports_open_interest,
            "supports_funding_rate": supports_funding_rate,
            "detected_open_interest": detected_open_interest,
            "detected_funding_rate": detected_funding_rate,
        }
    )


def _unsupported_requested_groups(
    asset: ResearchAssetConfig,
    capability: ResearchCapabilitySnapshot,
) -> list[ResearchFeatureGroup]:
    unsupported: list[ResearchFeatureGroup] = []
    requested = set(asset.required_feature_groups)
    if ResearchFeatureGroup.OPEN_INTEREST in requested and not capability.supports_open_interest:
        unsupported.append(ResearchFeatureGroup.OPEN_INTEREST)
    if ResearchFeatureGroup.FUNDING in requested and not capability.supports_funding_rate:
        unsupported.append(ResearchFeatureGroup.FUNDING)
    return unsupported


def _asset_limitation_notes(asset: ResearchAssetConfig) -> list[str]:
    symbol = asset.symbol.upper()
    if asset.asset_class == ResearchAssetClass.GOLD_PROXY or symbol in {"GC=F", "GLD"}:
        return [
            (
                "Gold proxy assets are OHLCV proxies only in v0; they do not provide "
                "CME gold options OI, futures OI, or XAU/USD spot execution data."
            )
        ]
    return []


def _dedupe_notes(notes: list[str]) -> list[str]:
    deduped: list[str] = []
    for note in notes:
        if note and note not in deduped:
            deduped.append(note)
    return deduped


def _first_timestamp(frame: pl.DataFrame) -> Any:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return None
    sorted_frame = frame.sort("timestamp")
    return sorted_frame["timestamp"][0]


def _last_timestamp(frame: pl.DataFrame) -> Any:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return None
    sorted_frame = frame.sort("timestamp")
    return sorted_frame["timestamp"][-1]
