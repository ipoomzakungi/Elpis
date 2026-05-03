from datetime import UTC, datetime

from src.data_bootstrap.report_store import DataBootstrapReportStore
from src.models.data_sources import DataSourceBootstrapRunResult, FirstEvidenceRunStatus


def test_report_store_writes_lists_and_reads_bootstrap_runs(isolated_data_paths):
    store = DataBootstrapReportStore(reports_root=isolated_data_paths / "reports")
    result = DataSourceBootstrapRunResult(
        bootstrap_run_id="bootstrap_test_run",
        status=FirstEvidenceRunStatus.BLOCKED,
        created_at=datetime.now(UTC),
        raw_root=isolated_data_paths / "raw",
        processed_root=isolated_data_paths / "processed",
        limitations=["XAU options OI remains a local CSV/Parquet import workflow."],
    )

    store.write_bootstrap_run(result)

    listed = store.list_bootstrap_runs()
    loaded = store.read_bootstrap_run("bootstrap_test_run")

    assert listed[0].bootstrap_run_id == "bootstrap_test_run"
    assert loaded.bootstrap_run_id == "bootstrap_test_run"
    assert "XAU options OI" in loaded.limitations[0]
