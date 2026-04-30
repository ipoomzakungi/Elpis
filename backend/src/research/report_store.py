"""Persistence helpers for grouped multi-asset research reports."""

from src.backtest.report_store import ReportStore
from src.models.research import (
    ResearchAssetSummaryResponse,
    ResearchComparisonResponse,
    ResearchRun,
    ResearchRunListResponse,
    ResearchRunSummary,
    ResearchValidationAggregationResponse,
)


class ResearchReportStore:
    """Skeleton store for grouped research reports.

    Phase 1/2 wires contracts and placeholders only. Story phases implement
    writes and reads for concrete grouped report artifacts.
    """

    def __init__(self, report_store: ReportStore | None = None):
        self.report_store = report_store or ReportStore()

    def list_runs(self) -> ResearchRunListResponse:
        return ResearchRunListResponse(runs=[])

    def list_run_summaries(self) -> list[ResearchRunSummary]:
        return []

    def read_run(self, research_run_id: str) -> ResearchRun:
        raise FileNotFoundError(research_run_id)

    def read_assets(self, research_run_id: str) -> ResearchAssetSummaryResponse:
        raise FileNotFoundError(research_run_id)

    def read_comparison(self, research_run_id: str) -> ResearchComparisonResponse:
        raise FileNotFoundError(research_run_id)

    def read_validation_aggregation(
        self,
        research_run_id: str,
    ) -> ResearchValidationAggregationResponse:
        raise FileNotFoundError(research_run_id)

