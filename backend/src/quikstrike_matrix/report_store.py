"""Path-safe persistence for local-only QuikStrike Matrix extraction reports."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.quikstrike_matrix import (
    QuikStrikeMatrixArtifact,
    QuikStrikeMatrixArtifactFormat,
    QuikStrikeMatrixArtifactType,
    QuikStrikeMatrixConversionResult,
    QuikStrikeMatrixConversionRowsResponse,
    QuikStrikeMatrixExtractionListResponse,
    QuikStrikeMatrixExtractionReport,
    QuikStrikeMatrixExtractionResult,
    QuikStrikeMatrixExtractionSummary,
    QuikStrikeMatrixNormalizedRow,
    QuikStrikeMatrixRowsResponse,
    QuikStrikeMatrixXauVolOiRow,
    validate_quikstrike_matrix_safe_id,
)


class QuikStrikeMatrixReportStore:
    """Local Matrix report store that never persists browser/session material."""

    def __init__(
        self,
        *,
        raw_dir: Path | None = None,
        processed_dir: Path | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.raw_root_base = raw_dir or settings.data_raw_path
        self.processed_root_base = processed_dir or settings.data_processed_path
        self.reports_root_base = reports_dir or settings.data_reports_path
        if reports_dir is not None and raw_dir is None and processed_dir is None:
            data_root = self.reports_root_base.parent
            self.raw_root_base = data_root / "raw"
            self.processed_root_base = data_root / "processed"
        self.repo_root = Path(__file__).resolve().parents[3]
        self.raw_root_dir = self.raw_root_base / "quikstrike_matrix"
        self.processed_root_dir = self.processed_root_base / "quikstrike_matrix"
        self.reports_root_dir = self.reports_root_base / "quikstrike_matrix"

    def raw_root(self) -> Path:
        return self.raw_root_dir

    def processed_root(self) -> Path:
        return self.processed_root_dir

    def report_root(self) -> Path:
        return self.reports_root_dir

    def ensure_roots(self) -> None:
        self.raw_root_dir.mkdir(parents=True, exist_ok=True)
        self.processed_root_dir.mkdir(parents=True, exist_ok=True)
        self.reports_root_dir.mkdir(parents=True, exist_ok=True)

    def report_dir(self, extraction_id: str) -> Path:
        safe_extraction_id = validate_quikstrike_matrix_safe_id(extraction_id)
        return self.reports_root_dir / safe_extraction_id

    def ensure_report_dir(self, extraction_id: str) -> Path:
        path = self.report_dir(extraction_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, extraction_id: str, filename: str, *, root: str = "reports") -> Path:
        if Path(filename).name != filename:
            raise ValueError("artifact filename must not contain path separators")
        validate_quikstrike_matrix_safe_id(extraction_id)
        if root == "raw":
            return self.raw_root_dir / filename
        if root == "processed":
            return self.processed_root_dir / filename
        if root == "reports":
            return self.report_dir(extraction_id) / filename
        raise ValueError("unknown artifact root")

    def persist_report(
        self,
        *,
        extraction_result: QuikStrikeMatrixExtractionResult,
        normalized_rows: list[QuikStrikeMatrixNormalizedRow],
        conversion_result: QuikStrikeMatrixConversionResult | None = None,
        conversion_rows: list[QuikStrikeMatrixXauVolOiRow] | None = None,
    ) -> QuikStrikeMatrixExtractionReport:
        """Persist metadata, rows, artifact metadata, and report JSON/Markdown."""

        self.ensure_roots()
        report_dir = self.ensure_report_dir(extraction_result.extraction_id)
        metadata_path = self.raw_root_dir / f"{extraction_result.extraction_id}_metadata.json"
        normalized_rows_path = (
            self.raw_root_dir / f"{extraction_result.extraction_id}_normalized_rows.json"
        )
        conversion_rows_path = (
            self.processed_root_dir
            / f"{extraction_result.extraction_id}_xau_vol_oi_input.csv"
        )
        conversion_metadata_path = (
            self.processed_root_dir
            / f"{extraction_result.extraction_id}_conversion_metadata.json"
        )
        artifact_metadata_path = report_dir / "artifact_metadata.json"
        report_json_path = report_dir / "report.json"
        report_markdown_path = report_dir / "report.md"

        artifacts = [
            self.artifact(
                artifact_type=QuikStrikeMatrixArtifactType.RAW_METADATA,
                path=metadata_path,
                artifact_format=QuikStrikeMatrixArtifactFormat.JSON,
            ),
            self.artifact(
                artifact_type=QuikStrikeMatrixArtifactType.RAW_NORMALIZED_ROWS_JSON,
                path=normalized_rows_path,
                artifact_format=QuikStrikeMatrixArtifactFormat.JSON,
                rows=len(normalized_rows),
            ),
            self.artifact(
                artifact_type=QuikStrikeMatrixArtifactType.REPORT_JSON,
                path=report_json_path,
                artifact_format=QuikStrikeMatrixArtifactFormat.JSON,
            ),
            self.artifact(
                artifact_type=QuikStrikeMatrixArtifactType.REPORT_MARKDOWN,
                path=report_markdown_path,
                artifact_format=QuikStrikeMatrixArtifactFormat.MARKDOWN,
            ),
        ]
        if conversion_rows is not None:
            artifacts.extend(
                [
                    self.artifact(
                        artifact_type=QuikStrikeMatrixArtifactType.PROCESSED_XAU_VOL_OI_CSV,
                        path=conversion_rows_path,
                        artifact_format=QuikStrikeMatrixArtifactFormat.CSV,
                        rows=len(conversion_rows),
                    ),
                    self.artifact(
                        artifact_type=QuikStrikeMatrixArtifactType.CONVERSION_METADATA,
                        path=conversion_metadata_path,
                        artifact_format=QuikStrikeMatrixArtifactFormat.JSON,
                    ),
                ]
            )
        report = QuikStrikeMatrixExtractionReport(
            extraction_id=extraction_result.extraction_id,
            status=extraction_result.status,
            created_at=extraction_result.created_at,
            completed_at=extraction_result.completed_at,
            request_summary=_request_summary(extraction_result),
            view_summaries=_view_summaries(extraction_result, normalized_rows),
            row_count=len(normalized_rows),
            strike_count=extraction_result.strike_count,
            expiration_count=extraction_result.expiration_count,
            unavailable_cell_count=extraction_result.unavailable_cell_count,
            mapping=extraction_result.mapping,
            conversion_result=conversion_result,
            artifacts=_dedupe_artifacts(artifacts),
            warnings=extraction_result.warnings,
            limitations=extraction_result.limitations,
            research_only_warnings=extraction_result.research_only_warnings,
        )

        self._write_json(metadata_path, _metadata_payload(report))
        self._write_json(
            normalized_rows_path,
            [row.model_dump(mode="json") for row in normalized_rows],
        )
        if conversion_rows is not None:
            self._write_csv(
                conversion_rows_path,
                [row.model_dump(mode="json") for row in conversion_rows],
            )
            self._write_json(
                conversion_metadata_path,
                conversion_result.model_dump(mode="json") if conversion_result else {},
            )
        self._write_json(
            artifact_metadata_path,
            [artifact.model_dump(mode="json") for artifact in report.artifacts],
        )
        self._write_json(report_json_path, report.model_dump(mode="json"))
        report_markdown_path.write_text(_report_markdown(report), encoding="utf-8")
        return report

    def read_report(self, extraction_id: str) -> QuikStrikeMatrixExtractionReport:
        path = self.report_dir(extraction_id) / "report.json"
        if not path.exists():
            raise FileNotFoundError(extraction_id)
        return QuikStrikeMatrixExtractionReport.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def list_reports(self) -> QuikStrikeMatrixExtractionListResponse:
        root = self.report_root()
        if not root.exists():
            return QuikStrikeMatrixExtractionListResponse(extractions=[])
        summaries: list[QuikStrikeMatrixExtractionSummary] = []
        for report_path in root.glob("*/report.json"):
            try:
                summaries.append(self.summarize_report(self.read_report(report_path.parent.name)))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return QuikStrikeMatrixExtractionListResponse(
            extractions=sorted(summaries, key=lambda item: item.created_at, reverse=True)
        )

    def summarize_report(
        self,
        report: QuikStrikeMatrixExtractionReport,
    ) -> QuikStrikeMatrixExtractionSummary:
        requested_views = report.request_summary.get("requested_views", [])
        completed_views = report.request_summary.get("completed_views", [])
        missing_views = report.request_summary.get("missing_views", [])
        conversion_eligible = bool(report.request_summary.get("conversion_eligible", False))
        return QuikStrikeMatrixExtractionSummary(
            extraction_id=report.extraction_id,
            status=report.status,
            created_at=report.created_at,
            completed_at=report.completed_at,
            requested_view_count=len(requested_views),
            completed_view_count=len(completed_views),
            missing_view_count=len(missing_views),
            row_count=report.row_count,
            strike_count=report.strike_count,
            expiration_count=report.expiration_count,
            unavailable_cell_count=report.unavailable_cell_count,
            conversion_eligible=conversion_eligible,
            conversion_status=(
                report.conversion_result.status if report.conversion_result else None
            ),
            artifact_count=len(report.artifacts),
            warning_count=len(report.warnings) + len(report.mapping.warnings),
            limitation_count=len(report.limitations) + len(report.mapping.limitations),
        )

    def read_normalized_rows(self, extraction_id: str) -> list[QuikStrikeMatrixNormalizedRow]:
        report = self.read_report(extraction_id)
        row_artifact = next(
            (
                artifact
                for artifact in report.artifacts
                if artifact.artifact_type == QuikStrikeMatrixArtifactType.RAW_NORMALIZED_ROWS_JSON
            ),
            None,
        )
        if row_artifact is None:
            raise FileNotFoundError(extraction_id)
        path = self._absolute_from_project_path(row_artifact.path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [QuikStrikeMatrixNormalizedRow.model_validate(row) for row in payload]

    def read_rows_response(self, extraction_id: str) -> QuikStrikeMatrixRowsResponse:
        return QuikStrikeMatrixRowsResponse(
            extraction_id=extraction_id,
            rows=self.read_normalized_rows(extraction_id),
        )

    def read_conversion_rows(
        self,
        extraction_id: str,
    ) -> list[QuikStrikeMatrixXauVolOiRow]:
        report = self.read_report(extraction_id)
        conversion_artifact = next(
            (
                artifact
                for artifact in report.artifacts
                if artifact.artifact_type == QuikStrikeMatrixArtifactType.PROCESSED_XAU_VOL_OI_CSV
            ),
            None,
        )
        if conversion_artifact is None:
            raise FileNotFoundError(extraction_id)
        path = self._absolute_from_project_path(conversion_artifact.path)
        with path.open(newline="", encoding="utf-8") as handle:
            return [
                QuikStrikeMatrixXauVolOiRow.model_validate(_coerce_csv_row(row))
                for row in csv.DictReader(handle)
            ]

    def read_conversion_response(
        self,
        extraction_id: str,
    ) -> QuikStrikeMatrixConversionRowsResponse:
        report = self.read_report(extraction_id)
        try:
            rows = self.read_conversion_rows(extraction_id)
        except FileNotFoundError:
            rows = []
        return QuikStrikeMatrixConversionRowsResponse(
            extraction_id=extraction_id,
            conversion_result=report.conversion_result,
            rows=rows,
        )

    def artifact(
        self,
        *,
        artifact_type: QuikStrikeMatrixArtifactType,
        path: Path,
        artifact_format: QuikStrikeMatrixArtifactFormat,
        rows: int | None = None,
    ) -> QuikStrikeMatrixArtifact:
        self._validate_artifact_scope(path)
        return QuikStrikeMatrixArtifact(
            artifact_type=artifact_type,
            path=self._project_relative_path(path),
            format=artifact_format,
            rows=rows,
            created_at=datetime.now(UTC),
        )

    def _validate_artifact_scope(self, path: Path) -> None:
        resolved_path = path.resolve()
        allowed_roots = (
            self.raw_root_dir.resolve(),
            self.processed_root_dir.resolve(),
            self.reports_root_dir.resolve(),
        )
        if not any(root in (resolved_path, *resolved_path.parents) for root in allowed_roots):
            raise ValueError("QuikStrike Matrix artifact path must stay under artifact roots")

    def _project_relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_root)).replace("\\", "/")
        except ValueError:
            pass
        candidates = [
            self.raw_root_base.parent.parent,
            self.processed_root_base.parent.parent,
            self.reports_root_base.parent.parent,
        ]
        for candidate in candidates:
            try:
                return str(path.relative_to(candidate)).replace("\\", "/")
            except ValueError:
                continue
        return str(path).replace("\\", "/")

    def _absolute_from_project_path(self, path: str) -> Path:
        normalized = Path(path)
        if normalized.is_absolute():
            return normalized
        candidates = [
            self.repo_root / normalized,
            self.raw_root_base.parent.parent / normalized,
            self.processed_root_base.parent.parent / normalized,
            self.reports_root_base.parent.parent / normalized,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = sorted({key for row in rows for key in row})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _request_summary(result: QuikStrikeMatrixExtractionResult) -> dict[str, Any]:
    return {
        "requested_views": [view.value for view in result.requested_views],
        "completed_views": [view.value for view in result.completed_views],
        "partial_views": [view.value for view in result.partial_views],
        "missing_views": [view.value for view in result.missing_views],
        "conversion_eligible": result.conversion_eligible,
    }


def _view_summaries(
    result: QuikStrikeMatrixExtractionResult,
    rows: list[QuikStrikeMatrixNormalizedRow],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for view in result.requested_views:
        view_rows = [row for row in rows if row.view_type == view]
        summaries.append(
            {
                "view_type": view.value,
                "row_count": len(view_rows),
                "strike_count": len({row.strike for row in view_rows if row.strike is not None}),
                "expiration_count": len(
                    {row.expiration for row in view_rows if row.expiration}
                ),
                "unavailable_cell_count": sum(
                    row.cell_state.value != "available" for row in view_rows
                ),
            }
        )
    return summaries


def _metadata_payload(report: QuikStrikeMatrixExtractionReport) -> dict[str, Any]:
    return {
        "extraction_id": report.extraction_id,
        "status": report.status.value,
        "created_at": report.created_at.isoformat(),
        "completed_at": report.completed_at.isoformat() if report.completed_at else None,
        "row_count": report.row_count,
        "strike_count": report.strike_count,
        "expiration_count": report.expiration_count,
        "unavailable_cell_count": report.unavailable_cell_count,
        "mapping": report.mapping.model_dump(mode="json"),
        "artifact_count": len(report.artifacts),
        "warnings": report.warnings,
        "limitations": report.limitations,
        "research_only_warnings": report.research_only_warnings,
    }


def _report_markdown(report: QuikStrikeMatrixExtractionReport) -> str:
    lines = [
        f"# QuikStrike Matrix Extraction Report {report.extraction_id}",
        "",
        "Local-only research report. No browser cookies, tokens, headers, viewstate, "
        "HAR files, screenshots, credentials, endpoint replay payloads, or private full "
        "URLs are persisted.",
        "",
        f"- Status: `{report.status.value}`",
        f"- Row count: `{report.row_count}`",
        f"- Strike count: `{report.strike_count}`",
        f"- Expiration count: `{report.expiration_count}`",
        f"- Unavailable cells: `{report.unavailable_cell_count}`",
        f"- Mapping: `{report.mapping.status.value}`",
        f"- Conversion eligible: `{report.request_summary.get('conversion_eligible', False)}`",
        "",
        "## View Summary",
    ]
    for summary in report.view_summaries:
        lines.append(
            "- {view_type}: {row_count} rows, {strike_count} strikes, "
            "{expiration_count} expirations, {unavailable_cell_count} unavailable cells".format(
                **summary
            )
        )
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in [*report.warnings, *report.mapping.warnings])
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    lines.extend(["", "## Artifacts"])
    lines.extend(f"- `{artifact.path}`" for artifact in report.artifacts)
    return "\n".join(lines) + "\n"


def _dedupe_artifacts(
    artifacts: list[QuikStrikeMatrixArtifact],
) -> list[QuikStrikeMatrixArtifact]:
    deduped: list[QuikStrikeMatrixArtifact] = []
    seen: set[tuple[str, str]] = set()
    for artifact in artifacts:
        key = (artifact.artifact_type.value, artifact.path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(artifact)
    return deduped


def _csv_value(value: Any) -> Any:
    if isinstance(value, list):
        return json.dumps(value)
    return value


def _coerce_csv_row(row: dict[str, str]) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    numeric_fields = {
        "strike",
        "open_interest",
        "oi_change",
        "volume",
        "dte",
        "underlying_futures_price",
    }
    json_list_fields = {"limitations"}
    for key, value in row.items():
        if value == "":
            coerced[key] = None
        elif key in numeric_fields:
            coerced[key] = float(value)
        elif key in json_list_fields:
            coerced[key] = json.loads(value)
        else:
            coerced[key] = value
    return coerced
