"""Processed-feature and capability preflight for multi-asset research."""

import re
from pathlib import Path
from typing import Any

import polars as pl

from src.config import get_settings
from src.models.research import (
    ResearchAssetConfig,
    ResearchCapabilitySnapshot,
    ResearchFeatureGroup,
    ResearchPreflightResult,
    ResearchPreflightStatus,
)


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
    capability = _base_capability_snapshot(asset.provider)

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

    capability = _capability_from_columns(asset.provider, frame.columns)
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
    required: set[str] = set()
    for group in groups:
        required.update(REQUIRED_COLUMNS_BY_GROUP[group])
    return required


def _base_capability_snapshot(provider: str) -> ResearchCapabilitySnapshot:
    normalized = provider.lower()
    if normalized == "binance":
        return ResearchCapabilitySnapshot(
            provider=normalized,
            supports_ohlcv=True,
            supports_open_interest=True,
            supports_funding_rate=True,
            limitation_notes=[
                "Binance public futures data is acceptable for v0 research but limited "
                "for serious multi-year OI/funding analysis."
            ],
        )
    if normalized == "yahoo_finance":
        return ResearchCapabilitySnapshot(
            provider=normalized,
            supports_ohlcv=True,
            supports_open_interest=False,
            supports_funding_rate=False,
            limitation_notes=[
                "Yahoo Finance assets are OHLCV-only in v0; OI and funding are not supported."
            ],
        )
    return ResearchCapabilitySnapshot(
        provider=normalized,
        supports_ohlcv=True,
        supports_open_interest=False,
        supports_funding_rate=False,
        limitation_notes=["Local-file capabilities depend on validated processed feature columns."],
    )


def _capability_from_columns(provider: str, columns: list[str]) -> ResearchCapabilitySnapshot:
    base = _base_capability_snapshot(provider)
    column_set = set(columns)
    return base.model_copy(
        update={
            "detected_ohlcv": REQUIRED_COLUMNS_BY_GROUP[ResearchFeatureGroup.OHLCV].issubset(
                column_set
            ),
            "detected_regime": REQUIRED_COLUMNS_BY_GROUP[ResearchFeatureGroup.REGIME].issubset(
                column_set
            ),
            "detected_open_interest": REQUIRED_COLUMNS_BY_GROUP[
                ResearchFeatureGroup.OPEN_INTEREST
            ].issubset(column_set),
            "detected_funding_rate": REQUIRED_COLUMNS_BY_GROUP[
                ResearchFeatureGroup.FUNDING
            ].issubset(column_set),
        }
    )


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
