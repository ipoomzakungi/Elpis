from fastapi import APIRouter, HTTPException

from src.api.validation import (
    invalid_research_config,
    research_not_implemented,
    research_report_not_found,
)
from src.models.research import (
    ResearchAssetSummaryResponse,
    ResearchComparisonResponse,
    ResearchRun,
    ResearchRunListResponse,
    ResearchRunRequest,
    ResearchValidationAggregationResponse,
)
from src.research.orchestration import (
    ResearchExecutionNotImplementedError,
    ResearchOrchestrator,
)
from src.research.report_store import ResearchReportStore

router = APIRouter()


@router.post("/research/runs", response_model=ResearchRun)
async def run_research_report(request: ResearchRunRequest) -> ResearchRun:
    """Run a synchronous local grouped research report."""
    try:
        return ResearchOrchestrator().run(request)
    except ResearchExecutionNotImplementedError:
        research_not_implemented()
    except ValueError as exc:
        invalid_research_config(str(exc))

    raise HTTPException(status_code=500, detail="Research report run failed")


@router.get("/research/runs", response_model=ResearchRunListResponse)
async def list_research_reports() -> ResearchRunListResponse:
    """List saved grouped research reports."""
    return ResearchReportStore().list_runs()


@router.get("/research/runs/{research_run_id}", response_model=ResearchRun)
async def get_research_report(research_run_id: str) -> ResearchRun:
    """Return grouped research report metadata."""
    try:
        return ResearchReportStore().read_run(research_run_id)
    except FileNotFoundError:
        research_report_not_found(research_run_id)

    raise HTTPException(status_code=500, detail="Research report read failed")


@router.get(
    "/research/runs/{research_run_id}/assets",
    response_model=ResearchAssetSummaryResponse,
)
async def get_research_assets(research_run_id: str) -> ResearchAssetSummaryResponse:
    """Return asset-level summary rows for a grouped research report."""
    try:
        return ResearchReportStore().read_assets(research_run_id)
    except FileNotFoundError:
        research_report_not_found(research_run_id)

    raise HTTPException(status_code=500, detail="Research asset summary read failed")


@router.get(
    "/research/runs/{research_run_id}/comparison",
    response_model=ResearchComparisonResponse,
)
async def get_research_comparison(research_run_id: str) -> ResearchComparisonResponse:
    """Return strategy and baseline comparison rows for a grouped research report."""
    try:
        return ResearchReportStore().read_comparison(research_run_id)
    except FileNotFoundError:
        research_report_not_found(research_run_id)

    raise HTTPException(status_code=500, detail="Research comparison read failed")


@router.get(
    "/research/runs/{research_run_id}/validation",
    response_model=ResearchValidationAggregationResponse,
)
async def get_research_validation(
    research_run_id: str,
) -> ResearchValidationAggregationResponse:
    """Return grouped validation aggregation sections for a research report."""
    try:
        return ResearchReportStore().read_validation_aggregation(research_run_id)
    except FileNotFoundError:
        research_report_not_found(research_run_id)

    raise HTTPException(status_code=500, detail="Research validation summary read failed")

