import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from src.config import get_settings
from src.models.xau import (
    XauArtifactFormat,
    XauArtifactType,
    XauReportArtifact,
    XauVolOiReport,
    XauVolOiReportListResponse,
    XauVolOiReportSummary,
    XauWallTableResponse,
    XauZoneTableResponse,
)
from src.reports.writer import compose_xau_report_json, compose_xau_report_markdown


class XauReportStore:
    """Persist XAU report metadata and source validation artifacts locally."""

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self.xau_dir = self.reports_dir / "xau_vol_oi"

    def save_source_validation_report(self, report: XauVolOiReport) -> XauVolOiReport:
        self.xau_dir.mkdir(parents=True, exist_ok=True)
        report_dir = self._report_dir(report.report_id)
        report_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = report_dir / "metadata.json"
        source_validation_path = report_dir / "source_validation.json"
        report_json_path = report_dir / "report.json"
        report_markdown_path = report_dir / "report.md"
        walls_path = report_dir / "walls.parquet"
        zones_path = report_dir / "zones.parquet"

        self._write_json(metadata_path, report.model_dump(mode="json", exclude={"artifacts"}))
        self._write_json(source_validation_path, report.source_validation.model_dump(mode="json"))
        self._write_json(report_json_path, compose_xau_report_json(report))
        report_markdown_path.write_text(compose_xau_report_markdown(report), encoding="utf-8")

        artifacts = [
            self._artifact(XauArtifactType.METADATA, metadata_path, XauArtifactFormat.JSON),
            self._artifact(
                XauArtifactType.SOURCE_VALIDATION,
                source_validation_path,
                XauArtifactFormat.JSON,
                rows=report.source_validation.source_row_count,
            ),
            self._artifact(XauArtifactType.REPORT_JSON, report_json_path, XauArtifactFormat.JSON),
            self._artifact(
                XauArtifactType.REPORT_MARKDOWN,
                report_markdown_path,
                XauArtifactFormat.MARKDOWN,
            ),
        ]
        if report.walls:
            self._write_parquet(walls_path, [wall.model_dump(mode="json") for wall in report.walls])
            artifacts.append(
                self._artifact(
                    XauArtifactType.WALLS,
                    walls_path,
                    XauArtifactFormat.PARQUET,
                    rows=len(report.walls),
                )
            )
        if report.zones:
            self._write_parquet(zones_path, [zone.model_dump(mode="json") for zone in report.zones])
            artifacts.append(
                self._artifact(
                    XauArtifactType.ZONES,
                    zones_path,
                    XauArtifactFormat.PARQUET,
                    rows=len(report.zones),
                )
            )
        report.artifacts = artifacts
        self._write_json(metadata_path, report.model_dump(mode="json"))
        self._write_json(report_json_path, compose_xau_report_json(report))
        report_markdown_path.write_text(compose_xau_report_markdown(report), encoding="utf-8")
        return report

    def list_reports(self) -> XauVolOiReportListResponse:
        if not self.xau_dir.exists():
            return XauVolOiReportListResponse(reports=[])
        summaries = []
        for metadata_path in sorted(self.xau_dir.glob("*/metadata.json"), reverse=True):
            report = self._read_report(metadata_path.parent.name)
            summaries.append(
                XauVolOiReportSummary(
                    report_id=report.report_id,
                    status=report.status,
                    created_at=report.created_at,
                    session_date=report.session_date,
                    source_row_count=report.source_row_count,
                    wall_count=report.wall_count,
                    zone_count=report.zone_count,
                    warning_count=len(report.warnings),
                )
            )
        return XauVolOiReportListResponse(reports=summaries)

    def read_report(self, report_id: str) -> XauVolOiReport:
        return self._read_report(report_id)

    def read_walls(self, report_id: str) -> XauWallTableResponse:
        report = self._read_report(report_id)
        return XauWallTableResponse(report_id=report_id, data=report.walls)

    def read_zones(self, report_id: str) -> XauZoneTableResponse:
        report = self._read_report(report_id)
        return XauZoneTableResponse(report_id=report_id, data=report.zones)

    def _read_report(self, report_id: str) -> XauVolOiReport:
        metadata_path = self._report_dir(report_id) / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(report_id)
        return XauVolOiReport.model_validate_json(metadata_path.read_text(encoding="utf-8"))

    def _report_dir(self, report_id: str) -> Path:
        safe_report_id = "".join(
            character for character in report_id if character.isalnum() or character in "_-"
        )
        if safe_report_id != report_id or not safe_report_id:
            raise ValueError("Invalid XAU report id")
        return self.xau_dir / safe_report_id

    def _artifact(
        self,
        artifact_type: XauArtifactType,
        path: Path,
        artifact_format: XauArtifactFormat,
        rows: int | None = None,
    ) -> XauReportArtifact:
        try:
            artifact_path = str(path.relative_to(self.repo_root))
        except ValueError:
            artifact_path = str(path)
        return XauReportArtifact(
            artifact_type=artifact_type,
            path=artifact_path,
            format=artifact_format,
            rows=rows,
            created_at=datetime.now(UTC),
        )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_parquet(self, path: Path, rows: list[dict[str, Any]]) -> None:
        pl.DataFrame(rows).write_parquet(path)
