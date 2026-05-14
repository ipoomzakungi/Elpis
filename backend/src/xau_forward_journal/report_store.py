from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_forward_journal import (
    XauForwardArtifactFormat,
    XauForwardArtifactType,
    XauForwardJournalArtifact,
    XauForwardJournalBaseModel,
    XauForwardJournalEntry,
    XauForwardJournalListResponse,
    XauForwardJournalSummary,
    XauForwardOutcomeLabel,
    XauForwardOutcomeObservation,
    XauForwardOutcomeResponse,
    XauForwardOutcomeStatus,
    validate_xau_forward_journal_safe_id,
)


class XauForwardJournalReportStore:
    """Path-safe helper for local-only XAU forward journal artifacts."""

    REPORT_ROOT_NAME = "xau_forward_journal"

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

    def report_dir(self, journal_id: str) -> Path:
        safe_journal_id = validate_xau_forward_journal_safe_id(journal_id, "journal_id")
        report_dir = (self._report_root / safe_journal_id).resolve()
        self._validate_report_scope(report_dir)
        return report_dir

    def ensure_report_dir(self, journal_id: str) -> Path:
        report_dir = self.report_dir(journal_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        return report_dir

    def artifact_path(self, journal_id: str, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("artifact filename must be a plain filename")
        artifact_path = (self.report_dir(journal_id) / filename).resolve()
        self._validate_report_scope(artifact_path)
        return artifact_path

    def artifact(
        self,
        *,
        artifact_type: XauForwardArtifactType,
        path: Path,
        artifact_format: XauForwardArtifactFormat,
        rows: int | None = None,
    ) -> XauForwardJournalArtifact:
        resolved = path.resolve()
        self._validate_report_scope(resolved)
        return XauForwardJournalArtifact(
            artifact_type=artifact_type,
            path=self._project_relative_path(resolved),
            format=artifact_format,
            rows=rows,
        )

    def artifact_for_filename(
        self,
        journal_id: str,
        filename: str,
        *,
        artifact_type: XauForwardArtifactType,
        artifact_format: XauForwardArtifactFormat,
        rows: int | None = None,
    ) -> XauForwardJournalArtifact:
        return self.artifact(
            artifact_type=artifact_type,
            path=self.artifact_path(journal_id, filename),
            artifact_format=artifact_format,
            rows=rows,
        )

    def serialize_json(self, payload: Any) -> str:
        return json.dumps(_jsonable(payload), indent=2, sort_keys=True)

    def write_json_artifact(
        self,
        journal_id: str,
        filename: str,
        payload: Any,
        *,
        artifact_type: XauForwardArtifactType,
        rows: int | None = None,
    ) -> XauForwardJournalArtifact:
        path = self.artifact_path(journal_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.serialize_json(payload) + "\n", encoding="utf-8")
        return self.artifact(
            artifact_type=artifact_type,
            path=path,
            artifact_format=XauForwardArtifactFormat.JSON,
            rows=rows,
        )

    def persist_entry(self, entry: XauForwardJournalEntry) -> XauForwardJournalEntry:
        self.ensure_report_dir(entry.journal_id)
        artifacts = [
            self.artifact_for_filename(
                entry.journal_id,
                "metadata.json",
                artifact_type=XauForwardArtifactType.METADATA,
                artifact_format=XauForwardArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact_for_filename(
                entry.journal_id,
                "entry.json",
                artifact_type=XauForwardArtifactType.ENTRY_JSON,
                artifact_format=XauForwardArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact_for_filename(
                entry.journal_id,
                "outcomes.json",
                artifact_type=XauForwardArtifactType.OUTCOMES_JSON,
                artifact_format=XauForwardArtifactFormat.JSON,
                rows=len(entry.outcomes),
            ),
            self.artifact_for_filename(
                entry.journal_id,
                "report.json",
                artifact_type=XauForwardArtifactType.REPORT_JSON,
                artifact_format=XauForwardArtifactFormat.JSON,
                rows=1,
            ),
            self.artifact_for_filename(
                entry.journal_id,
                "report.md",
                artifact_type=XauForwardArtifactType.REPORT_MARKDOWN,
                artifact_format=XauForwardArtifactFormat.MARKDOWN,
                rows=1,
            ),
        ]
        saved_entry = entry.model_copy(update={"artifacts": artifacts})
        self.artifact_path(entry.journal_id, "metadata.json").write_text(
            self.serialize_json(self.summarize_entry(saved_entry)) + "\n",
            encoding="utf-8",
        )
        self.artifact_path(entry.journal_id, "entry.json").write_text(
            self.serialize_json(saved_entry) + "\n",
            encoding="utf-8",
        )
        self.artifact_path(entry.journal_id, "outcomes.json").write_text(
            self.serialize_json(saved_entry.outcomes) + "\n",
            encoding="utf-8",
        )
        self.artifact_path(entry.journal_id, "report.json").write_text(
            self.serialize_json(saved_entry) + "\n",
            encoding="utf-8",
        )
        self.artifact_path(entry.journal_id, "report.md").write_text(
            _entry_markdown(saved_entry),
            encoding="utf-8",
        )
        return saved_entry

    def persist_outcome_update(
        self,
        entry: XauForwardJournalEntry,
    ) -> XauForwardJournalEntry:
        """Persist updated outcome windows and keep entry/report artifacts consistent."""

        if not self.report_dir(entry.journal_id).exists():
            raise FileNotFoundError(entry.journal_id)
        return self.persist_entry(entry)

    def read_entry(self, journal_id: str) -> XauForwardJournalEntry:
        path = self.artifact_path(journal_id, "entry.json")
        if not path.exists():
            path = self.artifact_path(journal_id, "report.json")
        if not path.exists():
            raise FileNotFoundError(journal_id)
        return XauForwardJournalEntry.model_validate_json(path.read_text(encoding="utf-8"))

    def read_outcomes(self, journal_id: str) -> list[XauForwardOutcomeObservation]:
        path = self.artifact_path(journal_id, "outcomes.json")
        if not path.exists():
            return self.read_entry(journal_id).outcomes
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [XauForwardOutcomeObservation.model_validate(item) for item in payload]

    def read_outcome_response(self, journal_id: str) -> XauForwardOutcomeResponse:
        entry = self.read_entry(journal_id)
        outcomes = self.read_outcomes(journal_id)
        return XauForwardOutcomeResponse(
            journal_id=entry.journal_id,
            outcomes=outcomes,
            updated_at=entry.updated_at,
            warnings=entry.warnings,
            limitations=[
                *entry.limitations,
                "Outcome labels are forward research annotations only.",
            ],
        )

    def list_entries(self) -> XauForwardJournalListResponse:
        root = self.report_root()
        if not root.exists():
            return XauForwardJournalListResponse(entries=[])
        summaries: list[XauForwardJournalSummary] = []
        for entry_path in root.glob("*/entry.json"):
            try:
                summaries.append(self.summarize_entry(self.read_entry(entry_path.parent.name)))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return XauForwardJournalListResponse(
            entries=sorted(summaries, key=lambda item: item.snapshot_time, reverse=True)
        )

    def find_entry_by_snapshot_key(
        self,
        snapshot_key: str,
    ) -> XauForwardJournalEntry | None:
        safe_snapshot_key = validate_xau_forward_journal_safe_id(snapshot_key, "snapshot_key")
        root = self.report_root()
        if not root.exists():
            return None
        for entry_path in root.glob("*/entry.json"):
            try:
                entry = self.read_entry(entry_path.parent.name)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if entry.snapshot_key == safe_snapshot_key:
                return entry
        return None

    def summarize_entry(self, entry: XauForwardJournalEntry) -> XauForwardJournalSummary:
        completed_outcomes = [
            outcome
            for outcome in entry.outcomes
            if outcome.status != XauForwardOutcomeStatus.PENDING
            or outcome.label != XauForwardOutcomeLabel.PENDING
        ]
        pending_outcomes = [
            outcome
            for outcome in entry.outcomes
            if outcome.status == XauForwardOutcomeStatus.PENDING
            and outcome.label == XauForwardOutcomeLabel.PENDING
        ]
        return XauForwardJournalSummary(
            journal_id=entry.journal_id,
            snapshot_key=entry.snapshot_key,
            status=entry.status,
            snapshot_time=entry.snapshot.snapshot_time,
            capture_window=entry.snapshot.capture_window,
            capture_session=entry.snapshot.capture_session,
            product=entry.snapshot.product,
            expiration=entry.snapshot.expiration,
            expiration_code=entry.snapshot.expiration_code,
            fusion_report_id=_source_report_id(entry, "xau_quikstrike_fusion"),
            xau_vol_oi_report_id=_source_report_id(entry, "xau_vol_oi"),
            xau_reaction_report_id=_source_report_id(entry, "xau_reaction"),
            outcome_status=_entry_outcome_status(entry.outcomes),
            completed_outcome_count=len(completed_outcomes),
            pending_outcome_count=len(pending_outcomes),
            no_trade_count=sum(
                1
                for reaction in entry.reaction_summaries
                if reaction.reaction_label == "NO_TRADE"
            ),
            warning_count=len(entry.warnings),
        )

    def _validate_report_scope(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self._report_root)
        except ValueError as exc:
            raise ValueError("path must remain under xau_forward_journal report root") from exc

    def _project_relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        for base in (self.repo_root, self.reports_dir.resolve().parent.parent):
            try:
                return resolved.relative_to(base).as_posix()
            except ValueError:
                continue
        return resolved.as_posix()


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, XauForwardJournalBaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, tuple):
        return [_jsonable(value) for value in payload]
    return payload


def _source_report_id(entry: XauForwardJournalEntry, source_type: str) -> str | None:
    for ref in entry.source_reports:
        if ref.source_type == source_type:
            return ref.report_id
    return None


def _entry_outcome_status(
    outcomes: list[XauForwardOutcomeObservation],
) -> XauForwardOutcomeStatus:
    if not outcomes:
        return XauForwardOutcomeStatus.PENDING
    pending_count = sum(
        1
        for outcome in outcomes
        if outcome.status == XauForwardOutcomeStatus.PENDING
        and outcome.label == XauForwardOutcomeLabel.PENDING
    )
    if pending_count == len(outcomes):
        return XauForwardOutcomeStatus.PENDING
    if pending_count:
        return XauForwardOutcomeStatus.PARTIAL
    if any(outcome.status == XauForwardOutcomeStatus.INCONCLUSIVE for outcome in outcomes):
        return XauForwardOutcomeStatus.INCONCLUSIVE
    return XauForwardOutcomeStatus.COMPLETED


def _entry_markdown(entry: XauForwardJournalEntry) -> str:
    lines = [
        f"# XAU Forward Journal Entry {entry.journal_id}",
        "",
        "Local-only forward research journal entry. This is not a historical "
        "QuikStrike strike-level backtest.",
        "",
        f"- Status: `{entry.status.value}`",
        f"- Snapshot key: `{entry.snapshot_key}`",
        f"- Snapshot time: `{entry.snapshot.snapshot_time.isoformat()}`",
        f"- Capture window: `{entry.snapshot.capture_window}`",
        f"- Product: `{entry.snapshot.product}`",
        f"- Expiration: `{entry.snapshot.expiration or entry.snapshot.expiration_code}`",
        "",
        "## Source Reports",
    ]
    lines.extend(
        f"- {ref.source_type.value}: `{ref.report_id}` ({ref.status})"
        for ref in entry.source_reports
    )
    lines.extend(["", "## Top OI Walls"])
    lines.extend(
        f"- {wall.rank}. {wall.option_type} {wall.strike} OI={wall.open_interest}"
        for wall in entry.top_oi_walls
    )
    lines.extend(["", "## Reaction Summaries"])
    lines.extend(
        f"- {reaction.reaction_id}: {reaction.reaction_label}"
        for reaction in entry.reaction_summaries
    )
    lines.extend(["", "## Missing Context"])
    lines.extend(
        f"- {item.context_key}: {item.status} - {item.message}"
        for item in entry.missing_context
    )
    lines.extend(["", "## Outcomes"])
    lines.extend(
        f"- {outcome.window.value}: {outcome.status.value}/{outcome.label.value}"
        for outcome in entry.outcomes
    )
    lines.extend(["", "## Limitations"])
    lines.extend(f"- {limitation}" for limitation in entry.limitations)
    lines.extend(["", "## Artifacts"])
    lines.extend(f"- `{artifact.path}`" for artifact in entry.artifacts)
    return "\n".join(lines) + "\n"
