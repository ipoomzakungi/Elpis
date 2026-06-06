from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import get_settings
from src.models.xau import XauDailyStructuralMap, XauDailyStructuralMapWall
from src.models.xau_daily_structural_map import (
    XauDailyStructuralMapArtifact,
    XauDailyStructuralMapArtifactFormat,
    XauDailyStructuralMapArtifactType,
    XauDailyStructuralMapReportMetadata,
    XauDailyStructuralMapReportResult,
    validate_xau_daily_structural_map_safe_id,
)
from src.reports.collision_guard import (
    assert_report_write_allowed,
    resolve_report_source_kind_for_write,
)


class XauDailyStructuralMapReportStore:
    """Path-safe helper for local-only XAU daily structural-map artifacts."""

    REPORT_ROOT_NAME = "xau_daily_structural_map"

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

    def report_dir(self, map_id: str) -> Path:
        safe_map_id = validate_xau_daily_structural_map_safe_id(map_id, "map_id")
        report_dir = (self._report_root / safe_map_id).resolve()
        self._validate_report_scope(report_dir)
        return report_dir

    def ensure_report_dir(self, map_id: str) -> Path:
        report_dir = self.report_dir(map_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir

    def artifact_path(self, map_id: str, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("artifact filename must be a plain filename")
        artifact_path = (self.report_dir(map_id) / filename).resolve()
        self._validate_report_scope(artifact_path)
        return artifact_path

    def artifact(
        self,
        *,
        artifact_type: XauDailyStructuralMapArtifactType,
        path: Path,
        artifact_format: XauDailyStructuralMapArtifactFormat,
        rows: int | None = None,
    ) -> XauDailyStructuralMapArtifact:
        resolved = path.resolve()
        self._validate_report_scope(resolved)
        return XauDailyStructuralMapArtifact(
            artifact_type=artifact_type,
            path=self._project_relative_path(resolved),
            format=artifact_format,
            rows=rows,
        )

    def artifact_for_filename(
        self,
        map_id: str,
        filename: str,
        *,
        artifact_type: XauDailyStructuralMapArtifactType,
        artifact_format: XauDailyStructuralMapArtifactFormat,
        rows: int | None = None,
    ) -> XauDailyStructuralMapArtifact:
        return self.artifact(
            artifact_type=artifact_type,
            path=self.artifact_path(map_id, filename),
            artifact_format=artifact_format,
            rows=rows,
        )

    def serialize_json(self, payload: Any) -> str:
        return json.dumps(_jsonable(payload), indent=2, sort_keys=True)

    def persist_map(
        self,
        daily_map: XauDailyStructuralMap,
        *,
        source_report_ids: list[str] | None = None,
        source_kind: str | None = None,
        overwrite_allowed: bool = False,
    ) -> XauDailyStructuralMapReportResult:
        """Persist one daily structural map as local research artifacts."""

        requested_source_kind = resolve_report_source_kind_for_write(
            report_id=daily_map.map_id,
            explicit_source_kind=source_kind,
        )
        normalized_source_kind = assert_report_write_allowed(
            report_dir=self.report_dir(daily_map.map_id),
            report_id=daily_map.map_id,
            source_kind=requested_source_kind,
            overwrite_allowed=overwrite_allowed,
        )
        self.ensure_report_dir(daily_map.map_id)
        artifacts = [
            self.artifact_for_filename(
                daily_map.map_id,
                "metadata.json",
                artifact_type=XauDailyStructuralMapArtifactType.METADATA,
                artifact_format=XauDailyStructuralMapArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact_for_filename(
                daily_map.map_id,
                "map.json",
                artifact_type=XauDailyStructuralMapArtifactType.MAP_JSON,
                artifact_format=XauDailyStructuralMapArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact_for_filename(
                daily_map.map_id,
                "map.md",
                artifact_type=XauDailyStructuralMapArtifactType.MAP_MARKDOWN,
                artifact_format=XauDailyStructuralMapArtifactFormat.MARKDOWN,
                rows=1,
            ),
            self.artifact_for_filename(
                daily_map.map_id,
                "walls.json",
                artifact_type=XauDailyStructuralMapArtifactType.WALLS_JSON,
                artifact_format=XauDailyStructuralMapArtifactFormat.JSON,
                rows=len(daily_map.walls),
            ),
        ]
        metadata = self.summarize_map(
            daily_map,
            source_kind=normalized_source_kind,
            source_report_ids=source_report_ids or [],
            artifacts=artifacts,
        )
        result = XauDailyStructuralMapReportResult(
            metadata=metadata,
            daily_map=daily_map,
            artifacts=artifacts,
        )

        self.artifact_path(daily_map.map_id, "metadata.json").write_text(
            self.serialize_json(metadata) + "\n",
            encoding="utf-8",
        )
        self.artifact_path(daily_map.map_id, "map.json").write_text(
            self.serialize_json(daily_map) + "\n",
            encoding="utf-8",
        )
        self.artifact_path(daily_map.map_id, "map.md").write_text(
            _map_markdown(result),
            encoding="utf-8",
        )
        self.artifact_path(daily_map.map_id, "walls.json").write_text(
            self.serialize_json(daily_map.walls) + "\n",
            encoding="utf-8",
        )
        return result

    def summarize_map(
        self,
        daily_map: XauDailyStructuralMap,
        *,
        source_kind: str,
        source_report_ids: list[str],
        artifacts: list[XauDailyStructuralMapArtifact],
    ) -> XauDailyStructuralMapReportMetadata:
        return XauDailyStructuralMapReportMetadata(
            map_id=daily_map.map_id,
            source_kind=source_kind,
            session_date=daily_map.session_date.isoformat(),
            created_at=daily_map.created_at.isoformat(),
            source_report_ids=source_report_ids,
            expected_range_source=(
                daily_map.expected_range_source.value
                if daily_map.expected_range_source
                else None
            ),
            basis_mapping_available=daily_map.basis_mapping_available,
            session_open_available=daily_map.session_open_available,
            wall_count=daily_map.wall_count,
            readiness=daily_map.data_quality_state,
            signal_allowed=daily_map.signal_allowed,
            limitation_count=len(daily_map.limitations),
            no_signal_reason_count=len(daily_map.no_signal_reasons),
            artifacts=artifacts,
        )

    def read_map(self, map_id: str) -> XauDailyStructuralMap:
        path = self.artifact_path(map_id, "map.json")
        if not path.exists():
            raise FileNotFoundError(map_id)
        return XauDailyStructuralMap.model_validate_json(path.read_text(encoding="utf-8"))

    def read_walls(self, map_id: str) -> list[XauDailyStructuralMapWall]:
        path = self.artifact_path(map_id, "walls.json")
        if not path.exists():
            return self.read_map(map_id).walls
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [XauDailyStructuralMapWall.model_validate(item) for item in payload]

    def read_metadata(self, map_id: str) -> XauDailyStructuralMapReportMetadata:
        path = self.artifact_path(map_id, "metadata.json")
        if not path.exists():
            raise FileNotFoundError(map_id)
        return XauDailyStructuralMapReportMetadata.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def _validate_report_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_daily_structural_map report root") from exc

    def _project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.repo_root, self.reports_dir.resolve().parent.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()


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


def _map_markdown(report: XauDailyStructuralMapReportResult) -> str:
    daily_map = report.daily_map
    lines = [
        f"# XAU Daily Structural Map {daily_map.map_id}",
        "",
        "Local-only research map. This artifact is not a signal, alert, order, "
        "position instruction, profitability claim, prediction, safety claim, "
        "or live-readiness claim.",
        "",
        f"- Session date: `{daily_map.session_date.isoformat()}`",
        f"- Readiness: `{daily_map.data_quality_state.value}`",
        f"- Signal allowed: `{daily_map.signal_allowed}`",
        f"- Source product: `{daily_map.source_product}`",
        f"- Expiration: `{daily_map.expiration_code or daily_map.expiry_date}`",
        f"- Expected range source: `{daily_map.expected_range_source}`",
        f"- Basis mapping available: `{daily_map.basis_mapping_available}`",
        f"- Session open available: `{daily_map.session_open_available}`",
        f"- Wall count: `{daily_map.wall_count}`",
        "",
        "## No-Signal Reasons",
    ]
    lines.extend(f"- {reason}" for reason in daily_map.no_signal_reasons)
    lines.extend(["", "## Limitations"])
    if daily_map.limitations:
        lines.extend(f"- {limitation}" for limitation in daily_map.limitations)
    else:
        lines.append("- No additional source limitations were supplied.")
    lines.extend(["", "## Walls"])
    if daily_map.walls:
        lines.extend(
            (
                f"- {wall.wall_id}: strike `{wall.strike}`, "
                f"mapped `{wall.spot_equivalent_level}`, score `{wall.wall_score}`"
            )
            for wall in daily_map.walls
        )
    else:
        lines.append("- No walls were supplied.")
    lines.extend(["", "## Artifacts"])
    lines.extend(f"- `{artifact.path}`" for artifact in report.artifacts)
    return "\n".join(lines) + "\n"
