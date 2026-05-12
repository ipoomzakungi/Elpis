import csv
import zipfile
from pathlib import Path

from src.free_derivatives.cftc import (
    create_cftc_request_plan,
    filter_gold_comex_records,
    load_cftc_gold_records,
    normalize_cftc_rows,
    read_cftc_fixture_rows,
)
from src.free_derivatives.orchestration import assemble_placeholder_bootstrap_run
from src.free_derivatives.processing import build_cftc_gold_positioning_summary
from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.models.free_derivatives import (
    CftcCotReportCategory,
    CftcCotRequest,
    FreeDerivativesArtifactType,
    FreeDerivativesBootstrapRequest,
    FreeDerivativesRunStatus,
    FreeDerivativesSourceStatus,
)


def test_cftc_request_plan_preserves_years_categories_urls_and_fixture_paths(tmp_path):
    fixture_path = tmp_path / "cftc_gold.csv"
    request = CftcCotRequest(
        years=[2025, 2026],
        categories=[
            CftcCotReportCategory.FUTURES_ONLY,
            CftcCotReportCategory.FUTURES_AND_OPTIONS_COMBINED,
        ],
        source_urls=["https://www.cftc.gov/files/dea/history/deacot2025.zip"],
        local_fixture_paths=[fixture_path],
    )

    plan = create_cftc_request_plan(request)

    assert [item.requested_item for item in plan] == [
        "2025:futures_only",
        "2025:futures_and_options_combined",
        "2026:futures_only",
        "2026:futures_and_options_combined",
    ]
    assert all(item.local_fixture_paths == [fixture_path] for item in plan)
    assert plan[0].source_url == "https://www.cftc.gov/files/dea/history/deacot2025.zip"
    assert plan[1].source_url is None


def test_cftc_fixture_parser_reads_csv_and_compressed_csv_rows(tmp_path):
    csv_path = _write_cftc_csv(tmp_path / "cot.csv", _sample_cftc_rows())
    zip_path = _write_cftc_zip(tmp_path / "cot.zip", _sample_cftc_rows())

    csv_rows = read_cftc_fixture_rows([csv_path])
    zipped_rows = read_cftc_fixture_rows([zip_path])

    assert len(csv_rows) == 4
    assert len(zipped_rows) == 4
    assert csv_rows[0]["_source_file"].endswith("cot.csv")
    assert zipped_rows[0]["_source_file"].endswith("cot.zip:cot.csv")
    assert csv_rows[0]["_source_row_number"] == "1"


def test_cftc_filter_keeps_gold_comex_rows_and_excludes_non_gold(tmp_path):
    csv_path = _write_cftc_csv(tmp_path / "cot.csv", _sample_cftc_rows())
    records = normalize_cftc_rows(
        read_cftc_fixture_rows([csv_path]),
        default_category=CftcCotReportCategory.FUTURES_ONLY,
    )

    filtered = filter_gold_comex_records(records, market_filters=["gold", "comex"])

    assert len(filtered) == 3
    assert {record.market_name for record in filtered} == {"GOLD"}
    assert all("gold" in record.matched_filters for record in filtered)
    assert all("comex" in record.matched_filters for record in filtered)


def test_cftc_category_labels_remain_separate_when_records_are_loaded(tmp_path):
    csv_path = _write_cftc_csv(tmp_path / "cot.csv", _sample_cftc_rows())

    records = load_cftc_gold_records(
        CftcCotRequest(
            categories=[
                CftcCotReportCategory.FUTURES_ONLY,
                CftcCotReportCategory.FUTURES_AND_OPTIONS_COMBINED,
            ],
            local_fixture_paths=[csv_path],
        )
    )

    assert {record.report_category for record in records} == {
        CftcCotReportCategory.FUTURES_ONLY,
        CftcCotReportCategory.FUTURES_AND_OPTIONS_COMBINED,
    }


def test_cftc_positioning_summary_calculates_net_and_week_over_week_fields(tmp_path):
    csv_path = _write_cftc_csv(tmp_path / "cot.csv", _sample_cftc_rows())
    records = load_cftc_gold_records(
        CftcCotRequest(
            categories=[CftcCotReportCategory.FUTURES_ONLY],
            local_fixture_paths=[csv_path],
        )
    )

    summaries = build_cftc_gold_positioning_summary(records)

    assert [summary.report_date.isoformat() for summary in summaries] == [
        "2025-01-07",
        "2025-01-14",
    ]
    assert summaries[0].noncommercial_net == 60.0
    assert summaries[0].commercial_net == -10.0
    assert summaries[0].total_reportable_net == 50.0
    assert summaries[0].week_over_week_noncommercial_net_change is None
    assert summaries[1].noncommercial_net == 65.0
    assert summaries[1].week_over_week_noncommercial_net_change == 5.0
    assert summaries[1].week_over_week_open_interest_change == 10.0


def test_cftc_orchestration_runs_cftc_alone_and_writes_generated_artifacts(tmp_path):
    csv_path = _write_cftc_csv(tmp_path / "cot.csv", _sample_cftc_rows())
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    request = FreeDerivativesBootstrapRequest(
        include_cftc=True,
        include_gvz=False,
        include_deribit=False,
        cftc={
            "categories": [
                "futures_only",
                "futures_and_options_combined",
            ],
            "local_fixture_paths": [csv_path],
        },
        research_only_acknowledged=True,
    )

    run = assemble_placeholder_bootstrap_run(request, store=store)

    assert run.status == FreeDerivativesRunStatus.COMPLETED
    assert len(run.source_results) == 1
    result = run.source_results[0]
    assert result.status == FreeDerivativesSourceStatus.COMPLETED
    assert result.row_count == 3
    assert len(result.artifacts) == 3
    assert {
        artifact.artifact_type for artifact in result.artifacts
    } == {
        FreeDerivativesArtifactType.RAW_CFTC,
        FreeDerivativesArtifactType.PROCESSED_CFTC,
    }
    assert all(Path(artifact.path).name for artifact in result.artifacts)
    assert not any(
        row.source in {"gvz", "deribit_public_options"} for row in run.source_results
    )


def _sample_cftc_rows() -> list[dict[str, str]]:
    return [
        {
            "report_category": "futures_only",
            "As_of_Date_In_Form_YYMMDD": "250107",
            "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
            "CFTC_Contract_Market_Code": "088691",
            "Open_Interest_All": "1000",
            "Noncommercial_Long_All": "130",
            "Noncommercial_Short_All": "70",
            "Noncommercial_Spread_All": "5",
            "Commercial_Long_All": "200",
            "Commercial_Short_All": "210",
            "Tot_Rept_Long_All": "330",
            "Tot_Rept_Short_All": "280",
            "NonRept_Long_All": "30",
            "NonRept_Short_All": "40",
        },
        {
            "report_category": "futures_only",
            "As_of_Date_In_Form_YYMMDD": "250114",
            "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
            "CFTC_Contract_Market_Code": "088691",
            "Open_Interest_All": "1010",
            "Noncommercial_Long_All": "140",
            "Noncommercial_Short_All": "75",
            "Noncommercial_Spread_All": "5",
            "Commercial_Long_All": "205",
            "Commercial_Short_All": "215",
            "Tot_Rept_Long_All": "345",
            "Tot_Rept_Short_All": "290",
            "NonRept_Long_All": "32",
            "NonRept_Short_All": "42",
        },
        {
            "report_category": "futures_and_options_combined",
            "As_of_Date_In_Form_YYMMDD": "250107",
            "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
            "CFTC_Contract_Market_Code": "088691",
            "Open_Interest_All": "2000",
            "Noncommercial_Long_All": "230",
            "Noncommercial_Short_All": "120",
            "Noncommercial_Spread_All": "8",
            "Commercial_Long_All": "400",
            "Commercial_Short_All": "420",
            "Tot_Rept_Long_All": "630",
            "Tot_Rept_Short_All": "540",
            "NonRept_Long_All": "50",
            "NonRept_Short_All": "60",
        },
        {
            "report_category": "futures_only",
            "As_of_Date_In_Form_YYMMDD": "250107",
            "Market_and_Exchange_Names": "CORN - CHICAGO BOARD OF TRADE",
            "CFTC_Contract_Market_Code": "002602",
            "Open_Interest_All": "5000",
            "Noncommercial_Long_All": "700",
            "Noncommercial_Short_All": "500",
        },
    ]


def _write_cftc_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_cftc_zip(path: Path, rows: list[dict[str, str]]) -> Path:
    csv_path = _write_cftc_csv(path.with_name(f"{path.stem}_archive.csv"), rows)
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(csv_path, arcname="cot.csv")
    csv_path.unlink()
    return path
