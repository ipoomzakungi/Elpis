"""Persistence skeleton for research execution evidence reports."""

import json
from pathlib import Path
from typing import Any

from src.config import get_reports_path
from src.models.research_execution import (
    ResearchEvidenceDecision,
    ResearchEvidenceSummary,
    ResearchExecutionMissingDataResponse,
    ResearchExecutionRun,
    ResearchExecutionRunListResponse,
    ResearchExecutionRunSummary,
    ResearchExecutionWorkflowStatus,
)
from src.reports.writer import (
    compose_research_execution_evidence_json,
    compose_research_execution_evidence_markdown,
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
                if not isinstance(payload, dict):
                    continue
                summary_payload = payload.get("summary")
                if summary_payload is not None:
                    summaries.append(ResearchExecutionRunSummary.model_validate(summary_payload))
                    continue
                summaries.append(_summary_from_run(ResearchExecutionRun.model_validate(payload)))
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

    def write_run_outputs(self, run: ResearchExecutionRun) -> ResearchExecutionRun:
        run_dir = self.run_path(run.execution_run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_paths = self.artifact_paths(run.execution_run_id)
        metadata_run = run.model_copy(update={"artifact_paths": artifact_paths})
        missing_data = ResearchExecutionMissingDataResponse(
            execution_run_id=run.execution_run_id,
            missing_data_checklist=(
                run.evidence_summary.missing_data_checklist if run.evidence_summary else []
            ),
        )
        _write_json(
            run_dir / "normalized_config.json",
            metadata_run.normalized_config.model_dump(mode="json"),
        )
        _write_json(
            run_dir / "evidence.json",
            metadata_run.evidence_summary.model_dump(mode="json")
            if metadata_run.evidence_summary is not None
            else compose_research_execution_evidence_json(metadata_run),
        )
        _write_text(
            run_dir / "evidence.md",
            compose_research_execution_evidence_markdown(metadata_run),
        )
        _write_json(run_dir / "missing_data.json", missing_data.model_dump(mode="json"))
        _write_json(run_dir / "metadata.json", metadata_run.model_dump(mode="json"))
        return metadata_run


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")


def _summary_from_run(run: ResearchExecutionRun) -> ResearchExecutionRunSummary:
    evidence = run.evidence_summary
    workflow_results = evidence.workflow_results if evidence else []
    return ResearchExecutionRunSummary(
        execution_run_id=run.execution_run_id,
        name=run.name,
        status=evidence.status if evidence else ResearchExecutionWorkflowStatus.FAILED,
        decision=evidence.decision if evidence else ResearchEvidenceDecision.INCONCLUSIVE,
        completed_workflow_count=sum(
            1 for result in workflow_results if result.status == "completed"
        ),
        blocked_workflow_count=sum(1 for result in workflow_results if result.status == "blocked"),
        partial_workflow_count=sum(1 for result in workflow_results if result.status == "partial"),
        failed_workflow_count=sum(1 for result in workflow_results if result.status == "failed"),
        created_at=run.created_at,
        artifact_root=_artifact_root(run),
    )


def _artifact_root(run: ResearchExecutionRun) -> str:
    metadata = run.artifact_paths.get("metadata")
    if not metadata:
        return ""
    return Path(metadata).parent.as_posix()
