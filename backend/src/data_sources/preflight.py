"""Safe skeleton for future data-source preflight checks."""

from collections.abc import Mapping

from src.data_sources.readiness import data_source_readiness
from src.models.data_sources import (
    DataSourcePreflightRequest,
    DataSourcePreflightResult,
    FirstEvidenceRunStatus,
)

PREFLIGHT_SKELETON_WARNING = (
    "Data-source preflight execution is not implemented in this readiness checkpoint."
)
PREFLIGHT_SKELETON_LIMITATION = (
    "Skeleton only: no external downloads, paid provider calls, trading, or evidence "
    "execution are performed."
)


class DataSourcePreflightNotImplementedError(NotImplementedError):
    """Raised when future preflight execution is requested before implementation."""


class DataSourcePreflightService:
    """Research-only placeholder for future first-run data preflight."""

    def preview(
        self,
        request: DataSourcePreflightRequest,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> DataSourcePreflightResult:
        """Return a non-executing preview snapshot for readiness-checkpoint tests."""

        del request
        readiness = data_source_readiness(environ=environ)
        return DataSourcePreflightResult(
            status=FirstEvidenceRunStatus.BLOCKED,
            readiness=readiness,
            missing_data_actions=list(readiness.missing_data_actions),
            warnings=[PREFLIGHT_SKELETON_WARNING],
            limitations=[PREFLIGHT_SKELETON_LIMITATION],
        )

    def run(self, request: DataSourcePreflightRequest) -> DataSourcePreflightResult:
        """Reject execution until the dedicated preflight user story is implemented."""

        del request
        raise DataSourcePreflightNotImplementedError(PREFLIGHT_SKELETON_WARNING)
