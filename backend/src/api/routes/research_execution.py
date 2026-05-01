from fastapi import APIRouter, HTTPException, status

from src.api.validation import (
    invalid_research_execution_config,
    research_execution_not_implemented,
    research_execution_run_not_found,
)
from src.models.research_execution import (
    ResearchEvidenceSummary,
    ResearchExecutionMissingDataResponse,
    ResearchExecutionRun,
    ResearchExecutionRunListResponse,
    ResearchExecutionRunRequest,
)
from src.research_execution.orchestration import (
    ResearchExecutionNotImplementedError,
    ResearchExecutionOrchestrator,
)
from src.research_execution.report_store import ResearchExecutionReportStore

router = APIRouter()


@router.post(
    "/research/execution-runs",
    response_model=ResearchExecutionRun,
    status_code=status.HTTP_201_CREATED,
)
async def run_research_execution(
    request: ResearchExecutionRunRequest,
) -> ResearchExecutionRun:
    """Start a research-only execution runbook workflow."""

    try:
        return ResearchExecutionOrchestrator().run(request)
    except ResearchExecutionNotImplementedError:
        research_execution_not_implemented()
    except ValueError as exc:
        invalid_research_execution_config(str(exc))

    raise HTTPException(status_code=500, detail="Research execution run failed")


@router.get("/research/execution-runs", response_model=ResearchExecutionRunListResponse)
async def list_research_execution_runs() -> ResearchExecutionRunListResponse:
    """List saved research execution runs."""

    return ResearchExecutionReportStore().list_runs()


@router.get("/research/execution-runs/{execution_run_id}", response_model=ResearchExecutionRun)
async def get_research_execution_run(execution_run_id: str) -> ResearchExecutionRun:
    """Read one persisted research execution run."""

    try:
        return ResearchExecutionReportStore().read_run(execution_run_id)
    except FileNotFoundError:
        research_execution_run_not_found(execution_run_id)
    except ValueError as exc:
        invalid_research_execution_config(str(exc))

    raise HTTPException(status_code=500, detail="Research execution run read failed")


@router.get(
    "/research/execution-runs/{execution_run_id}/evidence",
    response_model=ResearchEvidenceSummary,
)
async def get_research_execution_evidence(
    execution_run_id: str,
) -> ResearchEvidenceSummary:
    """Read the final evidence summary for one execution run."""

    try:
        return ResearchExecutionReportStore().read_evidence(execution_run_id)
    except FileNotFoundError:
        research_execution_run_not_found(execution_run_id)
    except ValueError as exc:
        invalid_research_execution_config(str(exc))

    raise HTTPException(status_code=500, detail="Research execution evidence read failed")


@router.get(
    "/research/execution-runs/{execution_run_id}/missing-data",
    response_model=ResearchExecutionMissingDataResponse,
)
async def get_research_execution_missing_data(
    execution_run_id: str,
) -> ResearchExecutionMissingDataResponse:
    """Read missing-data actions for one execution run."""

    try:
        return ResearchExecutionReportStore().read_missing_data(execution_run_id)
    except FileNotFoundError:
        research_execution_run_not_found(execution_run_id)
    except ValueError as exc:
        invalid_research_execution_config(str(exc))

    raise HTTPException(status_code=500, detail="Research execution missing-data read failed")
