import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from src.config import get_settings
from src.models.xau_reaction import (
    XauReactionArtifactFormat,
    XauReactionArtifactType,
    XauReactionReport,
    XauReactionReportArtifact,
    XauReactionReportListResponse,
    XauReactionReportSummary,
    XauReactionTableResponse,
    XauRiskPlanTableResponse,
    validate_filesystem_safe_id,
)
from src.reports.collision_guard import (
    assert_report_write_allowed,
    resolve_report_source_kind_for_write,
)
from src.reports.writer import (
    compose_xau_reaction_report_json,
    compose_xau_reaction_report_markdown,
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

    def save_report(
        self,
        report: XauReactionReport,
        *,
        source_kind: str | None = None,
        overwrite_allowed: bool = False,
    ) -> XauReactionReport:
        """Persist reaction report metadata, section tables, and report artifacts."""

        self.ensure_report_root()
        requested_source_kind = resolve_report_source_kind_for_write(
            report_id=report.report_id,
            explicit_source_kind=source_kind,
            model_source_kind=report.source_kind,
        )
        normalized_source_kind = assert_report_write_allowed(
            report_dir=self.report_dir(report.report_id),
            report_id=report.report_id,
            source_kind=requested_source_kind,
            overwrite_allowed=overwrite_allowed,
        )
        report = report.model_copy(update={"source_kind": normalized_source_kind})
        report_dir = self.ensure_report_dir(report.report_id)
        metadata_path = report_dir / "metadata.json"
        report_json_path = report_dir / "report.json"
        report_markdown_path = report_dir / "report.md"
        reactions_path = report_dir / "reactions.parquet"
        risk_plans_path = report_dir / "risk_plans.parquet"

        artifacts = [
            self.artifact(
                artifact_type=XauReactionArtifactType.METADATA,
                path=metadata_path,
                artifact_format=XauReactionArtifactFormat.JSON,
            )
        ]

        if report.reactions:
            self._write_parquet(
                reactions_path,
                [reaction.model_dump(mode="json") for reaction in report.reactions],
            )
            artifacts.append(
                self.artifact(
                    artifact_type=XauReactionArtifactType.REACTIONS,
                    path=reactions_path,
                    artifact_format=XauReactionArtifactFormat.PARQUET,
                    rows=len(report.reactions),
                )
            )

        if report.risk_plans:
            self._write_parquet(
                risk_plans_path,
                [risk_plan.model_dump(mode="json") for risk_plan in report.risk_plans],
            )
            artifacts.append(
                self.artifact(
                    artifact_type=XauReactionArtifactType.RISK_PLANS,
                    path=risk_plans_path,
                    artifact_format=XauReactionArtifactFormat.PARQUET,
                    rows=len(report.risk_plans),
                )
            )

        if report.request.report_format in {"json", "both"}:
            self._write_json(report_json_path, compose_xau_reaction_report_json(report))
            artifacts.append(
                self.artifact(
                    artifact_type=XauReactionArtifactType.REPORT_JSON,
                    path=report_json_path,
                    artifact_format=XauReactionArtifactFormat.JSON,
                )
            )

        if report.request.report_format in {"markdown", "both"}:
            report_markdown_path.write_text(
                compose_xau_reaction_report_markdown(report),
                encoding="utf-8",
            )
            artifacts.append(
                self.artifact(
                    artifact_type=XauReactionArtifactType.REPORT_MARKDOWN,
                    path=report_markdown_path,
                    artifact_format=XauReactionArtifactFormat.MARKDOWN,
                )
            )

        saved_report = report.model_copy(update={"artifacts": artifacts})
        self._write_json(metadata_path, saved_report.model_dump(mode="json"))
        if report_json_path.exists():
            self._write_json(report_json_path, compose_xau_reaction_report_json(saved_report))
        if report_markdown_path.exists():
            report_markdown_path.write_text(
                compose_xau_reaction_report_markdown(saved_report),
                encoding="utf-8",
            )
        return saved_report

    def list_reports(self) -> XauReactionReportListResponse:
        if not self.xau_reaction_dir.exists():
            return XauReactionReportListResponse(reports=[])
        reports = [
            self.read_report(metadata_path.parent.name)
            for metadata_path in self.xau_reaction_dir.glob("*/metadata.json")
        ]
        summaries = [
            XauReactionReportSummary(
                report_id=report.report_id,
                source_kind=report.source_kind,
                source_report_id=report.source_report_id,
                status=report.status,
                created_at=report.created_at,
                session_date=report.session_date,
                reaction_count=report.reaction_count,
                no_trade_count=report.no_trade_count,
                risk_plan_count=report.risk_plan_count,
                warning_count=len(report.warnings),
            )
            for report in sorted(reports, key=lambda item: item.created_at, reverse=True)
        ]
        return XauReactionReportListResponse(reports=summaries)

    def read_report(self, report_id: str) -> XauReactionReport:
        metadata_path = self.report_dir(report_id) / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(report_id)
        return XauReactionReport.model_validate_json(metadata_path.read_text(encoding="utf-8"))

    def read_reactions(self, report_id: str) -> XauReactionTableResponse:
        report = self.read_report(report_id)
        return XauReactionTableResponse(report_id=report.report_id, data=report.reactions)

    def read_risk_plan(self, report_id: str) -> XauRiskPlanTableResponse:
        report = self.read_report(report_id)
        return XauRiskPlanTableResponse(report_id=report.report_id, data=report.risk_plans)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_parquet(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if rows:
            pl.DataFrame(rows).write_parquet(path)
