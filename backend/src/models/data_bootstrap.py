"""Schemas for public/no-key data bootstrap workflows."""

from enum import StrEnum

from src.models.data_sources import (
    DataSourceBootstrapArtifact as DataBootstrapArtifact,
)
from src.models.data_sources import (
    DataSourceBootstrapAssetSummary as DataBootstrapAssetResult,
)
from src.models.data_sources import (
    DataSourceBootstrapPlanItem as DataBootstrapPlanItem,
)
from src.models.data_sources import (
    DataSourceBootstrapProvider as DataBootstrapProvider,
)
from src.models.data_sources import (
    DataSourceBootstrapRequest as PublicDataBootstrapRequest,
)
from src.models.data_sources import (
    DataSourceBootstrapRunListResponse as PublicDataBootstrapRunListResponse,
)
from src.models.data_sources import (
    DataSourceBootstrapRunResult as PublicDataBootstrapRun,
)


class DataBootstrapStatus(StrEnum):
    """Run-level bootstrap status."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class DataBootstrapAssetStatus(StrEnum):
    """Per-asset bootstrap status exposed in 009 reports."""

    DOWNLOADED = "downloaded"
    SKIPPED = "skipped"
    FAILED = "failed"


class DataBootstrapArtifactType(StrEnum):
    """Bootstrap artifact categories."""

    RAW_OHLCV = "raw_ohlcv"
    RAW_OPEN_INTEREST = "raw_open_interest"
    RAW_FUNDING_RATE = "raw_funding_rate"
    PROCESSED_FEATURES = "processed_features"
    BOOTSTRAP_REPORT = "bootstrap_report"


__all__ = [
    "DataBootstrapArtifact",
    "DataBootstrapArtifactType",
    "DataBootstrapAssetResult",
    "DataBootstrapAssetStatus",
    "DataBootstrapPlanItem",
    "DataBootstrapProvider",
    "DataBootstrapStatus",
    "PublicDataBootstrapRequest",
    "PublicDataBootstrapRun",
    "PublicDataBootstrapRunListResponse",
]
