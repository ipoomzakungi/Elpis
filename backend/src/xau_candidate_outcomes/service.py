from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.xau_candidate_outcome import (
    XauCandidateOutcomeLatestResponse,
    XauCandidateOutcomeRunReadiness,
    XauCandidateOutcomeRunRequest,
    XauCandidateOutcomeRunResult,
    candidate_outcome_limitations,
    candidate_outcome_no_signal_reasons,
)
from src.models.xau_sd_oi_candidate import XauSdOiCandidateSet
from src.xau_candidate_outcomes.calculator import build_xau_candidate_outcome_set
from src.xau_candidate_outcomes.price_series import load_price_bars_for_request
from src.xau_candidate_outcomes.report_store import XauCandidateOutcomeReportStore


class XauCandidateOutcomeService:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.store = XauCandidateOutcomeReportStore(reports_dir=reports_dir)

    def run(
        self,
        request: XauCandidateOutcomeRunRequest,
    ) -> XauCandidateOutcomeRunResult:
        redirected = self._service_for_request_output_root(request)
        if redirected is not None:
            redirected_request = request.model_copy(update={"output_root": None})
            return redirected.run(redirected_request)

        created_at = datetime.now(UTC)
        candidate_set = self._load_candidate_set(request.candidate_set_path)
        candidate_set_id = _candidate_set_id(candidate_set, request.candidate_set_path)
        outcome_run_id = _outcome_run_id(candidate_set.map_id, created_at)
        price_bars, price_source = load_price_bars_for_request(request)
        outcome_set = build_xau_candidate_outcome_set(
            candidate_set,
            price_bars,
            windows=request.windows,
            outcome_run_id=outcome_run_id,
            candidate_set_id=candidate_set_id,
            price_source=price_source,
        )
        result = XauCandidateOutcomeRunResult(
            outcome_run_id=outcome_run_id,
            created_at=created_at,
            readiness=_readiness(outcome_set.outcome_count, outcome_set.unavailable_count),
            candidate_set_id=candidate_set_id,
            map_id=candidate_set.map_id,
            candidate_count=candidate_set.candidate_count,
            outcome_count=outcome_set.outcome_count,
            unavailable_count=outcome_set.unavailable_count,
            artifact_paths={},
            outcome_set=outcome_set,
            no_signal_reasons=candidate_outcome_no_signal_reasons(
                *candidate_set.no_signal_reasons
            ),
            limitations=candidate_outcome_limitations(
                *candidate_set.limitations,
                *price_source.limitations,
            ),
            research_only=True,
            signal_allowed=False,
        )
        return self.store.persist_result(
            result,
            overwrite_allowed=request.overwrite_allowed,
        )

    def latest(self) -> XauCandidateOutcomeLatestResponse:
        latest = self.store.latest_result()
        available_runs = [result.outcome_run_id for result in self.store.list_results()]
        if latest is None:
            return XauCandidateOutcomeLatestResponse(
                readiness=XauCandidateOutcomeRunReadiness.BLOCKED,
                latest_run=None,
                available_runs=[],
                artifact_paths={},
                message="No XAU candidate outcome runs have been persisted yet.",
                no_signal_reasons=candidate_outcome_no_signal_reasons(
                    "No XAU candidate outcome runs have been persisted yet."
                ),
                research_only=True,
                signal_allowed=False,
            )
        return XauCandidateOutcomeLatestResponse(
            readiness=latest.readiness,
            latest_run=latest,
            available_runs=available_runs,
            artifact_paths=latest.artifact_paths,
            message="Latest XAU candidate outcome run loaded.",
            no_signal_reasons=latest.no_signal_reasons,
            research_only=True,
            signal_allowed=False,
        )

    def read_result(self, outcome_run_id: str) -> XauCandidateOutcomeRunResult:
        return self.store.read_result(outcome_run_id)

    def _load_candidate_set(self, path: Path) -> XauSdOiCandidateSet:
        resolved = path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return XauSdOiCandidateSet.model_validate_json(resolved.read_text(encoding="utf-8"))

    def _service_for_request_output_root(
        self,
        request: XauCandidateOutcomeRunRequest,
    ) -> XauCandidateOutcomeService | None:
        if request.output_root is None:
            return None
        normalized = _normalize_output_root(request.output_root)
        if normalized.resolve() == self.store.reports_dir.resolve():
            return None
        return XauCandidateOutcomeService(reports_dir=normalized)


def run_xau_candidate_forward_outcomes(
    request: XauCandidateOutcomeRunRequest,
) -> XauCandidateOutcomeRunResult:
    return XauCandidateOutcomeService(
        reports_dir=_normalize_output_root(request.output_root)
        if request.output_root is not None
        else None
    ).run(request)


def _candidate_set_id(candidate_set: XauSdOiCandidateSet, candidate_set_path: Path) -> str:
    metadata_path = candidate_set_path.resolve().parent / "candidate_metadata.json"
    if metadata_path.exists():
        try:
            payload: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
            value = str(payload.get("candidate_set_id", "")).strip()
            if value:
                return value
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return f"{candidate_set.map_id}_{candidate_set.timestamp.strftime('%Y%m%dT%H%M%S')}_candidates"


def _outcome_run_id(map_id: str, created_at: datetime) -> str:
    safe_map_id = "".join(
        character if character.isalnum() or character in "_-" else "_"
        for character in map_id
    ).strip("_")
    return f"xau_candidate_outcomes_{safe_map_id}_{created_at.strftime('%Y%m%dT%H%M%S%f')}"


def _readiness(
    outcome_count: int,
    unavailable_count: int,
) -> XauCandidateOutcomeRunReadiness:
    if outcome_count == 0 or unavailable_count == outcome_count:
        return XauCandidateOutcomeRunReadiness.BLOCKED
    if unavailable_count:
        return XauCandidateOutcomeRunReadiness.PARTIAL
    return XauCandidateOutcomeRunReadiness.COMPLETED


def _normalize_output_root(output_root: Path) -> Path:
    resolved = output_root.resolve()
    if resolved.name == "xau_candidate_outcomes":
        return resolved.parent
    return resolved


__all__ = [
    "XauCandidateOutcomeService",
    "run_xau_candidate_forward_outcomes",
]
