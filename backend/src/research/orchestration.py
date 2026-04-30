"""Coordinator for grouped multi-asset research reports."""

from src.models.research import ResearchRun, ResearchRunRequest


class ResearchExecutionNotImplementedError(NotImplementedError):
    """Raised until story implementation adds concrete grouped execution."""


class ResearchOrchestrator:
    """Skeleton service for multi-asset research orchestration."""

    def run(self, request: ResearchRunRequest) -> ResearchRun:
        raise ResearchExecutionNotImplementedError(
            "Multi-asset research execution is not implemented in this phase"
        )

