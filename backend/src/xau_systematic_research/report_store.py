from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import get_settings
from src.models.xau_systematic_research import (
    XauAiResearchPack,
    XauAlignedSourceState,
    XauSourceManifest,
    XauSystematicCycleRequest,
)


class XauSystematicReportStore:
    REPORT_ROOT_NAME = "xau_systematic_research"

    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or get_settings().data_reports_path
        self.report_root = (self.reports_dir / self.REPORT_ROOT_NAME).resolve()

    def cycle_dir(self, cycle_id: str) -> Path:
        safe = _safe_id(cycle_id)
        path = (self.report_root / safe).resolve()
        self._validate_scope(path)
        return path

    def persist_cycle(
        self,
        *,
        cycle_id: str,
        request: XauSystematicCycleRequest,
        manifest: XauSourceManifest,
        aligned_state: XauAlignedSourceState,
        ai_pack: XauAiResearchPack,
        ai_pack_markdown: str,
        ai_handoff_context: str,
        overwrite: bool = False,
    ) -> dict[str, Path]:
        output_dir = self.cycle_dir(cycle_id)
        if output_dir.exists() and not overwrite:
            raise FileExistsError(f"cycle output already exists: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "cycle": output_dir / "cycle.json",
            "source_manifest": output_dir / "source_manifest.json",
            "aligned_state": output_dir / "aligned_state.json",
            "ai_research_pack": output_dir / "ai_research_pack.json",
            "ai_research_pack_markdown": output_dir / "ai_research_pack.md",
            "ai_handoff_context": output_dir / "ai_handoff_context.md",
            "metadata": output_dir / "metadata.json",
        }
        _write_json(
            artifacts["cycle"],
            {
                "cycle_id": cycle_id,
                "request": request,
                "readiness": ai_pack.readiness.value,
                "signal_allowed": False,
                "research_only": True,
            },
        )
        _write_json(artifacts["source_manifest"], manifest)
        _write_json(artifacts["aligned_state"], aligned_state)
        _write_json(artifacts["ai_research_pack"], ai_pack)
        artifacts["ai_research_pack_markdown"].write_text(ai_pack_markdown, encoding="utf-8")
        artifacts["ai_handoff_context"].write_text(ai_handoff_context, encoding="utf-8")
        _write_json(
            artifacts["metadata"],
            {
                "cycle_id": cycle_id,
                "created_at": datetime.now(UTC).isoformat(),
                "artifact_names": sorted(artifacts),
                "research_only": True,
                "signal_allowed": False,
            },
        )
        return artifacts

    def _validate_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self.report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_systematic_research reports") from exc


def new_cycle_id(*, label: str | None, created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y%m%dT%H%M%S")
    suffix = f"_{_safe_id(label)}" if label else ""
    return f"xau_systematic_{timestamp}{suffix}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, Path):
        return payload.as_posix()
    return payload


def _safe_id(value: str) -> str:
    cleaned = "".join(char for char in value.strip() if char.isalnum() or char in "-_")
    if not cleaned:
        raise ValueError("cycle id must not be blank")
    return cleaned
