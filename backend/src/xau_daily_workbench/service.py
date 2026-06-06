from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from src.models.xau import XauDailyStructuralMap, XauDailyStructuralMapReadiness
from src.models.xau_daily_workbench import (
    XauDailyWorkbenchCandidateMetadata,
    XauDailyWorkbenchCandidateResponse,
    XauDailyWorkbenchCmeSource,
    XauDailyWorkbenchLatestResponse,
    XauDailyWorkbenchMapResponse,
    XauDailyWorkbenchMissingInput,
    XauDailyWorkbenchMissingInputSeverity,
    XauDailyWorkbenchProviderStatus,
    XauDailyWorkbenchProviderType,
    XauDailyWorkbenchReadiness,
    XauDailyWorkbenchRunRequest,
    XauDailyWorkbenchRunResult,
    XauDailyWorkbenchSourceQuality,
    missing_input,
    provider_status,
    research_only_no_signal_reasons,
)
from src.models.xau_sd_oi_candidate import XauSdOiCandidateSet, XauSdOiReadinessState
from src.xau_daily_structural_map.report_store import XauDailyStructuralMapReportStore
from src.xau_daily_workbench.basis import build_workbench_basis_snapshot
from src.xau_daily_workbench.candidate_store import XauDailyWorkbenchCandidateStore
from src.xau_daily_workbench.providers import (
    FUSED_ROWS_FILENAME,
    REPORT_JSON_FILENAME,
    WALLS_PARQUET_FILENAME,
    ApiOnlyCmeSource,
    CmeDataSource,
    CmeDataSourceResult,
    FixtureCmeDataSource,
    FuturesPriceProvider,
    LatestExistingXauArtifactSource,
    LocalBundleCmeDataSource,
    ManualPriceProvider,
    PriceResult,
    SessionOpenProvider,
    StaticFixturePriceProvider,
    TradedPriceProvider,
    YahooResearchPriceProvider,
)
from src.xau_daily_workbench.report_store import XauDailyWorkbenchReportStore
from src.xau_sd_oi_candidate.classifier import (
    BASIS_MISSING_REASON_CODE,
    SESSION_OPEN_MISSING_REASON_CODE,
    TRADED_PRICE_MISSING_REASON_CODE,
    build_xau_sd_oi_candidate_set,
)


class XauDailyWorkbenchService:
    def __init__(
        self,
        reports_dir: Path | None = None,
        *,
        cme_source: CmeDataSource | None = None,
        futures_price_provider: FuturesPriceProvider | None = None,
        traded_price_provider: TradedPriceProvider | None = None,
        session_open_provider: SessionOpenProvider | None = None,
    ) -> None:
        normalized = _normalize_output_root(reports_dir)
        self.map_store = XauDailyStructuralMapReportStore(reports_dir=normalized)
        self.workbench_store = XauDailyWorkbenchReportStore(reports_dir=normalized)
        self.candidate_store = XauDailyWorkbenchCandidateStore(
            map_store=self.map_store,
            workbench_store=self.workbench_store,
        )
        self._cme_source_override = cme_source
        self._futures_price_provider = futures_price_provider
        self._traded_price_provider = traded_price_provider
        self._session_open_provider = session_open_provider

    def run(
        self,
        request: XauDailyWorkbenchRunRequest,
        *,
        cme_source: CmeDataSource | None = None,
        futures_price_provider: FuturesPriceProvider | None = None,
        traded_price_provider: TradedPriceProvider | None = None,
        session_open_provider: SessionOpenProvider | None = None,
    ) -> XauDailyWorkbenchRunResult:
        redirected_service = self._service_for_request_output_root(request)
        if redirected_service is not None:
            redirected_request = request.model_copy(update={"output_root": None})
            return redirected_service.run(
                redirected_request,
                cme_source=cme_source,
                futures_price_provider=futures_price_provider,
                traded_price_provider=traded_price_provider,
                session_open_provider=session_open_provider,
            )

        created_at = datetime.now(UTC)
        price_context = self._resolve_price_context(
            request,
            timestamp=created_at,
            futures_price_provider=futures_price_provider,
            traded_price_provider=traded_price_provider,
            session_open_provider=session_open_provider,
        )
        resolved_request = request.model_copy(
            update={
                "gc_reference_price": price_context.gc_reference_price,
                "traded_reference_price": price_context.traded_reference_price,
                "session_open_price": price_context.session_open_price,
            }
        )
        basis_snapshot, basis_status, basis_missing, basis_no_signal = (
            build_workbench_basis_snapshot(resolved_request, timestamp=created_at)
        )
        source = cme_source or self._cme_source_override or self._source_for(
            resolved_request.cme_source
        )
        try:
            map_load = source.load_or_fetch_bundle(resolved_request)
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            map_load = _blocked_source_result(str(exc))

        daily_map = map_load.daily_map
        candidate_set: XauSdOiCandidateSet | None = None
        candidate_metadata: XauDailyWorkbenchCandidateMetadata | None = None
        candidate_set_id: str | None = None
        map_artifact_paths = dict(map_load.artifact_paths)
        candidate_artifact_paths: dict[str, str] = {}
        provider_statuses = _dedupe_statuses(
            [
                *price_context.provider_statuses,
                basis_status,
                map_load.provider_status,
            ]
        )
        missing_inputs: list[XauDailyWorkbenchMissingInput] = _dedupe_missing_inputs(
            [*map_load.missing_inputs]
        )
        no_signal_reasons = research_only_no_signal_reasons(
            *map_load.no_signal_reasons,
            *basis_no_signal,
        )
        limitations = _dedupe([*map_load.limitations, *basis_snapshot.limitations])

        if daily_map is not None and resolved_request.run_candidates:
            candidate_set = self._build_candidates(daily_map, resolved_request, created_at)
            candidate_set_id = _candidate_set_id(daily_map.map_id, candidate_set.timestamp)
            candidate_missing = _missing_inputs_from_candidate_set(candidate_set)
            missing_inputs = _dedupe_missing_inputs(
                [
                    *missing_inputs,
                    *candidate_missing,
                    *(
                        basis_missing
                        if any(item.input_name == "basis" for item in candidate_missing)
                        else []
                    ),
                ]
            )
            no_signal_reasons = research_only_no_signal_reasons(
                *no_signal_reasons,
                *candidate_set.no_signal_reasons,
                *_candidate_reason_messages(candidate_set),
            )
            readiness = _readiness_from_map_and_candidates(
                daily_map,
                candidate_set,
                missing_inputs,
            )
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
            candidate_artifact_paths = self.candidate_store.persist_candidate_set(
                daily_map.map_id,
                candidate_set,
                candidate_metadata,
            )
            provider_statuses.append(
                provider_status(
                    provider_name="XauDailyWorkbenchCandidateStore",
                    provider_type=XauDailyWorkbenchProviderType.CANDIDATE_STORE,
                    status=(
                        provider_status_state_available()
                    ),
                    source_quality=XauDailyWorkbenchSourceQuality.LOCAL_BUNDLE,
                    message="Candidate sidecar artifacts persisted.",
                    limitations=["Candidate artifacts are local research artifacts only."],
                )
            )
        else:
            readiness = _readiness_from_map(daily_map, missing_inputs)

        run_session_date = resolved_request.session_date or (
            daily_map.session_date if daily_map else None
        )
        run_expiration_code = resolved_request.expiration_code or (
            daily_map.expiration_code if daily_map else None
        )
        artifact_paths = {
            **map_artifact_paths,
            **candidate_artifact_paths,
        }
        run_result = XauDailyWorkbenchRunResult(
            run_id=_workbench_run_id(
                created_at=created_at,
                session_date=run_session_date,
                expiration_code=run_expiration_code,
            ),
            created_at=created_at,
            cme_source=resolved_request.cme_source,
            traded_instrument=resolved_request.traded_instrument,
            session_date=run_session_date,
            expiration_code=run_expiration_code,
            map_id=daily_map.map_id if daily_map else None,
            candidate_set_id=candidate_set_id,
            readiness=readiness,
            map_artifact_paths=map_artifact_paths,
            candidate_artifact_paths=candidate_artifact_paths,
            missing_inputs=missing_inputs,
            provider_statuses=provider_statuses,
            no_signal_reasons=no_signal_reasons,
            limitations=limitations,
            artifact_paths=artifact_paths,
            basis_snapshot=basis_snapshot,
            map_metadata=map_load.metadata,
            daily_map=daily_map,
            candidate_set=candidate_set,
            candidate_metadata=candidate_metadata,
            research_only=True,
            signal_allowed=False,
        )
        return self.workbench_store.persist_result(
            run_result,
            overwrite_allowed=resolved_request.overwrite_allowed,
        )

    def latest(self) -> XauDailyWorkbenchLatestResponse:
        latest = self.workbench_store.latest_result()
        available_runs = [result.run_id for result in self.workbench_store.list_results()]
        if latest is None:
            return XauDailyWorkbenchLatestResponse(
                readiness=XauDailyWorkbenchReadiness.BLOCKED,
                missing_inputs=[
                    missing_input(
                        "xau_daily_workbench_run",
                        "No XAU daily workbench run artifacts exist.",
                    )
                ],
                no_signal_reasons=research_only_no_signal_reasons(
                    "No XAU daily workbench run artifacts exist."
                ),
                artifact_paths={},
                latest_run=None,
                available_runs=[],
                message="No XAU daily workbench runs have been persisted yet.",
                research_only=True,
                signal_allowed=False,
            )
        return XauDailyWorkbenchLatestResponse(
            readiness=latest.readiness,
            missing_inputs=latest.missing_inputs,
            no_signal_reasons=latest.no_signal_reasons,
            artifact_paths=latest.artifact_paths,
            latest_run=latest,
            available_runs=available_runs,
            message="Latest XAU daily workbench run loaded.",
            research_only=True,
            signal_allowed=False,
        )

    def read_run(self, run_id: str) -> XauDailyWorkbenchRunResult:
        return self.workbench_store.read_result(run_id)

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
        return self.candidate_store.read_candidates(map_id)

    def _source_for(self, cme_source: XauDailyWorkbenchCmeSource) -> CmeDataSource:
        if cme_source == XauDailyWorkbenchCmeSource.LOCAL_BUNDLE:
            return LocalBundleCmeDataSource(self.map_store)
        if cme_source == XauDailyWorkbenchCmeSource.API_ONLY:
            return ApiOnlyCmeSource()
        if cme_source == XauDailyWorkbenchCmeSource.FIXTURE:
            return FixtureCmeDataSource(self.map_store)
        return LatestExistingXauArtifactSource(self.map_store)

    def _resolve_price_context(
        self,
        request: XauDailyWorkbenchRunRequest,
        *,
        timestamp: datetime,
        futures_price_provider: FuturesPriceProvider | None,
        traded_price_provider: TradedPriceProvider | None,
        session_open_provider: SessionOpenProvider | None,
    ) -> _ResolvedPriceContext:
        manual_provider = ManualPriceProvider(request)
        gc_result = _first_available_price_result(
            manual_provider.get_gc_reference_price(request.session_date, timestamp),
            (
                futures_price_provider or self._futures_price_provider
            ).get_gc_reference_price(request.session_date, timestamp)
            if futures_price_provider or self._futures_price_provider
            else None,
        )
        traded_result = _first_available_price_result(
            manual_provider.get_traded_reference_price(
                request.traded_instrument,
                request.session_date,
                timestamp,
            ),
            (
                traded_price_provider or self._traded_price_provider
            ).get_traded_reference_price(
                request.traded_instrument,
                request.session_date,
                timestamp,
            )
            if traded_price_provider or self._traded_price_provider
            else None,
        )
        open_result = _first_available_price_result(
            manual_provider.get_session_open_price(
                request.traded_instrument,
                request.session_date,
            ),
            (
                session_open_provider or self._session_open_provider
            ).get_session_open_price(
                request.traded_instrument,
                request.session_date,
            )
            if session_open_provider or self._session_open_provider
            else None,
        )
        return _ResolvedPriceContext(
            gc_reference_price=gc_result.price,
            traded_reference_price=traded_result.price,
            session_open_price=open_result.price,
            provider_statuses=[
                gc_result.provider_status,
                traded_result.provider_status,
                open_result.provider_status,
            ],
        )

    def _build_candidates(
        self,
        daily_map: XauDailyStructuralMap,
        request: XauDailyWorkbenchRunRequest,
        created_at: datetime,
    ) -> XauSdOiCandidateSet:
        traded_price = request.traded_reference_price or daily_map.traded_reference_price
        gc_price = request.gc_reference_price or daily_map.reference_futures_price
        return build_xau_sd_oi_candidate_set(
            daily_map,
            timestamp=created_at,
            traded_price=traded_price,
            gc_price=gc_price,
            confirmation_state=request.confirmation_state,
            iv_state=request.iv_state,
            flow_state=request.flow_state,
        )

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
        return XauDailyWorkbenchService(
            reports_dir=normalized,
            cme_source=self._cme_source_override,
            futures_price_provider=self._futures_price_provider,
            traded_price_provider=self._traded_price_provider,
            session_open_provider=self._session_open_provider,
        )


class _ResolvedPriceContext:
    def __init__(
        self,
        *,
        gc_reference_price: float | None,
        traded_reference_price: float | None,
        session_open_price: float | None,
        provider_statuses: list[XauDailyWorkbenchProviderStatus],
    ) -> None:
        self.gc_reference_price = gc_reference_price
        self.traded_reference_price = traded_reference_price
        self.session_open_price = session_open_price
        self.provider_statuses = provider_statuses


def run_xau_daily_research_workbench(
    request: XauDailyWorkbenchRunRequest | None = None,
    *,
    session_date: date | None = None,
    expiration_code: str | None = None,
    traded_instrument: str = "XAUUSD",
    cme_source: CmeDataSource | XauDailyWorkbenchCmeSource | str | None = None,
    futures_price_provider: FuturesPriceProvider | None = None,
    traded_price_provider: TradedPriceProvider | None = None,
    session_open_provider: SessionOpenProvider | None = None,
    input_dir: Path | None = None,
    gc_reference_price: float | None = None,
    traded_reference_price: float | None = None,
    manual_basis: float | None = None,
    session_open_price: float | None = None,
    confirmation_state: str = "unavailable",
    iv_state: str = "unavailable",
    flow_state: str = "unavailable",
    output_root: Path | None = None,
    run_candidates: bool = True,
    overwrite_allowed: bool = False,
) -> XauDailyWorkbenchRunResult:
    source_override: CmeDataSource | None = (
        cme_source if _is_cme_source_override(cme_source) else None
    )
    source_enum = (
        XauDailyWorkbenchCmeSource.LATEST_EXISTING
        if source_override is not None or cme_source is None
        else XauDailyWorkbenchCmeSource(str(cme_source))
    )
    resolved_request = request or XauDailyWorkbenchRunRequest(
        session_date=session_date,
        expiration_code=expiration_code,
        traded_instrument=traded_instrument,
        cme_source=source_enum,
        input_dir=input_dir,
        gc_reference_price=gc_reference_price,
        traded_reference_price=traded_reference_price,
        manual_basis=manual_basis,
        session_open_price=session_open_price,
        confirmation_state=confirmation_state,
        iv_state=iv_state,
        flow_state=flow_state,
        output_root=output_root,
        run_candidates=run_candidates,
        overwrite_allowed=overwrite_allowed,
        research_only_acknowledged=True,
    )
    return XauDailyWorkbenchService(
        reports_dir=_normalize_output_root(resolved_request.output_root),
        cme_source=source_override,
        futures_price_provider=futures_price_provider,
        traded_price_provider=traded_price_provider,
        session_open_provider=session_open_provider,
    ).run(
        resolved_request,
        cme_source=source_override,
        futures_price_provider=futures_price_provider,
        traded_price_provider=traded_price_provider,
        session_open_provider=session_open_provider,
    )


def _first_available_price_result(
    primary: PriceResult,
    fallback: PriceResult | None,
) -> PriceResult:
    if primary.price is not None or fallback is None:
        return primary
    if fallback.price is not None:
        return fallback
    return primary


def _blocked_source_result(message: str) -> CmeDataSourceResult:
    return CmeDataSourceResult(
        daily_map=None,
        metadata=None,
        artifact_paths={},
        provider_status=provider_status(
            provider_name="XauDailyWorkbenchService",
            provider_type=XauDailyWorkbenchProviderType.CME_DATA_SOURCE,
            status=provider_status_state_error(),
            source_quality=XauDailyWorkbenchSourceQuality.LOCAL_BUNDLE,
            message=message,
        ),
        missing_inputs=[missing_input("cme_source", message)],
        no_signal_reasons=[message],
        limitations=[],
    )


def _readiness_from_map_and_candidates(
    daily_map: XauDailyStructuralMap,
    candidate_set: XauSdOiCandidateSet,
    missing_inputs: list[XauDailyWorkbenchMissingInput],
) -> XauDailyWorkbenchReadiness:
    if missing_inputs:
        return XauDailyWorkbenchReadiness.BLOCKED
    if any(
        candidate.readiness_state == XauSdOiReadinessState.BLOCKED_MISSING_CONTEXT
        for candidate in candidate_set.candidates
    ):
        return XauDailyWorkbenchReadiness.BLOCKED
    return _readiness_from_map(daily_map, [])


def _readiness_from_map(
    daily_map: XauDailyStructuralMap | None,
    missing_inputs: list[XauDailyWorkbenchMissingInput],
) -> XauDailyWorkbenchReadiness:
    if daily_map is None or missing_inputs:
        return XauDailyWorkbenchReadiness.BLOCKED
    if daily_map.data_quality_state == XauDailyStructuralMapReadiness.STRUCTURAL_MAP_READY:
        return XauDailyWorkbenchReadiness.COMPLETED
    if daily_map.data_quality_state == XauDailyStructuralMapReadiness.BLOCKED_INSUFFICIENT_CONTEXT:
        return XauDailyWorkbenchReadiness.BLOCKED
    return XauDailyWorkbenchReadiness.PARTIAL


def _missing_inputs_from_candidate_set(
    candidate_set: XauSdOiCandidateSet,
) -> list[XauDailyWorkbenchMissingInput]:
    reason_codes = {
        reason.reason_code
        for candidate in candidate_set.candidates
        for reason in candidate.reasons
    }
    missing: list[XauDailyWorkbenchMissingInput] = []
    if BASIS_MISSING_REASON_CODE in reason_codes:
        missing.append(
            missing_input(
                "basis",
                "Basis mapping is unavailable; candidate classification is blocked.",
            )
        )
    if SESSION_OPEN_MISSING_REASON_CODE in reason_codes:
        missing.append(
            missing_input(
                "session_open_price",
                "Session open is unavailable; candidate classification is blocked.",
            )
        )
    if TRADED_PRICE_MISSING_REASON_CODE in reason_codes:
        missing.append(
            missing_input(
                "traded_reference_price",
                "Observed traded price is unavailable; candidate classification is blocked.",
            )
        )
    return missing


def _missing_inputs_from_map(
    daily_map: XauDailyStructuralMap,
) -> list[XauDailyWorkbenchMissingInput]:
    missing: list[XauDailyWorkbenchMissingInput] = []
    if not daily_map.basis_mapping_available:
        missing.append(
            missing_input("basis", "Basis mapping is unavailable for this map.")
        )
    if not daily_map.session_open_available:
        missing.append(
            missing_input(
                "session_open_price",
                "Session open is unavailable for this map.",
                severity=XauDailyWorkbenchMissingInputSeverity.WARNING,
            )
        )
    if daily_map.expected_range_source is None:
        missing.append(
            missing_input(
                "expected_range",
                "Expected-range context is unavailable for this map.",
            )
        )
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


def _dedupe_missing_inputs(
    values: Iterable[XauDailyWorkbenchMissingInput],
) -> list[XauDailyWorkbenchMissingInput]:
    output: list[XauDailyWorkbenchMissingInput] = []
    seen: set[str] = set()
    for value in values:
        key = value.input_name
        if key not in seen:
            output.append(value)
            seen.add(key)
    return output


def _dedupe_statuses(
    values: Iterable[XauDailyWorkbenchProviderStatus],
) -> list[XauDailyWorkbenchProviderStatus]:
    output: list[XauDailyWorkbenchProviderStatus] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        key = (value.provider_name, value.provider_type.value)
        if key not in seen:
            output.append(value)
            seen.add(key)
    return output


def _is_cme_source_override(value: object) -> bool:
    return value is not None and hasattr(value, "load_or_fetch_bundle")


def provider_status_state_available():
    from src.models.xau_daily_workbench import XauDailyWorkbenchProviderState

    return XauDailyWorkbenchProviderState.AVAILABLE


def provider_status_state_error():
    from src.models.xau_daily_workbench import XauDailyWorkbenchProviderState

    return XauDailyWorkbenchProviderState.ERROR


__all__ = [
    "ApiOnlyCmeSource",
    "CmeDataSource",
    "FUSED_ROWS_FILENAME",
    "FixtureCmeDataSource",
    "FuturesPriceProvider",
    "LatestExistingXauArtifactSource",
    "LocalBundleCmeDataSource",
    "ManualPriceProvider",
    "REPORT_JSON_FILENAME",
    "SessionOpenProvider",
    "StaticFixturePriceProvider",
    "TradedPriceProvider",
    "WALLS_PARQUET_FILENAME",
    "XauDailyWorkbenchService",
    "YahooResearchPriceProvider",
    "run_xau_daily_research_workbench",
]
