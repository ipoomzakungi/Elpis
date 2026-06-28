from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.models.xau_walk_forward_research import (
    XauResearchOrderPlan,
    XauWalkForwardRunRequest,
    XauWalkForwardRunResult,
    XauWalkForwardSnapshotRecord,
)
from src.xau_walk_forward.service import XauWalkForwardResearchService

router = APIRouter()


def get_xau_walk_forward_service() -> XauWalkForwardResearchService:
    return XauWalkForwardResearchService()


@router.post(
    "/research/xau/walk-forward/run",
    response_model=XauWalkForwardRunResult,
)
async def run_xau_walk_forward_research(
    request: XauWalkForwardRunRequest,
    service: XauWalkForwardResearchService = Depends(get_xau_walk_forward_service),
) -> XauWalkForwardRunResult:
    return service.run(request)


@router.get(
    "/research/xau/walk-forward/latest",
    response_model=XauWalkForwardRunResult,
)
async def get_latest_xau_walk_forward_run(
    service: XauWalkForwardResearchService = Depends(get_xau_walk_forward_service),
) -> XauWalkForwardRunResult:
    try:
        return service.latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No XAU walk-forward run exists") from exc


@router.get(
    "/research/xau/walk-forward/runs/{run_id}",
    response_model=XauWalkForwardRunResult,
)
async def get_xau_walk_forward_run(
    run_id: str,
    service: XauWalkForwardResearchService = Depends(get_xau_walk_forward_service),
) -> XauWalkForwardRunResult:
    try:
        return service.get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="XAU walk-forward run not found") from exc


@router.get(
    "/research/xau/walk-forward/runs/{run_id}/orders",
    response_model=list[XauResearchOrderPlan],
)
async def get_xau_walk_forward_orders(
    run_id: str,
    service: XauWalkForwardResearchService = Depends(get_xau_walk_forward_service),
) -> list[XauResearchOrderPlan]:
    try:
        return service.get_orders(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="XAU walk-forward run not found") from exc


@router.get(
    "/research/xau/walk-forward/runs/{run_id}/snapshots",
    response_model=list[XauWalkForwardSnapshotRecord],
)
async def get_xau_walk_forward_snapshots(
    run_id: str,
    service: XauWalkForwardResearchService = Depends(get_xau_walk_forward_service),
) -> list[XauWalkForwardSnapshotRecord]:
    try:
        return service.get_snapshots(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="XAU walk-forward run not found") from exc


__all__ = ["get_xau_walk_forward_service", "router"]
