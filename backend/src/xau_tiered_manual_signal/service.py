from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.config import get_reports_path
from src.models.xau_market_context import XauPriceBar
from src.models.xau_tiered_manual_signal import (
    XauBrokerQuote,
    XauManualSignal,
    XauManualSignalAcknowledgement,
    XauManualSignalAcknowledgementRequest,
    XauManualSignalLatestResponse,
    XauManualSignalState,
)
from src.xau_first_touch_study.models import CountingMode, EventSide, MappingMode, TimeAnchor
from src.xau_first_touch_study.selection import (
    load_source_snapshots,
    map_selection,
    select_snapshot,
)
from src.xau_tiered_manual_signal.journal import ManualSignalJournal
from src.xau_tiered_manual_signal.policy import load_policy
from src.xau_tiered_manual_signal.tiers import (
    build_tier_events,
    executable_rejection_entry,
    extended_tier_levels,
    qualifying_lower_oi_zone,
)
from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_raw_path,
    evaluate_daily_session_eligibility,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


class XauTieredManualSignalService:
    def __init__(
        self,
        *,
        journal_root: Path | None = None,
        policy_path: Path = Path("config/xau_tiered_first_touch_manual_signal_v1.json"),
        vol2vol_root: Path = Path("data/imports/vol2vol"),
        price_bars_folder: Path = Path("data/imports/xau/dukascopy/xauusd/m1"),
        timezone: str = "Asia/Bangkok",
    ) -> None:
        self.policy = load_policy(policy_path)
        self.vol2vol_root = vol2vol_root
        self.price_bars_folder = price_bars_folder
        self.timezone = timezone
        self.journal = ManualSignalJournal(
            journal_root or get_reports_path() / "xau_manual_signals",
            self.policy["policy_hash"],
        )

    def process_current(
        self,
        *,
        session_date: date,
        broker_quote: XauBrokerQuote | None = None,
        now: datetime | None = None,
    ) -> XauManualSignalLatestResponse:
        current_time = now or datetime.now(UTC)
        eligibility = evaluate_daily_session_eligibility(
            root=self.vol2vol_root,
            session_date=session_date,
            current_date=session_date,
        )
        raw_path = daily_raw_path(self.vol2vol_root, session_date)
        if not eligibility.forward_plan_eligible or not raw_path.exists():
            plan = self._blocked_plan(session_date, eligibility.reasons)
            self._append_once("plans", plan, "plan_id")
            self._append_daily_summary(session_date, "DATA_BLOCKED", 0)
            return XauManualSignalLatestResponse(plan=plan)

        price_result = load_traded_bars_folder(
            self.price_bars_folder,
            timezone=self.timezone,
        )
        session_bars = [
            item
            for item in price_result.bars
            if item.timestamp.astimezone(ZoneInfo(self.timezone)).date() == session_date
            and item.timestamp + timedelta(minutes=1) <= current_time
        ]
        snapshots = load_source_snapshots(raw_path, session_date)
        selection = select_snapshot(
            snapshots,
            anchor=TimeAnchor.T0_DTE_080,
            session_date=session_date,
            timezone=self.timezone,
            target_dte=self.policy["canonical_plan"]["target_source_dte"],
            dte_tolerance=(
                self.policy["canonical_plan"]["maximum_source_dte"]
                - self.policy["canonical_plan"]["target_source_dte"]
            ),
        )
        reasons = self._selection_reasons(selection, session_bars, current_time)
        plan = (
            map_selection(
                selection,
                session_bars,
                mapping_mode=MappingMode.DISTANCE_REANCHORED,
            )
            if selection is not None and not reasons
            else None
        )
        if plan is None:
            blocked = self._blocked_plan(session_date, reasons or ["Mapping unavailable."])
            self._append_once("plans", blocked, "plan_id")
            self._append_daily_summary(session_date, "DATA_BLOCKED", 0)
            return XauManualSignalLatestResponse(plan=blocked)

        plan_record = {
            "plan_id": f"xau_tiered_plan_{session_date.isoformat()}",
            "session_date": session_date.isoformat(),
            "status": XauManualSignalState.PLAN_READY.value,
            "source_dte": plan.selection.snapshot.source_dte,
            "selected_series": plan.selection.snapshot.series,
            "selected_snapshot_timestamp": plan.selection.snapshot.observed_at.isoformat(),
            "mapping_mode": plan.mapping_mode.value,
            "mapping_quality": plan.mapping_quality,
            "levels": {
                str(tier): {"lower": levels[0], "upper": levels[1]}
                for tier, levels in extended_tier_levels(plan).items()
            },
            "data_block_reasons": [],
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }
        self._append_once("plans", plan_record, "plan_id")
        events = build_tier_events(
            plan,
            session_bars,
            counting_mode=CountingMode.AGGREGATED,
        )
        emitted: list[XauManualSignal] = []
        active = self._has_active_manual_candidate()
        for event in events:
            signal = self._signal_for_event(
                plan=plan,
                event=event,
                bars=session_bars,
                broker_quote=broker_quote,
                now=current_time,
                active_candidate=active,
            )
            if signal is None:
                continue
            try:
                self.journal.append(
                    "signals",
                    signal.model_dump(mode="json"),
                    id_field="signal_id",
                )
            except ValueError:
                continue
            emitted.append(signal)
            if signal.status == XauManualSignalState.MANUAL_CANDIDATE:
                active = True
        self._append_daily_summary(session_date, "PLAN_READY", len(emitted))
        latest = emitted[-1] if emitted else None
        return XauManualSignalLatestResponse(signal=latest, plan=plan_record)

    def latest(self) -> XauManualSignalLatestResponse:
        signal_row = self.journal.latest("signals")
        plan = self.journal.latest("plans")
        signal = (
            XauManualSignal.model_validate(_model_fields(XauManualSignal, signal_row))
            if signal_row
            else None
        )
        acknowledgement = None
        if signal:
            matching = [
                item
                for item in self.journal.read("acknowledgements")
                if item.get("signal_id") == signal.signal_id
            ]
            if matching:
                acknowledgement = XauManualSignalAcknowledgement.model_validate(
                    _model_fields(XauManualSignalAcknowledgement, matching[-1])
                )
        return XauManualSignalLatestResponse(
            signal=signal,
            acknowledgement=acknowledgement,
            plan=plan,
        )

    def acknowledge(
        self,
        signal_id: str,
        request: XauManualSignalAcknowledgementRequest,
    ) -> XauManualSignalAcknowledgement:
        signal = next(
            (
                item
                for item in self.journal.read("signals")
                if item.get("signal_id") == signal_id
            ),
            None,
        )
        if signal is None:
            raise FileNotFoundError(f"Manual signal not found: {signal_id}")
        if signal["status"] not in {
            XauManualSignalState.MANUAL_CANDIDATE.value,
            XauManualSignalState.REFERENCE_ALERT.value,
        }:
            raise ValueError("Only manual candidates or reference alerts may be acknowledged")
        acknowledgement = XauManualSignalAcknowledgement(
            acknowledgement_id=f"ack_{uuid4().hex}",
            signal_id=signal_id,
            acknowledged_at=datetime.now(UTC),
            acknowledged_by=request.acknowledged_by,
            note=request.note,
        )
        self.journal.append(
            "acknowledgements",
            acknowledgement.model_dump(mode="json"),
            id_field="acknowledgement_id",
        )
        return acknowledgement

    def _signal_for_event(
        self,
        *,
        plan: Any,
        event: Any,
        bars: list[XauPriceBar],
        broker_quote: XauBrokerQuote | None,
        now: datetime,
        active_candidate: bool,
    ) -> XauManualSignal | None:
        tier_policy = next(
            item
            for item in self.policy["tier_matrix"]
            if float(item["tier"]) == float(event.tier)
        )
        barrier_id = tier_policy["primary_barrier"]
        barrier = self.policy["barriers"][barrier_id]
        status = XauManualSignalState(tier_policy["initial_state"]) if tier_policy[
            "initial_state"
        ] != "TAIL_WATCH" else XauManualSignalState.SHADOW_ONLY
        evidence_status = tier_policy.get("evidence_status", "experimental")
        reference_entry = event.boundary
        confirmation = None
        zone = None
        block_reasons: list[str] = []
        if float(event.tier) == 2.0 and event.side == EventSide.LOWER_LONG:
            zone = qualifying_lower_oi_zone(
                plan,
                maximum_distance_points=self.policy["oi_zone"][
                    "maximum_wall_distance_points"
                ],
                minimum_percentile=self.policy["oi_zone"]["minimum_oi_percentile"],
            )
            if zone is None:
                status = XauManualSignalState.FIRST_TOUCH_DETECTED
                block_reasons.append("QUALIFYING_OI_ZONE_UNAVAILABLE")
            elif zone.source_snapshot_at > event.touch_timestamp:
                status = XauManualSignalState.FIRST_TOUCH_DETECTED
                block_reasons.append("OI_SNAPSHOT_AFTER_FIRST_TOUCH")
            else:
                confirmation = executable_rejection_entry(
                    zone,
                    event,
                    bars,
                    rule="R1_BOUNDARY",
                )
                if confirmation is None:
                    status = XauManualSignalState.FIRST_TOUCH_DETECTED
                    block_reasons.append("REJECTION_NOT_CONFIRMED")
                else:
                    reference_entry = confirmation["entry_price"]
                    status = XauManualSignalState.REFERENCE_ALERT
                    if active_candidate:
                        status = XauManualSignalState.MISSED_DUE_TO_ACTIVE_POSITION
                        block_reasons.append("ACTIVE_MANUAL_CANDIDATE_EXISTS")
                    elif broker_quote is not None:
                        broker_gate = self._broker_translation(
                            broker_quote,
                            bars,
                            reference_entry,
                            now,
                        )
                        block_reasons.extend(broker_gate["reasons"])
                        if not broker_gate["reasons"]:
                            status = XauManualSignalState.MANUAL_CANDIDATE
                    else:
                        block_reasons.append("BROKER_QUOTE_REQUIRED_FOR_EXACT_ENTRY")
        elif event.side == EventSide.UPPER_SHORT:
            status = XauManualSignalState.SHADOW_ONLY
            evidence_status = "upper_side_observe_only"

        direction = 1 if event.side == EventSide.LOWER_LONG else -1
        reference_tp = reference_entry + direction * barrier["take_profit_points"]
        reference_sl = reference_entry - direction * barrier["stop_loss_points"]
        broker = (
            self._broker_translation(broker_quote, bars, reference_entry, now)
            if broker_quote is not None
            else None
        )
        offset = broker["offset"] if broker and not broker["reasons"] else None
        return XauManualSignal(
            signal_id=(
                f"xau_ft_{event.session_date.isoformat()}_{event.side.value}_"
                f"{float(event.tier):g}sd_{barrier_id.lower()}"
            ),
            session_date=event.session_date.isoformat(),
            status=status,
            evidence_status=evidence_status,
            broker_symbol=broker_quote.symbol if broker_quote else None,
            side="BUY" if direction > 0 else "SELL",
            tier=float(event.tier),
            barrier_id=barrier_id,
            first_touch=True,
            entry=reference_entry + offset if offset is not None else None,
            take_profit=reference_tp + offset if offset is not None else None,
            stop_loss=reference_sl + offset if offset is not None else None,
            reference_entry=reference_entry,
            reference_take_profit=reference_tp,
            reference_stop_loss=reference_sl,
            source_dte=event.source_dte,
            selected_series=event.source_series,
            mapping_mode=plan.mapping_mode.value,
            mapping_quality=plan.mapping_quality,
            selected_snapshot_timestamp=plan.selection.snapshot.observed_at,
            xau_reference_timestamp=plan.planning_xau_timestamp,
            touch_timestamp=event.touch_timestamp,
            confirmation_timestamp=(
                confirmation["confirmation_timestamp"] if confirmation else None
            ),
            entry_timestamp=confirmation["entry_timestamp"] if confirmation else None,
            source_gap_seconds=plan.source_gap_seconds,
            current_spread_points=broker["spread"] if broker else None,
            broker_offset_points=offset,
            oi_zone_lower=zone.lower if zone else None,
            oi_zone_upper=zone.upper if zone else None,
            oi_percentile=zone.oi_percentile if zone else None,
            rejection_rule=confirmation["rule"] if confirmation else None,
            data_block_reasons=block_reasons,
        )

    def _broker_translation(
        self,
        quote: XauBrokerQuote,
        bars: list[XauPriceBar],
        reference_entry: float,
        now: datetime,
    ) -> dict[str, Any]:
        reasons = []
        age = (now - quote.timestamp.astimezone(now.tzinfo)).total_seconds()
        spread = quote.ask - quote.bid
        if age < 0 or age > self.policy["data_gates"]["maximum_broker_quote_age_seconds"]:
            reasons.append("BROKER_QUOTE_STALE")
        if spread > self.policy["data_gates"]["maximum_broker_spread_points"]:
            reasons.append("BROKER_SPREAD_TOO_WIDE")
        reference = max(
            (item for item in bars if item.timestamp <= quote.timestamp),
            key=lambda item: item.timestamp,
            default=None,
        )
        if reference is None:
            reasons.append("SYNCHRONIZED_REFERENCE_PRICE_UNAVAILABLE")
            offset = None
        else:
            offset = ((quote.bid + quote.ask) / 2) - reference.close
        return {
            "reasons": reasons,
            "spread": spread,
            "offset": offset,
            "reference_entry": reference_entry,
        }

    def _selection_reasons(
        self,
        selection: Any,
        bars: list[XauPriceBar],
        now: datetime,
    ) -> list[str]:
        if selection is None:
            return ["T0_DTE_080_SELECTION_UNAVAILABLE"]
        dte = selection.snapshot.source_dte
        reasons = []
        if not (
            self.policy["canonical_plan"]["minimum_source_dte"]
            <= dte
            <= self.policy["canonical_plan"]["maximum_source_dte"]
        ):
            reasons.append("SOURCE_DTE_OUTSIDE_FROZEN_RANGE")
        if selection.snapshot.observed_at > selection.activation_at:
            reasons.append("FUTURE_SNAPSHOT_REJECTED")
        if not bars:
            reasons.append("XAUUSD_PRICE_UNAVAILABLE")
        elif (now - max(item.timestamp for item in bars)).total_seconds() > self.policy[
            "data_gates"
        ]["maximum_xau_price_age_seconds"]:
            reasons.append("XAUUSD_PRICE_STALE")
        return reasons

    def _has_active_manual_candidate(self) -> bool:
        closed_signal_ids = {
            item.get("signal_id") for item in self.journal.read("outcomes")
        }
        return any(
            item.get("status") == XauManualSignalState.MANUAL_CANDIDATE
            and item.get("signal_id") not in closed_signal_ids
            for item in self.journal.read("signals")
        )

    def _blocked_plan(self, session_date: date, reasons: list[str]) -> dict[str, Any]:
        return {
            "plan_id": f"xau_tiered_plan_{session_date.isoformat()}",
            "session_date": session_date.isoformat(),
            "status": XauManualSignalState.DATA_BLOCKED.value,
            "data_block_reasons": reasons,
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }

    def _append_once(self, stream: str, row: dict[str, Any], id_field: str) -> None:
        try:
            self.journal.append(stream, row, id_field=id_field)
        except ValueError:
            pass

    def _append_daily_summary(
        self,
        session_date: date,
        status: str,
        signal_count: int,
    ) -> None:
        row = {
            "summary_id": f"xau_tiered_summary_{session_date.isoformat()}",
            "session_date": session_date.isoformat(),
            "status": status,
            "signal_count": signal_count,
        }
        self._append_once("daily_summary", row, "summary_id")


def _model_fields(model: Any, row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in model.model_fields if key in row}
