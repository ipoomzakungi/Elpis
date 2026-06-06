from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from src.models.xau import XauDailyStructuralMap, XauDailyStructuralMapReadiness
from src.models.xau_daily_structural_map import XauDailyStructuralMapReportMetadata
from src.models.xau_daily_workbench import (
    XauDailyWorkbenchCandidateMetadata,
    XauDailyWorkbenchCandidateResponse,
    XauDailyWorkbenchCmeSource,
    XauDailyWorkbenchLatestResponse,
    XauDailyWorkbenchMapResponse,
    XauDailyWorkbenchReadiness,
    XauDailyWorkbenchRunRequest,
    XauDailyWorkbenchRunResult,
    research_only_no_signal_reasons,
)
from src.models.xau_sd_oi_candidate import XauSdOiCandidateSet, XauSdOiReadinessState
from src.xau_daily_structural_map.bundle_adapter import (
    generate_xau_daily_structural_map_from_bundle,
)
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_daily_structural_map.sample_run import stable_xau_daily_structural_map_id
from src.xau_daily_workbench.report_store import XauDailyWorkbenchReportStore
from src.xau_sd_oi_candidate.classifier import (
    BASIS_MISSING_REASON_CODE,
    SESSION_OPEN_MISSING_REASON_CODE,
    TRADED_PRICE_MISSING_REASON_CODE,
    build_xau_sd_oi_candidate_set,
)

REPORT_JSON_FILENAME = "04_xau_vol_oi_report_report.json"
WALLS_PARQUET_FILENAME = "04_xau_vol_oi_report_walls.parquet"
FUSED_ROWS_FILENAME = "03_xau_quikstrike_fusion_fused_rows.json"


class CmeDataSource(Protocol):
    def load_map(self, request: XauDailyWorkbenchRunRequest) -> WorkbenchMapLoadResult:
        """Load or create one structural map for the workbench request."""


class FuturesPriceProvider(Protocol):
    def gc_reference_price(self, request: XauDailyWorkbenchRunRequest) -> float | None:
        """Return a GC/futures reference price for research basis calculation."""


class TradedPriceProvider(Protocol):
    def traded_reference_price(self, request: XauDailyWorkbenchRunRequest) -> float | None:
        """Return the traded chart reference price for research classification."""


class SessionOpenProvider(Protocol):
    def session_open_price(self, request: XauDailyWorkbenchRunRequest) -> float | None:
        """Return the session open reference price for research context."""


@dataclass(frozen=True)
class WorkbenchMapLoadResult:
    daily_map: XauDailyStructuralMap | None
    metadata: XauDailyStructuralMapReportMetadata | None
    artifact_paths: dict[str, str]
    missing_inputs: list[str]
    no_signal_reasons: list[str]


class StaticFixturePriceProvider:
    """Uses caller-supplied price fields; no network or live market access."""

    def gc_reference_price(self, request: XauDailyWorkbenchRunRequest) -> float | None:
        return request.gc_reference_price

    def traded_reference_price(self, request: XauDailyWorkbenchRunRequest) -> float | None:
        return request.traded_reference_price

    def session_open_price(self, request: XauDailyWorkbenchRunRequest) -> float | None:
        return request.session_open_price


class LocalBundleSource:
    def __init__(self, map_store: XauDailyStructuralMapReportStore) -> None:
        self.map_store = map_store

    def load_map(self, request: XauDailyWorkbenchRunRequest) -> WorkbenchMapLoadResult:
        missing_inputs: list[str] = []
        if request.input_dir is None:
            missing_inputs.append("input_dir")
        if request.session_date is None:
            missing_inputs.append("session_date")
        if request.expiration_code is None:
            missing_inputs.append("expiration_code")
        if missing_inputs:
            return _blocked_map_result(
                missing_inputs,
                "Local bundle source requires input_dir, session_date, and expiration_code.",
            )

        input_dir = request.input_dir.resolve()
        if not input_dir.exists():
            return _blocked_map_result(
                ["input_dir"],
                f"Local bundle input directory was not found: {input_dir}",
            )
        if not input_dir.is_dir():
            return _blocked_map_result(
                ["input_dir"],
                f"Local bundle input path is not a directory: {input_dir}",
            )

        report_path = input_dir / REPORT_JSON_FILENAME
        if not report_path.exists():
            return _blocked_map_result(
                [REPORT_JSON_FILENAME],
                f"Missing required XAU Vol-OI report JSON: {report_path}",
            )

        map_id = request.map_id or stable_xau_daily_structural_map_id(
            session_date=request.session_date,
            expiration_code=request.expiration_code,
        )
        result = generate_xau_daily_structural_map_from_bundle(
            map_id=map_id,
            session_date=request.session_date,
            xau_vol_oi_report_path=report_path,
            walls_path=_optional_path(input_dir / WALLS_PARQUET_FILENAME),
            fused_rows_path=_optional_path(input_dir / FUSED_ROWS_FILENAME),
            traded_instrument=request.traded_instrument,
            traded_reference_price=request.traded_reference_price,
            gc_reference_price=request.gc_reference_price,
            manual_basis=request.manual_basis,
            session_open_price=request.session_open_price,
            session_open_source=request.session_open_source,
            output_root=self.map_store.reports_dir,
            overwrite_allowed=request.overwrite_allowed,
        )
        return WorkbenchMapLoadResult(
            daily_map=result.daily_map,
            metadata=result.metadata,
            artifact_paths={
                artifact.artifact_type.value: artifact.path
                for artifact in result.artifacts
            },
            missing_inputs=[],
            no_signal_reasons=result.daily_map.no_signal_reasons,
        )


class LatestExistingXauArtifactSource:
    def __init__(self, map_store: XauDailyStructuralMapReportStore) -> None:
        self.map_store = map_store

    def load_map(self, request: XauDailyWorkbenchRunRequest) -> WorkbenchMapLoadResult:
        latest = _latest_existing_map(self.map_store, request)
        if latest is None:
            missing = ["xau_daily_structural_map"]
            return _blocked_map_result(
                missing,
                "No existing XAU daily structural map matched the requested filters.",
            )
        daily_map, metadata = latest
        return WorkbenchMapLoadResult(
            daily_map=daily_map,
            metadata=metadata,
            artifact_paths={
                artifact.artifact_type.value: artifact.path
                for artifact in metadata.artifacts
            },
            missing_inputs=[],
            no_signal_reasons=daily_map.no_signal_reasons,
        )


class ApiOnlyCmeSource:
    def load_map(self, request: XauDailyWorkbenchRunRequest) -> WorkbenchMapLoadResult:
        return _blocked_map_result(
            ["cme_source.api_only"],
            "API-only CME source is not configured for this local workbench slice.",
        )


class XauDailyWorkbenchService:
    def __init__(self, reports_dir: Path | None = None) -> None:
        normalized = _normalize_output_root(reports_dir)
        self.map_store = XauDailyStructuralMapReportStore(reports_dir=normalized)
        self.workbench_store = XauDailyWorkbenchReportStore(reports_dir=normalized)
        self.price_provider = StaticFixturePriceProvider()

    def run(self, request: XauDailyWorkbenchRunRequest) -> XauDailyWorkbenchRunResult:
        redirected_service = self._service_for_request_output_root(request)
        if redirected_service is not None:
            redirected_request = request.model_copy(update={"output_root": None})
            return redirected_service.run(redirected_request)

        created_at = datetime.now(UTC)
        source = self._source_for(request.cme_source)
        try:
            map_load = source.load_map(request)
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            map_load = _blocked_map_result(["cme_source"], str(exc))

        daily_map = map_load.daily_map
        candidate_set: XauSdOiCandidateSet | None = None
        candidate_metadata: XauDailyWorkbenchCandidateMetadata | None = None
        candidate_set_id: str | None = None
        artifact_paths = dict(map_load.artifact_paths)
        missing_inputs = list(map_load.missing_inputs)
        no_signal_reasons = research_only_no_signal_reasons(*map_load.no_signal_reasons)

        if daily_map is not None and request.run_candidates:
            candidate_set = self._build_candidates(daily_map, request, created_at)
            candidate_set_id = _candidate_set_id(daily_map.map_id, candidate_set.timestamp)
            missing_inputs = _dedupe(
                [
                    *missing_inputs,
                    *_missing_inputs_from_candidate_set(candidate_set),
                ]
            )
            no_signal_reasons = research_only_no_signal_reasons(
                *no_signal_reasons,
                *candidate_set.no_signal_reasons,
                *_candidate_reason_messages(candidate_set),
            )
            readiness = _readiness_from_map_and_candidates(daily_map, candidate_set)
            candidate_metadata = XauDailyWorkbenchCandidateMetadata(
                candidate_set_id=candidate_set_id,
                map_id=daily_map.map_id,
                created_at=created_at,
                candidate_count=candidate_set.candidate_count,
                readiness=readiness,
                missing_inputs=missing_inputs,
                no_signal_reasons=no_signal_reasons,
                research_only=True,
                signal_allowed=False,
            )
            artifact_paths.update(
                self._persist_candidate_artifacts(
                    daily_map.map_id,
                    candidate_set,
                    candidate_metadata,
                )
            )
        else:
            readiness = _readiness_from_map(daily_map, missing_inputs)

        run_session_date = request.session_date or (
            daily_map.session_date if daily_map else None
        )
        run_expiration_code = request.expiration_code or (
            daily_map.expiration_code if daily_map else None
        )
        run_result = XauDailyWorkbenchRunResult(
            run_id=_workbench_run_id(
                created_at=created_at,
                session_date=run_session_date,
                expiration_code=run_expiration_code,
            ),
            created_at=created_at,
            cme_source=request.cme_source,
            traded_instrument=request.traded_instrument,
            session_date=run_session_date,
            expiration_code=run_expiration_code,
            map_id=daily_map.map_id if daily_map else None,
            candidate_set_id=candidate_set_id,
            readiness=readiness,
            missing_inputs=missing_inputs,
            no_signal_reasons=no_signal_reasons,
            artifact_paths=artifact_paths,
            map_metadata=map_load.metadata,
            daily_map=daily_map,
            candidate_set=candidate_set,
            candidate_metadata=candidate_metadata,
            research_only=True,
            signal_allowed=False,
        )
        return self.workbench_store.persist_result(
            run_result,
            overwrite_allowed=request.overwrite_allowed,
        )

    def latest(self) -> XauDailyWorkbenchLatestResponse:
        latest = self.workbench_store.latest_result()
        if latest is None:
            return XauDailyWorkbenchLatestResponse(
                readiness=XauDailyWorkbenchReadiness.BLOCKED,
                missing_inputs=["xau_daily_workbench_run"],
                no_signal_reasons=research_only_no_signal_reasons(
                    "No XAU daily workbench run artifacts exist."
                ),
                artifact_paths={},
                latest_run=None,
                research_only=True,
                signal_allowed=False,
            )
        return XauDailyWorkbenchLatestResponse(
            readiness=latest.readiness,
            missing_inputs=latest.missing_inputs,
            no_signal_reasons=latest.no_signal_reasons,
            artifact_paths=latest.artifact_paths,
            latest_run=latest,
            research_only=True,
            signal_allowed=False,
        )

    def read_map(self, map_id: str) -> XauDailyWorkbenchMapResponse:
        daily_map = self.map_store.read_map(map_id)
        metadata = self.map_store.read_metadata(map_id)
        return XauDailyWorkbenchMapResponse(
            map_id=map_id,
            readiness=_readiness_from_map(daily_map, []),
            missing_inputs=_missing_inputs_from_map(daily_map),
            no_signal_reasons=research_only_no_signal_reasons(*daily_map.no_signal_reasons),
            artifact_paths={
                artifact.artifact_type.value: artifact.path
                for artifact in metadata.artifacts
            },
            map_metadata=metadata,
            daily_map=daily_map,
            research_only=True,
            signal_allowed=False,
        )

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

    def _source_for(self, cme_source: XauDailyWorkbenchCmeSource) -> CmeDataSource:
        if cme_source == XauDailyWorkbenchCmeSource.LOCAL_BUNDLE:
            return LocalBundleSource(self.map_store)
        if cme_source == XauDailyWorkbenchCmeSource.API_ONLY:
            return ApiOnlyCmeSource()
        return LatestExistingXauArtifactSource(self.map_store)

    def _build_candidates(
        self,
        daily_map: XauDailyStructuralMap,
        request: XauDailyWorkbenchRunRequest,
        created_at: datetime,
    ) -> XauSdOiCandidateSet:
        traded_price = (
            self.price_provider.traded_reference_price(request)
            or daily_map.traded_reference_price
        )
        gc_price = (
            self.price_provider.gc_reference_price(request)
            or daily_map.reference_futures_price
        )
        return build_xau_sd_oi_candidate_set(
            daily_map,
            timestamp=created_at,
            traded_price=traded_price,
            gc_price=gc_price,
            confirmation_state="unavailable",
            iv_state="unavailable",
            flow_state="unavailable",
        )

    def _persist_candidate_artifacts(
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

    def _service_for_request_output_root(
        self,
        request: XauDailyWorkbenchRunRequest,
    ) -> XauDailyWorkbenchService | None:
        if request.output_root is None:
            return None
        normalized = _normalize_output_root(request.output_root)
        if normalized is None:
            return None
        if normalized.resolve() == self.map_store.reports_dir.resolve():
            return None
        return XauDailyWorkbenchService(reports_dir=normalized)


def run_xau_daily_research_workbench(
    request: XauDailyWorkbenchRunRequest | None = None,
    *,
    session_date: date | None = None,
    expiration_code: str | None = None,
    traded_instrument: str = "XAUUSD",
    cme_source: XauDailyWorkbenchCmeSource | str = XauDailyWorkbenchCmeSource.LATEST_EXISTING,
    input_dir: Path | None = None,
    gc_reference_price: float | None = None,
    traded_reference_price: float | None = None,
    session_open_price: float | None = None,
    output_root: Path | None = None,
    run_candidates: bool = True,
) -> XauDailyWorkbenchRunResult:
    resolved_request = request or XauDailyWorkbenchRunRequest(
        session_date=session_date,
        expiration_code=expiration_code,
        traded_instrument=traded_instrument,
        cme_source=XauDailyWorkbenchCmeSource(str(cme_source)),
        input_dir=input_dir,
        gc_reference_price=gc_reference_price,
        traded_reference_price=traded_reference_price,
        session_open_price=session_open_price,
        output_root=output_root,
        run_candidates=run_candidates,
        research_only_acknowledged=True,
    )
    return XauDailyWorkbenchService(
        reports_dir=_normalize_output_root(resolved_request.output_root)
    ).run(resolved_request)


def _latest_existing_map(
    map_store: XauDailyStructuralMapReportStore,
    request: XauDailyWorkbenchRunRequest,
) -> tuple[XauDailyStructuralMap, XauDailyStructuralMapReportMetadata] | None:
    root = map_store.report_root()
    if not root.exists():
        return None
    matches: list[tuple[XauDailyStructuralMap, XauDailyStructuralMapReportMetadata]] = []
    for metadata_path in root.glob("*/metadata.json"):
        map_id = metadata_path.parent.name
        try:
            daily_map = map_store.read_map(map_id)
            metadata = map_store.read_metadata(map_id)
        except (OSError, ValueError):
            continue
        if request.session_date is not None and daily_map.session_date != request.session_date:
            continue
        if (
            request.expiration_code is not None
            and daily_map.expiration_code != request.expiration_code
        ):
            continue
        if (
            request.traded_instrument
            and daily_map.traded_instrument.lower() != request.traded_instrument.lower()
        ):
            continue
        matches.append((daily_map, metadata))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0].created_at)


def _blocked_map_result(
    missing_inputs: list[str],
    reason: str,
) -> WorkbenchMapLoadResult:
    return WorkbenchMapLoadResult(
        daily_map=None,
        metadata=None,
        artifact_paths={},
        missing_inputs=missing_inputs,
        no_signal_reasons=[reason],
    )


def _readiness_from_map_and_candidates(
    daily_map: XauDailyStructuralMap,
    candidate_set: XauSdOiCandidateSet,
) -> XauDailyWorkbenchReadiness:
    if any(
        candidate.readiness_state == XauSdOiReadinessState.BLOCKED_MISSING_CONTEXT
        for candidate in candidate_set.candidates
    ):
        return XauDailyWorkbenchReadiness.BLOCKED
    return _readiness_from_map(daily_map, [])


def _readiness_from_map(
    daily_map: XauDailyStructuralMap | None,
    missing_inputs: list[str],
) -> XauDailyWorkbenchReadiness:
    if daily_map is None or missing_inputs:
        return XauDailyWorkbenchReadiness.BLOCKED
    if daily_map.data_quality_state == XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY:
        return XauDailyWorkbenchReadiness.COMPLETED
    if daily_map.data_quality_state == XauDailyStructuralMapReadiness.BLOCKED_INSUFFICIENT_CONTEXT:
        return XauDailyWorkbenchReadiness.BLOCKED
    return XauDailyWorkbenchReadiness.PARTIAL


def _missing_inputs_from_candidate_set(candidate_set: XauSdOiCandidateSet) -> list[str]:
    reason_codes = {
        reason.reason_code
        for candidate in candidate_set.candidates
        for reason in candidate.reasons
    }
    missing: list[str] = []
    if BASIS_MISSING_REASON_CODE in reason_codes:
        missing.append("basis")
    if SESSION_OPEN_MISSING_REASON_CODE in reason_codes:
        missing.append("session_open_price")
    if TRADED_PRICE_MISSING_REASON_CODE in reason_codes:
        missing.append("traded_reference_price")
    return missing


def _missing_inputs_from_map(daily_map: XauDailyStructuralMap) -> list[str]:
    missing: list[str] = []
    if not daily_map.basis_mapping_available:
        missing.append("basis")
    if not daily_map.session_open_available:
        missing.append("session_open_price")
    if daily_map.expected_range_source is None:
        missing.append("expected_range")
    return missing


def _candidate_reason_messages(candidate_set: XauSdOiCandidateSet) -> list[str]:
    return [
        reason.message
        for candidate in candidate_set.candidates
        for reason in candidate.reasons
    ]


def _candidate_set_id(map_id: str, timestamp: datetime) -> str:
    return f"{map_id}_{timestamp.strftime('%Y%m%dT%H%M%S')}_candidates"


def _workbench_run_id(
    *,
    created_at: datetime,
    session_date: date | None,
    expiration_code: str | None,
) -> str:
    session = session_date.isoformat() if session_date else "unknown_date"
    expiration = expiration_code or "unknown_expiry"
    return (
        f"xau_daily_workbench_{_safe_id_part(session)}_"
        f"{_safe_id_part(expiration)}_{created_at.strftime('%Y%m%dT%H%M%S%f')}"
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
        f"- Map id: `{metadata.map_id}`",
        f"- Readiness: `{metadata.readiness.value}`",
        f"- Signal allowed: `{metadata.signal_allowed}`",
        f"- Candidate count: `{metadata.candidate_count}`",
        "",
        "## Missing Inputs",
    ]
    if metadata.missing_inputs:
        lines.extend(f"- {item}" for item in metadata.missing_inputs)
    else:
        lines.append("- None.")
    lines.extend(["", "## No-Signal Reasons"])
    lines.extend(f"- {reason}" for reason in metadata.no_signal_reasons)
    lines.extend(["", "## Candidates"])
    for candidate in candidate_set.candidates:
        reason_text = "; ".join(reason.reason_code for reason in candidate.reasons)
        lines.append(
            f"- {candidate.candidate_id}: `{candidate.side.value}`, "
            f"`{candidate.readiness_state.value}`, reasons `{reason_text}`"
        )
    return "\n".join(lines) + "\n"


def _optional_path(path: Path) -> Path | None:
    return path if path.exists() else None


def _normalize_output_root(output_root: Path | None) -> Path | None:
    if output_root is None:
        return None
    resolved = output_root.resolve()
    if resolved.name in {"xau_daily_structural_map", "xau_daily_workbench"}:
        return resolved.parent
    return resolved


def _safe_id_part(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "_-" else "_"
        for character in value
    )
    return safe.strip("_") or "unknown"


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        if normalized and normalized not in seen:
            output.append(normalized)
            seen.add(normalized)
    return output


def _jsonable(payload: object) -> object:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, Mapping):
        return {key: _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, tuple):
        return [_jsonable(value) for value in payload]
    return payload


__all__ = [
    "ApiOnlyCmeSource",
    "CmeDataSource",
    "FuturesPriceProvider",
    "LatestExistingXauArtifactSource",
    "LocalBundleSource",
    "SessionOpenProvider",
    "StaticFixturePriceProvider",
    "TradedPriceProvider",
    "XauDailyWorkbenchService",
    "run_xau_daily_research_workbench",
]
