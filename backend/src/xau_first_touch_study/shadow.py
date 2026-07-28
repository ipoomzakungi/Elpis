from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.xau_first_touch_study.models import (
    EventOutcome,
    FirstPassageStatus,
    FirstTouchEvent,
    MappedPlan,
    ShadowState,
)


@dataclass
class ShadowSession:
    state: ShadowState = ShadowState.DATA_BLOCKED
    locked_tiers: set[int] = field(default_factory=set)
    active_event_id: str | None = None
    transitions: list[dict[str, Any]] = field(default_factory=list)

    def load_plan(self, plan: MappedPlan | None) -> None:
        self._transition(ShadowState.PLAN_READY if plan else ShadowState.DATA_BLOCKED)
        if plan:
            self._transition(ShadowState.WAITING_FOR_FIRST_TOUCH)

    def first_touch(self, event: FirstTouchEvent) -> dict[str, Any] | None:
        if event.tier in self.locked_tiers:
            self._transition(ShadowState.TIER_LOCKED, event.event_id)
            return None
        if self.active_event_id is not None:
            return None
        tier_state = {
            1: ShadowState.FIRST_TOUCH_1SD_CONTROL,
            2: ShadowState.FIRST_TOUCH_2SD_ARMED,
            3: ShadowState.FIRST_TOUCH_3SD_ARMED,
        }[event.tier]
        self._transition(tier_state, event.event_id)
        self.locked_tiers.add(event.tier)
        if event.tier == 1:
            self._transition(ShadowState.TIER_LOCKED, event.event_id)
            return None
        self.active_event_id = event.event_id
        self._transition(ShadowState.SHADOW_POSITION_OPEN, event.event_id)
        direction = 1 if event.side.value == "lower_long" else -1
        return {
            "event_id": event.event_id,
            "side": event.side.value,
            "mapped_entry": event.boundary,
            "tp": event.boundary + direction * 25,
            "sl": event.boundary - direction * 25,
            "tier": event.tier,
            "source_dte": event.source_dte,
            "source_series": event.source_series,
            "mapping_mode": event.mapping_mode.value,
            "spread_assumption_points": 1.0,
            "estimated_maximum_loss_points": 26.0,
            "decision_reason": "literal first touch, shadow observation only",
            "research_warning": "No order is created or submitted.",
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }

    def resolve(self, outcome: EventOutcome) -> None:
        if outcome.event_id != self.active_event_id:
            return
        state = {
            FirstPassageStatus.TP_FIRST.value: ShadowState.TP_HIT,
            FirstPassageStatus.SL_FIRST.value: ShadowState.SL_HIT,
            FirstPassageStatus.SAME_BAR_AMBIGUOUS.value: ShadowState.AMBIGUOUS,
        }.get(outcome.status, ShadowState.SESSION_EXPIRED)
        self._transition(state, outcome.event_id)
        self.active_event_id = None

    def expire(self) -> None:
        self._transition(ShadowState.SESSION_EXPIRED, self.active_event_id)
        self.active_event_id = None

    def as_record(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "locked_tiers": sorted(self.locked_tiers),
            "active_event_id": self.active_event_id,
            "transitions": self.transitions,
            "broker_orders": [],
            "averaging_allowed": False,
            "recovery_allowed": False,
            "martingale_allowed": False,
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }

    def _transition(
        self,
        state: ShadowState,
        event_id: str | None = None,
    ) -> None:
        self.state = state
        self.transitions.append({"state": state.value, "event_id": event_id})
