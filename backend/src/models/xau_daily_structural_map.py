from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.xau import XauDailyStructuralMap, XauDailyStructuralMapReadiness

SAFE_XAU_DAILY_MAP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_XAU_DAILY_MAP_ARTIFACT_PREFIXES = (
    "data/reports/xau_daily_structural_map/",
    "backend/data/reports/xau_daily_structural_map/",
)


class XauDailyStructuralMapStoreBaseModel(BaseModel):
    """Strict base model for daily structural-map persistence schemas."""

    model_config = ConfigDict(extra="forbid")


class XauDailyStructuralMapArtifactType(StrEnum):
    METADATA = "metadata"
    MAP_JSON = "map_json"
    MAP_MARKDOWN = "map_markdown"
    WALLS_JSON = "walls_json"


class XauDailyStructuralMapArtifactFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class XauDailyStructuralMapArtifact(XauDailyStructuralMapStoreBaseModel):
    artifact_type: XauDailyStructuralMapArtifactType
    path: str
    format: XauDailyStructuralMapArtifactFormat
    rows: int | None = Field(default=None, ge=0)

    @field_validator("path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            raise ValueError("artifact path must not be blank")
        if not normalized.startswith(ALLOWED_XAU_DAILY_MAP_ARTIFACT_PREFIXES):
            raise ValueError("artifact path must stay under xau_daily_structural_map reports")
        return normalized


class XauDailyStructuralMapReportMetadata(XauDailyStructuralMapStoreBaseModel):
    map_id: str
    source_kind: str = "operational"
    session_date: str
    created_at: str
    source_report_ids: list[str] = Field(default_factory=list)
    expected_range_source: str | None = None
    basis_mapping_available: bool
    session_open_available: bool
    wall_count: int = Field(ge=0)
    readiness: XauDailyStructuralMapReadiness
    signal_allowed: bool = False
    limitation_count: int = Field(ge=0)
    no_signal_reason_count: int = Field(ge=0)
    artifacts: list[XauDailyStructuralMapArtifact] = Field(default_factory=list)

    @field_validator("map_id")
    @classmethod
    def validate_map_id(cls, value: str) -> str:
        return validate_xau_daily_structural_map_safe_id(value, "map_id")

    @field_validator("source_kind", "session_date", "created_at")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("metadata text fields must not be blank")
        return normalized

    @field_validator("source_report_ids")
    @classmethod
    def normalize_source_report_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            safe_value = validate_xau_daily_structural_map_safe_id(value, "source_report_id")
            if safe_value not in seen:
                normalized.append(safe_value)
                seen.add(safe_value)
        return normalized

    @model_validator(mode="after")
    def validate_no_signal_state(self) -> XauDailyStructuralMapReportMetadata:
        if self.signal_allowed:
            raise ValueError("daily structural map reports cannot enable signals")
        return self


class XauDailyStructuralMapReportResult(XauDailyStructuralMapStoreBaseModel):
    metadata: XauDailyStructuralMapReportMetadata
    daily_map: XauDailyStructuralMap
    artifacts: list[XauDailyStructuralMapArtifact] = Field(default_factory=list)

    @field_validator("artifacts")
    @classmethod
    def validate_unique_artifact_paths(
        cls,
        values: list[XauDailyStructuralMapArtifact],
    ) -> list[XauDailyStructuralMapArtifact]:
        paths = [artifact.path for artifact in values]
        if len(paths) != len(set(paths)):
            raise ValueError("daily structural map artifact paths must be unique")
        return values

    @model_validator(mode="after")
    def validate_metadata_matches_map(self) -> XauDailyStructuralMapReportResult:
        if self.metadata.map_id != self.daily_map.map_id:
            raise ValueError("metadata map_id must match daily_map map_id")
        if self.metadata.artifacts != self.artifacts:
            raise ValueError("metadata artifacts must match result artifacts")
        return self


def validate_xau_daily_structural_map_safe_id(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if not SAFE_XAU_DAILY_MAP_ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must contain only letters, numbers, underscore, or dash")
    return normalized
