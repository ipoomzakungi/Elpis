from fastapi import APIRouter

from src.models.xau_range_desk import XauRangeDeskPlan, XauRangeDeskPlanRequest
from src.xau_range_desk.planner import build_xau_range_desk_plan

router = APIRouter()


@router.post("/research/xau/range-desk/plan", response_model=XauRangeDeskPlan)
async def create_xau_range_desk_plan(
    request: XauRangeDeskPlanRequest,
) -> XauRangeDeskPlan:
    """Build a research-only futures-to-traded Range Desk planning map."""

    return build_xau_range_desk_plan(request)
