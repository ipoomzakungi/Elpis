from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from src.models.xau import XauBaseModel


class XauManualSignalState(StrEnum):
    DATA_BLOCKED = "DATA_BLOCKED"
    PLAN_READY = "PLAN_READY"
    WAITING = "WAITING"
    FIRST_TOUCH_DETECTED = "FIRST_TOUCH_DETECTED"
    REFERENCE_ALERT = "REFERENCE_ALERT"
    SHADOW_ONLY = "SHADOW_ONLY"
    MANUAL_CANDIDATE = "MANUAL_CANDIDATE"
    MANUAL_ACKNOWLEDGED = "MANUAL_ACKNOWLEDGED"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    AMBIGUOUS = "AMBIGUOUS"
    EXPIRED = "EXPIRED"
    TIER_LOCKED = "TIER_LOCKED"
    MISSED_DUE_TO_ACTIVE_POSITION = "MISSED_DUE_TO_ACTIVE_POSITION"


class XauBrokerQuote(XauBaseModel):
    timestamp: datetime
    symbol: str
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_quote(self) -> XauBrokerQuote:
        if self.timestamp.tzinfo is None:
            raise ValueError("broker quote timestamp must be timezone-aware")
        if self.ask < self.bid:
            raise ValueError("broker ask must be greater than or equal to bid")
        return self


class XauManualSignal(XauBaseModel):
    signal_id: str
    session_date: str
    status: XauManualSignalState
    evidence_status: str
    symbol_reference: str = "Dukascopy XAUUSD"
    broker_symbol: str | None = None
    side: str
    tier: float
    barrier_id: str
    first_touch: bool
    entry: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    reference_entry: float
    reference_take_profit: float
    reference_stop_loss: float
    source_dte: float
    selected_series: str
    mapping_mode: str
    mapping_quality: str
    selected_snapshot_timestamp: datetime
    xau_reference_timestamp: datetime
    touch_timestamp: datetime
    confirmation_timestamp: datetime | None = None
    entry_timestamp: datetime | None = None
    source_gap_seconds: float
    current_spread_points: float | None = None
    broker_offset_points: float | None = None
    expires_at: str = "session_end"
    oi_zone_lower: float | None = None
    oi_zone_upper: float | None = None
    oi_percentile: float | None = None
    rejection_rule: str | None = None
    data_block_reasons: list[str] = Field(default_factory=list)
    research_warning: str = "Manual research alert only; no order is submitted."
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False

    @model_validator(mode="after")
    def validate_guardrails(self) -> XauManualSignal:
        if not self.research_only or self.signal_allowed or self.order_submission_allowed:
            raise ValueError("manual alerts must remain research-only and non-executable")
        return self


class XauManualSignalAcknowledgementRequest(XauBaseModel):
    acknowledged_by: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class XauManualSignalAcknowledgement(XauBaseModel):
    acknowledgement_id: str
    signal_id: str
    acknowledged_at: datetime
    acknowledged_by: str
    note: str | None = None
    status: XauManualSignalState = XauManualSignalState.MANUAL_ACKNOWLEDGED
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False


class XauManualSignalLatestResponse(XauBaseModel):
    signal: XauManualSignal | None = None
    acknowledgement: XauManualSignalAcknowledgement | None = None
    plan: dict | None = None
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False
