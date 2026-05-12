from datetime import UTC, datetime
from pathlib import Path

from src.config import get_settings
from src.models.xau_reaction import (
    XauReactionArtifactFormat,
    XauReactionArtifactType,
    XauReactionReportArtifact,
    validate_filesystem_safe_id,
)


class XauReactionReportStore:
    """Path-safe local storage surface for XAU reaction report artifacts."""

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.xau_reaction_dir = self.reports_dir / "xau_reaction"

    def report_root(self) -> Path:
        return self.xau_reaction_dir

    def ensure_report_root(self) -> Path:
        self.xau_reaction_dir.mkdir(parents=True, exist_ok=True)
        return self.xau_reaction_dir

    def report_dir(self, report_id: str) -> Path:
        safe_report_id = validate_filesystem_safe_id(report_id)
        return self.xau_reaction_dir / safe_report_id

    def ensure_report_dir(self, report_id: str) -> Path:
        path = self.report_dir(report_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, report_id: str, filename: str) -> Path:
        if Path(filename).name != filename:
            raise ValueError("artifact filename must not contain path separators")
        return self.report_dir(report_id) / filename

    def artifact(
        self,
        *,
        artifact_type: XauReactionArtifactType,
        path: Path,
        artifact_format: XauReactionArtifactFormat,
        rows: int | None = None,
    ) -> XauReactionReportArtifact:
        resolved_root = self.xau_reaction_dir.resolve()
        resolved_path = path.resolve()
        if resolved_root not in (resolved_path, *resolved_path.parents):
            raise ValueError("XAU reaction artifact path must stay under report root")
        try:
            artifact_path = str(path.relative_to(self.repo_root))
        except ValueError:
            artifact_path = str(path)
        return XauReactionReportArtifact(
            artifact_type=artifact_type,
            path=artifact_path,
            format=artifact_format,
            rows=rows,
            created_at=datetime.now(UTC),
        )
