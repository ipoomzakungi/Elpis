from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "session_date",
    "selected_series",
    "dte",
    "futures_reference",
    "lower_2sd",
    "upper_2sd",
    "touch_time",
    "mapping_mode",
    "mapping_reference",
}


def validate_external_study_file(path: Path) -> dict[str, Any]:
    rows = _load_rows(path)
    validated = []
    errors = []
    for index, row in enumerate(rows):
        missing = sorted(field for field in REQUIRED_FIELDS if row.get(field) in (None, ""))
        if missing:
            errors.append({"row": index, "error": f"missing fields: {', '.join(missing)}"})
            continue
        if not row.get("price_path") and not row.get("barrier_ordering"):
            errors.append(
                {
                    "row": index,
                    "error": "price_path or barrier_ordering is required",
                }
            )
            continue
        try:
            normalized = {
                **row,
                "dte": float(row["dte"]),
                "futures_reference": float(row["futures_reference"]),
                "lower_2sd": float(row["lower_2sd"]),
                "upper_2sd": float(row["upper_2sd"]),
                "observation_source": "external_author_supplied",
                "eligible_for_elpis_local_pool": False,
                "research_only": True,
                "signal_allowed": False,
                "order_submission_allowed": False,
            }
        except (TypeError, ValueError):
            errors.append({"row": index, "error": "numeric field parse failure"})
            continue
        validated.append(normalized)
    return {
        "source_path": path.as_posix(),
        "row_count": len(rows),
        "valid_row_count": len(validated),
        "invalid_row_count": len(errors),
        "rows": validated,
        "errors": errors,
        "pooling_policy": "External observations remain separate from Elpis observations.",
        "fabricated_observations_allowed": False,
        "research_only": True,
        "signal_allowed": False,
        "order_submission_allowed": False,
    }


def write_external_import(output_dir: Path, report: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "external_author_observations.json"
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(item) for item in csv.DictReader(handle)]
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(item) for item in payload]
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if isinstance(rows, list):
            return [dict(item) for item in rows]
        raise ValueError("External JSON must be a list or contain a rows list")
    raise ValueError("External study importer accepts only .csv or .json")
