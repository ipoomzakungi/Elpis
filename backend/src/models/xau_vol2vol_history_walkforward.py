from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from src.models.xau import XauBaseModel


class XauHistorySourceMode(StrEnum):
    LOCAL_FILE = "local_file"
    LOCAL_FOLDER = "local_folder"
    HTTP_ENDPOINT = "http_endpoint"
    LATEST_EXISTING = "latest_existing"
    UNAVAILABLE = "unavailable"


class XauMappingMode(StrEnum):
    SAME_TIME_BASIS = "same_time_basis"
    DISTANCE_REANCHORED = "distance_reanchored"


class XauSourceClass(StrEnum):
    EXACT_FUTURES_CONTRACT = "exact_futures_contract"
    CONTINUOUS_FUTURES_PROXY = "continuous_futures_proxy"
    SPOT_BASIS = "spot_basis"
    DISTANCE_REANCHORED = "distance_reanchored"


class XauContractAlignmentStatus(StrEnum):
    EXACT = "exact"
    PROXY = "proxy"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"


class XauSdEntryLevel(StrEnum):
    ONE_SD = "one_sd"
    TWO_SD = "two_sd"
    THREE_SD = "three_sd"


class XauTpMode(StrEnum):
    HALF_SD = "half_sd"
    ONE_SD = "one_sd"
    FIXED_12_5 = "fixed_12_5"
    FIXED_25 = "fixed_25"
    OPEN_PRICE = "open_price"
    NEXT_WALL = "next_wall"


class XauSlMode(StrEnum):
    NEXT_HALF_SD = "next_half_sd"
    NEXT_SD = "next_sd"
    THREE_SD = "three_sd"
    THREE_5SD = "three_5sd"
    FIXED_12_5 = "fixed_12_5"
    FIXED_25 = "fixed_25"


class XauTradeSide(StrEnum):
    LONG_REVERSION = "long_reversion"
    SHORT_REVERSION = "short_reversion"


class XauEntryType(StrEnum):
    TOUCH = "touch"
    REJECTION_CONFIRMED = "rejection_confirmed"


class XauWalkforwardTradeStatus(StrEnum):
    NO_FILL = "no_fill"
    TRIGGERED = "triggered"
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    EXPIRED = "expired"
    TIME_EXIT_PROFIT = "time_exit_profit"
    TIME_EXIT_LOSS = "time_exit_loss"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class XauTimeExitPolicy(StrEnum):
    CLOSE_AT_CYCLE_END = "close_at_cycle_end"
    MARK_ONLY_EXCLUDE_FROM_EXPECTANCY = "mark_only_exclude_from_expectancy"
    UNAVAILABLE = "unavailable"


class XauWindowAlignmentStatus(StrEnum):
    ALIGNED = "aligned"
    NO_BARS_IN_WINDOW = "no_bars_in_window"
    STALE_PLAN = "stale_plan"
    INVALID = "invalid"


class XauPlanReadiness(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class XauVolRegimeLabel(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class XauOiConfluenceLabel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    UNAVAILABLE = "unavailable"


class XauWormholeLabel(StrEnum):
    TARGET_VACUUM = "target_vacuum"
    STOP_VACUUM = "stop_vacuum"
    BOTH_SIDES_VACUUM = "both_sides_vacuum"
    NONE = "none"
    UNAVAILABLE = "unavailable"


class XauVol2VolStrikeSnapshot(XauBaseModel):
    session_date: date
    observed_at: datetime
    series: str | None = None
    snapshot_kind: str
    strike: float
    call: float | None = Field(default=None, ge=0)
    put: float | None = Field(default=None, ge=0)
    total: float | None = Field(default=None, ge=0)
    vol_settle: float | None = Field(default=None, ge=0)
    call_change: float | None = None
    put_change: float | None = None
    total_change: float | None = None
    source: str
    warnings: list[str] = Field(default_factory=list)


class XauVol2VolRangeDeskSnapshot(XauBaseModel):
    session_date: date
    observed_at: datetime
    series: str | None = None
    dte: float | None = Field(default=None, ge=0)
    future_open: float | None = Field(default=None, gt=0)
    cfd_open: float | None = Field(default=None, gt=0)
    diff: float | None = None
    vol_now: float | None = Field(default=None, ge=0)
    vol_chg: float | None = None
    future_chg: float | None = None
    expected_move: float | None = Field(default=None, ge=0)
    sd_step_1: float | None = Field(default=None, ge=0)
    sd_step_2: float | None = Field(default=None, ge=0)
    sd_step_3: float | None = Field(default=None, ge=0)
    cfd_buy_1sd: float | None = Field(default=None, gt=0)
    cfd_buy_2sd: float | None = Field(default=None, gt=0)
    cfd_buy_3sd: float | None = Field(default=None, gt=0)
    cfd_sell_1sd: float | None = Field(default=None, gt=0)
    cfd_sell_2sd: float | None = Field(default=None, gt=0)
    cfd_sell_3sd: float | None = Field(default=None, gt=0)
    future_buy_1sd: float | None = Field(default=None, gt=0)
    future_buy_2sd: float | None = Field(default=None, gt=0)
    future_buy_3sd: float | None = Field(default=None, gt=0)
    future_sell_1sd: float | None = Field(default=None, gt=0)
    future_sell_2sd: float | None = Field(default=None, gt=0)
    future_sell_3sd: float | None = Field(default=None, gt=0)
    basis_formula: str = "cfd_level = future_level - diff"
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def compute_diff_if_possible(self) -> XauVol2VolRangeDeskSnapshot:
        if self.diff is None and self.future_open is not None and self.cfd_open is not None:
            self.diff = self.future_open - self.cfd_open
        return self


class XauOiConfluenceState(XauBaseModel):
    nearest_strike: float | None = None
    nearest_total: float | None = Field(default=None, ge=0)
    nearest_call: float | None = Field(default=None, ge=0)
    nearest_put: float | None = Field(default=None, ge=0)
    top_rank: int | None = Field(default=None, ge=1)
    distance_points: float | None = Field(default=None, ge=0)
    distance_to_entry_points: float | None = None
    confluence_label: XauOiConfluenceLabel
    notes: list[str] = Field(default_factory=list)


class XauWormholeState(XauBaseModel):
    entry_level: float
    side: XauTradeSide
    low_activity_between_entry_and_target: bool
    low_activity_between_entry_and_stop: bool
    min_total_between_entry_and_target: float | None = Field(default=None, ge=0)
    min_total_between_entry_and_stop: float | None = Field(default=None, ge=0)
    wormhole_label: XauWormholeLabel
    notes: list[str] = Field(default_factory=list)


class XauSdMeanReversionPlan(XauBaseModel):
    plan_id: str
    session_date: date
    cycle_label: str
    baseline_config: str = "custom"
    entry_type: XauEntryType = XauEntryType.TOUCH
    observed_at: datetime
    side: XauTradeSide
    entry_sd: XauSdEntryLevel
    entry_level: float | None = Field(default=None, gt=0)
    tp_mode: XauTpMode
    target_level: float | None = Field(default=None, gt=0)
    sl_mode: XauSlMode
    stop_level: float | None = Field(default=None, gt=0)
    open_price: float | None = Field(default=None, gt=0)
    sd_step_points: float | None = Field(default=None, gt=0)
    rr_points: float | None = None
    risk_points: float | None = None
    oi_confluence: XauOiConfluenceState | None = None
    wormhole_state: XauWormholeState | None = None
    vol_regime_label: XauVolRegimeLabel
    readiness: XauPlanReadiness
    blocked_reasons: list[str] = Field(default_factory=list)
    selected_vol2vol_snapshot_time: datetime | None = None
    selected_xau_price_time: datetime | None = None
    basis_alignment_seconds: float | None = Field(default=None, ge=0)
    mapping_mode: XauMappingMode = XauMappingMode.DISTANCE_REANCHORED
    source_alignment_seconds: float | None = Field(default=None, ge=0)
    xau_price_age_at_planning_seconds: float | None = Field(default=None, ge=0)
    snapshot_age_at_planning_seconds: float | None = Field(default=None, ge=0)
    series_selection_reason: str | None = None
    candidate_series: list[dict] = Field(default_factory=list)
    plan_created_at: datetime | None = None
    simulation_window_start: datetime | None = None
    simulation_window_end: datetime | None = None
    selected_series: str | None = None
    selected_dte: float | None = Field(default=None, ge=0)
    future_reference_price: float | None = Field(default=None, gt=0)
    traded_reference_price: float | None = Field(default=None, gt=0)
    basis_points: float | None = None
    expected_move: float | None = Field(default=None, ge=0)
    mapped_lower_1sd: float | None = Field(default=None, gt=0)
    mapped_lower_2sd: float | None = Field(default=None, gt=0)
    mapped_lower_3sd: float | None = Field(default=None, gt=0)
    mapped_upper_1sd: float | None = Field(default=None, gt=0)
    mapped_upper_2sd: float | None = Field(default=None, gt=0)
    mapped_upper_3sd: float | None = Field(default=None, gt=0)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only(self) -> XauSdMeanReversionPlan:
        if self.signal_allowed:
            raise ValueError("Vol2Vol walk-forward plans cannot enable signals")
        if not self.research_only:
            raise ValueError("Vol2Vol walk-forward plans must remain research_only")
        return self


class XauWalkforwardTradeOutcome(XauBaseModel):
    plan_id: str
    session_date: date
    side: XauTradeSide
    entry_sd: XauSdEntryLevel
    tp_mode: XauTpMode
    sl_mode: XauSlMode
    status: XauWalkforwardTradeStatus
    baseline_config: str = "custom"
    entry_type: XauEntryType = XauEntryType.TOUCH
    cycle_label: str = "manual"
    cost_points: float = Field(default=0, ge=0)
    triggered_at: datetime | None = None
    exited_at: datetime | None = None
    entry_level: float | None = None
    target_level: float | None = None
    stop_level: float | None = None
    exit_level: float | None = None
    mfe_points: float | None = None
    mae_points: float | None = None
    max_drawdown_points: float | None = None
    time_to_exit_minutes: float | None = Field(default=None, ge=0)
    bars_evaluated: int = Field(ge=0)
    simulation_window_start: datetime | None = None
    simulation_window_end: datetime | None = None
    plan_observed_at: datetime | None = None
    first_bar_used: datetime | None = None
    last_bar_used: datetime | None = None
    window_alignment_status: XauWindowAlignmentStatus = XauWindowAlignmentStatus.INVALID
    ambiguity_notes: list[str] = Field(default_factory=list)
    same_bar_ambiguous: bool = False
    raw_result: str | None = None
    gross_points: float | None = None
    total_cost_points: float | None = Field(default=None, ge=0)
    net_points: float | None = None
    time_exit_policy: XauTimeExitPolicy = XauTimeExitPolicy.CLOSE_AT_CYCLE_END
    include_in_expectancy: bool = True
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only(self) -> XauWalkforwardTradeOutcome:
        if self.signal_allowed:
            raise ValueError("Vol2Vol walk-forward outcomes cannot enable signals")
        if not self.research_only:
            raise ValueError("Vol2Vol walk-forward outcomes must remain research_only")
        return self


class XauWalkforwardStats(XauBaseModel):
    run_id: str
    session_date_from: date | None = None
    session_date_to: date | None = None
    plan_count: int = Field(ge=0)
    triggered_count: int = Field(ge=0)
    no_fill_count: int = Field(ge=0)
    target_hit_count: int = Field(ge=0)
    stop_hit_count: int = Field(ge=0)
    expired_count: int = Field(ge=0)
    ambiguous_count: int = Field(ge=0)
    unavailable_count: int = Field(default=0, ge=0)
    time_exit_profit_count: int = Field(default=0, ge=0)
    time_exit_loss_count: int = Field(default=0, ge=0)
    fill_rate: float | None = Field(default=None, ge=0, le=1)
    target_hit_rate_after_fill: float | None = Field(default=None, ge=0, le=1)
    stop_hit_rate_after_fill: float | None = Field(default=None, ge=0, le=1)
    avg_mfe_points: float | None = None
    avg_mae_points: float | None = None
    worst_mae_points: float | None = None
    median_mfe_points: float | None = None
    median_mae_points: float | None = None
    mae_p90_points: float | None = None
    mae_p95_points: float | None = None
    gross_expectancy_points: float | None = None
    net_expectancy_points: float | None = None
    target_hit_expectancy_points: float | None = None
    profit_factor_points: float | None = None
    maximum_cumulative_drawdown_points: float | None = None
    maximum_consecutive_losses: int = Field(default=0, ge=0)
    avg_time_to_exit_minutes: float | None = Field(default=None, ge=0)
    grouped_stats: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only(self) -> XauWalkforwardStats:
        if self.signal_allowed:
            raise ValueError("Vol2Vol walk-forward stats cannot enable signals")
        if not self.research_only:
            raise ValueError("Vol2Vol walk-forward stats must remain research_only")
        return self


class XauDailySdPathRecord(XauBaseModel):
    morning_plan_id: str
    session_date: date
    cycle_label: str
    planning_at: datetime
    simulation_window_start: datetime
    simulation_window_end: datetime
    selected_snapshot_time: datetime
    selected_xau_price_time: datetime
    selected_series: str | None = None
    dte: float | None = Field(default=None, ge=0)
    future_reference_price: float
    traded_reference_price: float
    basis_points: float
    basis_alignment_seconds: float = Field(ge=0)
    expected_move: float | None = Field(default=None, ge=0)
    lower_1sd: float
    lower_1_5sd: float
    lower_2sd: float
    lower_2_5sd: float
    lower_3sd: float
    upper_1sd: float
    upper_1_5sd: float
    upper_2sd: float
    upper_2_5sd: float
    upper_3sd: float
    reached_lower_1sd: bool
    reached_lower_1_5sd: bool
    reached_lower_2sd: bool
    reached_lower_2_5sd: bool
    reached_lower_3sd: bool
    reached_upper_1sd: bool
    reached_upper_1_5sd: bool
    reached_upper_2sd: bool
    reached_upper_2_5sd: bool
    reached_upper_3sd: bool
    first_lower_2sd_touch_time: datetime | None = None
    first_upper_2sd_touch_time: datetime | None = None
    first_lower_3sd_touch_time: datetime | None = None
    first_upper_3sd_touch_time: datetime | None = None
    maximum_positive_sd: float
    maximum_negative_sd: float
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only(self) -> XauDailySdPathRecord:
        if self.signal_allowed or not self.research_only:
            raise ValueError("Daily SD paths must remain research-only")
        return self


class XauMarketOpportunity(XauBaseModel):
    opportunity_id: str
    morning_plan_id: str
    session_date: date
    cycle_label: str
    side: XauTradeSide
    entry_sd: XauSdEntryLevel
    entry_level: float
    first_touch_time: datetime
    configuration_plan_ids: list[str] = Field(default_factory=list)
    configuration_fill_count: int = Field(default=0, ge=0)
    cost_scenario_filled_row_count: int = Field(default=0, ge=0)
    target_configuration_count: int = Field(default=0, ge=0)
    stop_configuration_count: int = Field(default=0, ge=0)
    time_exit_configuration_count: int = Field(default=0, ge=0)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only(self) -> XauMarketOpportunity:
        if self.signal_allowed or not self.research_only:
            raise ValueError("Market opportunities must remain research-only")
        return self
