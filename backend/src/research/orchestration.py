"""Coordinator for grouped multi-asset research reports."""

import hashlib
from datetime import datetime
from pathlib import Path

from src.models.backtest import BacktestStatus
from src.models.research import (
    ResearchAssetClassification,
    ResearchAssetResult,
    ResearchAssetRunStatus,
    ResearchPreflightResult,
    ResearchPreflightStatus,
    ResearchRun,
    ResearchRunRequest,
)
from src.reports.writer import RESEARCH_ONLY_WARNING
from src.research.preflight import preflight_research_assets
from src.research.report_store import ResearchReportStore


class ResearchExecutionNotImplementedError(NotImplementedError):
    """Raised until story implementation adds concrete grouped execution."""


class ResearchOrchestrator:
    """Skeleton service for multi-asset research orchestration."""

    def __init__(self, report_store: ResearchReportStore | None = None):
        self.report_store = report_store or ResearchReportStore()

    def run(self, request: ResearchRunRequest) -> ResearchRun:
        created_at = datetime.utcnow()
        preflight_results = preflight_research_assets(request.assets)
        asset_configs = [asset for asset in request.assets if asset.enabled]
        assets = [
            _asset_result(asset_config, preflight)
            for asset_config, preflight in zip(asset_configs, preflight_results, strict=True)
        ]
        completed_count = sum(
            1 for asset in assets if asset.status == ResearchAssetRunStatus.COMPLETED
        )
        blocked_count = sum(1 for asset in assets if asset.status == ResearchAssetRunStatus.BLOCKED)
        warnings = [
            (
                "Grouped report is a research comparison only and does not imply "
                "profitability, predictive power, safety, or live readiness."
            )
        ]
        if blocked_count:
            warnings.append(
                "Some configured assets were blocked by missing or incomplete processed features."
            )
        status = _run_status(completed_count=completed_count, blocked_count=blocked_count)
        run = ResearchRun(
            research_run_id=_research_run_id(created_at),
            status=status,
            created_at=created_at,
            completed_at=datetime.utcnow(),
            request=request,
            assets=assets,
            completed_count=completed_count,
            blocked_count=blocked_count,
            warnings=warnings,
            limitations=[
                RESEARCH_ONLY_WARNING,
                "Feature 005 US1 uses existing processed feature files only; no synthetic "
                "fallback is used for missing real-data research inputs.",
                "Strategy comparison and validation aggregation are added in later phases.",
            ],
        )
        return self.report_store.write_run_outputs(run)


def _asset_result(
    asset_config,
    preflight: ResearchPreflightResult,
) -> ResearchAssetResult:
    if preflight.status == ResearchPreflightStatus.READY:
        return ResearchAssetResult(
            symbol=asset_config.symbol,
            provider=asset_config.provider,
            asset_class=asset_config.asset_class,
            status=ResearchAssetRunStatus.COMPLETED,
            classification=ResearchAssetClassification.INCONCLUSIVE,
            preflight=preflight,
            data_identity=_data_identity(
                preflight,
                source_kind="explicit_feature_path"
                if asset_config.feature_path is not None
                else "processed_features",
            ),
            warnings=preflight.warnings,
            limitations=[
                *preflight.capability_snapshot.limitation_notes,
                "US1 confirms real processed feature availability; strategy comparisons "
                "are not populated until later phases.",
            ],
        )

    classification = (
        ResearchAssetClassification.MISSING_DATA
        if preflight.status == ResearchPreflightStatus.MISSING_DATA
        else ResearchAssetClassification.INCONCLUSIVE
    )
    return ResearchAssetResult(
        symbol=asset_config.symbol,
        provider=asset_config.provider,
        asset_class=asset_config.asset_class,
        status=ResearchAssetRunStatus.BLOCKED,
        classification=classification,
        preflight=preflight,
        warnings=preflight.warnings,
        limitations=preflight.capability_snapshot.limitation_notes,
    )


def _data_identity(preflight: ResearchPreflightResult, source_kind: str) -> dict:
    path = Path(preflight.feature_path)
    identity = {
        "source_kind": source_kind,
        "feature_path": preflight.feature_path,
        "exists": path.exists(),
        "row_count": preflight.row_count,
        "first_timestamp": preflight.first_timestamp.isoformat()
        if preflight.first_timestamp
        else None,
        "last_timestamp": preflight.last_timestamp.isoformat()
        if preflight.last_timestamp
        else None,
    }
    if path.exists():
        identity["content_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return identity


def _run_status(completed_count: int, blocked_count: int) -> BacktestStatus:
    if completed_count and not blocked_count:
        return BacktestStatus.COMPLETED
    if completed_count:
        return BacktestStatus.PARTIAL
    return BacktestStatus.FAILED


def _research_run_id(created_at: datetime) -> str:
    return f"research_{created_at.strftime('%Y%m%d_%H%M%S_%f')}_multi_asset"
