from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field, model_validator

from src.models.xau import XauBaseModel


class XauOptionsResearchExperiment(XauBaseModel):
    experiment_id: str
    hypothesis: str
    feature_definitions: list[str]
    entry_rule: str
    outcome_label: str
    threshold_source: str
    development_holdout_policy: str
    experiment_hash: str


class XauOptionsCheckpoint(XauBaseModel):
    checkpoint_id: str
    session_date: date
    planning_mode: str
    checkpoint_at: datetime
    source_snapshot_at: datetime
    selected_series: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_guardrails(self) -> XauOptionsCheckpoint:
        if not self.research_only or self.signal_allowed:
            raise ValueError("Options research checkpoints must remain research-only")
        return self


class XauOptionsEvent(XauBaseModel):
    event_id: str
    episode_id: str
    session_date: date
    planning_mode: str
    event_type: str
    side: str
    event_timestamp: datetime
    checkpoint_id: str
    entry_price: float
    one_sd_points: float = Field(gt=0)
    features: dict[str, Any] = Field(default_factory=dict)
    reset_timestamp: datetime | None = None
    reset_reason: str | None = None
    research_only: bool = True
    signal_allowed: bool = False

    @model_validator(mode="after")
    def validate_guardrails(self) -> XauOptionsEvent:
        if not self.research_only or self.signal_allowed:
            raise ValueError("Options research events must remain research-only")
        return self
