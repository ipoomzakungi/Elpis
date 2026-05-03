"""Persistence helpers for first evidence run wrappers."""

import json
from pathlib import Path
from typing import Any

from src.config import get_reports_path
from src.models.data_sources import DataSourceBootstrapRunResult, FirstEvidenceRunResult

FIRST_EVIDENCE_REPORT_DIR = "data_sources/first_evidence"
PUBLIC_BOOTSTRAP_REPORT_DIR = "data_sources/bootstrap"


class DataSourceFirstRunReportStore:
    """Store first-run wrapper metadata under ignored report paths."""

    def __init__(self, reports_root: Path | None = None):
        self.reports_root = (reports_root or get_reports_path()).resolve()
        self.first_run_root = self.reports_root / FIRST_EVIDENCE_REPORT_DIR

    def run_path(self, first_run_id: str) -> Path:
        if not first_run_id or any(
            part in {"", ".", ".."} for part in Path(first_run_id).parts
        ):
            raise ValueError("first_run_id must be a safe path segment")
        path = (self.first_run_root / first_run_id).resolve()
        if self.first_run_root != path and self.first_run_root not in path.parents:
            raise ValueError(
                "first evidence run path must stay under data/reports/data_sources"
            )
        return path

    def artifact_paths(self, first_run_id: str) -> dict[str, str]:
        run_dir = self.run_path(first_run_id)
        return {
            "metadata": (run_dir / "metadata.json").as_posix(),
            "preflight": (run_dir / "preflight.json").as_posix(),
        }

    def write_first_run(self, result: FirstEvidenceRunResult) -> FirstEvidenceRunResult:
        run_dir = self.run_path(result.first_run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(run_dir / "metadata.json", result.model_dump(mode="json"))
        _write_json(
            run_dir / "preflight.json",
            result.preflight_result.model_dump(mode="json"),
        )
        return result

    def read_first_run(self, first_run_id: str) -> FirstEvidenceRunResult:
        return FirstEvidenceRunResult.model_validate(
            _read_json(self.run_path(first_run_id) / "metadata.json")
        )


class DataSourceBootstrapReportStore:
    """Store public bootstrap metadata under ignored report paths."""

    def __init__(self, reports_root: Path | None = None):
        self.reports_root = (reports_root or get_reports_path()).resolve()
        self.bootstrap_root = self.reports_root / PUBLIC_BOOTSTRAP_REPORT_DIR

    def run_path(self, bootstrap_run_id: str) -> Path:
        if not bootstrap_run_id or any(
            part in {"", ".", ".."} for part in Path(bootstrap_run_id).parts
        ):
            raise ValueError("bootstrap_run_id must be a safe path segment")
        path = (self.bootstrap_root / bootstrap_run_id).resolve()
        if self.bootstrap_root != path and self.bootstrap_root not in path.parents:
            raise ValueError("bootstrap run path must stay under data/reports/data_sources")
        return path

    def write_bootstrap_run(
        self,
        result: DataSourceBootstrapRunResult,
    ) -> DataSourceBootstrapRunResult:
        run_dir = self.run_path(result.bootstrap_run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(run_dir / "metadata.json", result.model_dump(mode="json"))
        return result

    def read_bootstrap_run(self, bootstrap_run_id: str) -> DataSourceBootstrapRunResult:
        return DataSourceBootstrapRunResult.model_validate(
            _read_json(self.run_path(bootstrap_run_id) / "metadata.json")
        )

    def list_bootstrap_runs(self) -> list[DataSourceBootstrapRunResult]:
        if not self.bootstrap_root.exists():
            return []
        runs: list[DataSourceBootstrapRunResult] = []
        for metadata_path in sorted(
            self.bootstrap_root.glob("*/metadata.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            runs.append(DataSourceBootstrapRunResult.model_validate(_read_json(metadata_path)))
        return runs


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
