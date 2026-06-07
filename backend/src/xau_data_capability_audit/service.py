from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.xau_data_capability_audit import (
    DATA_CAPABILITY_AUDIT_NO_SIGNAL_REASON,
    XauDataCapabilityAuditReadiness,
    XauDataCapabilityAuditRequest,
    XauDataCapabilityAuditResult,
    XauDataCapabilityEvidence,
    XauDataCapabilityName,
    XauDataCapabilityResult,
    XauDataCapabilitySourceSummary,
    XauDataCapabilitySourceType,
    XauDataCapabilityStatus,
)
from src.quikstrike.report_store import QuikStrikeReportStore
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore
from src.xau.report_store import XauReportStore
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore


class XauDataCapabilityAuditService:
    def __init__(self, reports_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir
        self.vol2vol_store = QuikStrikeReportStore(reports_dir=reports_dir)
        self.matrix_store = QuikStrikeMatrixReportStore(reports_dir=reports_dir)
        self.fusion_store = XauQuikStrikeFusionReportStore(reports_dir=reports_dir)
        self.xau_store = XauReportStore(reports_dir=reports_dir)

    def run(
        self,
        request: XauDataCapabilityAuditRequest | None = None,
    ) -> XauDataCapabilityAuditResult:
        resolved_request = request or XauDataCapabilityAuditRequest()
        redirected = self._service_for_request_reports_dir(resolved_request)
        if redirected is not None:
            redirected_request = resolved_request.model_copy(update={"reports_dir": None})
            return redirected.run(redirected_request)

        collector = _CapabilityCollector()
        source_reports: list[XauDataCapabilitySourceSummary] = []
        limitations: list[str] = []

        self._audit_vol2vol_sources(resolved_request, collector, source_reports, limitations)
        self._audit_matrix_sources(resolved_request, collector, source_reports, limitations)
        self._audit_fusion_sources(resolved_request, collector, source_reports, limitations)
        self._audit_xau_vol_oi_sources(resolved_request, collector, source_reports, limitations)

        capabilities = collector.results()
        capability_by_name = {item.capability: item for item in capabilities}
        if _is_available(capability_by_name[XauDataCapabilityName.HAS_GAMMA]) and _is_available(
            capability_by_name[XauDataCapabilityName.HAS_OI]
        ):
            collector.set_manual_status(
                XauDataCapabilityName.HAS_GEX_POSSIBLE,
                XauDataCapabilityStatus.AVAILABLE,
                (
                    "Gamma and open interest are present; GEX calculation is possible "
                    "in a later slice."
                ),
            )
        else:
            collector.set_manual_status(
                XauDataCapabilityName.HAS_GEX_POSSIBLE,
                XauDataCapabilityStatus.BLOCKED,
                "GEX is blocked because gamma and open interest are not both available.",
            )
        capabilities = collector.results()
        missing = [
            item.capability
            for item in capabilities
            if item.status == XauDataCapabilityStatus.UNAVAILABLE
        ]
        blocked = [
            item.capability
            for item in capabilities
            if item.status == XauDataCapabilityStatus.BLOCKED
        ]
        return XauDataCapabilityAuditResult(
            audit_id=f"xau_data_capability_audit_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}",
            created_at=datetime.now(UTC),
            readiness=_readiness(source_reports, missing, blocked),
            source_reports=source_reports,
            capabilities=capabilities,
            missing_capabilities=missing,
            blocked_capabilities=blocked,
            limitations=_dedupe(
                [
                    *limitations,
                    "Capability audit is read-only and does not fetch fresh CME data.",
                    "Unavailable fields must not be inferred or fabricated.",
                ]
            ),
            no_signal_reasons=[DATA_CAPABILITY_AUDIT_NO_SIGNAL_REASON],
            research_only=True,
            signal_allowed=False,
        )

    def _audit_vol2vol_sources(
        self,
        request: XauDataCapabilityAuditRequest,
        collector: _CapabilityCollector,
        source_reports: list[XauDataCapabilitySourceSummary],
        limitations: list[str],
    ) -> None:
        audited_count = 0
        for report_id in _selected_ids(
            request.vol2vol_report_ids,
            _latest_report_ids(self.vol2vol_store.report_root(), "report.json"),
            request.max_reports_per_source,
        ):
            try:
                report = self.vol2vol_store.read_report(report_id)
                rows = self.vol2vol_store.read_normalized_rows(report_id)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                limitations.append(f"Vol2Vol report {report_id} could not be audited: {exc}")
                continue

            source_reports.append(
                XauDataCapabilitySourceSummary(
                    source_type=XauDataCapabilitySourceType.VOL2VOL,
                    report_id=report_id,
                    status=_enum_value(report.status),
                    row_count=len(rows),
                    artifact_paths=[artifact.path for artifact in report.artifacts],
                    limitations=[*report.limitations, *report.research_only_warnings],
                )
            )
            audited_count += 1
            collector.add_value_type_rows(
                XauDataCapabilityName.HAS_OI,
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                rows=rows,
                value_type="open_interest",
                field_name="value_type=open_interest",
            )
            collector.add_value_type_rows(
                XauDataCapabilityName.HAS_OI_CHANGE,
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                rows=rows,
                value_type="oi_change",
                field_name="value_type=oi_change",
            )
            collector.add_value_type_rows(
                XauDataCapabilityName.HAS_INTRADAY_VOLUME,
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                rows=rows,
                value_type="intraday_volume",
                field_name="value_type=intraday_volume",
            )
            collector.add_non_null_attrs(
                XauDataCapabilityName.HAS_VOL,
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                rows=rows,
                attrs=["vol_settle"],
            )
            collector.add_non_null_attrs(
                XauDataCapabilityName.HAS_DTE,
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                rows=rows,
                attrs=["dte"],
            )
            collector.add_non_null_attrs(
                XauDataCapabilityName.HAS_FUTURE_REFERENCE,
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                rows=rows,
                attrs=["future_reference_price"],
            )
            collector.add_non_null_attrs(
                XauDataCapabilityName.HAS_SD_RANGES,
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                rows=rows,
                attrs=["range_label", "sigma_label"],
            )
            self._audit_vol2vol_range_bands(report_id, collector)
            if audited_count >= request.max_reports_per_source:
                break

    def _audit_vol2vol_range_bands(
        self,
        report_id: str,
        collector: _CapabilityCollector,
    ) -> None:
        path = self.vol2vol_store.report_dir(report_id) / "range_bands.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        bands = _flatten_values(payload, key_name="cme_numeric_sd")
        if not bands:
            return
        collector.add_manual_evidence(
            XauDataCapabilityName.HAS_NATIVE_SD,
            XauDataCapabilityEvidence(
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                field_names=["range_bands.cme_numeric_sd"],
                row_count=len(bands),
                non_null_count=len([value for value in bands if value is not None]),
                sample_values=_sample_values(bands),
            ),
        )
        collector.add_manual_evidence(
            XauDataCapabilityName.HAS_SD_RANGES,
            XauDataCapabilityEvidence(
                source_type=XauDataCapabilitySourceType.VOL2VOL,
                report_id=report_id,
                field_names=["range_bands"],
                row_count=len(bands),
                non_null_count=len(bands),
                sample_values=_sample_values(bands),
            ),
        )

    def _audit_matrix_sources(
        self,
        request: XauDataCapabilityAuditRequest,
        collector: _CapabilityCollector,
        source_reports: list[XauDataCapabilitySourceSummary],
        limitations: list[str],
    ) -> None:
        audited_count = 0
        for report_id in _selected_ids(
            request.matrix_report_ids,
            _latest_report_ids(self.matrix_store.report_root(), "report.json"),
            request.max_reports_per_source,
        ):
            try:
                report = self.matrix_store.read_report(report_id)
                rows = self.matrix_store.read_normalized_rows(report_id)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                limitations.append(f"Matrix report {report_id} could not be audited: {exc}")
                continue

            source_reports.append(
                XauDataCapabilitySourceSummary(
                    source_type=XauDataCapabilitySourceType.MATRIX,
                    report_id=report_id,
                    status=_enum_value(report.status),
                    row_count=len(rows),
                    artifact_paths=[artifact.path for artifact in report.artifacts],
                    limitations=[*report.limitations, *report.research_only_warnings],
                )
            )
            audited_count += 1
            for capability, value_type in (
                (XauDataCapabilityName.HAS_OI, "open_interest"),
                (XauDataCapabilityName.HAS_OI_CHANGE, "oi_change"),
            ):
                collector.add_value_type_rows(
                    capability,
                    source_type=XauDataCapabilitySourceType.MATRIX,
                    report_id=report_id,
                    rows=rows,
                    value_type=value_type,
                    field_name=f"value_type={value_type}",
                )
            collector.add_value_type_rows(
                XauDataCapabilityName.HAS_INTRADAY_VOLUME,
                source_type=XauDataCapabilitySourceType.MATRIX,
                report_id=report_id,
                rows=rows,
                value_type="volume",
                field_name="value_type=volume",
                status_override=XauDataCapabilityStatus.PARTIAL,
                limitation="Matrix volume is present but is not intraday-volume qualified.",
            )
            collector.add_non_null_attrs(
                XauDataCapabilityName.HAS_DTE,
                source_type=XauDataCapabilitySourceType.MATRIX,
                report_id=report_id,
                rows=rows,
                attrs=["dte"],
            )
            collector.add_non_null_attrs(
                XauDataCapabilityName.HAS_FUTURE_REFERENCE,
                source_type=XauDataCapabilitySourceType.MATRIX,
                report_id=report_id,
                rows=rows,
                attrs=["future_reference_price"],
            )
            if audited_count >= request.max_reports_per_source:
                break

    def _audit_fusion_sources(
        self,
        request: XauDataCapabilityAuditRequest,
        collector: _CapabilityCollector,
        source_reports: list[XauDataCapabilitySourceSummary],
        limitations: list[str],
    ) -> None:
        audited_count = 0
        for report_id in _selected_ids(
            request.fusion_report_ids,
            _latest_report_ids(self.fusion_store.report_root(), "report.json"),
            request.max_reports_per_source,
        ):
            try:
                report = self.fusion_store.read_report(report_id)
                rows = self.fusion_store.read_fused_rows(report_id)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                limitations.append(f"Fusion report {report_id} could not be audited: {exc}")
                continue
            source_reports.append(
                XauDataCapabilitySourceSummary(
                    source_type=XauDataCapabilitySourceType.FUSION,
                    report_id=report_id,
                    status=_enum_value(report.status),
                    row_count=len(rows),
                    artifact_paths=[artifact.path for artifact in report.artifacts],
                    limitations=[*report.limitations, *report.research_only_warnings],
                )
            )
            audited_count += 1
            if report.expected_range_snapshot is not None:
                snapshot = report.expected_range_snapshot
                collector.add_snapshot_values(
                    XauDataCapabilityName.HAS_NATIVE_SD,
                    source_type=XauDataCapabilitySourceType.FUSION,
                    report_id=report_id,
                    values=[
                        snapshot.cme_numeric_1sd,
                        snapshot.cme_numeric_2sd,
                        snapshot.cme_numeric_3sd,
                    ],
                    field_names=[
                        "expected_range_snapshot.cme_numeric_1sd",
                        "expected_range_snapshot.cme_numeric_2sd",
                        "expected_range_snapshot.cme_numeric_3sd",
                    ],
                )
                collector.add_snapshot_values(
                    XauDataCapabilityName.HAS_VOL,
                    source_type=XauDataCapabilitySourceType.FUSION,
                    report_id=report_id,
                    values=[snapshot.vol_settle, snapshot.report_level_iv],
                    field_names=[
                        "expected_range_snapshot.vol_settle",
                        "expected_range_snapshot.report_level_iv",
                    ],
                )
            if audited_count >= request.max_reports_per_source:
                break

    def _audit_xau_vol_oi_sources(
        self,
        request: XauDataCapabilityAuditRequest,
        collector: _CapabilityCollector,
        source_reports: list[XauDataCapabilitySourceSummary],
        limitations: list[str],
    ) -> None:
        audited_count = 0
        for report_id in _selected_ids(
            request.xau_vol_oi_report_ids,
            _latest_report_ids(self.xau_store.xau_dir, "metadata.json"),
            request.max_reports_per_source,
        ):
            try:
                report = self.xau_store.read_report(report_id)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                limitations.append(f"XAU Vol-OI report {report_id} could not be audited: {exc}")
                continue
            rows = list(report.source_validation.rows)
            source_reports.append(
                XauDataCapabilitySourceSummary(
                    source_type=XauDataCapabilitySourceType.XAU_VOL_OI,
                    report_id=report_id,
                    status=_enum_value(report.status),
                    row_count=len(rows) or report.source_row_count,
                    artifact_paths=[artifact.path for artifact in report.artifacts],
                    limitations=report.limitations,
                )
            )
            audited_count += 1
            for capability, attrs in (
                (XauDataCapabilityName.HAS_OI, ["open_interest"]),
                (XauDataCapabilityName.HAS_OI_CHANGE, ["oi_change"]),
                (XauDataCapabilityName.HAS_VOL, ["implied_volatility"]),
                (XauDataCapabilityName.HAS_DTE, ["days_to_expiry"]),
                (XauDataCapabilityName.HAS_FUTURE_REFERENCE, ["underlying_futures_price"]),
                (XauDataCapabilityName.HAS_DELTA, ["delta"]),
                (XauDataCapabilityName.HAS_GAMMA, ["gamma"]),
            ):
                collector.add_non_null_attrs(
                    capability,
                    source_type=XauDataCapabilitySourceType.XAU_VOL_OI,
                    report_id=report_id,
                    rows=rows,
                    attrs=attrs,
                )
            collector.add_non_null_attrs(
                XauDataCapabilityName.HAS_INTRADAY_VOLUME,
                source_type=XauDataCapabilitySourceType.XAU_VOL_OI,
                report_id=report_id,
                rows=rows,
                attrs=["volume"],
                status_override=XauDataCapabilityStatus.PARTIAL,
                limitation="XAU Vol-OI volume is present but is not intraday-volume qualified.",
            )
            if audited_count >= request.max_reports_per_source:
                break

    def _service_for_request_reports_dir(
        self,
        request: XauDataCapabilityAuditRequest,
    ) -> XauDataCapabilityAuditService | None:
        if request.reports_dir is None:
            return None
        normalized = request.reports_dir.resolve()
        if self.reports_dir is not None and normalized == self.reports_dir.resolve():
            return None
        return XauDataCapabilityAuditService(reports_dir=normalized)


class _CapabilityCollector:
    def __init__(self) -> None:
        self._evidence: dict[XauDataCapabilityName, list[XauDataCapabilityEvidence]] = {
            capability: [] for capability in XauDataCapabilityName
        }
        self._manual_status: dict[
            XauDataCapabilityName, tuple[XauDataCapabilityStatus, str]
        ] = {}
        self._limitations: dict[XauDataCapabilityName, list[str]] = {
            capability: [] for capability in XauDataCapabilityName
        }

    def add_value_type_rows(
        self,
        capability: XauDataCapabilityName,
        *,
        source_type: XauDataCapabilitySourceType,
        report_id: str,
        rows: Iterable[Any],
        value_type: str,
        field_name: str,
        status_override: XauDataCapabilityStatus | None = None,
        limitation: str | None = None,
    ) -> None:
        matched = [row for row in rows if str(getattr(row, "value_type", "")) == value_type]
        values = [getattr(row, "value", None) for row in matched]
        self.add_manual_evidence(
            capability,
            XauDataCapabilityEvidence(
                source_type=source_type,
                report_id=report_id,
                field_names=[field_name],
                row_count=len(matched),
                non_null_count=len([value for value in values if value is not None]),
                sample_values=_sample_values(values),
            ),
        )
        if status_override is not None and matched:
            self._manual_status[capability] = (
                status_override,
                limitation or f"{capability.value} is partially available.",
            )

    def add_non_null_attrs(
        self,
        capability: XauDataCapabilityName,
        *,
        source_type: XauDataCapabilitySourceType,
        report_id: str,
        rows: Iterable[Any],
        attrs: list[str],
        status_override: XauDataCapabilityStatus | None = None,
        limitation: str | None = None,
    ) -> None:
        row_list = list(rows)
        values: list[Any] = []
        for row in row_list:
            for attr in attrs:
                values.append(getattr(row, attr, None))
        self.add_manual_evidence(
            capability,
            XauDataCapabilityEvidence(
                source_type=source_type,
                report_id=report_id,
                field_names=attrs,
                row_count=len(row_list),
                non_null_count=len([value for value in values if value is not None]),
                sample_values=_sample_values(values),
            ),
        )
        if status_override is not None and any(value is not None for value in values):
            self._manual_status[capability] = (
                status_override,
                limitation or f"{capability.value} is partially available.",
            )

    def add_snapshot_values(
        self,
        capability: XauDataCapabilityName,
        *,
        source_type: XauDataCapabilitySourceType,
        report_id: str,
        values: list[Any],
        field_names: list[str],
    ) -> None:
        self.add_manual_evidence(
            capability,
            XauDataCapabilityEvidence(
                source_type=source_type,
                report_id=report_id,
                field_names=field_names,
                row_count=1,
                non_null_count=len([value for value in values if value is not None]),
                sample_values=_sample_values(values),
            ),
        )

    def add_manual_evidence(
        self,
        capability: XauDataCapabilityName,
        evidence: XauDataCapabilityEvidence,
    ) -> None:
        self._evidence[capability].append(evidence)

    def set_manual_status(
        self,
        capability: XauDataCapabilityName,
        status: XauDataCapabilityStatus,
        limitation: str,
    ) -> None:
        self._manual_status[capability] = (status, limitation)

    def results(self) -> list[XauDataCapabilityResult]:
        results: list[XauDataCapabilityResult] = []
        for capability in XauDataCapabilityName:
            evidence = self._evidence[capability]
            row_count = sum(item.row_count for item in evidence)
            non_null_count = sum(item.non_null_count for item in evidence)
            if capability in self._manual_status:
                status, manual_limitation = self._manual_status[capability]
                limitations = [manual_limitation]
            elif non_null_count > 0:
                status = XauDataCapabilityStatus.AVAILABLE
                limitations = []
            else:
                status = XauDataCapabilityStatus.UNAVAILABLE
                limitations = [_default_unavailable_reason(capability)]
            results.append(
                XauDataCapabilityResult(
                    capability=capability,
                    status=status,
                    source_count=len({item.report_id for item in evidence if item.row_count}),
                    row_count=row_count,
                    non_null_count=non_null_count,
                    evidence=evidence,
                    limitations=_dedupe([*limitations, *self._limitations[capability]]),
                )
            )
        return results


def _selected_ids(
    requested_ids: list[str] | None,
    available_ids: list[str],
    max_reports: int,
) -> list[str]:
    if requested_ids is not None:
        return requested_ids[:max_reports]
    return available_ids[: max_reports * 20]


def _latest_report_ids(root: Path, artifact_name: str) -> list[str]:
    if not root.exists():
        return []
    return sorted(
        [path.parent.name for path in root.glob(f"*/{artifact_name}")],
        reverse=True,
    )


def _is_available(result: XauDataCapabilityResult) -> bool:
    return result.status in {
        XauDataCapabilityStatus.AVAILABLE,
        XauDataCapabilityStatus.PARTIAL,
    }


def _readiness(
    source_reports: list[XauDataCapabilitySourceSummary],
    missing: list[XauDataCapabilityName],
    blocked: list[XauDataCapabilityName],
) -> XauDataCapabilityAuditReadiness:
    if not source_reports:
        return XauDataCapabilityAuditReadiness.BLOCKED
    if missing or blocked:
        return XauDataCapabilityAuditReadiness.PARTIAL
    return XauDataCapabilityAuditReadiness.COMPLETE


def _default_unavailable_reason(capability: XauDataCapabilityName) -> str:
    reasons = {
        XauDataCapabilityName.HAS_VOL_CHG: "No audited artifact exposes Vol Chg.",
        XauDataCapabilityName.HAS_FUTURE_CHG: "No audited artifact exposes Future Chg.",
        XauDataCapabilityName.HAS_DELTA_RANGES: "No audited artifact exposes delta ranges.",
        XauDataCapabilityName.HAS_GEX_POSSIBLE: "GEX requires gamma and open interest.",
    }
    return reasons.get(capability, f"No audited artifact exposes {capability.value}.")


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _sample_values(values: Iterable[Any]) -> list[str]:
    samples: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text not in samples:
            samples.append(text)
        if len(samples) >= 3:
            break
    return samples


def _flatten_values(payload: Any, *, key_name: str) -> list[Any]:
    values: list[Any] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == key_name:
                values.append(value)
            else:
                values.extend(_flatten_values(value, key_name=key_name))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_flatten_values(item, key_name=key_name))
    return values


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


__all__ = ["XauDataCapabilityAuditService"]
