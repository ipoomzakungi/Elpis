from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.models.xau_walk_forward_research import (
    XauOhlcvBar,
    XauWalkForwardPriceSource,
    XauWalkForwardReadiness,
    XauWalkForwardRunRequest,
    XauWalkForwardRunResult,
    XauWalkForwardSdSource,
    XauWalkForwardSnapshotRecord,
)
from src.xau_walk_forward.order_planner import generate_research_order_plans
from src.xau_walk_forward.price_provider import (
    ManualPriceProvider,
    StaticFixturePriceProvider,
    YahooResearchPriceProvider,
)
from src.xau_walk_forward.range_desk_builder import (
    build_range_desk_from_walk_forward_snapshot,
)
from src.xau_walk_forward.report_store import XauWalkForwardReportStore, new_run_id
from src.xau_walk_forward.schedule import build_xau_walk_forward_schedule
from src.xau_walk_forward.sd_source import resolve_sd_snapshot
from src.xau_walk_forward.simulated_order_engine import (
    load_ohlcv_bars,
    simulate_research_order_outcomes,
)


class XauWalkForwardResearchService:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir
        self.store = XauWalkForwardReportStore(reports_dir=reports_dir)

    def run(self, request: XauWalkForwardRunRequest) -> XauWalkForwardRunResult:
        run_id = new_run_id(request.session_date)
        scheduled = build_xau_walk_forward_schedule(
            request.session_date,
            request.schedule_config,
        )
        bars = _load_bars(request.price_bars_path) if request.run_outcome_simulation else []
        snapshots: list[XauWalkForwardSnapshotRecord] = []
        all_orders = []
        all_outcomes = []
        missing_inputs: list[str] = []
        limitations: list[str] = [
            "Feature 025 creates research planning records only; it does not place orders.",
            "Gamma/GEX is skipped unless future source data supports it.",
        ]

        if not scheduled:
            missing_inputs.append("schedule.weekday")
            limitations.append("No schedule timestamps were generated for this session date.")

        for index, scheduled_item in enumerate(scheduled):
            snapshot_id = f"{run_id}_{index:03d}"
            price_snapshot = self._price_snapshot(request, scheduled_item.timestamp)
            sd_snapshot = resolve_sd_snapshot(
                timestamp=scheduled_item.timestamp,
                cme_source=request.cme_source.value,
                reports_dir=self.reports_dir,
                expiration_code=request.expiration_code,
                future_reference_price=price_snapshot.future_reference_price,
            )
            range_desk_plan = build_range_desk_from_walk_forward_snapshot(
                session_date=request.session_date,
                price_snapshot=price_snapshot,
                sd_snapshot=sd_snapshot,
            )
            snapshot_missing: list[str] = []
            snapshot_limitations = [*price_snapshot.limitations, *sd_snapshot.limitations]
            if price_snapshot.future_reference_price is None:
                snapshot_missing.append("future_reference_price")
            if price_snapshot.traded_reference_price is None:
                snapshot_missing.append("traded_reference_price")
            if sd_snapshot.sd_source == XauWalkForwardSdSource.UNAVAILABLE:
                snapshot_missing.append("native_sd")
            if range_desk_plan is None:
                snapshot_missing.append("range_desk_plan")
            orders = (
                generate_research_order_plans(
                    snapshot_id=snapshot_id,
                    timestamp=scheduled_item.timestamp,
                    price_snapshot=price_snapshot,
                    sd_snapshot=sd_snapshot,
                    config=request.order_plan_config,
                    risk_config=request.risk_config,
                )
                if range_desk_plan is not None
                else []
            )
            outcomes = (
                simulate_research_order_outcomes(orders, bars)
                if request.run_outcome_simulation
                else []
            )
            record = XauWalkForwardSnapshotRecord(
                snapshot_id=snapshot_id,
                timestamp=scheduled_item.timestamp,
                schedule_tag=scheduled_item.tag,
                price_snapshot=price_snapshot,
                sd_snapshot=sd_snapshot,
                range_desk_plan=range_desk_plan,
                research_order_plans=orders,
                data_capability_summary={
                    "native_sd": sd_snapshot.sd_source.value,
                    "gamma": "skipped_or_unavailable",
                    "gex": "blocked_unless_gamma_available",
                },
                missing_inputs=snapshot_missing,
                limitations=snapshot_limitations,
                research_only=True,
                signal_allowed=False,
            )
            snapshots.append(record)
            all_orders.extend(orders)
            all_outcomes.extend(outcomes)
            missing_inputs.extend(snapshot_missing)

        readiness = _readiness(snapshots, missing_inputs)
        result = XauWalkForwardRunResult(
            run_id=run_id,
            created_at=datetime.now(UTC),
            session_date=request.session_date,
            readiness=readiness,
            snapshot_count=len(snapshots),
            order_plan_count=len(all_orders),
            outcome_count=len(all_outcomes),
            missing_inputs=_dedupe(missing_inputs),
            limitations=_dedupe(limitations),
            research_only=True,
            signal_allowed=False,
        )
        output_store = (
            XauWalkForwardReportStore(reports_dir=request.output_root)
            if request.output_root is not None
            else self.store
        )
        return output_store.persist_run(
            result=result,
            snapshots=snapshots,
            orders=all_orders,
            outcomes=all_outcomes,
            overwrite_allowed=request.overwrite_allowed,
        )

    def latest(self) -> XauWalkForwardRunResult:
        return self.store.latest_result()

    def get_run(self, run_id: str) -> XauWalkForwardRunResult:
        return self.store.read_result(run_id)

    def get_snapshots(self, run_id: str) -> list[XauWalkForwardSnapshotRecord]:
        return self.store.read_snapshots(run_id)

    def get_orders(self, run_id: str):
        return self.store.read_orders(run_id)

    def _price_snapshot(self, request: XauWalkForwardRunRequest, timestamp: datetime):
        if request.price_source == XauWalkForwardPriceSource.FIXTURE:
            return StaticFixturePriceProvider().snapshot(
                timestamp=timestamp,
                future_reference_price=request.future_reference_price or 4500.0,
                traded_reference_price=request.traded_reference_price or 4470.0,
            )
        if request.price_source == XauWalkForwardPriceSource.YAHOO_RESEARCH:
            return YahooResearchPriceProvider().snapshot(timestamp=timestamp)
        return ManualPriceProvider().snapshot(
            timestamp=timestamp,
            future_reference_price=request.future_reference_price,
            traded_reference_price=request.traded_reference_price,
        )


def _readiness(
    snapshots: list[XauWalkForwardSnapshotRecord],
    missing_inputs: list[str],
) -> XauWalkForwardReadiness:
    if not snapshots:
        return XauWalkForwardReadiness.BLOCKED
    if missing_inputs:
        return XauWalkForwardReadiness.PARTIAL
    return XauWalkForwardReadiness.COMPLETE


def _load_bars(path: Path | None) -> list[XauOhlcvBar]:
    if path is None:
        return []
    return load_ohlcv_bars(path)


def _dedupe(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


__all__ = ["XauWalkForwardResearchService"]
