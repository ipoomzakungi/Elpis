from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from src.models.xau_daily_workbench import (
    XauDailyWorkbenchCandidateMetadata,
    XauDailyWorkbenchCandidateResponse,
)
from src.models.xau_sd_oi_candidate import XauSdOiCandidateSet
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_daily_workbench.report_store import XauDailyWorkbenchReportStore


class XauDailyWorkbenchCandidateStore:
    """Persist Feature 021 candidate sidecars next to structural-map artifacts."""

    def __init__(
        self,
        *,
        map_store: XauDailyStructuralMapReportStore,
        workbench_store: XauDailyWorkbenchReportStore,
    ) -> None:
        self.map_store = map_store
        self.workbench_store = workbench_store

    def persist_candidate_set(
        self,
        map_id: str,
        candidate_set: XauSdOiCandidateSet,
        candidate_metadata: XauDailyWorkbenchCandidateMetadata,
    ) -> dict[str, str]:
        candidates_json = self.map_store.artifact_path(map_id, "candidates.json")
        candidates_md = self.map_store.artifact_path(map_id, "candidates.md")
        metadata_json = self.map_store.artifact_path(map_id, "candidate_metadata.json")
        candidates_json.write_text(
            json.dumps(_jsonable(candidate_set), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        metadata_json.write_text(
            json.dumps(_jsonable(candidate_metadata), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        candidates_md.write_text(
            _candidate_markdown(candidate_set, candidate_metadata),
            encoding="utf-8",
        )
        return {
            "candidates_json": self.workbench_store.project_relative_path(candidates_json),
            "candidates_markdown": self.workbench_store.project_relative_path(candidates_md),
            "candidate_metadata_json": self.workbench_store.project_relative_path(
                metadata_json
            ),
        }

    def read_candidates(self, map_id: str) -> XauDailyWorkbenchCandidateResponse:
        candidates_path = self.map_store.artifact_path(map_id, "candidates.json")
        metadata_path = self.map_store.artifact_path(map_id, "candidate_metadata.json")
        if not candidates_path.exists() or not metadata_path.exists():
            raise FileNotFoundError(map_id)
        candidate_set = XauSdOiCandidateSet.model_validate_json(
            candidates_path.read_text(encoding="utf-8")
        )
        candidate_metadata = XauDailyWorkbenchCandidateMetadata.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
        return XauDailyWorkbenchCandidateResponse(
            map_id=map_id,
            candidate_set_id=candidate_metadata.candidate_set_id,
            readiness=candidate_metadata.readiness,
            missing_inputs=candidate_metadata.missing_inputs,
            no_signal_reasons=candidate_metadata.no_signal_reasons,
            artifact_paths={
                "candidates_json": self.workbench_store.project_relative_path(candidates_path),
                "candidates_markdown": self.workbench_store.project_relative_path(
                    self.map_store.artifact_path(map_id, "candidates.md")
                ),
                "candidate_metadata_json": self.workbench_store.project_relative_path(
                    metadata_path
                ),
            },
            candidate_metadata=candidate_metadata,
            candidate_set=candidate_set,
            research_only=True,
            signal_allowed=False,
        )


def _candidate_markdown(
    candidate_set: XauSdOiCandidateSet,
    metadata: XauDailyWorkbenchCandidateMetadata,
) -> str:
    lines = [
        f"# XAU Candidate Set {metadata.candidate_set_id}",
        "",
        "Local-only research candidates. These are not signals, alerts, orders, "
        "position instructions, profitability claims, predictions, safety claims, "
        "or live-readiness claims.",
        "",
        "## Run Info",
        f"- Map id: `{metadata.map_id}`",
        f"- Readiness: `{metadata.readiness.value}`",
        f"- Signal allowed: `{metadata.signal_allowed}`",
        f"- Research only: `{metadata.research_only}`",
        f"- Candidate count: `{metadata.candidate_count}`",
        "",
        "## Candidate Summary",
    ]
    for candidate in candidate_set.candidates:
        lines.extend(
            [
                f"### {candidate.candidate_id}",
                f"- Side: `{candidate.side.value}`",
                f"- Readiness: `{candidate.readiness_state.value}`",
                f"- Stretch zone: `{candidate.stretch_zone.value}`",
                f"- Traded price: `{candidate.traded_price}`",
                f"- GC price: `{candidate.gc_price}`",
                f"- Basis: `{candidate.basis}`",
                f"- Target 1: `{candidate.target_1}`",
                f"- Target 2: `{candidate.target_2}`",
                f"- Target 3: `{candidate.target_3}`",
                f"- Stop reference: `{candidate.stop_reference}`",
                f"- Nearest wall: `{candidate.nearest_wall_level}`",
                f"- IV state: `{candidate.iv_state.value}`",
                f"- Flow state: `{candidate.flow_state.value}`",
                f"- Confirmation state: `{candidate.confirmation_state.value}`",
                "",
            ]
        )
    lines.extend(["## No-Signal Reasons"])
    lines.extend(f"- {reason}" for reason in metadata.no_signal_reasons)
    lines.extend(["", "## Missing Inputs"])
    if metadata.missing_inputs:
        lines.extend(
            f"- {item.input_name}: {item.message} ({item.severity.value})"
            for item in metadata.missing_inputs
        )
    else:
        lines.append("- None.")
    lines.extend(["", "## Limitations"])
    if candidate_set.limitations:
        lines.extend(f"- {limitation}" for limitation in candidate_set.limitations)
    else:
        lines.append("- No additional limitations were supplied.")
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


__all__ = ["XauDailyWorkbenchCandidateStore"]
