from __future__ import annotations

from datetime import date, datetime, time
from datetime import time as datetime_time

from pydantic import Field, field_validator, model_validator

from src.models.xau import XauBaseModel
from src.models.xau_price_plan_tracker import XauResearchOrderSide, XauTrackedOrderStatus

PLAN_TRACKER_STATS_NO_SIGNAL_REASON = (
    "Feature 028 is a research-only plan-tracker outcome analytics layer; no signal "
    "generation or execution is enabled."
)


class XauPlanTrackerStatsRequest(XauBaseModel):
    session_date_from: date | None = None
    session_date_to: date | None = None
    planning_times: list[time] = Field(default_factory=list)
    sides: list[XauResearchOrderSide] = Field(default_factory=list)
    statuses: list[XauTrackedOrderStatus] = Field(default_factory=list)
    include_unavailable_orders: bool = False
    max_runs: int | None = Field(default=None, ge=1)

    @field_validator("planning_times", mode="before")
    @classmethod
    def parse_planning_times(
        cls,
        value: list[datetime_time | str],
    ) -> list[time]:
        return [_parse_time(item) for item in value]

    @model_validator(mode="after")
    def validate_request(self) -> XauPlanTrackerStatsRequest:
        if (
            self.session_date_from is not None
            and self.session_date_to is not None
            and self.session_date_from > self.session_date_to
        ):
            raise ValueError("session_date_from must be <= session_date_to")
        self.planning_times = _dedupe(self.planning_times)
        self.sides = _dedupe(self.sides)
        self.statuses = _dedupe(self.statuses)
        return self


class XauPlanTrackerStatsRunSummary(XauBaseModel):
    run_id: str
    session_date: date
    snapshot_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
    side_counts: dict[str, int] = Field(default_factory=dict)
    planning_time_counts: dict[str, int] = Field(default_factory=dict)
    near_miss_count: int = Field(ge=0)
    strict_triggered_count: int = Field(ge=0)
    avg_current_pnl_points: float | None = Field(default=None)
    avg_drawdown_points: float | None = Field(default=None)


class XauPlanTrackerDteStats(XauBaseModel):
    sample_count: int = Field(ge=0)
    min: float | None = None
    max: float | None = None
    average: float | None = None


class XauPlanTrackerStatsResult(XauBaseModel):
    generated_at: datetime
    run_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    run_ids: list[str] = Field(default_factory=list)
    planning_time_filter: list[time] = Field(default_factory=list)
    side_filter: list[XauResearchOrderSide] = Field(default_factory=list)
    status_filter: list[XauTrackedOrderStatus] = Field(default_factory=list)
    include_unavailable_orders: bool = False
    status_counts: dict[str, int] = Field(default_factory=dict)
    side_counts: dict[str, int] = Field(default_factory=dict)
    planning_time_counts: dict[str, int] = Field(default_factory=dict)
    recovery_order_count: int = Field(ge=0)
    near_miss_count: int = Field(ge=0)
    strict_triggered_count: int = Field(ge=0)
    avg_current_pnl_points: float | None = Field(default=None)
    max_current_pnl_points: float | None = None
    min_current_pnl_points: float | None = None
    avg_drawdown_points: float | None = Field(default=None)
    avg_mfe_points: float | None = Field(default=None)
    avg_mae_points: float | None = Field(default=None)
    dte_summary: XauPlanTrackerDteStats = Field(default_factory=XauPlanTrackerDteStats)
    run_summaries: list[XauPlanTrackerStatsRunSummary] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    no_signal_reasons: list[str] = Field(
        default_factory=lambda: [PLAN_TRACKER_STATS_NO_SIGNAL_REASON]
    )
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_research_only_state(self) -> XauPlanTrackerStatsResult:
        if self.signal_allowed:
            raise ValueError("plan-tracker stats cannot enable signals")
        if not self.research_only:
            raise ValueError("plan-tracker stats must remain research_only")
        if not self.no_signal_reasons:
            raise ValueError("plan-tracker stats require no_signal_reasons")
        return self



def _parse_time(value: time | str) -> time:
    if isinstance(value, datetime_time):
        return value
    try:
        hour, minute = str(value).split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError) as exc:
        raise ValueError("time values must use HH:MM format") from exc


def _dedupe(values: list) -> list:
    output: list = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


__all__ = [
    "PLAN_TRACKER_STATS_NO_SIGNAL_REASON",
    "XauPlanTrackerDteStats",
    "XauPlanTrackerStatsRequest",
    "XauPlanTrackerStatsResult",
    "XauPlanTrackerStatsRunSummary",
]
