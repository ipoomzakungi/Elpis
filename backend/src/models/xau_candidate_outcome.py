from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

XAU_CANDIDATE_OUTCOME_NO_SIGNAL_REASON = (
    "Feature 023 is research-only; candidate outcome labels are not trading signals."
)
XAU_CANDIDATE_OUTCOME_RESEARCH_LIMITATION = (
    "Outcome labels are forward research annotations only, not PnL, alerts, "
    "orders, position sizing, or trade recommendations."
)


class XauCandidateOutcomeBaseModel(BaseModel):
    """Strict base model for XAU candidate outcome schemas."""

    model_config = ConfigDict(extra="forbid")


class XauCandidateOutcomeWindow(StrEnum):
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    SESSION_CLOSE = "session_close"
    NEXT_DAY = "next_day"


class XauCandidateOutcomeCoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class XauCandidateOutcomeLabel(StrEnum):
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    MEAN_REVERTED = "mean_reverted"
    BREAKOUT_CONTINUED = "breakout_continued"
    UNRESOLVED = "unresolved"
    UNAVAILABLE = "unavailable"


class XauCandidatePriceSourceKind(StrEnum):
    LOCAL_CSV = "local_csv"
    LOCAL_JSON = "local_json"
    LOCAL_PARQUET = "local_parquet"
    STATIC_FIXTURE = "static_fixture"


class XauCandidateOutcomeRunReadiness(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauCandidatePriceBar(XauCandidateOutcomeBaseModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)
    source: str = "local"

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("price bar source must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_ohlc_shape(self) -> XauCandidatePriceBar:
        if self.high < self.low or self.high < self.open or self.high < self.close:
            raise ValueError("high must be greater than or equal to open, low, and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be less than or equal to open and close")
        return self


class XauCandidatePriceSeriesSource(XauCandidateOutcomeBaseModel):
    source_kind: XauCandidatePriceSourceKind
    source_path: str
    row_count: int = Field(ge=0)
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    limitations: list[str] = Field(default_factory=list)

    @field_validator("source_path")
    @classmethod
    def normalize_source_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            raise ValueError("source_path must not be blank")
        if ".." in normalized.split("/"):
            raise ValueError("source_path must not contain parent traversal")
        return normalized

    @field_validator("first_timestamp", "last_timestamp")
    @classmethod
    def normalize_optional_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_aware_datetime(value)

    @field_validator("limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)


class XauCandidateOutcome(XauCandidateOutcomeBaseModel):
    candidate_id: str
    map_id: str
    run_id: str | None = None
    session_date: date
    window: XauCandidateOutcomeWindow
    entry_reference: float | None = Field(default=None, gt=0)
    stop_reference: float | None = Field(default=None, gt=0)
    target_1: float | None = Field(default=None, gt=0)
    target_2: float | None = Field(default=None, gt=0)
    target_3: float | None = Field(default=None, gt=0)
    open: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    close: float | None = Field(default=None, gt=0)
    mfe_points: float | None = Field(default=None, ge=0)
    mae_points: float | None = Field(default=None, ge=0)
    hit_target_1: bool = False
    hit_target_2: bool = False
    hit_target_3: bool = False
    hit_stop_reference: bool = False
    returned_to_1sd: bool = False
    touched_2sd: bool = False
    touched_3sd: bool = False
    touched_3_5sd: bool = False
    touched_next_wall: bool = False
    continued_breakout: bool = False
    outcome_label: XauCandidateOutcomeLabel
    price_source: str
    coverage_status: XauCandidateOutcomeCoverageStatus
    limitations: list[str] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [XAU_CANDIDATE_OUTCOME_NO_SIGNAL_REASON]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator("candidate_id", "map_id", "price_source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("candidate outcome text fields must not be blank")
        return normalized

    @field_validator("run_id")
    @classmethod
    def normalize_optional_run_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("limitations", "no_signal_reasons")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def validate_outcome_state(self) -> XauCandidateOutcome:
        if self.signal_allowed:
            raise ValueError("XAU candidate outcomes cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU candidate outcomes must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("candidate outcomes require no_signal_reasons")
        if None not in (self.open, self.high, self.low, self.close):
            high = self.high or 0
            low = self.low or 0
            open_price = self.open or 0
            close_price = self.close or 0
            if high < low or high < open_price or high < close_price:
                raise ValueError("high must be greater than or equal to open, low, and close")
            if low > open_price or low > close_price:
                raise ValueError("low must be less than or equal to open and close")
        return self


class XauCandidateOutcomeSet(XauCandidateOutcomeBaseModel):
    outcome_run_id: str
    map_id: str
    candidate_set_id: str
    session_date: date
    windows: list[XauCandidateOutcomeWindow]
    candidate_count: int = Field(ge=0)
    outcome_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    price_source: XauCandidatePriceSeriesSource
    outcomes: list[XauCandidateOutcome] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [XAU_CANDIDATE_OUTCOME_NO_SIGNAL_REASON]
    )
    limitations: list[str] = Field(
        default_factory=lambda: [XAU_CANDIDATE_OUTCOME_RESEARCH_LIMITATION]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator("outcome_run_id", "map_id", "candidate_set_id")
    @classmethod
    def normalize_required_ids(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate outcome set ids must not be blank")
        return normalized

    @field_validator("windows")
    @classmethod
    def require_windows(
        cls,
        values: list[XauCandidateOutcomeWindow],
    ) -> list[XauCandidateOutcomeWindow]:
        if not values:
            raise ValueError("at least one outcome window is required")
        return list(dict.fromkeys(values))

    @field_validator("no_signal_reasons", "limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def validate_outcome_set_state(self) -> XauCandidateOutcomeSet:
        if self.outcome_count != len(self.outcomes):
            raise ValueError("outcome_count must match number of outcomes")
        unavailable_count = sum(
            1
            for outcome in self.outcomes
            if outcome.outcome_label == XauCandidateOutcomeLabel.UNAVAILABLE
        )
        if self.unavailable_count != unavailable_count:
            raise ValueError("unavailable_count must match unavailable outcomes")
        if self.signal_allowed:
            raise ValueError("XAU candidate outcome sets cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU candidate outcome sets must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("candidate outcome sets require no_signal_reasons")
        return self


class XauCandidateOutcomeRunRequest(XauCandidateOutcomeBaseModel):
    candidate_set_path: Path
    price_bars_path: Path
    windows: list[XauCandidateOutcomeWindow] = Field(
        default_factory=lambda: [
            XauCandidateOutcomeWindow.THIRTY_MINUTES,
            XauCandidateOutcomeWindow.ONE_HOUR,
            XauCandidateOutcomeWindow.FOUR_HOURS,
            XauCandidateOutcomeWindow.SESSION_CLOSE,
            XauCandidateOutcomeWindow.NEXT_DAY,
        ]
    )
    output_root: Path | None = None
    overwrite_allowed: bool = False
    timestamp_column: str = "timestamp"
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    close_column: str = "close"
    volume_column: str | None = "volume"
    timezone: str = "UTC"
    research_only_acknowledged: bool = True

    @field_validator("candidate_set_path", "price_bars_path", "output_root", mode="before")
    @classmethod
    def validate_local_path(cls, value: object) -> object:
        if value is None:
            return None
        cleaned = str(value).replace("\\", "/").strip()
        if not cleaned:
            raise ValueError("local path must not be blank")
        if cleaned.startswith(("http://", "https://")):
            raise ValueError("remote URLs are not accepted for local research files")
        if ".." in cleaned.split("/"):
            raise ValueError("local path must not contain parent traversal")
        return Path(cleaned)

    @field_validator(
        "timestamp_column",
        "open_column",
        "high_column",
        "low_column",
        "close_column",
        "volume_column",
        "timezone",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        normalized = " ".join(str(value).split())
        return normalized or None

    @field_validator(
        "timestamp_column",
        "open_column",
        "high_column",
        "low_column",
        "close_column",
        "timezone",
    )
    @classmethod
    def require_text_fields(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("column and timezone fields are required")
        return value

    @field_validator("windows")
    @classmethod
    def require_windows(
        cls,
        values: list[XauCandidateOutcomeWindow],
    ) -> list[XauCandidateOutcomeWindow]:
        if not values:
            raise ValueError("at least one outcome window is required")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def require_research_acknowledgement(self) -> XauCandidateOutcomeRunRequest:
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        return self


class XauCandidateOutcomeRunResult(XauCandidateOutcomeBaseModel):
    outcome_run_id: str
    created_at: datetime
    readiness: XauCandidateOutcomeRunReadiness
    candidate_set_id: str
    map_id: str
    candidate_count: int = Field(ge=0)
    outcome_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    outcome_set: XauCandidateOutcomeSet
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [XAU_CANDIDATE_OUTCOME_NO_SIGNAL_REASON]
    )
    limitations: list[str] = Field(
        default_factory=lambda: [XAU_CANDIDATE_OUTCOME_RESEARCH_LIMITATION]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator("outcome_run_id", "candidate_set_id", "map_id")
    @classmethod
    def normalize_required_ids(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate outcome run ids must not be blank")
        return normalized

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("artifact_paths")
    @classmethod
    def normalize_artifact_paths(cls, values: dict[str, str]) -> dict[str, str]:
        return {str(key): str(value).replace("\\", "/") for key, value in values.items()}

    @field_validator("no_signal_reasons", "limitations")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def validate_run_state(self) -> XauCandidateOutcomeRunResult:
        if self.signal_allowed:
            raise ValueError("XAU candidate outcome runs cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU candidate outcome runs must remain research_only")
        if self.outcome_count != self.outcome_set.outcome_count:
            raise ValueError("run outcome_count must match outcome set")
        if self.unavailable_count != self.outcome_set.unavailable_count:
            raise ValueError("run unavailable_count must match outcome set")
        return self


class XauCandidateOutcomeLatestResponse(XauCandidateOutcomeBaseModel):
    readiness: XauCandidateOutcomeRunReadiness
    latest_run: XauCandidateOutcomeRunResult | None = None
    available_runs: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    message: str
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [XAU_CANDIDATE_OUTCOME_NO_SIGNAL_REASON]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @field_validator("available_runs", "no_signal_reasons")
    @classmethod
    def normalize_text_list(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def validate_latest_state(self) -> XauCandidateOutcomeLatestResponse:
        if self.signal_allowed:
            raise ValueError("XAU candidate outcome latest response cannot enable signals")
        if not self.research_only:
            raise ValueError("XAU candidate outcome latest response must remain research_only")
        return self


def candidate_outcome_no_signal_reasons(*extra: str) -> list[str]:
    return _dedupe([XAU_CANDIDATE_OUTCOME_NO_SIGNAL_REASON, *extra])


def candidate_outcome_limitations(*extra: str) -> list[str]:
    return _dedupe([XAU_CANDIDATE_OUTCOME_RESEARCH_LIMITATION, *extra])


def _normalize_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


__all__ = [
    "XAU_CANDIDATE_OUTCOME_NO_SIGNAL_REASON",
    "XAU_CANDIDATE_OUTCOME_RESEARCH_LIMITATION",
    "XauCandidateOutcome",
    "XauCandidateOutcomeCoverageStatus",
    "XauCandidateOutcomeLabel",
    "XauCandidateOutcomeLatestResponse",
    "XauCandidateOutcomeRunReadiness",
    "XauCandidateOutcomeRunRequest",
    "XauCandidateOutcomeRunResult",
    "XauCandidateOutcomeSet",
    "XauCandidateOutcomeWindow",
    "XauCandidatePriceBar",
    "XauCandidatePriceSeriesSource",
    "XauCandidatePriceSourceKind",
    "candidate_outcome_limitations",
    "candidate_outcome_no_signal_reasons",
]
