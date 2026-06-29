from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from src.models.xau import XauBaseModel


class XauPriceProviderKind(StrEnum):
    MANUAL = "manual"
    LOCAL_BARS = "local_bars"
    LATEST_LOCAL_IMPORT = "latest_local_import"
    LATEST_FUSION = "latest_fusion"
    YFINANCE = "yfinance"
    UNAVAILABLE = "unavailable"


class XauPriceProviderQuality(StrEnum):
    EXECUTION_CANDIDATE = "execution_candidate"
    RESEARCH_GOOD = "research_good"
    RESEARCH_FALLBACK = "research_fallback"
    MANUAL_FALLBACK = "manual_fallback"
    UNAVAILABLE = "unavailable"


class XauResolvedPrice(XauBaseModel):
    symbol: str
    price: float | None = Field(default=None, gt=0)
    timestamp: datetime | None = None
    provider: XauPriceProviderKind
    provider_quality: XauPriceProviderQuality
    source_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class XauResolvedMarketInputs(XauBaseModel):
    traded_price: XauResolvedPrice
    gc_futures_price: XauResolvedPrice
    current_timestamp: datetime | None = None
    price_bars_path: Path | None = None
    fusion_report_id: str | None = None
    fusion_report_path: Path | None = None
    basis_alignment_seconds: float | None = Field(default=None, ge=0)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    signal_allowed: bool = False
    research_only: bool = True

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauResolvedMarketInputs:
        if self.signal_allowed:
            raise ValueError("resolved XAU market inputs cannot enable signals")
        if not self.research_only:
            raise ValueError("resolved XAU market inputs must remain research_only")
        return self

