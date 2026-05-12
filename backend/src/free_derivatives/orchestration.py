from datetime import UTC, datetime

from src.free_derivatives.cftc import (
    create_cftc_request_plan,
    load_cftc_gold_records,
    read_cftc_fixture_rows,
)
from src.free_derivatives.gvz import (
    create_gvz_request_plan,
    load_gvz_daily_close_records,
    read_gvz_fixture_rows,
)
from src.free_derivatives.processing import (
    CFTC_WEEKLY_POSITIONING_LIMITATION,
    FREE_DERIVATIVES_NO_REPLACEMENT_LIMITATION,
    FREE_DERIVATIVES_RESEARCH_ONLY_WARNING,
    build_cftc_gold_positioning_summary,
    build_gvz_gap_summary,
    foundational_limitations,
    source_limitations,
)
from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.models.free_derivatives import (
    FreeDerivativesBootstrapRequest,
    FreeDerivativesBootstrapRun,
    FreeDerivativesRunStatus,
    FreeDerivativesSource,
    FreeDerivativesSourceResult,
    FreeDerivativesSourceStatus,
    create_free_derivatives_run_id,
)


def assemble_placeholder_bootstrap_run(
    request: FreeDerivativesBootstrapRequest,
    store: FreeDerivativesReportStore | None = None,
) -> FreeDerivativesBootstrapRun:
    """Build a structured research run for implemented sources and placeholders."""

    created_at = datetime.now(UTC)
    run_id = create_free_derivatives_run_id(request.run_label, created_at=created_at)
    artifact_store = store or FreeDerivativesReportStore()
    source_results: list[FreeDerivativesSourceResult] = []
    if request.include_cftc:
        source_results.append(_run_cftc_source(request, run_id, artifact_store))
    if request.include_gvz:
        source_results.append(_run_gvz_source(request, run_id, artifact_store))
    if request.include_deribit:
        source_results.append(
            _placeholder_source_result(FreeDerivativesSource.DERIBIT_PUBLIC_OPTIONS)
        )

    return FreeDerivativesBootstrapRun(
        run_id=run_id,
        status=_aggregate_run_status(source_results),
        created_at=created_at,
        completed_at=created_at,
        request=request,
        source_results=source_results,
        artifacts=[artifact for result in source_results for artifact in result.artifacts],
        warnings=[FREE_DERIVATIVES_RESEARCH_ONLY_WARNING],
        limitations=foundational_limitations(),
        missing_data_actions=list(
            dict.fromkeys(
                [
                    action
                    for result in source_results
                    for action in result.missing_data_actions
                ]
                + [FREE_DERIVATIVES_NO_REPLACEMENT_LIMITATION]
            )
        ),
        research_only_warnings=[
            (
                "No live trading, paper trading, broker integration, wallet handling, "
                "paid vendors, or execution behavior is included."
            )
        ],
    )


def _run_cftc_source(
    request: FreeDerivativesBootstrapRequest,
    run_id: str,
    store: FreeDerivativesReportStore,
) -> FreeDerivativesSourceResult:
    plan = create_cftc_request_plan(request.cftc)
    requested_items = [item.requested_item for item in plan]
    limitations = source_limitations(FreeDerivativesSource.CFTC_COT)
    if not request.cftc.local_fixture_paths:
        return FreeDerivativesSourceResult(
            source=FreeDerivativesSource.CFTC_COT,
            status=FreeDerivativesSourceStatus.SKIPPED,
            requested_items=requested_items,
            skipped_items=requested_items or ["cftc_fixture_or_public_source"],
            warnings=[
                "CFTC source execution needs a local fixture/import file in this slice."
            ],
            limitations=limitations,
            missing_data_actions=[
                (
                    "Provide a public CFTC historical file as a local CSV/ZIP fixture "
                    "before running CFTC processing."
                )
            ],
        )

    try:
        raw_rows = read_cftc_fixture_rows(request.cftc.local_fixture_paths)
        records = load_cftc_gold_records(request.cftc)
        if not records:
            return FreeDerivativesSourceResult(
                source=FreeDerivativesSource.CFTC_COT,
                status=FreeDerivativesSourceStatus.PARTIAL,
                requested_items=requested_items,
                completed_items=[],
                skipped_items=requested_items,
                row_count=0,
                artifacts=[
                    store.write_cftc_raw_rows(run_id, raw_rows),
                ],
                warnings=[
                    "CFTC fixtures were readable but no gold/COMEX rows matched the filters."
                ],
                limitations=limitations,
                missing_data_actions=[
                    "Check the CFTC fixture for gold/COMEX rows and report category labels."
                ],
            )

        summaries = build_cftc_gold_positioning_summary(records)
        artifacts = [
            store.write_cftc_raw_rows(run_id, raw_rows),
            store.write_cftc_processed_records(run_id, records),
            store.write_cftc_positioning_summary(run_id, summaries),
        ]
        return FreeDerivativesSourceResult(
            source=FreeDerivativesSource.CFTC_COT,
            status=FreeDerivativesSourceStatus.COMPLETED,
            requested_items=requested_items,
            completed_items=sorted(
                {
                    f"{record.report_date.isoformat()}:{record.report_category.value}"
                    for record in records
                }
            ),
            row_count=len(records),
            coverage_start=min(record.report_date for record in records),
            coverage_end=max(record.report_date for record in records),
            artifacts=artifacts,
            warnings=[],
            limitations=[CFTC_WEEKLY_POSITIONING_LIMITATION, *limitations],
            missing_data_actions=[],
        )
    except Exception as exc:
        return FreeDerivativesSourceResult(
            source=FreeDerivativesSource.CFTC_COT,
            status=FreeDerivativesSourceStatus.FAILED,
            requested_items=requested_items,
            failed_items=requested_items or ["cftc_fixture"],
            warnings=[f"CFTC fixture processing failed: {exc}"],
            limitations=limitations,
            missing_data_actions=[
                "Use a readable CFTC CSV or ZIP fixture with report date and positioning columns."
            ],
        )


def _run_gvz_source(
    request: FreeDerivativesBootstrapRequest,
    run_id: str,
    store: FreeDerivativesReportStore,
) -> FreeDerivativesSourceResult:
    plan = create_gvz_request_plan(request.gvz)
    requested_items = [plan.requested_item]
    limitations = source_limitations(FreeDerivativesSource.GVZ)
    if request.gvz.local_fixture_path is None:
        return FreeDerivativesSourceResult(
            source=FreeDerivativesSource.GVZ,
            status=FreeDerivativesSourceStatus.SKIPPED,
            requested_items=requested_items,
            skipped_items=requested_items,
            warnings=["GVZ source execution needs a local fixture/import file in this slice."],
            limitations=limitations,
            missing_data_actions=[
                (
                    "Provide a public GVZ daily close CSV as a local fixture before "
                    "running GVZ processing."
                )
            ],
        )

    try:
        raw_rows = read_gvz_fixture_rows(request.gvz.local_fixture_path)
        records = load_gvz_daily_close_records(request.gvz)
        raw_artifact = store.write_gvz_raw_rows(run_id, raw_rows)
        if not records:
            return FreeDerivativesSourceResult(
                source=FreeDerivativesSource.GVZ,
                status=FreeDerivativesSourceStatus.PARTIAL,
                requested_items=requested_items,
                skipped_items=requested_items,
                row_count=0,
                artifacts=[raw_artifact],
                warnings=["GVZ fixture was readable but no rows matched the date window."],
                limitations=limitations,
                missing_data_actions=[
                    "Check the GVZ fixture date coverage or adjust the requested date window."
                ],
            )

        observed_records = [record for record in records if not record.is_missing]
        gap_summary = build_gvz_gap_summary(
            records,
            start_date=request.gvz.start_date,
            end_date=request.gvz.end_date,
        )
        artifacts = [
            raw_artifact,
            store.write_gvz_daily_close(run_id, records),
            store.write_gvz_gap_summary(run_id, gap_summary),
        ]
        if not observed_records:
            return FreeDerivativesSourceResult(
                source=FreeDerivativesSource.GVZ,
                status=FreeDerivativesSourceStatus.PARTIAL,
                requested_items=requested_items,
                skipped_items=requested_items,
                row_count=len(records),
                coverage_start=min(record.date for record in records),
                coverage_end=max(record.date for record in records),
                artifacts=artifacts,
                warnings=["GVZ fixture had rows but no usable close observations."],
                limitations=limitations,
                missing_data_actions=[
                    "Provide GVZ rows with numeric daily close values for volatility proxy context."
                ],
            )

        warnings: list[str] = []
        if gap_summary.missing_date_count:
            warnings.append(
                "GVZ date coverage has "
                f"{gap_summary.missing_date_count} missing daily observations."
            )
        return FreeDerivativesSourceResult(
            source=FreeDerivativesSource.GVZ,
            status=FreeDerivativesSourceStatus.COMPLETED,
            requested_items=requested_items,
            completed_items=[
                f"{record.series_id}:{record.date.isoformat()}"
                for record in records
                if not record.is_missing
            ],
            row_count=len(records),
            coverage_start=min(record.date for record in records),
            coverage_end=max(record.date for record in records),
            artifacts=artifacts,
            warnings=warnings,
            limitations=limitations,
            missing_data_actions=[],
        )
    except Exception as exc:
        return FreeDerivativesSourceResult(
            source=FreeDerivativesSource.GVZ,
            status=FreeDerivativesSourceStatus.FAILED,
            requested_items=requested_items,
            failed_items=requested_items,
            warnings=[f"GVZ fixture processing failed: {exc}"],
            limitations=limitations,
            missing_data_actions=[
                "Use a readable GVZ CSV fixture with DATE and GVZCLS or close columns."
            ],
        )


def _placeholder_source_result(source: FreeDerivativesSource) -> FreeDerivativesSourceResult:
    return FreeDerivativesSourceResult(
        source=source,
        status=FreeDerivativesSourceStatus.SKIPPED,
        requested_items=["foundation_placeholder"],
        skipped_items=["source-specific implementation is deferred"],
        warnings=[
            (
                "Placeholder only: source collection and parsing are not implemented "
                "in this slice."
            )
        ],
        limitations=source_limitations(source),
        missing_data_actions=[
            (
                "Continue with the source-specific implementation tasks before "
                "running real or fixture collection."
            )
        ],
    )


def _aggregate_run_status(
    source_results: list[FreeDerivativesSourceResult],
) -> FreeDerivativesRunStatus:
    if not source_results:
        return FreeDerivativesRunStatus.BLOCKED
    completed = [
        result
        for result in source_results
        if result.status == FreeDerivativesSourceStatus.COMPLETED
    ]
    if len(completed) == len(source_results):
        return FreeDerivativesRunStatus.COMPLETED
    if completed:
        return FreeDerivativesRunStatus.PARTIAL
    if any(result.status == FreeDerivativesSourceStatus.PARTIAL for result in source_results):
        return FreeDerivativesRunStatus.PARTIAL
    if any(result.status == FreeDerivativesSourceStatus.FAILED for result in source_results):
        return FreeDerivativesRunStatus.FAILED
    return FreeDerivativesRunStatus.BLOCKED
