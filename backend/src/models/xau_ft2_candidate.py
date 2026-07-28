from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from src.models.xau import XauBaseModel


class XauFt2State(StrEnum):
    DATA_BLOCKED = "DATA_BLOCKED"
    PLAN_READY = "PLAN_READY"
    WAITING_FOR_FIRST_TOUCH = "WAITING_FOR_FIRST_TOUCH"
    REFERENCE_ALERT = "REFERENCE_ALERT"
    PROVISIONAL_MANUAL_ALERT = "PROVISIONAL_MANUAL_ALERT"
    TIER_LOCKED = "TIER_LOCKED"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    AMBIGUOUS = "AMBIGUOUS"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class XauFt2BrokerQuote(XauBaseModel):
    timestamp: datetime
    symbol: str
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_quote(self) -> XauFt2BrokerQuote:
        if self.timestamp.tzinfo is None:
            raise ValueError("broker quote timestamp must be timezone-aware")
        if self.ask < self.bid:
            raise ValueError("broker ask must be greater than or equal to bid")
        return self


class XauFt2Alert(XauBaseModel):
    alert_id: str
    candidate_id: str
    candidate_hash: str
    session_date: str
    status: XauFt2State
    side: str
    source_symbol: str
    broker_symbol: str | None = None
    selected_series: str
    source_dte: float
    original_futures_reference: float
    raw_futures_2sd_level: float
    mapped_xauusd_level: float
    broker_translated_level: float | None = None
    reference_take_profit: float
    reference_stop_loss: float
    take_profit: float | None = None
    stop_loss: float | None = None
    selected_snapshot_timestamp: datetime
    activation_timestamp: datetime
    xau_reference_timestamp: datetime
    touch_timestamp: datetime
    source_gap_seconds: float
    mapping_mode: str
    mapping_quality: str
    spread_points: float | None = None
    broker_offset_points: float | None = None
    oi_context: dict = Field(default_factory=dict)
    iv_context: dict = Field(default_factory=dict)
    volume_context: dict = Field(default_factory=dict)
    rejection_context: dict = Field(default_factory=dict)
    evidence_status: str = "external_location_prior_plus_three_local_events"
    research_warning: str = (
        "Provisional manual research alert only; no order is submitted."
    )
    data_block_reasons: list[str] = Field(default_factory=list)
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False

    @model_validator(mode="after")
    def validate_guardrails(self) -> XauFt2Alert:
        if not self.research_only or self.signal_allowed or self.order_submission_allowed:
            raise ValueError("FT2 alerts must remain research-only and non-executable")
        return self


class XauFt2AcknowledgementRequest(XauBaseModel):
    acknowledged_by: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class XauFt2LatestResponse(XauBaseModel):
    plan: dict | None = None
    event: dict | None = None
    alert: XauFt2Alert | None = None
    acknowledgement: dict | None = None
    outcome: dict | None = None
    research_only: bool = True
    signal_allowed: bool = False
    order_submission_allowed: bool = False
