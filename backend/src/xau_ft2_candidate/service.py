from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.config import get_reports_path
from src.models.xau_ft2_candidate import (
    XauFt2AcknowledgementRequest,
    XauFt2Alert,
    XauFt2BrokerQuote,
    XauFt2LatestResponse,
    XauFt2OrderType,
    XauFt2State,
)
from src.models.xau_market_context import XauPriceBar
from src.xau_first_touch_study.models import MappingMode, TimeAnchor
from src.xau_first_touch_study.selection import (
    load_source_snapshots,
    map_selection,
    select_snapshot,
)
from src.xau_ft2_candidate.integrity_policy import (
    load_integrity_policy,
    synchronized_reference_accepted,
)
from src.xau_ft2_candidate.journal import Ft2CandidateJournal
from src.xau_ft2_candidate.policy import load_candidate_policy
from src.xau_vol2vol_history_walkforward.data_lake import (
    daily_raw_path,
    evaluate_daily_session_eligibility,
)
from src.xau_vol2vol_history_walkforward.walkforward_simulator import (
    load_traded_bars_folder,
)


class XauFt2CandidateService:
    def __init__(
        self,
        *,
        journal_root: Path | None = None,
        policy_path: Path = Path("config/xau_ft2_raw_candidate_v1.json"),
        integrity_policy_path: Path = Path("config/xau_ft2_integrity_v1.json"),
        vol2vol_root: Path = Path("data/imports/vol2vol"),
        price_bars_folder: Path = Path("data/imports/xau/dukascopy/xauusd/m1"),
        timezone: str = "Asia/Bangkok",
    ) -> None:
        self.policy = load_candidate_policy(policy_path)
        self.integrity_policy = load_integrity_policy(
            integrity_policy_path,
            candidate_policy_path=policy_path,
        )
        self.vol2vol_root = vol2vol_root
        self.price_bars_folder = price_bars_folder
        self.timezone = timezone
        self.journal = Ft2CandidateJournal(
            journal_root or get_reports_path() / "xau_ft2_candidate" / "v1",
            self.policy["candidate_hash"],
        )

    def process_session(
        self,
        *,
        session_date: date,
        broker_quote: XauFt2BrokerQuote | None = None,
        now: datetime | None = None,
    ) -> XauFt2LatestResponse:
        current_time = now or datetime.now(UTC)
        price_result = load_traded_bars_folder(
            self.price_bars_folder,
            timezone=self.timezone,
        )
        bars = [
            item
            for item in price_result.bars
            if item.timestamp + timedelta(minutes=1) <= current_time
        ]
        self._resolve_open_alerts(bars, current_time)
        existing_plan = self._latest_for_session("plans", session_date)
        maximum_gap = self.integrity_policy["mapping"][
            "maximum_source_gap_seconds"
        ]
        current_ready_plan = (
            existing_plan
            and existing_plan["status"] == XauFt2State.PLAN_READY
            and existing_plan.get("engine_revision")
            == self.integrity_policy["engine_revision"]
            and float(existing_plan.get("source_gap_seconds") or 0) <= maximum_gap
        )
        if current_ready_plan:
            plan = existing_plan
        else:
            candidate = self._create_plan(session_date, bars)
            unchanged_block = (
                existing_plan is not None
                and existing_plan["status"] == XauFt2State.DATA_BLOCKED
                and candidate["status"] == XauFt2State.DATA_BLOCKED
                and existing_plan.get("data_block_reasons")
                == candidate.get("data_block_reasons")
            )
            if unchanged_block:
                plan = existing_plan
            else:
                plan = candidate
                if existing_plan:
                    revision = len(self.journal.by_session("plans", session_date)) + 1
                    plan["supersedes_id"] = existing_plan["plan_id"]
                    plan["plan_id"] = (
                        f"{self.policy['candidate_id']}_{session_date.isoformat()}"
                        f"_r{revision}"
                    )
                self.journal.append("plans", plan, id_field="plan_id")
        if plan["status"] == XauFt2State.DATA_BLOCKED:
            self._daily_summary(session_date, plan["status"])
            return self._response(plan=plan)

        zone = ZoneInfo(self.timezone)
        trading_date = date.fromisoformat(plan["trading_date_bangkok"])
        monitoring_bars = [
            item
            for item in bars
            if item.timestamp.astimezone(zone).date() == trading_date
        ]
        existing_event = self._latest_for_session("events", session_date)
        event = existing_event or self._first_touch(plan, monitoring_bars)
        if event is None:
            self._daily_summary(session_date, XauFt2State.WAITING_FOR_FIRST_TOUCH)
            return self._response(plan=plan)
        if existing_event is None:
            self.journal.append("events", event, id_field="event_id")

        existing_alert = self._latest_for_session("alerts", session_date)
        if existing_alert is None:
            alert = self._create_alert(
                plan=plan,
                event=event,
                bars=monitoring_bars,
                broker_quote=broker_quote,
                now=current_time,
            )
            self.journal.append(
                "alerts",
                alert.model_dump(mode="json"),
                id_field="alert_id",
            )
        else:
            alert = XauFt2Alert.model_validate(_model_fields(XauFt2Alert, existing_alert))
        self._daily_summary(session_date, alert.status)
        return self._response(plan=plan, event=event, alert=alert)

    def latest(self) -> XauFt2LatestResponse:
        plan = self.journal.latest("plans")
        event = self.journal.latest("events")
        alert_row = self.journal.latest("alerts")
        alert = (
            XauFt2Alert.model_validate(_model_fields(XauFt2Alert, alert_row))
            if alert_row
            else None
        )
        acknowledgement = None
        outcome = None
        if alert:
            acknowledgement = _latest_matching(
                self.journal.read("acknowledgements"),
                "alert_id",
                alert.alert_id,
            )
            outcome = _latest_matching(
                self.journal.read("outcomes"),
                "alert_id",
                alert.alert_id,
            )
        return XauFt2LatestResponse(
            plan=plan,
            event=event,
            alert=alert,
            acknowledgement=acknowledgement,
            outcome=outcome,
        )

    def acknowledge(
        self,
        alert_id: str,
        request: XauFt2AcknowledgementRequest,
    ) -> dict[str, Any]:
        if not any(
            item.get("alert_id") == alert_id
            for item in self.journal.read("alerts")
        ):
            raise FileNotFoundError(f"FT2 alert not found: {alert_id}")
        alert = next(
            item
            for item in reversed(self.journal.read("alerts"))
            if item.get("alert_id") == alert_id
        )
        row = {
            "acknowledgement_id": f"ack_{uuid4().hex}",
            "alert_id": alert_id,
            "acknowledged_at": datetime.now(UTC).isoformat(),
            "acknowledged_by": request.acknowledged_by,
            "note": request.note,
            "broker_symbol": request.broker_symbol or alert.get("broker_symbol"),
            "order_type": request.order_type.value,
            "reference_entry_price": alert["mapped_xauusd_level"],
            "actual_fill_timestamp": (
                request.actual_fill_timestamp.isoformat() if request.actual_fill_timestamp else None
            ),
            "actual_fill_price": request.actual_fill_price,
            "bid": request.bid,
            "ask": request.ask,
            "spread": (
                request.ask - request.bid
                if request.ask is not None and request.bid is not None
                else None
            ),
        }
        self.journal.append(
            "acknowledgements",
            row,
            id_field="acknowledgement_id",
        )
        return {
            **row,
            "candidate_hash": self.policy["candidate_hash"],
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }

    def _create_plan(
        self,
        session_date: date,
        bars: list[XauPriceBar],
    ) -> dict[str, Any]:
        eligibility = evaluate_daily_session_eligibility(
            root=self.vol2vol_root,
            session_date=session_date,
            current_date=session_date,
        )
        if not (eligibility.forward_plan_eligible or eligibility.backtest_eligible):
            return self._blocked_plan(session_date, eligibility.reasons)
        raw_path = daily_raw_path(self.vol2vol_root, session_date)
        if not raw_path.exists():
            return self._blocked_plan(session_date, ["EXACT_DATE_VOL2VOL_MISSING"])
        try:
            selection = select_snapshot(
                load_source_snapshots(raw_path, session_date),
                anchor=TimeAnchor.T0_DTE_080,
                session_date=session_date,
                timezone=self.timezone,
                target_dte=self.policy["canonical_plan"]["source_dte_target"],
                dte_tolerance=self.policy["canonical_plan"]["source_dte_tolerance"],
            )
        except ValueError as exc:
            return self._blocked_plan(session_date, [str(exc)])
        if selection is None or not selection.strict_dte_eligible:
            return self._blocked_plan(
                session_date,
                ["STRICT_T0_DTE_080_SELECTION_UNAVAILABLE"],
            )
        plan = map_selection(
            selection,
            bars,
            mapping_mode=MappingMode.DISTANCE_REANCHORED,
            maximum_gap_seconds=self.integrity_policy["mapping"][
                "maximum_source_gap_seconds"
            ],
            bar_interval_minutes=self.integrity_policy["mapping"][
                "bar_interval_minutes"
            ],
        )
        if plan is None:
            return self._blocked_plan(session_date, ["XAUUSD_MAPPING_UNAVAILABLE"])
        if not synchronized_reference_accepted(
            plan,
            maximum_gap_seconds=self.integrity_policy["mapping"][
                "maximum_source_gap_seconds"
            ],
        ):
            return self._blocked_plan(
                session_date,
                ["XAU_REFERENCE_UNAVAILABLE_STALE"],
            )
        activation_bangkok = selection.activation_at.astimezone(
            ZoneInfo(self.timezone)
        )
        future_lower, future_upper = selection.snapshot.ranges[2]
        mapped_lower, mapped_upper = plan.mapped_levels[2]
        return {
            "plan_id": f"{self.policy['candidate_id']}_{session_date.isoformat()}",
            "candidate_id": self.policy["candidate_id"],
            "session_date": session_date.isoformat(),
            "source_session_date": session_date.isoformat(),
            "status": XauFt2State.PLAN_READY.value,
            "source_payload_sha256": _sha256(raw_path),
            "selected_series": selection.snapshot.series,
            "source_dte": selection.snapshot.source_dte,
            "selected_snapshot_timestamp": selection.snapshot.observed_at.isoformat(),
            "activation_timestamp": selection.activation_at.isoformat(),
            "snapshot_timestamp_utc": selection.snapshot.observed_at.isoformat(),
            "activation_timestamp_bangkok": activation_bangkok.isoformat(),
            "trading_date_bangkok": activation_bangkok.date().isoformat(),
            "original_futures_reference": selection.snapshot.future_reference,
            "raw_futures_lower_2sd": future_lower,
            "raw_futures_upper_2sd": future_upper,
            "mapped_xauusd_lower_2sd": mapped_lower,
            "mapped_xauusd_upper_2sd": mapped_upper,
            "xau_reference_timestamp": plan.planning_xau_timestamp.isoformat(),
            "selected_xau_timestamp": plan.planning_xau_timestamp.isoformat(),
            "xau_reference_price": plan.planning_xau_price,
            "source_gap_seconds": plan.source_gap_seconds,
            "mapping_mode": plan.mapping_mode.value,
            "mapping_quality": plan.mapping_quality,
            "levels_frozen": True,
            "engine_revision": self.integrity_policy["engine_revision"],
            "engine_hash": self.integrity_policy["engine_hash"],
            "candidate_hash": self.policy["candidate_hash"],
            "reference_trade_levels": {
                "lower_long": {
                    "entry": mapped_lower,
                    "take_profit": mapped_lower
                    + self.policy["canonical_plan"]["take_profit_points"],
                    "stop_loss": mapped_lower
                    - self.policy["canonical_plan"]["stop_loss_points"],
                },
                "upper_short": {
                    "entry": mapped_upper,
                    "take_profit": mapped_upper
                    - self.policy["canonical_plan"]["take_profit_points"],
                    "stop_loss": mapped_upper
                    + self.policy["canonical_plan"]["stop_loss_points"],
                },
            },
            "context": _descriptive_context(selection.snapshot, plan),
            "data_block_reasons": [],
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }

    def _first_touch(
        self,
        plan: dict[str, Any],
        bars: list[XauPriceBar],
    ) -> dict[str, Any] | None:
        activation = datetime.fromisoformat(plan["activation_timestamp"])
        candidates = []
        lower = plan["mapped_xauusd_lower_2sd"]
        upper = plan["mapped_xauusd_upper_2sd"]
        for bar in sorted(bars, key=lambda item: item.timestamp):
            if bar.timestamp < activation:
                continue
            if bar.low <= lower:
                candidates.append(("lower_long", lower, bar.timestamp))
                break
        for bar in sorted(bars, key=lambda item: item.timestamp):
            if bar.timestamp < activation:
                continue
            if bar.high >= upper:
                candidates.append(("upper_short", upper, bar.timestamp))
                break
        if not candidates:
            return None
        side, boundary, touched_at = min(candidates, key=lambda item: (item[2], item[0]))
        return {
            "event_id": (
                f"{self.policy['candidate_id']}_{plan['session_date']}_{side}_first_touch"
            ),
            "candidate_id": self.policy["candidate_id"],
            "session_date": plan["session_date"],
            "side": side,
            "tier": 2.0,
            "first_touch": True,
            "touch_reference": boundary,
            "touch_timestamp": touched_at.isoformat(),
            "repeated_touch_allowed": False,
            "status": "FIRST_TOUCH",
        }

    def _create_alert(
        self,
        *,
        plan: dict[str, Any],
        event: dict[str, Any],
        bars: list[XauPriceBar],
        broker_quote: XauFt2BrokerQuote | None,
        now: datetime,
    ) -> XauFt2Alert:
        active = self._active_provisional_alert()
        side = event["side"]
        direction = 1 if side == "lower_long" else -1
        reference_entry = float(event["touch_reference"])
        tp_points = self.policy["canonical_plan"]["take_profit_points"]
        sl_points = self.policy["canonical_plan"]["stop_loss_points"]
        reference_tp = reference_entry + direction * tp_points
        reference_sl = reference_entry - direction * sl_points
        status = XauFt2State.REFERENCE_ALERT
        reasons = []
        translated = None
        touch_timestamp = datetime.fromisoformat(event["touch_timestamp"])
        touch_age = (now - touch_timestamp.astimezone(now.tzinfo)).total_seconds()
        if (
            touch_age < 0
            or touch_age
            > self.policy["broker_translation"]["maximum_alert_delay_seconds"]
        ):
            reasons.append("FIRST_TOUCH_ALERT_STALE")
        if active is not None:
            status = XauFt2State.TIER_LOCKED
            reasons.append(f"ACTIVE_CANDIDATE:{active['alert_id']}")
        elif broker_quote is not None:
            translated = self._translate_quote(
                broker_quote,
                bars,
                now,
                touch_timestamp,
            )
            reasons.extend(translated["reasons"])
            if not reasons:
                status = XauFt2State.PROVISIONAL_MANUAL_ALERT
        else:
            reasons.append("SYNCHRONIZED_BROKER_QUOTE_NOT_SUPPLIED")
        offset = (
            translated["offset"]
            if translated is not None and not translated["reasons"]
            else None
        )
        context = plan.get("context") or {}
        raw_futures_level = (
            plan["raw_futures_lower_2sd"]
            if side == "lower_long"
            else plan["raw_futures_upper_2sd"]
        )
        return XauFt2Alert(
            alert_id=f"{self.policy['candidate_id']}_{plan['session_date']}_{side}",
            candidate_id=self.policy["candidate_id"],
            candidate_hash=self.policy["candidate_hash"],
            session_date=plan["session_date"],
            status=status,
            side="BUY" if direction > 0 else "SELL",
            source_symbol="CME Gold futures/options via Vol2Vol",
            broker_symbol=broker_quote.symbol if broker_quote else None,
            selected_series=plan["selected_series"],
            source_dte=plan["source_dte"],
            original_futures_reference=plan["original_futures_reference"],
            raw_futures_2sd_level=raw_futures_level,
            mapped_xauusd_level=reference_entry,
            broker_translated_level=(
                reference_entry + offset if offset is not None else None
            ),
            reference_take_profit=reference_tp,
            reference_stop_loss=reference_sl,
            take_profit=reference_tp + offset if offset is not None else None,
            stop_loss=reference_sl + offset if offset is not None else None,
            selected_snapshot_timestamp=datetime.fromisoformat(
                plan["selected_snapshot_timestamp"]
            ),
            activation_timestamp=datetime.fromisoformat(plan["activation_timestamp"]),
            xau_reference_timestamp=datetime.fromisoformat(
                plan["xau_reference_timestamp"]
            ),
            touch_timestamp=datetime.fromisoformat(event["touch_timestamp"]),
            source_gap_seconds=plan["source_gap_seconds"],
            mapping_mode=plan["mapping_mode"],
            mapping_quality=plan["mapping_quality"],
            spread_points=translated["spread"] if translated else None,
            broker_offset_points=offset,
            oi_context=context.get("oi") or {},
            iv_context=context.get("iv") or {},
            volume_context=context.get("volume") or {},
            rejection_context={
                "state": "not_required_for_primary",
                "challenger_id": "FT2_REJECTION_V1",
                "manual_alert_allowed": False,
            },
            data_block_reasons=reasons,
        )

    def _translate_quote(
        self,
        quote: XauFt2BrokerQuote,
        bars: list[XauPriceBar],
        now: datetime,
        touch_timestamp: datetime,
    ) -> dict[str, Any]:
        reasons = []
        age = (now - quote.timestamp.astimezone(now.tzinfo)).total_seconds()
        spread = quote.ask - quote.bid
        config = self.policy["broker_translation"]
        if age < 0 or age > config["maximum_quote_age_seconds"]:
            reasons.append("BROKER_QUOTE_STALE")
        touch_gap = abs((quote.timestamp - touch_timestamp).total_seconds())
        if touch_gap > config["maximum_touch_quote_gap_seconds"]:
            reasons.append("BROKER_QUOTE_NOT_SYNCHRONIZED_TO_TOUCH")
        if spread > config["maximum_spread_points"]:
            reasons.append("BROKER_SPREAD_TOO_WIDE")
        reference = max(
            (item for item in bars if item.timestamp <= quote.timestamp),
            key=lambda item: item.timestamp,
            default=None,
        )
        if reference is None:
            reasons.append("SYNCHRONIZED_XAUUSD_REFERENCE_UNAVAILABLE")
            offset = None
        else:
            offset = ((quote.bid + quote.ask) / 2) - reference.close
        return {"reasons": reasons, "spread": spread, "offset": offset}

    def _resolve_open_alerts(
        self,
        bars: list[XauPriceBar],
        now: datetime,
    ) -> None:
        resolved_ids = {
            item.get("alert_id") for item in self.journal.read("outcomes")
        }
        for alert in self.journal.read("alerts"):
            if alert.get("alert_id") in resolved_ids:
                continue
            acknowledgement = _latest_matching(
                self.journal.read("acknowledgements"),
                "alert_id",
                alert["alert_id"],
            )
            if (
                acknowledgement is None
                or acknowledgement.get("order_type")
                == XauFt2OrderType.OBSERVATION_ONLY.value
                or acknowledgement.get("actual_fill_timestamp") is None
                or acknowledgement.get("actual_fill_price") is None
            ):
                continue
            fill_at = datetime.fromisoformat(
                acknowledgement["actual_fill_timestamp"]
            )
            fill_price = float(acknowledgement["actual_fill_price"])
            later = [
                item
                for item in sorted(bars, key=lambda row: row.timestamp)
                if item.timestamp >= fill_at
            ]
            if not later:
                continue
            side = alert["side"]
            direction = 1 if side == "BUY" else -1
            tp = fill_price + direction * self.policy["canonical_plan"][
                "take_profit_points"
            ]
            sl = fill_price - direction * self.policy["canonical_plan"][
                "stop_loss_points"
            ]
            spread = float(acknowledgement.get("spread") or 0)
            status = None
            resolved_at = None
            for index, bar in enumerate(later):
                if side == "BUY":
                    tp_hit = bar.high >= tp
                    sl_hit = bar.low <= sl
                else:
                    tp_hit = bar.low + spread <= tp
                    sl_hit = bar.high + spread >= sl
                fill_bar_unknown = index == 0 and (tp_hit or sl_hit)
                if (tp_hit and sl_hit) or fill_bar_unknown:
                    status = XauFt2State.AMBIGUOUS
                elif tp_hit:
                    status = XauFt2State.TP_HIT
                elif sl_hit:
                    status = XauFt2State.SL_HIT
                if status is not None:
                    resolved_at = bar.timestamp
                    break
            local_now_date = now.astimezone(ZoneInfo(self.timezone)).date()
            fill_date = fill_at.astimezone(ZoneInfo(self.timezone)).date()
            if status is None and fill_date < local_now_date:
                status = XauFt2State.SESSION_EXPIRED
            if status is None:
                continue
            row = {
                "outcome_id": f"outcome_{alert['alert_id']}",
                "alert_id": alert["alert_id"],
                "session_date": alert["session_date"],
                "status": status.value,
                "resolved_at": resolved_at.isoformat() if resolved_at else None,
                "reference_entry_price": alert["mapped_xauusd_level"],
                "actual_fill_timestamp": fill_at.isoformat(),
                "actual_fill_price": fill_price,
                "take_profit_from_actual_fill": tp,
                "stop_loss_from_actual_fill": sl,
                "order_type": acknowledgement["order_type"],
                "research_only": True,
                "signal_allowed": False,
                "order_submission_allowed": False,
            }
            self.journal.append("outcomes", row, id_field="outcome_id")

    def _active_provisional_alert(self) -> dict[str, Any] | None:
        resolved = {item.get("alert_id") for item in self.journal.read("outcomes")}
        return next(
            (
                item
                for item in reversed(self.journal.read("alerts"))
                if item.get("status") == XauFt2State.PROVISIONAL_MANUAL_ALERT
                and item.get("alert_id") not in resolved
            ),
            None,
        )

    def _response(
        self,
        *,
        plan: dict[str, Any],
        event: dict[str, Any] | None = None,
        alert: XauFt2Alert | None = None,
    ) -> XauFt2LatestResponse:
        acknowledgement = None
        outcome = None
        if alert:
            acknowledgement = _latest_matching(
                self.journal.read("acknowledgements"),
                "alert_id",
                alert.alert_id,
            )
            outcome = _latest_matching(
                self.journal.read("outcomes"),
                "alert_id",
                alert.alert_id,
            )
        return XauFt2LatestResponse(
            plan=plan,
            event=event,
            alert=alert,
            acknowledgement=acknowledgement,
            outcome=outcome,
        )

    def _latest_for_session(
        self,
        stream: str,
        session_date: date,
    ) -> dict[str, Any] | None:
        rows = self.journal.by_session(stream, session_date)
        return rows[-1] if rows else None

    def _blocked_plan(
        self,
        session_date: date,
        reasons: list[str],
    ) -> dict[str, Any]:
        return {
            "plan_id": f"{self.policy['candidate_id']}_{session_date.isoformat()}",
            "candidate_id": self.policy["candidate_id"],
            "session_date": session_date.isoformat(),
            "status": XauFt2State.DATA_BLOCKED.value,
            "data_block_reasons": reasons,
            "research_only": True,
            "signal_allowed": False,
            "order_submission_allowed": False,
        }

    def _daily_summary(self, session_date: date, status: Any) -> None:
        existing = self._latest_for_session("daily_summaries", session_date)
        status_value = status.value if isinstance(status, XauFt2State) else str(status)
        if existing and existing.get("status") == status_value:
            return
        revision = len(self.journal.by_session("daily_summaries", session_date)) + 1
        row = {
            "summary_id": (
                f"summary_{self.policy['candidate_id']}_{session_date.isoformat()}_r{revision}"
            ),
            "session_date": session_date.isoformat(),
            "status": status_value,
            "eligible_plan_count": len(
                [
                    item
                    for item in self.journal.read("plans")
                    if item.get("status") == XauFt2State.PLAN_READY
                ]
            ),
            "first_touch_event_count": len(self.journal.read("events")),
        }
        if existing:
            row["supersedes_id"] = existing["summary_id"]
        self.journal.append("daily_summaries", row, id_field="summary_id")


def _descriptive_context(snapshot: Any, plan: Any) -> dict[str, Any]:
    offset = plan.planning_xau_price - snapshot.future_reference
    rows = [
        {
            "mapped_strike": float(item["strike"]) + offset,
            "total": float(item.get("total") or 0),
        }
        for item in snapshot.strike_rows
        if item.get("strike") is not None
    ]
    lower, upper = plan.mapped_levels[2]
    return {
        "oi": {
            "nearest_lower_wall": _nearest_wall(rows, lower),
            "nearest_upper_wall": _nearest_wall(rows, upper),
            "descriptive_only": True,
        },
        "iv": {
            "atm_iv": snapshot.atm_iv,
            "iv_change": snapshot.iv_change,
            "descriptive_only": True,
        },
        "volume": {
            "activity_total": snapshot.activity_total,
            "descriptive_only": True,
        },
    }


def _nearest_wall(rows: list[dict[str, float]], level: float) -> dict[str, Any] | None:
    if not rows:
        return None
    item = min(
        rows,
        key=lambda row: (abs(row["mapped_strike"] - level), -row["total"]),
    )
    return {
        **item,
        "distance_points": abs(item["mapped_strike"] - level),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest_matching(
    rows: list[dict[str, Any]],
    field: str,
    value: str,
) -> dict[str, Any] | None:
    return next(
        (item for item in reversed(rows) if item.get(field) == value),
        None,
    )


def _model_fields(model: Any, row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in model.model_fields if key in row}
