from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import get_settings
from src.models.xau_daily_workbench import XauDailyWorkbenchRunResult
from src.reports.collision_guard import (
    assert_report_write_allowed,
    resolve_report_source_kind_for_write,
)

SAFE_WORKBENCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class XauDailyWorkbenchReportStore:
    """Path-safe helper for local XAU daily workbench run artifacts."""

    REPORT_ROOT_NAME = "xau_daily_workbench"

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

    def run_dir(self, run_id: str) -> Path:
        safe_run_id = validate_xau_daily_workbench_safe_id(run_id, "run_id")
        run_dir = (self._report_root / safe_run_id).resolve()
        self._validate_report_scope(run_dir)
        return run_dir

    def artifact_path(self, run_id: str, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("artifact filename must be a plain filename")
        artifact_path = (self.run_dir(run_id) / filename).resolve()
        self._validate_report_scope(artifact_path)
        return artifact_path

    def persist_result(
        self,
        result: XauDailyWorkbenchRunResult,
        *,
        overwrite_allowed: bool = False,
    ) -> XauDailyWorkbenchRunResult:
        requested_source_kind = resolve_report_source_kind_for_write(
            report_id=result.run_id,
            explicit_source_kind="operational",
        )
        assert_report_write_allowed(
            report_dir=self.run_dir(result.run_id),
            report_id=result.run_id,
            source_kind=requested_source_kind,
            overwrite_allowed=overwrite_allowed,
        )
        self.run_dir(result.run_id).mkdir(parents=True, exist_ok=True)
        workbench_json = self.artifact_path(result.run_id, "workbench.json")
        workbench_md = self.artifact_path(result.run_id, "workbench.md")
        artifact_paths = {
            **result.artifact_paths,
            "workbench_json": self._project_relative_path(workbench_json),
            "workbench_markdown": self._project_relative_path(workbench_md),
        }
        stored_result = result.model_copy(update={"artifact_paths": artifact_paths})
        workbench_json.write_text(
            self.serialize_json(stored_result) + "\n",
            encoding="utf-8",
        )
        workbench_md.write_text(_workbench_markdown(stored_result), encoding="utf-8")
        return stored_result

    def read_result(self, run_id: str) -> XauDailyWorkbenchRunResult:
        path = self.artifact_path(run_id, "workbench.json")
        if not path.exists():
            raise FileNotFoundError(run_id)
        return XauDailyWorkbenchRunResult.model_validate_json(path.read_text(encoding="utf-8"))

    def latest_result(self) -> XauDailyWorkbenchRunResult | None:
        root = self.report_root()
        if not root.exists():
            return None
        results: list[XauDailyWorkbenchRunResult] = []
        for path in root.glob("*/workbench.json"):
            try:
                results.append(
                    XauDailyWorkbenchRunResult.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValueError):
                continue
        if not results:
            return None
        return max(results, key=lambda result: result.created_at)

    def serialize_json(self, payload: Any) -> str:
        return json.dumps(_jsonable(payload), indent=2, sort_keys=True)

    def project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        self._validate_known_scope(resolved)
        return self._project_relative_path(resolved)

    def _validate_report_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_daily_workbench report root") from exc

    def _validate_known_scope(self, path: Path) -> None:
        resolved = path.resolve()
        allowed_roots = [
            self._report_root,
            (self.reports_dir / "xau_daily_structural_map").resolve(),
        ]
        if not any(_is_relative_to(resolved, root) for root in allowed_roots):
            raise ValueError("artifact path must remain under known XAU report roots")

    def _project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.repo_root, self.reports_dir.resolve().parent.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()


def validate_xau_daily_workbench_safe_id(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if not SAFE_WORKBENCH_ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must contain only letters, numbers, underscore, or dash")
    return normalized


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, tuple):
        return [_jsonable(value) for value in payload]
    return payload


def _workbench_markdown(result: XauDailyWorkbenchRunResult) -> str:
    lines = [
        f"# XAU Daily Research Workbench {result.run_id}",
        "",
        "Local-only research artifact. This is not a signal, alert, order, "
        "position instruction, profitability claim, prediction, safety claim, "
        "or live-readiness claim.",
        "",
        f"- Readiness: `{result.readiness.value}`",
        f"- Signal allowed: `{result.signal_allowed}`",
        f"- Research only: `{result.research_only}`",
        f"- CME source: `{result.cme_source.value}`",
        f"- Session date: `{result.session_date}`",
        f"- Expiration: `{result.expiration_code}`",
        f"- Map id: `{result.map_id}`",
        f"- Candidate set id: `{result.candidate_set_id}`",
        "",
        "## Missing Inputs",
    ]
    if result.missing_inputs:
        lines.extend(f"- {item}" for item in result.missing_inputs)
    else:
        lines.append("- None.")
    lines.extend(["", "## No-Signal Reasons"])
    lines.extend(f"- {reason}" for reason in result.no_signal_reasons)
    lines.extend(["", "## Artifacts"])
    if result.artifact_paths:
        lines.extend(f"- {key}: `{path}`" for key, path in sorted(result.artifact_paths.items()))
    else:
        lines.append("- No artifacts were produced.")
    return "\n".join(lines) + "\n"


__all__ = [
    "XauDailyWorkbenchReportStore",
    "validate_xau_daily_workbench_safe_id",
]
