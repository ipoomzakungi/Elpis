from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPORT_SOURCE_KIND_OPERATIONAL = "operational"
REPORT_SOURCE_KIND_SYNTHETIC = "synthetic"
REPORT_SOURCE_KIND_SMOKE = "smoke"
REPORT_SOURCE_KIND_TEST = "test"

REPORT_SOURCE_KINDS = {
    REPORT_SOURCE_KIND_OPERATIONAL,
    REPORT_SOURCE_KIND_SYNTHETIC,
    REPORT_SOURCE_KIND_SMOKE,
    REPORT_SOURCE_KIND_TEST,
}


class ReportIdCollisionError(FileExistsError):
    """Raised when a report write would overwrite an existing report id."""


class ReportSourceKindIsolationError(ValueError):
    """Raised when a synthetic/smoke/test report id is not clearly isolated."""


def infer_report_source_kind(report_id: str) -> str:
    normalized = report_id.lower().replace("-", "_")
    if "smoke" in normalized:
        return REPORT_SOURCE_KIND_SMOKE
    if "synthetic" in normalized or "fixture" in normalized:
        return REPORT_SOURCE_KIND_SYNTHETIC
    if normalized.startswith("test_") or "_test_" in normalized or normalized.endswith("_test"):
        return REPORT_SOURCE_KIND_TEST
    return REPORT_SOURCE_KIND_OPERATIONAL


def normalize_report_source_kind(
    source_kind: str | None,
    *,
    report_id: str,
) -> str:
    if source_kind is None:
        return infer_report_source_kind(report_id)
    normalized = source_kind.strip().lower()
    if normalized not in REPORT_SOURCE_KINDS:
        raise ValueError("source_kind must be operational, synthetic, smoke, or test")
    return normalized


def resolve_report_source_kind_for_write(
    *,
    report_id: str,
    explicit_source_kind: str | None = None,
    model_source_kind: str | None = None,
) -> str:
    if explicit_source_kind is not None:
        return normalize_report_source_kind(explicit_source_kind, report_id=report_id)
    if model_source_kind and model_source_kind != REPORT_SOURCE_KIND_OPERATIONAL:
        return normalize_report_source_kind(model_source_kind, report_id=report_id)
    return infer_report_source_kind(report_id)


def assert_report_write_allowed(
    *,
    report_dir: Path,
    report_id: str,
    source_kind: str | None = None,
    overwrite_allowed: bool = False,
    allowed_existing_filenames: Iterable[str] = (),
) -> str:
    normalized_kind = normalize_report_source_kind(source_kind, report_id=report_id)
    _assert_source_kind_isolated(
        report_id=report_id,
        source_kind=normalized_kind,
        report_dir=report_dir,
    )
    if report_dir.exists() and not overwrite_allowed:
        allowed_names = set(allowed_existing_filenames)
        unexpected_paths = [
            path for path in report_dir.iterdir() if path.name not in allowed_names
        ]
        if not unexpected_paths:
            return normalized_kind
        raise ReportIdCollisionError(
            f"Report id '{report_id}' already exists; refusing to overwrite without "
            "overwrite_allowed=True."
        )
    return normalized_kind


def source_kind_from_report(
    report: dict[str, Any],
    *,
    report_id: str,
) -> str:
    source_kind = report.get("source_kind")
    if isinstance(source_kind, str):
        return normalize_report_source_kind(source_kind, report_id=report_id)
    return infer_report_source_kind(report_id)


def source_kind_warning(report_id: str, source_kind: str) -> str | None:
    if source_kind == REPORT_SOURCE_KIND_OPERATIONAL:
        return None
    return (
        f"Source report '{report_id}' is marked {source_kind}; keep it isolated from "
        "operational forward evidence."
    )


def _assert_source_kind_isolated(
    *,
    report_id: str,
    source_kind: str,
    report_dir: Path,
) -> None:
    if source_kind == REPORT_SOURCE_KIND_OPERATIONAL:
        return
    inferred = infer_report_source_kind(report_id)
    if inferred != REPORT_SOURCE_KIND_OPERATIONAL:
        return
    if "_smoke" in {part.lower() for part in report_dir.parts}:
        return
    raise ReportSourceKindIsolationError(
        "Synthetic, smoke, and test report ids must be clearly isolated with a "
        "synthetic_*, smoke_*, or test_* id, or under an _smoke report path."
    )
