"""Persistence facade for public bootstrap reports."""

from src.data_sources.report_store import (
    PUBLIC_BOOTSTRAP_REPORT_DIR,
    DataSourceBootstrapReportStore,
)

DataBootstrapReportStore = DataSourceBootstrapReportStore

__all__ = [
    "DataBootstrapReportStore",
    "DataSourceBootstrapReportStore",
    "PUBLIC_BOOTSTRAP_REPORT_DIR",
]
