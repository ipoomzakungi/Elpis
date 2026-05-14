from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.models.xau_forward_journal import (
    XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION,
    XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING,
    XauForwardJournalCreateRequest,
    XauForwardJournalEntry,
    XauForwardJournalEntryStatus,
    XauForwardJournalSourceType,
    XauForwardMissingContextItem,
    XauForwardReactionSummary,
    XauForwardSnapshotContext,
    XauForwardSourceReportRef,
    XauForwardWallSummary,
    validate_xau_forward_journal_safe_id,
)
from src.xau_forward_journal.outcome import create_default_pending_outcomes


class XauForwardJournalBuildError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "VALIDATION_ERROR",
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


class XauForwardSourceReportNotFoundError(XauForwardJournalBuildError):
    def __init__(self, details: list[dict[str, str]]) -> None:
        super().__init__(
            "One or more selected source reports were not found",
            code="SOURCE_REPORT_NOT_FOUND",
            details=details,
        )


class XauForwardIncompatibleSourceReportError(XauForwardJournalBuildError):
    def __init__(self, details: list[dict[str, str]]) -> None:
        super().__init__(
            "Selected source reports are not compatible for one forward journal entry",
            code="INCOMPATIBLE_SOURCE_REPORTS",
            details=details,
        )


@dataclass(frozen=True)
class XauForwardLoadedSources:
    reports_dir: Path
    request: XauForwardJournalCreateRequest
    vol2vol_report: dict[str, Any]
    matrix_report: dict[str, Any]
    fusion_report: dict[str, Any]
    xau_vol_oi_report: dict[str, Any]
    xau_reaction_report: dict[str, Any]
    vol2vol_rows: list[dict[str, Any]]
    matrix_rows: list[dict[str, Any]]

    @property
    def source_refs(self) -> list[XauForwardSourceReportRef]:
        return build_source_refs(self)


def load_source_reports(
    request: XauForwardJournalCreateRequest,
    *,
    reports_dir: Path | None = None,
) -> XauForwardLoadedSources:
    root = reports_dir or get_settings().data_reports_path
    missing: list[dict[str, str]] = []

    vol2vol_report = _read_json_report(
        root,
        "quikstrike",
        request.vol2vol_report_id,
        ("report.json",),
        field_name="vol2vol_report_id",
        missing=missing,
    )
    matrix_report = _read_json_report(
        root,
        "quikstrike_matrix",
        request.matrix_report_id,
        ("report.json",),
        field_name="matrix_report_id",
        missing=missing,
    )
    fusion_report = _read_json_report(
        root,
        "xau_quikstrike_fusion",
        request.fusion_report_id,
        ("report.json",),
        field_name="fusion_report_id",
        missing=missing,
    )
    xau_vol_oi_report = _read_json_report(
        root,
        "xau_vol_oi",
        request.xau_vol_oi_report_id,
        ("metadata.json", "report.json"),
        field_name="xau_vol_oi_report_id",
        missing=missing,
    )
    xau_reaction_report = _read_json_report(
        root,
        "xau_reaction",
        request.xau_reaction_report_id,
        ("metadata.json", "report.json"),
        field_name="xau_reaction_report_id",
        missing=missing,
    )

    if missing:
        raise XauForwardSourceReportNotFoundError(missing)

    return XauForwardLoadedSources(
        reports_dir=root,
        request=request,
        vol2vol_report=vol2vol_report,
        matrix_report=matrix_report,
        fusion_report=fusion_report,
        xau_vol_oi_report=xau_vol_oi_report,
        xau_reaction_report=xau_reaction_report,
        vol2vol_rows=_read_optional_json_rows(root, "quikstrike", request.vol2vol_report_id),
        matrix_rows=_read_optional_matrix_rows(root, request.matrix_report_id, matrix_report),
    )


def build_source_refs(loaded: XauForwardLoadedSources) -> list[XauForwardSourceReportRef]:
    request = loaded.request
    return [
        _source_ref(
            XauForwardJournalSourceType.QUIKSTRIKE_VOL2VOL,
            request.vol2vol_report_id,
            loaded.vol2vol_report,
            product=_first_text_from_rows(loaded.vol2vol_rows, "product"),
            expiration=_first_text_from_rows(loaded.vol2vol_rows, "expiration"),
            expiration_code=_first_text_from_rows(loaded.vol2vol_rows, "expiration_code"),
        ),
        _source_ref(
            XauForwardJournalSourceType.QUIKSTRIKE_MATRIX,
            request.matrix_report_id,
            loaded.matrix_report,
            product=_first_text_from_rows(loaded.matrix_rows, "product"),
            expiration=_first_text_from_rows(loaded.matrix_rows, "expiration"),
        ),
        _source_ref(
            XauForwardJournalSourceType.XAU_QUIKSTRIKE_FUSION,
            request.fusion_report_id,
            loaded.fusion_report,
            product=_extract_fusion_product(loaded.fusion_report),
            expiration=_first_fusion_expiration(loaded.fusion_report),
            expiration_code=_first_fusion_expiration_code(loaded.fusion_report),
        ),
        _source_ref(
            XauForwardJournalSourceType.XAU_VOL_OI,
            request.xau_vol_oi_report_id,
            loaded.xau_vol_oi_report,
            product="Gold (XAU/GC)",
            expiration=_first_xau_wall_field(loaded.xau_vol_oi_report, "expiry"),
        ),
        _source_ref(
            XauForwardJournalSourceType.XAU_REACTION,
            request.xau_reaction_report_id,
            loaded.xau_reaction_report,
            product="Gold (XAU/GC)",
            expiration=_date_like_text(loaded.xau_reaction_report.get("session_date")),
        ),
    ]


def validate_source_compatibility(loaded: XauForwardLoadedSources) -> None:
    request = loaded.request
    details: list[dict[str, str]] = []

    for ref in loaded.source_refs:
        if ref.product and not _is_gold_product(ref.product):
            details.append(
                {
                    "field": f"{ref.source_type.value}.product",
                    "message": f"Source report product is not Gold/XAU compatible: {ref.product}",
                }
            )
        if ref.status in {"blocked", "failed"}:
            details.append(
                {
                    "field": f"{ref.source_type.value}.status",
                    "message": f"Source report status is {ref.status}",
                }
            )

    _check_report_link(
        details,
        "fusion_report_id",
        request.vol2vol_report_id,
        _nested_text(loaded.fusion_report, "vol2vol_source", "report_id"),
        "Fusion report does not reference the selected Vol2Vol report",
    )
    _check_report_link(
        details,
        "fusion_report_id",
        request.matrix_report_id,
        _nested_text(loaded.fusion_report, "matrix_source", "report_id"),
        "Fusion report does not reference the selected Matrix report",
    )
    _check_report_link(
        details,
        "xau_reaction_report_id",
        request.xau_vol_oi_report_id,
        _text_or_none(loaded.xau_reaction_report.get("source_report_id")),
        "XAU reaction report does not reference the selected XAU Vol-OI report",
    )

    downstream = loaded.fusion_report.get("downstream_result")
    if isinstance(downstream, dict):
        _check_report_link(
            details,
            "fusion_report_id",
            request.xau_vol_oi_report_id,
            _text_or_none(downstream.get("xau_vol_oi_report_id")),
            "Fusion downstream result does not reference the selected XAU Vol-OI report",
            required=False,
        )
        _check_report_link(
            details,
            "fusion_report_id",
            request.xau_reaction_report_id,
            _text_or_none(downstream.get("xau_reaction_report_id")),
            "Fusion downstream result does not reference the selected XAU reaction report",
            required=False,
        )

    if details:
        raise XauForwardIncompatibleSourceReportError(details)


def build_journal_entry(
    request: XauForwardJournalCreateRequest,
    *,
    reports_dir: Path | None = None,
) -> XauForwardJournalEntry:
    loaded = load_source_reports(request, reports_dir=reports_dir)
    validate_source_compatibility(loaded)

    refs = loaded.source_refs
    snapshot = build_snapshot_context(loaded)
    snapshot_key = derive_snapshot_key(request, snapshot)
    journal_id = f"xau_forward_journal_{snapshot_key}"
    missing_context = build_missing_context_items(loaded, snapshot)
    warnings = _journal_warnings(refs, missing_context)
    limitations = _dedupe(
        [
            XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION,
            *[limitation for ref in refs for limitation in ref.limitations],
        ]
    )
    status = (
        XauForwardJournalEntryStatus.COMPLETED
        if not warnings and not missing_context
        else XauForwardJournalEntryStatus.PARTIAL
    )

    return XauForwardJournalEntry(
        journal_id=journal_id,
        snapshot_key=snapshot_key,
        status=status,
        snapshot=snapshot,
        source_reports=refs,
        top_oi_walls=build_top_oi_walls(loaded),
        top_oi_change_walls=build_top_fusion_value_walls(loaded, "oi_change"),
        top_volume_walls=build_top_fusion_value_walls(loaded, "volume"),
        reaction_summaries=build_reaction_summaries(loaded),
        missing_context=missing_context,
        outcomes=create_default_pending_outcomes(),
        notes=request.notes,
        warnings=warnings,
        limitations=limitations,
        research_only_warnings=[XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING],
    )


def build_snapshot_context(loaded: XauForwardLoadedSources) -> XauForwardSnapshotContext:
    request = loaded.request
    basis = request.basis
    if (
        basis is None
        and request.spot_price_at_snapshot is not None
        and request.futures_price_at_snapshot is not None
    ):
        basis = request.futures_price_at_snapshot - request.spot_price_at_snapshot

    missing_context = [
        field_name
        for field_name, value in (
            ("spot_price_at_snapshot", request.spot_price_at_snapshot),
            ("futures_price_at_snapshot", request.futures_price_at_snapshot),
            ("basis", basis),
            ("session_open_price", request.session_open_price),
            ("event_news_flag", request.event_news_flag),
        )
        if value is None
    ]

    return XauForwardSnapshotContext(
        snapshot_time=request.snapshot_time,
        capture_window=request.capture_window,
        capture_session=request.capture_session,
        product=_derive_product(loaded),
        expiration=_derive_expiration(loaded),
        expiration_code=_derive_expiration_code(loaded),
        spot_price_at_snapshot=request.spot_price_at_snapshot,
        futures_price_at_snapshot=request.futures_price_at_snapshot,
        basis=basis,
        session_open_price=request.session_open_price,
        event_news_flag=request.event_news_flag,
        missing_context=missing_context,
        notes=request.notes,
    )


def derive_snapshot_key(
    request: XauForwardJournalCreateRequest,
    snapshot: XauForwardSnapshotContext,
) -> str:
    capture_date = request.snapshot_time.date().strftime("%Y%m%d")
    expiration_token = snapshot.expiration_code or snapshot.expiration or "no_expiration"
    raw_key = "|".join(
        [
            snapshot.product or "gold",
            capture_date,
            snapshot.capture_window,
            expiration_token,
            request.vol2vol_report_id,
            request.matrix_report_id,
            request.fusion_report_id,
            request.xau_vol_oi_report_id,
            request.xau_reaction_report_id,
        ]
    )
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]
    key = "_".join(
        token
        for token in (
            capture_date,
            _safe_slug(snapshot.capture_window),
            _safe_slug(expiration_token),
            digest,
        )
        if token
    )
    return validate_xau_forward_journal_safe_id(key, "snapshot_key")


def build_missing_context_items(
    loaded: XauForwardLoadedSources,
    snapshot: XauForwardSnapshotContext,
) -> list[XauForwardMissingContextItem]:
    items: list[XauForwardMissingContextItem] = []
    for context_key in snapshot.missing_context:
        items.append(
            XauForwardMissingContextItem(
                context_key=context_key,
                status="unavailable",
                severity="warning",
                message=f"Optional snapshot input '{context_key}' was not provided.",
                source_report_ids=[loaded.request.fusion_report_id],
                blocks_outcome_label=False,
                blocks_reaction_review=context_key
                in {"basis", "session_open_price", "spot_price_at_snapshot"},
            )
        )

    context_summary = loaded.fusion_report.get("context_summary")
    if isinstance(context_summary, dict):
        for item in context_summary.get("missing_context", []):
            if not isinstance(item, dict):
                continue
            context_key = _text_or_none(item.get("context_key")) or "source_context"
            items.append(
                XauForwardMissingContextItem(
                    context_key=context_key,
                    status=_text_or_none(item.get("status")) or "unavailable",
                    severity=_text_or_none(item.get("severity")) or "warning",
                    message=_text_or_none(item.get("message"))
                    or f"Fusion context '{context_key}' is unavailable.",
                    source_report_ids=[
                        validate_xau_forward_journal_safe_id(ref, "source_report_id")
                        for ref in _text_list(item.get("source_refs"))
                        if _is_safe_id(ref)
                    ],
                    blocks_outcome_label=bool(item.get("blocks_outcome_label", False)),
                    blocks_reaction_review=bool(
                        item.get("blocks_reaction_confidence", False)
                    ),
                )
            )
    return _dedupe_missing_context(items)


def build_top_oi_walls(
    loaded: XauForwardLoadedSources,
    *,
    limit: int = 5,
) -> list[XauForwardWallSummary]:
    walls = [
        wall
        for wall in loaded.xau_vol_oi_report.get("walls", [])
        if isinstance(wall, dict) and _float_or_none(wall.get("open_interest")) is not None
    ]
    walls = sorted(
        walls,
        key=lambda wall: (
            _float_or_none(wall.get("wall_score")) or 0.0,
            _float_or_none(wall.get("open_interest")) or 0.0,
        ),
        reverse=True,
    )
    summaries: list[XauForwardWallSummary] = []
    for rank, wall in enumerate(walls[:limit], start=1):
        summaries.append(
            XauForwardWallSummary(
                summary_id=f"open_interest_{rank}",
                wall_type="open_interest",
                source_report_id=loaded.request.xau_vol_oi_report_id,
                strike=_float_or_none(wall.get("strike")) or 0.01,
                expiration=_date_like_text(wall.get("expiry")),
                expiration_code=_derive_expiration_code(loaded),
                option_type=_text_or_none(wall.get("option_type")),
                open_interest=_float_or_none(wall.get("open_interest")),
                wall_score=_float_or_none(wall.get("wall_score")),
                rank=rank,
                notes=_notes_from_texts(wall.get("notes")),
                limitations=_text_list(wall.get("limitations")),
            )
        )
    return summaries


def build_top_fusion_value_walls(
    loaded: XauForwardLoadedSources,
    value_type: str,
    *,
    limit: int = 5,
) -> list[XauForwardWallSummary]:
    candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for row in loaded.fusion_report.get("fused_rows", []):
        if not isinstance(row, dict):
            continue
        match_key = row.get("match_key")
        if not isinstance(match_key, dict) or match_key.get("value_type") != value_type:
            continue
        source_value = _source_value_for_fusion_row(row)
        value = _float_or_none(source_value.get("value"))
        if value is None:
            continue
        candidates.append((abs(value), row, source_value))

    summaries: list[XauForwardWallSummary] = []
    for rank, (_sort_value, row, source_value) in enumerate(
        sorted(candidates, key=lambda item: item[0], reverse=True)[:limit],
        start=1,
    ):
        match_key = row["match_key"]
        value = _float_or_none(source_value.get("value"))
        kwargs: dict[str, float | None] = {
            "oi_change": value if value_type == "oi_change" else None,
            "volume": value if value_type == "volume" else None,
        }
        summaries.append(
            XauForwardWallSummary(
                summary_id=f"{value_type}_{rank}",
                wall_type=value_type,
                source_report_id=loaded.request.fusion_report_id,
                strike=_float_or_none(match_key.get("strike")) or 0.01,
                expiration=_text_or_none(match_key.get("expiration")),
                expiration_code=_text_or_none(match_key.get("expiration_code")),
                option_type=_text_or_none(match_key.get("option_type")),
                wall_score=abs(value or 0.0),
                rank=rank,
                limitations=_text_list(row.get("limitations"))
                or _text_list(source_value.get("limitations")),
                **kwargs,
            )
        )
    return summaries


def build_reaction_summaries(
    loaded: XauForwardLoadedSources,
    *,
    limit: int = 10,
) -> list[XauForwardReactionSummary]:
    risk_counts: dict[str, int] = {}
    for plan in _dict_list(loaded.xau_reaction_report.get("risk_plans")):
        reaction_id = _text_or_none(plan.get("reaction_id"))
        if reaction_id:
            risk_counts[reaction_id] = risk_counts.get(reaction_id, 0) + 1

    summaries: list[XauForwardReactionSummary] = []
    for reaction in _dict_list(loaded.xau_reaction_report.get("reactions"))[:limit]:
        reaction_id = _text_or_none(reaction.get("reaction_id"))
        if not reaction_id:
            continue
        summaries.append(
            XauForwardReactionSummary(
                reaction_id=reaction_id,
                source_report_id=loaded.request.xau_reaction_report_id,
                wall_id=_text_or_none(reaction.get("wall_id")),
                zone_id=_text_or_none(reaction.get("zone_id")),
                reaction_label=_text_or_none(reaction.get("reaction_label")) or "UNKNOWN",
                confidence_label=_text_or_none(reaction.get("confidence_label")),
                no_trade_reasons=_text_list(reaction.get("no_trade_reasons")),
                bounded_risk_annotation_count=risk_counts.get(reaction_id, 0),
                limitations=_text_list(loaded.xau_reaction_report.get("limitations")),
            )
        )
    return summaries


def _read_json_report(
    root: Path,
    family: str,
    report_id: str,
    filenames: tuple[str, ...],
    *,
    field_name: str,
    missing: list[dict[str, str]],
) -> dict[str, Any]:
    report_dir = root / family / report_id
    for filename in filenames:
        path = report_dir / filename
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    missing.append(
        {
            "field": field_name,
            "message": f"{family} report '{report_id}' was not found",
        }
    )
    return {}


def _read_optional_json_rows(root: Path, family: str, report_id: str) -> list[dict[str, Any]]:
    path = root / family / report_id / "normalized_rows.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _read_optional_matrix_rows(
    root: Path,
    report_id: str,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    direct_path = root / "quikstrike_matrix" / report_id / "normalized_rows.json"
    if direct_path.exists():
        payload = json.loads(direct_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []

    for artifact in report.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        if artifact.get("artifact_type") != "raw_normalized_rows_json":
            continue
        artifact_path = _absolute_artifact_path(root, artifact.get("path"))
        if artifact_path.exists():
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []

    raw_path = root.parent / "raw" / "quikstrike_matrix" / f"{report_id}_normalized_rows.json"
    if raw_path.exists():
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    return []


def _absolute_artifact_path(root: Path, value: Any) -> Path:
    text = _text_or_none(value) or ""
    path = Path(text)
    if path.is_absolute():
        return path
    return root.parent.parent / path


def _source_ref(
    source_type: XauForwardJournalSourceType,
    report_id: str,
    report: dict[str, Any],
    *,
    product: str | None = None,
    expiration: str | None = None,
    expiration_code: str | None = None,
) -> XauForwardSourceReportRef:
    status = _text_or_none(report.get("status")) or "available"
    warnings = _text_list(report.get("warnings"))
    if status != "completed" and status != "available":
        warnings.append(f"{source_type.value} source status is {status}.")
    return XauForwardSourceReportRef(
        source_type=source_type,
        report_id=report_id,
        status=status,
        created_at=_datetime_or_none(report.get("created_at")),
        product=product or _text_or_none(report.get("product")),
        expiration=expiration or _text_or_none(report.get("expiration")),
        expiration_code=expiration_code or _text_or_none(report.get("expiration_code")),
        row_count=_int_or_zero(
            report.get("row_count")
            or report.get("fused_row_count")
            or report.get("source_row_count")
            or report.get("reaction_count")
        ),
        warnings=warnings,
        limitations=_dedupe(
            [
                *_text_list(report.get("limitations")),
                *_text_list(report.get("research_only_warnings")),
            ]
        ),
        artifact_paths=[
            path
            for path in (
                _text_or_none(artifact.get("path"))
                for artifact in report.get("artifacts", [])
                if isinstance(artifact, dict)
            )
            if path
        ],
    )


def _derive_product(loaded: XauForwardLoadedSources) -> str:
    return (
        _extract_fusion_product(loaded.fusion_report)
        or _first_text_from_rows(loaded.vol2vol_rows, "product")
        or _first_text_from_rows(loaded.matrix_rows, "product")
        or "Gold (XAU/GC)"
    )


def _derive_expiration(loaded: XauForwardLoadedSources) -> str | None:
    return (
        _first_xau_wall_field(loaded.xau_vol_oi_report, "expiry")
        or _first_fusion_expiration(loaded.fusion_report)
        or _first_text_from_rows(loaded.matrix_rows, "expiration")
        or _first_text_from_rows(loaded.vol2vol_rows, "expiration")
    )


def _derive_expiration_code(loaded: XauForwardLoadedSources) -> str | None:
    return (
        _first_fusion_expiration_code(loaded.fusion_report)
        or _first_text_from_rows(loaded.vol2vol_rows, "expiration_code")
        or _first_xau_wall_field(loaded.xau_vol_oi_report, "expiration_code")
    )


def _extract_fusion_product(report: dict[str, Any]) -> str | None:
    return (
        _nested_text(report, "vol2vol_source", "product")
        or _nested_text(report, "matrix_source", "product")
        or _text_or_none(report.get("product"))
    )


def _first_fusion_expiration(report: dict[str, Any]) -> str | None:
    for row in report.get("fused_rows", []):
        if not isinstance(row, dict):
            continue
        match_key = row.get("match_key")
        if isinstance(match_key, dict):
            expiration = _text_or_none(match_key.get("expiration"))
            if expiration:
                return expiration
    return None


def _first_fusion_expiration_code(report: dict[str, Any]) -> str | None:
    for row in report.get("fused_rows", []):
        if not isinstance(row, dict):
            continue
        match_key = row.get("match_key")
        if isinstance(match_key, dict):
            expiration_code = _text_or_none(match_key.get("expiration_code"))
            if expiration_code:
                return expiration_code
    return None


def _first_xau_wall_field(report: dict[str, Any], field_name: str) -> str | None:
    for wall in report.get("walls", []):
        if isinstance(wall, dict):
            value = _date_like_text(wall.get(field_name))
            if value:
                return value
    return None


def _journal_warnings(
    refs: list[XauForwardSourceReportRef],
    missing_context: list[XauForwardMissingContextItem],
) -> list[str]:
    return _dedupe(
        [
            *[warning for ref in refs for warning in ref.warnings],
            *[
                f"{item.context_key}: {item.message}"
                for item in missing_context
                if item.severity in {"warning", "error"}
            ],
        ]
    )


def _source_value_for_fusion_row(row: dict[str, Any]) -> dict[str, Any]:
    for field_name in ("matrix_value", "vol2vol_value"):
        value = row.get(field_name)
        if isinstance(value, dict) and _float_or_none(value.get("value")) is not None:
            return value
    return {}


def _notes_from_texts(value: Any) -> list[dict[str, str]]:
    return [{"text": text, "source": "source_report"} for text in _text_list(value)]


def _check_report_link(
    details: list[dict[str, str]],
    field: str,
    expected: str,
    actual: str | None,
    message: str,
    *,
    required: bool = True,
) -> None:
    if actual is None and not required:
        return
    if actual != expected:
        details.append({"field": field, "message": message})


def _is_gold_product(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ("gold", "og|gc", "xau", " gc", "gc "))


def _first_text_from_rows(rows: list[dict[str, Any]], field_name: str) -> str | None:
    for row in rows:
        if isinstance(row, dict):
            value = _date_like_text(row.get(field_name))
            if value:
                return value
    return None


def _nested_text(report: dict[str, Any], outer: str, inner: str) -> str | None:
    value = report.get(outer)
    if not isinstance(value, dict):
        return None
    return _text_or_none(value.get(inner))


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _date_like_text(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _text_or_none(value)


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [str(item) for item in value if item is not None]
    else:
        values = [str(value)]
    return _dedupe([text for text in (_text_or_none(item) for item in values) if text])


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text_or_none(value)
        if text and text not in seen:
            deduped.append(text)
            seen.add(text)
    return deduped


def _dedupe_missing_context(
    items: list[XauForwardMissingContextItem],
) -> list[XauForwardMissingContextItem]:
    deduped: list[XauForwardMissingContextItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.context_key, item.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _safe_slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_-]+", "_", value)).strip("_").lower()


def _is_safe_id(value: str) -> bool:
    try:
        validate_xau_forward_journal_safe_id(value, "source_report_id")
    except ValueError:
        return False
    return True
