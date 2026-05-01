"""Persistence skeleton for research execution evidence reports."""

import json
from pathlib import Path
from typing import Any

from src.config import get_reports_path
from src.models.research_execution import (
    ResearchEvidenceSummary,
    ResearchExecutionMissingDataResponse,
    ResearchExecutionRun,
    ResearchExecutionRunListResponse,
    ResearchExecutionRunSummary,
)

RESEARCH_EXECUTION_REPORT_DIR = "research_execution"


class ResearchExecutionReportStore:
    """Local report store for generated research execution evidence artifacts."""

    def __init__(self, reports_root: Path | None = None):
        self.reports_root = (reports_root or get_reports_path()).resolve()
        self.execution_root = self.reports_root / RESEARCH_EXECUTION_REPORT_DIR

    def list_runs(self) -> ResearchExecutionRunListResponse:
        return ResearchExecutionRunListResponse(runs=self.list_run_summaries())

    def list_run_summaries(self) -> list[ResearchExecutionRunSummary]:
        if not self.execution_root.exists():
            return []
        summaries: list[ResearchExecutionRunSummary] = []
        for metadata_path in self.execution_root.glob("*/metadata.json"):
            try:
                payload = _read_json(metadata_path)
                summary_payload = payload.get("summary") if isinstance(payload, dict) else None
                if summary_payload:
                    summaries.append(ResearchExecutionRunSummary.model_validate(summary_payload))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        return sorted(summaries, key=lambda summary: summary.created_at, reverse=True)

    def artifact_paths(self, execution_run_id: str) -> dict[str, str]:
        run_dir = self.run_path(execution_run_id)
        return {
            "metadata": (run_dir / "metadata.json").as_posix(),
            "normalized_config": (run_dir / "normalized_config.json").as_posix(),
            "evidence": (run_dir / "evidence.json").as_posix(),
            "markdown": (run_dir / "evidence.md").as_posix(),
            "missing_data": (run_dir / "missing_data.json").as_posix(),
        }

    def run_path(self, execution_run_id: str) -> Path:
        if not execution_run_id or any(
            part in {"", ".", ".."} for part in Path(execution_run_id).parts
        ):
            raise ValueError("execution_run_id must be a safe path segment")
        path = (self.execution_root / execution_run_id).resolve()
        if self.execution_root != path and self.execution_root not in path.parents:
            raise ValueError("execution run path must stay under data/reports/research_execution")
        return path

    def read_run(self, execution_run_id: str) -> ResearchExecutionRun:
        return ResearchExecutionRun.model_validate(
            _read_json(self.run_path(execution_run_id) / "metadata.json")
        )

    def read_evidence(self, execution_run_id: str) -> ResearchEvidenceSummary:
        return ResearchEvidenceSummary.model_validate(
            _read_json(self.run_path(execution_run_id) / "evidence.json")
        )

    def read_missing_data(self, execution_run_id: str) -> ResearchExecutionMissingDataResponse:
        payload = _read_json(self.run_path(execution_run_id) / "missing_data.json")
        if isinstance(payload, dict) and "execution_run_id" in payload:
            return ResearchExecutionMissingDataResponse.model_validate(payload)
        return ResearchExecutionMissingDataResponse(
            execution_run_id=execution_run_id,
            missing_data_checklist=list(payload) if isinstance(payload, list) else [],
        )


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))
