from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from src.models.xau import XauBaseModel
from src.models.xau_walk_forward_research import XauResearchOrderSide

PLAN_TRACKER_NO_SIGNAL_REASON = (
    "Feature 026 is a research-only XAU plan tracker; signal generation and "
    "execution are disabled."
)


class XauDukasCaptureStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class XauPlanTrackerReadiness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauReferenceAlignmentStatus(StrEnum):
    EXACT = "exact"
    WITHIN_TOLERANCE = "within_tolerance"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class XauTrackedOrderStatus(StrEnum):
    PLANNED = "planned"
    TRIGGERED = "triggered"
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    RECOVERY_TRIGGERED = "recovery_triggered"
    RECOVERY_TARGET_HIT = "recovery_target_hit"
    EXPIRED = "expired"
    OPEN = "open"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class XauDukasCliCaptureRequest(XauBaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "1m"
    start_time: datetime
    end_time: datetime
    timezone: str = "Asia/Bangkok"
    dukas_cli_path: Path | None = None
    command_template: str | None = None
    output_dir: Path | None = None
    timeout_seconds: int = Field(default=120, gt=0, le=3600)
    research_only_acknowledged: bool = True

    @model_validator(mode="after")
    def validate_research_only(self) -> XauDukasCliCaptureRequest:
        if not self.research_only_acknowledged:
            raise ValueError("Dukascopy capture must be research-only acknowledged")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class XauDukasPriceBar(XauBaseModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)
    symbol: str = "XAUUSD"
    timeframe: str = "1m"
    source: str = "dukascopy_cli"
    source_quality: str = "research_price_feed"

    @model_validator(mode="after")
    def validate_ohlc(self) -> XauDukasPriceBar:
        if self.low > self.high:
            raise ValueError("bar low must be <= high")
        if not self.low <= self.open <= self.high:
            raise ValueError("bar open must be inside high/low")
        if not self.low <= self.close <= self.high:
            raise ValueError("bar close must be inside high/low")
        return self


class XauDukasCaptureResult(XauBaseModel):
    capture_id: str
    created_at: datetime
    status: XauDukasCaptureStatus
    bars_count: int = Field(ge=0)
    bars_path: Path | None = None
    latest_price: float | None = Field(default=None, gt=0)
    limitations: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauDukasCaptureResult:
        if self.signal_allowed:
            raise ValueError("Dukascopy capture results cannot enable signals")
        if not self.research_only:
            raise ValueError("Dukascopy capture results must remain research_only")
        return self


class XauReferencePriceResult(XauBaseModel):
    requested_timestamp: datetime
    reference_price: float | None = Field(default=None, gt=0)
    matched_timestamp: datetime | None = None
    alignment_status: XauReferenceAlignmentStatus
    limitations: list[str] = Field(default_factory=list)


class XauPlanLevels(XauBaseModel):
    side: XauResearchOrderSide
    entry_level: float = Field(gt=0)
    target_level: float = Field(gt=0)
    stop_level: float = Field(gt=0)
    recovery_entry_level: float | None = Field(default=None, gt=0)
    recovery_target_level: float | None = Field(default=None, gt=0)


class XauPlanTrackerRequest(XauBaseModel):
    session_date: date
    planning_times: list[time] = Field(default_factory=lambda: [time(10, 10), time(18, 10)])
    timezone: str = "Asia/Bangkok"
    cme_source: str = "latest_existing"
    price_source: str = "dukascopy_cli"
    dukas_cli_path: Path | None = None
    command_template: str | None = None
    price_bars_path: Path | None = None
    symbol: str = "XAUUSD"
    timeframe: str = "1m"
    entry_sd: float = Field(default=2.0, gt=0)
    target_sd: float = Field(default=1.0, gt=0)
    stop_sd: float = Field(default=2.5, gt=0)
    recovery_entry_sd: float = Field(default=3.0, gt=0)
    recovery_target_sd: float = Field(default=2.0, gt=0)
    max_recovery_steps: int = Field(default=1, ge=0, le=2)
    run_until_time: time = time(21, 50)
    output_root: Path | None = None
    overwrite: bool = False
    research_only_acknowledged: bool = True

    @field_validator("planning_times", mode="before")
    @classmethod
    def parse_planning_times(cls, value: list[str | time]) -> list[time]:
        return [_parse_time(item) for item in value]

    @field_validator("run_until_time", mode="before")
    @classmethod
    def parse_run_until_time(cls, value: str | time) -> time:
        return _parse_time(value)

    @model_validator(mode="after")
    def validate_research_only(self) -> XauPlanTrackerRequest:
        if not self.research_only_acknowledged:
            raise ValueError("XAU plan tracker runs must be research-only acknowledged")
        if not self.planning_times:
            raise ValueError("at least one planning time is required")
        return self


class XauResearchPlanTrackerSnapshot(XauBaseModel):
    snapshot_id: str
    planning_time: datetime
    future_reference_price: float | None = Field(default=None, gt=0)
    traded_reference_price: float | None = Field(default=None, gt=0)
    diff_points: float | None = None
    dte: float | None = Field(default=None, ge=0)
    native_1sd: float | None = Field(default=None, ge=0)
    native_2sd: float | None = Field(default=None, ge=0)
    native_3sd: float | None = Field(default=None, ge=0)
    reference_alignment: XauReferenceAlignmentStatus = XauReferenceAlignmentStatus.UNAVAILABLE
    long_plan: XauPlanLevels | None = None
    short_plan: XauPlanLevels | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauResearchPlanTrackerSnapshot:
        if self.signal_allowed:
            raise ValueError("plan tracker snapshots cannot enable signals")
        if not self.research_only:
            raise ValueError("plan tracker snapshots must remain research_only")
        return self


class XauResearchTrackedOrder(XauBaseModel):
    order_id: str
    planning_time: datetime
    side: XauResearchOrderSide
    entry_level: float = Field(gt=0)
    target_level: float = Field(gt=0)
    stop_level: float = Field(gt=0)
    recovery_entry_level: float | None = Field(default=None, gt=0)
    recovery_target_level: float | None = Field(default=None, gt=0)
    status: XauTrackedOrderStatus
    trigger_time: datetime | None = None
    exit_time: datetime | None = None
    current_price: float | None = Field(default=None, gt=0)
    current_pnl_points: float | None = None
    max_favorable_excursion_points: float | None = None
    max_adverse_excursion_points: float | None = None
    drawdown_points: float | None = Field(default=None, ge=0)
    bars_covered_count: int = Field(default=0, ge=0)
    limitations: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauResearchTrackedOrder:
        if self.signal_allowed:
            raise ValueError("tracked orders cannot enable signals")
        if not self.research_only:
            raise ValueError("tracked orders must remain research_only")
        return self


class XauPlanTrackerRunResult(XauBaseModel):
    run_id: str
    created_at: datetime
    session_date: date
    snapshot_count: int = Field(ge=0)
    tracked_order_count: int = Field(ge=0)
    open_order_count: int = Field(ge=0)
    completed_order_count: int = Field(ge=0)
    artifact_paths: list[str] = Field(default_factory=list)
    readiness: XauPlanTrackerReadiness
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [PLAN_TRACKER_NO_SIGNAL_REASON]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauPlanTrackerRunResult:
        if self.signal_allowed:
            raise ValueError("plan tracker runs cannot enable signals")
        if not self.research_only:
            raise ValueError("plan tracker runs must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("plan tracker runs require no_signal_reasons")
        return self


def _parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    try:
        hour, minute = str(value).split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError) as exc:
        raise ValueError("time values must use HH:MM format") from exc


__all__ = [
    "PLAN_TRACKER_NO_SIGNAL_REASON",
    "XauDukasCaptureResult",
    "XauDukasCaptureStatus",
    "XauDukasCliCaptureRequest",
    "XauDukasPriceBar",
    "XauPlanLevels",
    "XauPlanTrackerReadiness",
    "XauPlanTrackerRequest",
    "XauPlanTrackerRunResult",
    "XauReferenceAlignmentStatus",
    "XauReferencePriceResult",
    "XauResearchPlanTrackerSnapshot",
    "XauResearchTrackedOrder",
    "XauTrackedOrderStatus",
]
