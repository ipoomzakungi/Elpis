import csv
from datetime import date
from pathlib import Path

from src.free_derivatives.gvz import (
    create_gvz_request_plan,
    filter_gvz_records_by_date,
    load_gvz_daily_close_records,
    normalize_gvz_rows,
    read_gvz_fixture_rows,
)
from src.free_derivatives.orchestration import assemble_placeholder_bootstrap_run
from src.free_derivatives.processing import build_gvz_gap_summary
from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.models.free_derivatives import (
    FreeDerivativesArtifactType,
    FreeDerivativesBootstrapRequest,
    FreeDerivativesRunStatus,
    FreeDerivativesSourceStatus,
    GvzRequest,
)


def test_gvz_request_plan_preserves_series_window_source_and_fixture_path(tmp_path):
    fixture_path = tmp_path / "gvzcls.csv"
    request = GvzRequest(
        series_id="gvzcls",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 5),
        source_url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=GVZCLS",
        local_fixture_path=fixture_path,
    )

    plan = create_gvz_request_plan(request)

    assert plan.series_id == "GVZCLS"
    assert plan.start_date == date(2025, 1, 1)
    assert plan.end_date == date(2025, 1, 5)
    assert plan.source_url == "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GVZCLS"
    assert plan.local_fixture_path == fixture_path
    assert plan.requested_item == "GVZCLS:2025-01-01:2025-01-05"


def test_gvz_fixture_parser_reads_csv_and_normalizes_daily_close(tmp_path):
    csv_path = _write_gvz_csv(tmp_path / "gvzcls.csv", _sample_gvz_rows())

    raw_rows = read_gvz_fixture_rows(csv_path)
    records = normalize_gvz_rows(raw_rows, series_id="GVZCLS")

    assert len(raw_rows) == 3
    assert len(records) == 3
    assert records[0].date == date(2025, 1, 1)
    assert records[0].close == 17.5
    assert records[0].series_id == "GVZCLS"
    assert records[0].source.endswith("gvzcls.csv")
    assert records[1].date == date(2025, 1, 2)
    assert records[1].close is None
    assert records[1].is_missing is True
    assert any("GLD-options-derived volatility proxy" in item for item in records[0].limitations)


def test_gvz_date_window_filtering_and_gap_summary(tmp_path):
    csv_path = _write_gvz_csv(tmp_path / "gvzcls.csv", _sample_gvz_rows())
    request = GvzRequest(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 4),
        local_fixture_path=csv_path,
    )

    records = load_gvz_daily_close_records(request)
    filtered = filter_gvz_records_by_date(
        records,
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 4),
    )
    summary = build_gvz_gap_summary(
        records,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    assert [record.date for record in filtered] == [date(2025, 1, 2), date(2025, 1, 4)]
    assert summary.start_date == date(2025, 1, 1)
    assert summary.end_date == date(2025, 1, 4)
    assert summary.observed_row_count == 2
    assert summary.missing_date_count == 2
    assert summary.missing_dates == [date(2025, 1, 2), date(2025, 1, 3)]
    assert any("not a CME gold options" in item for item in summary.limitations)


def test_gvz_orchestration_runs_gvz_alone_and_writes_generated_artifacts(tmp_path):
    csv_path = _write_gvz_csv(tmp_path / "gvzcls.csv", _sample_gvz_rows())
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    request = FreeDerivativesBootstrapRequest(
        include_cftc=False,
        include_gvz=True,
        include_deribit=False,
        gvz={
            "start_date": "2025-01-01",
            "end_date": "2025-01-04",
            "local_fixture_path": csv_path,
        },
        research_only_acknowledged=True,
    )

    run = assemble_placeholder_bootstrap_run(request, store=store)

    assert run.status == FreeDerivativesRunStatus.COMPLETED
    assert len(run.source_results) == 1
    result = run.source_results[0]
    assert result.status == FreeDerivativesSourceStatus.COMPLETED
    assert result.row_count == 3
    assert result.coverage_start == date(2025, 1, 1)
    assert result.coverage_end == date(2025, 1, 4)
    assert {
        artifact.artifact_type for artifact in result.artifacts
    } == {
        FreeDerivativesArtifactType.RAW_GVZ,
        FreeDerivativesArtifactType.PROCESSED_GVZ,
    }
    assert any("GLD-options-derived volatility proxy" in item for item in result.limitations)
    assert any("not strike-level options open interest" in item for item in result.limitations)


def test_gvz_orchestration_returns_skipped_when_fixture_is_missing():
    request = FreeDerivativesBootstrapRequest(
        include_cftc=False,
        include_gvz=True,
        include_deribit=False,
        research_only_acknowledged=True,
    )

    run = assemble_placeholder_bootstrap_run(request)

    assert run.status == FreeDerivativesRunStatus.BLOCKED
    assert run.source_results[0].status == FreeDerivativesSourceStatus.SKIPPED
    assert run.source_results[0].artifacts == []
    assert run.source_results[0].missing_data_actions


def test_gvz_orchestration_returns_partial_when_fixture_has_no_usable_close_rows(tmp_path):
    csv_path = _write_gvz_csv(
        tmp_path / "gvzcls.csv",
        [
            {"DATE": "2025-01-01", "GVZCLS": "."},
            {"DATE": "2025-01-02", "GVZCLS": ""},
        ],
    )
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    request = FreeDerivativesBootstrapRequest(
        include_cftc=False,
        include_gvz=True,
        include_deribit=False,
        gvz={"local_fixture_path": csv_path},
        research_only_acknowledged=True,
    )

    run = assemble_placeholder_bootstrap_run(request, store=store)

    assert run.status == FreeDerivativesRunStatus.PARTIAL
    result = run.source_results[0]
    assert result.status == FreeDerivativesSourceStatus.PARTIAL
    assert result.row_count == 2
    assert result.skipped_items
    assert "no usable close" in " ".join(result.warnings).lower()


def _sample_gvz_rows() -> list[dict[str, str]]:
    return [
        {"DATE": "2025-01-01", "GVZCLS": "17.5"},
        {"DATE": "2025-01-02", "GVZCLS": "."},
        {"DATE": "2025-01-04", "GVZCLS": "18.25"},
    ]


def _write_gvz_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path
