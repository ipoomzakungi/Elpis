"""Safe skeleton for future first evidence run orchestration."""

from src.models.data_sources import FirstEvidenceRunRequest, FirstEvidenceRunResult

FIRST_RUN_SKELETON_WARNING = (
    "First evidence run orchestration is not implemented in this readiness checkpoint."
)


class FirstEvidenceRunNotImplementedError(NotImplementedError):
    """Raised when first-run execution is requested before implementation."""


class FirstEvidenceRunOrchestrator:
    """Research-only placeholder that performs no execution or external data fetches."""

    def run(self, request: FirstEvidenceRunRequest) -> FirstEvidenceRunResult:
        """Reject execution until the dedicated first-run user story is implemented."""

        del request
        raise FirstEvidenceRunNotImplementedError(FIRST_RUN_SKELETON_WARNING)
