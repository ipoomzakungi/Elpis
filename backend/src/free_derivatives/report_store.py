from datetime import UTC, datetime
from pathlib import Path

from src.config import get_settings
from src.models.free_derivatives import (
    FreeDerivativesArtifact,
    FreeDerivativesArtifactFormat,
    FreeDerivativesArtifactType,
    FreeDerivativesSource,
    validate_filesystem_safe_id,
)

SOURCE_DIRECTORY_NAMES = {
    FreeDerivativesSource.CFTC_COT: "cftc",
    FreeDerivativesSource.GVZ: "gvz",
    FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS: "deribit",
}


class FreeDerivativesReportStore:
    """Path-safe local storage surface for free derivatives research artifacts."""

    def __init__(
        self,
        raw_dir: Path | None = None,
        processed_dir: Path | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.raw_dir = raw_dir or settings.data_raw_path
        self.processed_dir = processed_dir or settings.data_processed_path
        self.reports_dir = reports_dir or settings.data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.free_derivatives_reports_dir = self.reports_dir / "free_derivatives"

    def raw_source_root(self, source: FreeDerivativesSource) -> Path:
        return self.raw_dir / SOURCE_DIRECTORY_NAMES[source]

    def processed_source_root(self, source: FreeDerivativesSource) -> Path:
        return self.processed_dir / SOURCE_DIRECTORY_NAMES[source]

    def report_root(self) -> Path:
        return self.free_derivatives_reports_dir

    def ensure_roots(self) -> None:
        for source in FreeDerivativesSource:
            self.raw_source_root(source).mkdir(parents=True, exist_ok=True)
            self.processed_source_root(source).mkdir(parents=True, exist_ok=True)
        self.free_derivatives_reports_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        safe_run_id = validate_filesystem_safe_id(run_id, label="run_id")
        return self.free_derivatives_reports_dir / safe_run_id

    def ensure_run_dir(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, run_id: str, filename: str) -> Path:
        if Path(filename).name != filename:
            raise ValueError("artifact filename must not contain path separators")
        return self.run_dir(run_id) / filename

    def artifact(
        self,
        *,
        artifact_type: FreeDerivativesArtifactType,
        source: FreeDerivativesSource,
        path: Path,
        artifact_format: FreeDerivativesArtifactFormat,
        rows: int | None = None,
        limitations: list[str] | None = None,
    ) -> FreeDerivativesArtifact:
        self._validate_artifact_scope(path)
        try:
            artifact_path = str(path.relative_to(self.repo_root))
        except ValueError:
            artifact_path = str(path)
        return FreeDerivativesArtifact(
            artifact_type=artifact_type,
            source=source,
            path=artifact_path,
            format=artifact_format,
            rows=rows,
            created_at=datetime.now(UTC),
            limitations=limitations or [],
        )

    def _validate_artifact_scope(self, path: Path) -> None:
        resolved_path = path.resolve()
        allowed_roots = [
            self.raw_dir.resolve(),
            self.processed_dir.resolve(),
            self.free_derivatives_reports_dir.resolve(),
        ]
        if not any(root in (resolved_path, *resolved_path.parents) for root in allowed_roots):
            raise ValueError("free derivatives artifact path must stay under generated roots")

