from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from src.xau_forward_journal.entry_builder import XauForwardLoadedSources


@dataclass(frozen=True)
class XauForwardContentFingerprint:
    fingerprint: str
    component_fingerprints: dict[str, str]
    component_counts: dict[str, int]


def build_snapshot_content_fingerprint(
    loaded: XauForwardLoadedSources,
) -> XauForwardContentFingerprint:
    """Fingerprint sanitized XAU snapshot content, excluding run/session artifacts."""

    vol2vol_rows = _vol2vol_fingerprint_rows(
        loaded.vol2vol_rows,
        capture_source_kind=_source_kind(loaded.vol2vol_report),
    )
    matrix_rows = _matrix_fingerprint_rows(
        loaded.matrix_rows,
        capture_source_kind=_source_kind(loaded.matrix_report),
    )
    fusion_rows = _fusion_fingerprint_rows(
        _fusion_rows(loaded.fusion_report),
        product=_fusion_product(loaded),
        capture_source_kind=_source_kind(loaded.fusion_report),
    )
    components = {
        "vol2vol": _digest(vol2vol_rows),
        "matrix": _digest(matrix_rows),
        "fusion": _digest(fusion_rows),
    }
    payload = {
        "version": 1,
        "components": components,
        "counts": {
            "vol2vol": len(vol2vol_rows),
            "matrix": len(matrix_rows),
            "fusion": len(fusion_rows),
        },
    }
    return XauForwardContentFingerprint(
        fingerprint=_digest(payload),
        component_fingerprints=components,
        component_counts=payload["counts"],
    )


def _vol2vol_fingerprint_rows(
    rows: list[dict[str, Any]],
    *,
    capture_source_kind: str,
) -> list[dict[str, Any]]:
    return _sort_rows(
        [
            _fingerprint_row(
                product=_text(row.get("product")),
                expiration=_text(row.get("expiration")),
                expiration_code=_text(row.get("expiration_code")),
                view_type=_text(row.get("view_type") or row.get("source_view")),
                strike=_number(row.get("strike")),
                option_type=_text(row.get("option_type")),
                value_type=_text(row.get("value_type")),
                value=_number(row.get("value")),
                capture_source_kind=capture_source_kind,
            )
            for row in rows
        ]
    )


def _matrix_fingerprint_rows(
    rows: list[dict[str, Any]],
    *,
    capture_source_kind: str,
) -> list[dict[str, Any]]:
    return _sort_rows(
        [
            _fingerprint_row(
                product=_text(row.get("product")),
                expiration=_text(row.get("expiration")),
                expiration_code=_text(row.get("expiration_code") or row.get("expiration")),
                view_type=_text(row.get("view_type") or row.get("source_menu")),
                strike=_number(row.get("strike")),
                option_type=_text(row.get("option_type")),
                value_type=_text(row.get("value_type")),
                value=_number(row.get("value")),
                capture_source_kind=capture_source_kind,
            )
            for row in rows
        ]
    )


def _fusion_fingerprint_rows(
    rows: list[dict[str, Any]],
    *,
    product: str | None,
    capture_source_kind: str,
) -> list[dict[str, Any]]:
    fingerprint_rows: list[dict[str, Any]] = []
    for row in rows:
        match_key = row.get("match_key") if isinstance(row.get("match_key"), dict) else {}
        base = {
            "product": _text(product),
            "expiration": _text(match_key.get("expiration")),
            "expiration_code": _text(match_key.get("expiration_code")),
            "strike": _number(match_key.get("strike")),
            "option_type": _text(match_key.get("option_type")),
            "capture_source_kind": capture_source_kind,
        }
        row_source = _text(row.get("source_type"))
        added_value = False
        for value_key in ("matrix_value", "vol2vol_value"):
            value_payload = row.get(value_key)
            if not isinstance(value_payload, dict):
                continue
            fingerprint_rows.append(
                _fingerprint_row(
                    **base,
                    view_type=row_source or value_key,
                    value_type=_text(
                        value_payload.get("value_type") or match_key.get("value_type")
                    ),
                    value=_number(value_payload.get("value")),
                )
            )
            added_value = True
        if not added_value:
            fingerprint_rows.append(
                _fingerprint_row(
                    **base,
                    view_type=row_source,
                    value_type=_text(match_key.get("value_type")),
                    value=None,
                )
            )
    return _sort_rows(fingerprint_rows)


def _fingerprint_row(
    *,
    product: str | None,
    expiration: str | None,
    expiration_code: str | None,
    view_type: str | None,
    strike: str | None,
    option_type: str | None,
    value_type: str | None,
    value: str | None,
    capture_source_kind: str,
) -> dict[str, str | None]:
    return {
        "product": product,
        "expiration": expiration,
        "expiration_code": expiration_code,
        "view_type": view_type,
        "strike": strike,
        "option_type": option_type,
        "value_type": value_type,
        "value": value,
        "capture_source_kind": capture_source_kind,
    }


def _sort_rows(rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_kind(report: dict[str, Any]) -> str:
    return _text(report.get("source_kind")) or "unknown"


def _fusion_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("fused_rows")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _fusion_product(loaded: XauForwardLoadedSources) -> str | None:
    for report in (loaded.fusion_report, loaded.vol2vol_report, loaded.matrix_report):
        product = _text(report.get("product"))
        if product:
            return product
    for row in [*loaded.vol2vol_rows, *loaded.matrix_rows]:
        product = _text(row.get("product"))
        if product:
            return product
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text or None


def _number(value: Any) -> str | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)
    return f"{number:.12g}"
