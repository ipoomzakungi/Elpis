from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from src.models.xau import XauBaseModel
from src.models.xau_range_desk import XauRangeDeskPlan

WALK_FORWARD_NO_SIGNAL_REASON = (
    "Feature 025 is a research-only walk-forward Range Desk runner; "
    "signal generation and execution are disabled."
)


class XauWalkForwardReadiness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauWalkForwardScheduleTag(StrEnum):
    PLANNING_1010 = "planning_1010"
    PLANNING_1910 = "planning_1910"
    WALK_FORWARD = "walk_forward"


class XauWalkForwardCmeSource(StrEnum):
    LATEST_EXISTING = "latest_existing"
    LOCAL_BUNDLE = "local_bundle"
    API_ONLY = "api_only"
    FIXTURE = "fixture"


class XauWalkForwardPriceSource(StrEnum):
    MANUAL = "manual"
    YAHOO_RESEARCH = "yahoo_research"
    FIXTURE = "fixture"
    UNAVAILABLE = "unavailable"


class XauWalkForwardSourceQuality(StrEnum):
    OFFICIAL = "official"
    RESEARCH_FALLBACK = "research_fallback"
    MANUAL = "manual"
    FIXTURE = "fixture"
    UNAVAILABLE = "unavailable"


class XauWalkForwardAlignmentStatus(StrEnum):
    ALIGNED = "aligned"
    MISMATCHED = "mismatched"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class XauWalkForwardSdSource(StrEnum):
    CME_NATIVE = "cme_native"
    DERIVED_FROM_IV = "derived_from_iv"
    MANUAL_FIX_RANGE = "manual_fix_range"
    FIXTURE = "fixture"
    UNAVAILABLE = "unavailable"


class XauResearchOrderSide(StrEnum):
    LONG_REVERSION = "long_reversion"
    SHORT_REVERSION = "short_reversion"


class XauResearchOrderStage(StrEnum):
    INITIAL = "initial"
    RECOVERY_1 = "recovery_1"
    RECOVERY_2 = "recovery_2"


class XauResearchRiskStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    MISSING_CONFIG = "missing_config"


class XauResearchOrderOutcomeStatus(StrEnum):
    PLANNED = "planned"
    TRIGGERED = "triggered"
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    EXPIRED = "expired"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class XauWalkForwardScheduleConfig(XauBaseModel):
    timezone: str = "Asia/Bangkok"
    weekdays_only: bool = True
    planning_times: list[time] = Field(
        default_factory=lambda: [time(10, 10), time(19, 10)]
    )
    capture_start_time: time = time(10, 10)
    capture_end_time: time = time(21, 50)
    capture_interval_minutes: int = Field(default=10, ge=1, le=240)
    include_planning_times_only: bool = False

    @field_validator("planning_times", mode="before")
    @classmethod
    def parse_planning_times(cls, value: list[str | time]) -> list[time]:
        return [_parse_time(item) for item in value]

    @field_validator("capture_start_time", "capture_end_time", mode="before")
    @classmethod
    def parse_capture_time(cls, value: str | time) -> time:
        return _parse_time(value)

    @model_validator(mode="after")
    def validate_time_window(self) -> XauWalkForwardScheduleConfig:
        if self.capture_end_time < self.capture_start_time:
            raise ValueError("capture_end_time must be after capture_start_time")
        return self


class XauWalkForwardScheduledTimestamp(XauBaseModel):
    timestamp: datetime
    tag: XauWalkForwardScheduleTag


class XauWalkForwardPriceSnapshot(XauBaseModel):
    timestamp: datetime
    future_reference_price: float | None = Field(default=None, gt=0)
    traded_reference_price: float | None = Field(default=None, gt=0)
    diff_points: float | None = None
    traded_offset: float | None = None
    future_price_source: XauWalkForwardPriceSource = XauWalkForwardPriceSource.UNAVAILABLE
    traded_price_source: XauWalkForwardPriceSource = XauWalkForwardPriceSource.UNAVAILABLE
    source_quality: XauWalkForwardSourceQuality = XauWalkForwardSourceQuality.UNAVAILABLE
    alignment_status: XauWalkForwardAlignmentStatus = XauWalkForwardAlignmentStatus.UNKNOWN
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def calculate_diff(self) -> XauWalkForwardPriceSnapshot:
        if self.future_reference_price is not None and self.traded_reference_price is not None:
            self.diff_points = self.future_reference_price - self.traded_reference_price
            self.traded_offset = self.traded_reference_price - self.future_reference_price
        return self


class XauWalkForwardSdSnapshot(XauBaseModel):
    timestamp: datetime
    expiration_code: str | None = None
    dte: float | None = Field(default=None, ge=0)
    future_reference_price: float | None = Field(default=None, gt=0)
    native_1sd: float | None = Field(default=None, ge=0)
    native_2sd: float | None = Field(default=None, ge=0)
    native_3sd: float | None = Field(default=None, ge=0)
    native_3_5sd: float | None = Field(default=None, ge=0)
    lower_1sd: float | None = None
    upper_1sd: float | None = None
    lower_2sd: float | None = None
    upper_2sd: float | None = None
    lower_2_5sd: float | None = None
    upper_2_5sd: float | None = None
    lower_3sd: float | None = None
    upper_3sd: float | None = None
    lower_3_5sd: float | None = None
    upper_3_5sd: float | None = None
    sd_source: XauWalkForwardSdSource
    source_report_id: str | None = None
    source_view: str | None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available_native_sd(self) -> XauWalkForwardSdSnapshot:
        if self.sd_source in {
            XauWalkForwardSdSource.CME_NATIVE,
            XauWalkForwardSdSource.FIXTURE,
            XauWalkForwardSdSource.DERIVED_FROM_IV,
            XauWalkForwardSdSource.MANUAL_FIX_RANGE,
        }:
            required = [
                self.future_reference_price,
                self.native_1sd,
                self.native_2sd,
                self.native_3sd,
                self.lower_1sd,
                self.upper_1sd,
                self.lower_2sd,
                self.upper_2sd,
                self.lower_3sd,
                self.upper_3sd,
            ]
            if any(value is None for value in required):
                raise ValueError("available SD snapshots require numeric 1SD/2SD/3SD levels")
        if self.sd_source == XauWalkForwardSdSource.UNAVAILABLE and not self.limitations:
            raise ValueError("unavailable SD snapshot requires limitations")
        return self


class XauResearchOrderPlanConfig(XauBaseModel):
    use_gamma_filter: bool = False
    entry_sd_abs: float = Field(default=2.0, gt=0)
    target_sd_abs: float = Field(default=1.0, gt=0)
    stop_sd_abs: float = Field(default=2.5, gt=0)
    recovery_entry_sd_abs: float = Field(default=3.0, gt=0)
    recovery_target_sd_abs: float = Field(default=2.0, gt=0)
    max_recovery_steps: int = Field(default=1, ge=0, le=2)
    no_trade_inside_sd_abs: float = Field(default=1.0, ge=0)
    expire_time: time = time(21, 50)
    allow_long_lower_side: bool = True
    allow_short_upper_side: bool = True
    spread_buffer_points: float = Field(default=0.0, ge=0)
    slippage_buffer_points: float = Field(default=0.0, ge=0)
    max_ambiguous_bars_allowed: int = Field(default=0, ge=0)

    @field_validator("expire_time", mode="before")
    @classmethod
    def parse_expire_time(cls, value: str | time) -> time:
        return _parse_time(value)


class XauResearchRiskConfig(XauBaseModel):
    account_equity: float | None = Field(default=None, gt=0)
    max_total_risk_percent: float | None = Field(default=None, gt=0)
    max_recovery_risk_percent: float | None = Field(default=None, gt=0)
    max_size: float | None = Field(default=None, gt=0)
    point_value_per_size_unit: float | None = Field(default=None, gt=0)
    contract_size: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    min_liquidation_buffer_points: float | None = Field(default=None, ge=0)
    costs_per_order: float | None = Field(default=None, ge=0)
    recovery_enabled: bool = False
    recovery_multiplier: float = Field(default=1.0, gt=0)


class XauResearchOrderPlan(XauBaseModel):
    plan_id: str
    snapshot_id: str
    timestamp: datetime
    side: XauResearchOrderSide
    stage: XauResearchOrderStage
    entry_level: float = Field(gt=0)
    target_level: float = Field(gt=0)
    stop_level: float = Field(gt=0)
    entry_sd: float
    target_sd: float
    stop_sd: float
    tp_points: float = Field(ge=0)
    sl_points: float = Field(ge=0)
    planned_size: float | None = Field(default=None, gt=0)
    cumulative_loss_to_recover: float = Field(default=0.0, ge=0)
    desired_net_profit: float = Field(default=0.0, ge=0)
    recovery_formula: str | None = None
    risk_status: XauResearchRiskStatus
    risk_reasons: list[str] = Field(default_factory=list)
    parent_plan_id: str | None = None
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauResearchOrderPlan:
        if self.signal_allowed:
            raise ValueError("research order plans cannot enable signals")
        if not self.research_only:
            raise ValueError("research order plans must remain research_only")
        return self


class XauOhlcvBar(XauBaseModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_prices(self) -> XauOhlcvBar:
        if self.low > self.high:
            raise ValueError("bar low must be <= high")
        if not self.low <= self.open <= self.high:
            raise ValueError("bar open must be inside high/low")
        if not self.low <= self.close <= self.high:
            raise ValueError("bar close must be inside high/low")
        return self


class XauResearchOrderOutcome(XauBaseModel):
    plan_id: str
    status: XauResearchOrderOutcomeStatus
    trigger_time: datetime | None = None
    exit_time: datetime | None = None
    entry_fill_level: float | None = Field(default=None, gt=0)
    exit_level: float | None = Field(default=None, gt=0)
    mfe_points: float | None = None
    mae_points: float | None = None
    realized_points: float | None = None
    realized_currency: float | None = None
    limitations: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauResearchOrderOutcome:
        if self.signal_allowed:
            raise ValueError("research outcomes cannot enable signals")
        if not self.research_only:
            raise ValueError("research outcomes must remain research_only")
        return self


class XauWalkForwardSnapshotRecord(XauBaseModel):
    snapshot_id: str
    timestamp: datetime
    schedule_tag: XauWalkForwardScheduleTag
    price_snapshot: XauWalkForwardPriceSnapshot
    sd_snapshot: XauWalkForwardSdSnapshot | None = None
    range_desk_plan: XauRangeDeskPlan | None = None
    research_order_plans: list[XauResearchOrderPlan] = Field(default_factory=list)
    data_capability_summary: dict[str, str] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauWalkForwardSnapshotRecord:
        if self.signal_allowed:
            raise ValueError("walk-forward snapshots cannot enable signals")
        if not self.research_only:
            raise ValueError("walk-forward snapshots must remain research_only")
        return self


class XauWalkForwardRunRequest(XauBaseModel):
    session_date: date
    expiration_code: str | None = None
    schedule_config: XauWalkForwardScheduleConfig = Field(
        default_factory=XauWalkForwardScheduleConfig
    )
    order_plan_config: XauResearchOrderPlanConfig = Field(
        default_factory=XauResearchOrderPlanConfig
    )
    risk_config: XauResearchRiskConfig = Field(default_factory=XauResearchRiskConfig)
    cme_source: XauWalkForwardCmeSource = XauWalkForwardCmeSource.LATEST_EXISTING
    price_source: XauWalkForwardPriceSource = XauWalkForwardPriceSource.MANUAL
    future_reference_price: float | None = Field(default=None, gt=0)
    traded_reference_price: float | None = Field(default=None, gt=0)
    input_dir: Path | None = None
    price_bars_path: Path | None = None
    run_outcome_simulation: bool = False
    output_root: Path | None = None
    overwrite_allowed: bool = False
    research_only_acknowledged: bool = True

    @model_validator(mode="after")
    def validate_research_only(self) -> XauWalkForwardRunRequest:
        if not self.research_only_acknowledged:
            raise ValueError("walk-forward research runs must be acknowledged")
        if self.price_source == XauWalkForwardPriceSource.MANUAL and (
            self.future_reference_price is None or self.traded_reference_price is None
        ):
            raise ValueError("manual price source requires future and traded reference prices")
        return self


class XauWalkForwardRunResult(XauBaseModel):
    run_id: str
    created_at: datetime
    session_date: date
    readiness: XauWalkForwardReadiness
    snapshot_count: int = Field(ge=0)
    order_plan_count: int = Field(ge=0)
    outcome_count: int = Field(ge=0)
    artifact_paths: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [WALK_FORWARD_NO_SIGNAL_REASON]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauWalkForwardRunResult:
        if self.signal_allowed:
            raise ValueError("walk-forward runs cannot enable signals")
        if not self.research_only:
            raise ValueError("walk-forward runs must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("walk-forward runs require no_signal_reasons")
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
    "WALK_FORWARD_NO_SIGNAL_REASON",
    "XauOhlcvBar",
    "XauResearchOrderOutcome",
    "XauResearchOrderOutcomeStatus",
    "XauResearchOrderPlan",
    "XauResearchOrderPlanConfig",
    "XauResearchOrderSide",
    "XauResearchOrderStage",
    "XauResearchRiskConfig",
    "XauResearchRiskStatus",
    "XauWalkForwardAlignmentStatus",
    "XauWalkForwardCmeSource",
    "XauWalkForwardPriceSnapshot",
    "XauWalkForwardPriceSource",
    "XauWalkForwardReadiness",
    "XauWalkForwardRunRequest",
    "XauWalkForwardRunResult",
    "XauWalkForwardScheduleConfig",
    "XauWalkForwardScheduleTag",
    "XauWalkForwardScheduledTimestamp",
    "XauWalkForwardSdSnapshot",
    "XauWalkForwardSdSource",
    "XauWalkForwardSnapshotRecord",
    "XauWalkForwardSourceQuality",
]
