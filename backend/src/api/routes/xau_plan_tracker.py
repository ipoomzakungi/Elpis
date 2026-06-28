from __future__ import annotations

from datetime import time

from fastapi import APIRouter, Depends, HTTPException, Query

from src.models.xau_plan_tracker_statistics import (
    XauPlanTrackerStatsRequest,
    XauPlanTrackerStatsResult,
)
from src.models.xau_price_plan_tracker import (
    XauPlanTrackerRequest,
    XauPlanTrackerRunResult,
    XauResearchOrderSide,
    XauResearchPlanTrackerSnapshot,
    XauResearchTrackedOrder,
    XauTrackedOrderStatus,
)
from src.xau_plan_tracker_statistics.service import XauPlanTrackerStatisticsService
from src.xau_price_plan_tracker.service import XauPlanTrackerService

router = APIRouter()


def get_xau_plan_tracker_service() -> XauPlanTrackerService:
    return XauPlanTrackerService()


def get_xau_plan_tracker_statistics_service() -> XauPlanTrackerStatisticsService:
    return XauPlanTrackerStatisticsService()


@router.post(
    "/research/xau/plan-tracker/run",
    response_model=XauPlanTrackerRunResult,
)
async def run_xau_plan_tracker(
    request: XauPlanTrackerRequest,
    service: XauPlanTrackerService = Depends(get_xau_plan_tracker_service),
) -> XauPlanTrackerRunResult:
    return service.run(request)


@router.get(
    "/research/xau/plan-tracker/latest",
    response_model=XauPlanTrackerRunResult,
)
async def get_latest_xau_plan_tracker_run(
    service: XauPlanTrackerService = Depends(get_xau_plan_tracker_service),
) -> XauPlanTrackerRunResult:
    try:
        return service.latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No XAU plan tracker run exists") from exc


@router.get(
    "/research/xau/plan-tracker/runs/{run_id}",
    response_model=XauPlanTrackerRunResult,
)
async def get_xau_plan_tracker_run(
    run_id: str,
    service: XauPlanTrackerService = Depends(get_xau_plan_tracker_service),
) -> XauPlanTrackerRunResult:
    try:
        return service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="XAU plan tracker run not found") from exc


@router.get(
    "/research/xau/plan-tracker/runs/{run_id}/orders",
    response_model=list[XauResearchTrackedOrder],
)
async def get_xau_plan_tracker_orders(
    run_id: str,
    service: XauPlanTrackerService = Depends(get_xau_plan_tracker_service),
) -> list[XauResearchTrackedOrder]:
    try:
        return service.get_orders(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="XAU plan tracker run not found") from exc


@router.get(
    "/research/xau/plan-tracker/runs/{run_id}/snapshots",
    response_model=list[XauResearchPlanTrackerSnapshot],
)
async def get_xau_plan_tracker_snapshots(
    run_id: str,
    service: XauPlanTrackerService = Depends(get_xau_plan_tracker_service),
) -> list[XauResearchPlanTrackerSnapshot]:
    try:
        return service.get_snapshots(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="XAU plan tracker run not found") from exc


@router.post(
    "/research/xau/plan-tracker/stats",
    response_model=XauPlanTrackerStatsResult,
)
async def run_xau_plan_tracker_stats(
    request: XauPlanTrackerStatsRequest,
    service: XauPlanTrackerStatisticsService = Depends(
        get_xau_plan_tracker_statistics_service,
    ),
) -> XauPlanTrackerStatsResult:
    return service.run(request)


@router.get(
    "/research/xau/plan-tracker/stats/{run_id}",
    response_model=XauPlanTrackerStatsResult,
)
async def get_xau_plan_tracker_run_stats(
    run_id: str,
    planning_times: list[time] = Query(default=[]),
    sides: list[XauResearchOrderSide] = Query(default=[]),
    statuses: list[XauTrackedOrderStatus] = Query(default=[]),
    include_unavailable_orders: bool = Query(default=False),
    service: XauPlanTrackerStatisticsService = Depends(
        get_xau_plan_tracker_statistics_service,
    ),
) -> XauPlanTrackerStatsResult:
    request = XauPlanTrackerStatsRequest(
        planning_times=planning_times,
        sides=sides,
        statuses=statuses,
        include_unavailable_orders=include_unavailable_orders,
    )
    try:
        return service.run_for_run(run_id=run_id, request=request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="XAU plan tracker run not found") from exc


__all__ = [
    "get_xau_plan_tracker_service",
    "get_xau_plan_tracker_statistics_service",
    "router",
]
