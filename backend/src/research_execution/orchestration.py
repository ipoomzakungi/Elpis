"""Research execution runbook orchestration skeleton."""

from src.models.research_execution import ResearchExecutionRun, ResearchExecutionRunRequest


class ResearchExecutionNotImplementedError(NotImplementedError):
    """Raised until story phases implement execution orchestration."""


class ResearchExecutionOrchestrator:
    """Coordinates existing research systems without adding strategy logic."""

    def run(self, request: ResearchExecutionRunRequest) -> ResearchExecutionRun:
        """Run a research execution workflow.

        Foundation phases expose the API contract and validation boundary only.
        Story phases will wire existing feature 005 and 006 report systems here.
        """

        raise ResearchExecutionNotImplementedError(
            "Research execution orchestration is not implemented in this phase"
        )
