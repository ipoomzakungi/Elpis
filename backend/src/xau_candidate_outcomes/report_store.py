from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import get_settings
from src.models.xau_candidate_outcome import (
    XauCandidateOutcomeRunResult,
)
from src.reports.collision_guard import (
    assert_report_write_allowed,
    resolve_report_source_kind_for_write,
)

SAFE_XAU_CANDIDATE_OUTCOME_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class XauCandidateOutcomeReportStore:
    """Path-safe helper for local XAU candidate outcome artifacts."""

    REPORT_ROOT_NAME = "xau_candidate_outcomes"

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

    def report_dir(self, outcome_run_id: str) -> Path:
        safe_id = validate_xau_candidate_outcome_safe_id(
            outcome_run_id,
            "outcome_run_id",
        )
        report_dir = (self._report_root / safe_id).resolve()
        self._validate_report_scope(report_dir)
        return report_dir

    def artifact_path(self, outcome_run_id: str, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("artifact filename must be a plain filename")
        artifact_path = (self.report_dir(outcome_run_id) / filename).resolve()
        self._validate_report_scope(artifact_path)
        return artifact_path

    def persist_result(
        self,
        result: XauCandidateOutcomeRunResult,
        *,
        overwrite_allowed: bool = False,
    ) -> XauCandidateOutcomeRunResult:
        requested_source_kind = resolve_report_source_kind_for_write(
            report_id=result.outcome_run_id,
            explicit_source_kind="operational",
        )
        assert_report_write_allowed(
            report_dir=self.report_dir(result.outcome_run_id),
            report_id=result.outcome_run_id,
            source_kind=requested_source_kind,
            overwrite_allowed=overwrite_allowed,
        )
        self.report_dir(result.outcome_run_id).mkdir(parents=True, exist_ok=True)
        metadata_path = self.artifact_path(result.outcome_run_id, "outcome_metadata.json")
        outcomes_path = self.artifact_path(result.outcome_run_id, "outcomes.json")
        markdown_path = self.artifact_path(result.outcome_run_id, "outcomes.md")
        artifact_paths = {
            **result.artifact_paths,
            "outcome_metadata_json": self.project_relative_path(metadata_path),
            "outcomes_json": self.project_relative_path(outcomes_path),
            "outcomes_markdown": self.project_relative_path(markdown_path),
        }
        stored_result = result.model_copy(update={"artifact_paths": artifact_paths})
        metadata_path.write_text(
            self.serialize_json(stored_result) + "\n",
            encoding="utf-8",
        )
        outcomes_path.write_text(
            self.serialize_json(stored_result.outcome_set) + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(_outcomes_markdown(stored_result), encoding="utf-8")
        return stored_result

    def read_result(self, outcome_run_id: str) -> XauCandidateOutcomeRunResult:
        path = self.artifact_path(outcome_run_id, "outcome_metadata.json")
        if not path.exists():
            raise FileNotFoundError(outcome_run_id)
        return XauCandidateOutcomeRunResult.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def latest_result(self) -> XauCandidateOutcomeRunResult | None:
        results = self.list_results()
        if not results:
            return None
        return max(results, key=lambda result: result.created_at)

    def list_results(self) -> list[XauCandidateOutcomeRunResult]:
        root = self.report_root()
        if not root.exists():
            return []
        results: list[XauCandidateOutcomeRunResult] = []
        for path in root.glob("*/outcome_metadata.json"):
            try:
                results.append(
                    XauCandidateOutcomeRunResult.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return sorted(results, key=lambda result: result.created_at, reverse=True)

    def serialize_json(self, payload: Any) -> str:
        return json.dumps(_jsonable(payload), indent=2, sort_keys=True)

    def project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        self._validate_report_scope(resolved)
        return self._project_relative_path(resolved)

    def _validate_report_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_candidate_outcomes report root") from exc

    def _project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.repo_root, self.reports_dir.resolve().parent.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()


def validate_xau_candidate_outcome_safe_id(value: str, field_name: str = "id") -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if not SAFE_XAU_CANDIDATE_OUTCOME_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, underscore, or dash"
        )
    return normalized


def _outcomes_markdown(result: XauCandidateOutcomeRunResult) -> str:
    lines = [
        f"# XAU Candidate Outcome Run {result.outcome_run_id}",
        "",
        "Local-only research artifact. These outcome labels are not signals, alerts, "
        "orders, position instructions, PnL, profitability claims, predictions, "
        "safety claims, or live-readiness claims.",
        "",
        f"- Readiness: `{result.readiness.value}`",
        f"- Signal allowed: `{result.signal_allowed}`",
        f"- Research only: `{result.research_only}`",
        f"- Candidate set id: `{result.candidate_set_id}`",
        f"- Map id: `{result.map_id}`",
        f"- Candidate count: `{result.candidate_count}`",
        f"- Outcome count: `{result.outcome_count}`",
        f"- Unavailable count: `{result.unavailable_count}`",
        "",
        "## Outcome Summary",
    ]
    for outcome in result.outcome_set.outcomes:
        lines.extend(
            [
                f"### {outcome.candidate_id} / {outcome.window.value}",
                f"- Label: `{outcome.outcome_label.value}`",
                f"- Coverage: `{outcome.coverage_status.value}`",
                (
                    f"- Open/high/low/close: `{outcome.open}` / `{outcome.high}` / "
                    f"`{outcome.low}` / `{outcome.close}`"
                ),
                f"- MFE/MAE: `{outcome.mfe_points}` / `{outcome.mae_points}`",
                f"- Target 1 hit: `{outcome.hit_target_1}`",
                f"- Stop hit: `{outcome.hit_stop_reference}`",
                f"- Continued breakout: `{outcome.continued_breakout}`",
                "",
            ]
        )
    lines.extend(["## No-Signal Reasons"])
    lines.extend(f"- {reason}" for reason in result.no_signal_reasons)
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {limitation}" for limitation in result.limitations)
    lines.extend(["", "## Artifacts"])
    lines.extend(f"- {key}: `{path}`" for key, path in sorted(result.artifact_paths.items()))
    return "\n".join(lines) + "\n"


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


__all__ = [
    "XauCandidateOutcomeReportStore",
    "validate_xau_candidate_outcome_safe_id",
]
