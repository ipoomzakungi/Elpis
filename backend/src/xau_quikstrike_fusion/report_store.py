from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_quikstrike_fusion import (
    XauFusionArtifact,
    XauFusionArtifactFormat,
    XauFusionArtifactType,
    XauFusionBaseModel,
    XauFusionContextStatus,
    XauFusionMissingContextResponse,
    XauFusionRow,
    XauFusionRowsResponse,
    XauFusionVolOiInputRow,
    XauQuikStrikeFusionListResponse,
    XauQuikStrikeFusionReport,
    XauQuikStrikeFusionSummary,
    validate_xau_fusion_safe_id,
)


class XauQuikStrikeFusionReportStore:
    """Path-safe helper for local-only XAU QuikStrike fusion report artifacts."""

    REPORT_ROOT_NAME = "xau_quikstrike_fusion"

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.settings = get_settings()
        self.reports_dir = reports_dir or self.settings.data_reports_path
        self.repo_root = Path(__file__).resolve().parents[3]
        self._report_root = (self.reports_dir / self.REPORT_ROOT_NAME).resolve()

    def report_root(self) -> Path:
        return self._report_root

    def ensure_report_root(self) -> Path:
        self._report_root.mkdir(parents=True, exist_ok=True)
        return self._report_root

    def report_dir(self, report_id: str) -> Path:
        safe_report_id = validate_xau_fusion_safe_id(report_id, "report_id")
        report_dir = (self._report_root / safe_report_id).resolve()
        self._validate_report_scope(report_dir)
        return report_dir

    def ensure_report_dir(self, report_id: str) -> Path:
        report_dir = self.report_dir(report_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir

    def artifact_path(self, report_id: str, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("artifact filename must be a plain filename")
        artifact_path = (self.report_dir(report_id) / filename).resolve()
        self._validate_report_scope(artifact_path)
        return artifact_path

    def artifact(
        self,
        *,
        artifact_type: XauFusionArtifactType,
        path: Path,
        artifact_format: XauFusionArtifactFormat,
        rows: int | None = None,
    ) -> XauFusionArtifact:
        resolved = path.resolve()
        self._validate_report_scope(resolved)
        return XauFusionArtifact(
            artifact_type=artifact_type,
            path=self._project_relative_path(resolved),
            format=artifact_format,
            rows=rows,
        )

    def artifact_for_filename(
        self,
        report_id: str,
        filename: str,
        *,
        artifact_type: XauFusionArtifactType,
        artifact_format: XauFusionArtifactFormat,
        rows: int | None = None,
    ) -> XauFusionArtifact:
        return self.artifact(
            artifact_type=artifact_type,
            path=self.artifact_path(report_id, filename),
            artifact_format=artifact_format,
            rows=rows,
        )

    def serialize_json(self, payload: Any) -> str:
        return json.dumps(_jsonable(payload), indent=2, sort_keys=True)

    def write_json_artifact(
        self,
        report_id: str,
        filename: str,
        payload: Any,
        *,
        artifact_type: XauFusionArtifactType,
        rows: int | None = None,
    ) -> XauFusionArtifact:
        path = self.artifact_path(report_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.serialize_json(payload), encoding="utf-8")
        return self.artifact(
            artifact_type=artifact_type,
            path=path,
            artifact_format=XauFusionArtifactFormat.JSON,
            rows=rows,
        )

    def write_xau_vol_oi_input_rows(
        self,
        report_id: str,
        rows: list[XauFusionVolOiInputRow],
        *,
        filename: str = "xau_vol_oi_input.csv",
    ) -> XauFusionArtifact:
        """Persist fused XAU Vol-OI input rows as a local CSV artifact."""

        path = self.artifact_path(report_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "date",
            "timestamp",
            "expiry",
            "expiration_code",
            "strike",
            "spot_equivalent_strike",
            "option_type",
            "open_interest",
            "oi_change",
            "volume",
            "intraday_volume",
            "eod_volume",
            "churn",
            "implied_volatility",
            "underlying_futures_price",
            "source",
            "source_report_ids",
            "source_agreement_status",
            "limitations",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                payload = row.model_dump(mode="json")
                payload["source_report_ids"] = "|".join(row.source_report_ids)
                payload["source_agreement_status"] = row.source_agreement_status.value
                payload["limitations"] = "|".join(row.limitations)
                writer.writerow({field: payload.get(field) for field in fieldnames})
        return self.artifact(
            artifact_type=XauFusionArtifactType.XAU_VOL_OI_INPUT_CSV,
            path=path,
            artifact_format=XauFusionArtifactFormat.CSV,
            rows=len(rows),
        )

    def persist_report(
        self,
        report: XauQuikStrikeFusionReport,
        *,
        xau_vol_oi_input_rows: list[XauFusionVolOiInputRow] | None = None,
    ) -> XauQuikStrikeFusionReport:
        """Persist MVP fusion metadata, rows, JSON, and Markdown artifacts."""

        report_dir = self.ensure_report_dir(report.report_id)
        metadata_path = report_dir / "metadata.json"
        fused_rows_path = report_dir / "fused_rows.json"
        report_json_path = report_dir / "report.json"
        report_markdown_path = report_dir / "report.md"

        artifacts = [
            self.artifact(
                artifact_type=XauFusionArtifactType.METADATA,
                path=metadata_path,
                artifact_format=XauFusionArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact(
                artifact_type=XauFusionArtifactType.FUSED_ROWS_JSON,
                path=fused_rows_path,
                artifact_format=XauFusionArtifactFormat.JSON,
                rows=len(report.fused_rows),
            ),
            self.artifact(
                artifact_type=XauFusionArtifactType.REPORT_JSON,
                path=report_json_path,
                artifact_format=XauFusionArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact(
                artifact_type=XauFusionArtifactType.REPORT_MARKDOWN,
                path=report_markdown_path,
                artifact_format=XauFusionArtifactFormat.MARKDOWN,
                rows=1,
            ),
        ]
        if xau_vol_oi_input_rows is not None:
            artifacts.append(
                self.write_xau_vol_oi_input_rows(
                    report.report_id,
                    xau_vol_oi_input_rows,
                )
            )
        saved_report = report.model_copy(update={"artifacts": artifacts})
        metadata_path.write_text(
            self.serialize_json(_metadata_payload(saved_report)) + "\n",
            encoding="utf-8",
        )
        fused_rows_path.write_text(
            self.serialize_json(saved_report.fused_rows) + "\n",
            encoding="utf-8",
        )
        report_json_path.write_text(
            self.serialize_json(saved_report) + "\n",
            encoding="utf-8",
        )
        report_markdown_path.write_text(_report_markdown(saved_report), encoding="utf-8")
        return saved_report

    def read_report(self, report_id: str) -> XauQuikStrikeFusionReport:
        path = self.artifact_path(report_id, "report.json")
        if not path.exists():
            raise FileNotFoundError(report_id)
        return XauQuikStrikeFusionReport.model_validate_json(path.read_text(encoding="utf-8"))

    def list_reports(self) -> XauQuikStrikeFusionListResponse:
        root = self.report_root()
        if not root.exists():
            return XauQuikStrikeFusionListResponse(reports=[])
        summaries: list[XauQuikStrikeFusionSummary] = []
        for report_path in root.glob("*/report.json"):
            try:
                summaries.append(self.summarize_report(self.read_report(report_path.parent.name)))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return XauQuikStrikeFusionListResponse(
            reports=sorted(summaries, key=lambda item: item.created_at, reverse=True)
        )

    def summarize_report(self, report: XauQuikStrikeFusionReport) -> XauQuikStrikeFusionSummary:
        context_summary = report.context_summary
        coverage = report.coverage
        downstream_result = report.downstream_result
        return XauQuikStrikeFusionSummary(
            report_id=report.report_id,
            status=report.status,
            created_at=report.created_at,
            vol2vol_report_id=report.vol2vol_source.report_id,
            matrix_report_id=report.matrix_source.report_id,
            fused_row_count=report.fused_row_count,
            strike_count=coverage.strike_count if coverage else 0,
            expiration_count=coverage.expiration_count if coverage else 0,
            basis_status=(
                context_summary.basis_status
                if context_summary
                else XauFusionContextStatus.UNAVAILABLE
            ),
            iv_range_status=(
                context_summary.iv_range_status
                if context_summary
                else XauFusionContextStatus.UNAVAILABLE
            ),
            open_regime_status=(
                context_summary.open_regime_status
                if context_summary
                else XauFusionContextStatus.UNAVAILABLE
            ),
            candle_acceptance_status=(
                context_summary.candle_acceptance_status
                if context_summary
                else XauFusionContextStatus.UNAVAILABLE
            ),
            xau_vol_oi_report_id=(
                downstream_result.xau_vol_oi_report_id if downstream_result else None
            ),
            xau_reaction_report_id=(
                downstream_result.xau_reaction_report_id if downstream_result else None
            ),
            all_reactions_no_trade=(
                downstream_result.all_reactions_no_trade if downstream_result else None
            ),
            warning_count=len(report.warnings),
        )

    def read_fused_rows(self, report_id: str) -> list[XauFusionRow]:
        path = self.artifact_path(report_id, "fused_rows.json")
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [XauFusionRow.model_validate(row) for row in payload]
        return self.read_report(report_id).fused_rows

    def read_rows_response(self, report_id: str) -> XauFusionRowsResponse:
        return XauFusionRowsResponse(
            report_id=validate_xau_fusion_safe_id(report_id, "report_id"),
            rows=self.read_fused_rows(report_id),
        )

    def read_missing_context_response(
        self,
        report_id: str,
    ) -> XauFusionMissingContextResponse:
        report = self.read_report(report_id)
        return XauFusionMissingContextResponse(
            report_id=report.report_id,
            missing_context=(
                report.context_summary.missing_context if report.context_summary else []
            ),
        )

    def _validate_report_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_quikstrike_fusion report root") from exc

    def _project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.repo_root, self.reports_dir.resolve().parent.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, XauFusionBaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, tuple):
        return [_jsonable(value) for value in payload]
    return payload


def _metadata_payload(report: XauQuikStrikeFusionReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "status": report.status.value,
        "created_at": report.created_at.isoformat(),
        "completed_at": report.completed_at.isoformat() if report.completed_at else None,
        "vol2vol_report_id": report.vol2vol_source.report_id,
        "matrix_report_id": report.matrix_source.report_id,
        "fused_row_count": report.fused_row_count,
        "xau_vol_oi_input_row_count": report.xau_vol_oi_input_row_count,
        "coverage": report.coverage.model_dump(mode="json") if report.coverage else None,
        "basis_state": report.basis_state.model_dump(mode="json") if report.basis_state else None,
        "context_summary": (
            report.context_summary.model_dump(mode="json") if report.context_summary else None
        ),
        "downstream_result": (
            report.downstream_result.model_dump(mode="json") if report.downstream_result else None
        ),
        "missing_context_count": (
            len(report.context_summary.missing_context) if report.context_summary else 0
        ),
        "warnings": report.warnings,
        "limitations": report.limitations,
        "research_only_warnings": report.research_only_warnings,
    }


def _report_markdown(report: XauQuikStrikeFusionReport) -> str:
    lines = [
        f"# XAU QuikStrike Fusion Report {report.report_id}",
        "",
        "Local-only research report. No cookies, tokens, headers, HAR files, screenshots, "
        "viewstate values, credentials, private URLs, browser sessions, or endpoint replay "
        "payloads are persisted.",
        "",
        f"- Status: `{report.status.value}`",
        f"- Vol2Vol report: `{report.vol2vol_source.report_id}`",
        f"- Matrix report: `{report.matrix_source.report_id}`",
        f"- Fused rows: `{report.fused_row_count}`",
        f"- XAU Vol-OI input rows: `{report.xau_vol_oi_input_row_count}`",
    ]
    if report.coverage is not None:
        lines.extend(
            [
                f"- Matched keys: `{report.coverage.matched_key_count}`",
                f"- Vol2Vol-only keys: `{report.coverage.vol2vol_only_key_count}`",
                f"- Matrix-only keys: `{report.coverage.matrix_only_key_count}`",
                f"- Conflicting keys: `{report.coverage.conflict_key_count}`",
                f"- Blocked keys: `{report.coverage.blocked_key_count}`",
            ]
        )
    if report.basis_state is not None:
        lines.extend(
            [
                "",
                "## Basis Context",
                f"- Status: `{report.basis_state.status.value}`",
                f"- Basis points: `{report.basis_state.basis_points}`",
                f"- Note: {report.basis_state.calculation_note}",
            ]
        )
    if report.context_summary is not None:
        lines.extend(
            [
                "",
                "## Context Status",
                f"- IV/range: `{report.context_summary.iv_range_status.value}`",
                f"- Open regime: `{report.context_summary.open_regime_status.value}`",
                (
                    "- Candle acceptance: "
                    f"`{report.context_summary.candle_acceptance_status.value}`"
                ),
                (
                    "- Realized volatility: "
                    f"`{report.context_summary.realized_volatility_status.value}`"
                ),
                f"- Source agreement: `{report.context_summary.source_agreement_status.value}`",
                "",
                "## Missing Context Checklist",
            ]
        )
        lines.extend(
            f"- {item.context_key}: `{item.status.value}` - {item.message}"
            for item in report.context_summary.missing_context
        )
    if report.downstream_result is not None:
        lines.extend(
            [
                "",
                "## Downstream Research Reports",
                f"- XAU Vol-OI report: `{report.downstream_result.xau_vol_oi_report_id}`",
                f"- XAU reaction report: `{report.downstream_result.xau_reaction_report_id}`",
                f"- XAU report status: `{report.downstream_result.xau_report_status}`",
                f"- Reaction report status: `{report.downstream_result.reaction_report_status}`",
                f"- Reaction rows: `{report.downstream_result.reaction_row_count}`",
                f"- NO_TRADE rows: `{report.downstream_result.no_trade_count}`",
            ]
        )
        if report.downstream_result.notes:
            lines.extend(["", "### Downstream Notes"])
            lines.extend(f"- {note}" for note in report.downstream_result.notes)
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    lines.extend(["", "## Artifacts"])
    lines.extend(f"- `{artifact.path}`" for artifact in report.artifacts)
    return "\n".join(lines) + "\n"
