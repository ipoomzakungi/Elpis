"""Persistence helpers for grouped multi-asset research reports."""

import json
from typing import Any

import polars as pl

from src.backtest.report_store import ReportStore
from src.models.backtest import ReportArtifactType, ReportFormat
from src.models.research import (
    ResearchAssetSummaryResponse,
    ResearchComparisonResponse,
    ResearchRun,
    ResearchRunListResponse,
    ResearchRunSummary,
    ResearchValidationAggregationResponse,
    StrategyComparisonRow,
)
from src.reports.writer import compose_research_report_json, compose_research_report_markdown
from src.research.aggregation import (
    collect_concentration,
    collect_regime_coverage,
    collect_strategy_comparison,
    collect_stress_survival,
    collect_walk_forward_stability,
)


class ResearchReportStore:
    """Skeleton store for grouped research reports.

    Phase 1/2 wires contracts and placeholders only. Story phases implement
    writes and reads for concrete grouped report artifacts.
    """

    def __init__(self, report_store: ReportStore | None = None):
        self.report_store = report_store or ReportStore()

    def list_runs(self) -> ResearchRunListResponse:
        return ResearchRunListResponse(runs=self.list_run_summaries())

    def list_run_summaries(self) -> list[ResearchRunSummary]:
        summaries = []
        for run in self._list_research_runs():
            summaries.append(
                ResearchRunSummary(
                    research_run_id=run.research_run_id,
                    status=run.status,
                    created_at=run.created_at,
                    completed_count=run.completed_count,
                    blocked_count=run.blocked_count,
                    asset_count=len(run.assets),
                    warnings=run.warnings,
                )
            )
        return sorted(summaries, key=lambda summary: summary.created_at, reverse=True)

    def read_run(self, research_run_id: str) -> ResearchRun:
        return ResearchRun.model_validate(
            self.report_store.read_json(research_run_id, "research_metadata.json")
        )

    def read_assets(self, research_run_id: str) -> ResearchAssetSummaryResponse:
        run = self.read_run(research_run_id)
        return ResearchAssetSummaryResponse(research_run_id=research_run_id, data=run.assets)

    def read_comparison(self, research_run_id: str) -> ResearchComparisonResponse:
        try:
            frame = self.report_store.read_parquet(
                research_run_id,
                "strategy_comparison.parquet",
            )
        except FileNotFoundError:
            run = self.read_run(research_run_id)
            return ResearchComparisonResponse(
                research_run_id=research_run_id,
                data=collect_strategy_comparison(run.assets),
            )
        return ResearchComparisonResponse(
            research_run_id=research_run_id,
            data=_comparison_rows_from_frame(frame),
        )

    def read_validation_aggregation(
        self,
        research_run_id: str,
    ) -> ResearchValidationAggregationResponse:
        run = self.read_run(research_run_id)
        return ResearchValidationAggregationResponse(
            research_run_id=research_run_id,
            stress=collect_stress_survival(run.assets),
            walk_forward=collect_walk_forward_stability(run.assets),
            regime_coverage=collect_regime_coverage(run.assets),
            concentration=collect_concentration(run.assets),
        )

    def write_run_outputs(self, research_run: ResearchRun) -> ResearchRun:
        artifacts = [
            self.report_store.write_json(
                research_run.research_run_id,
                "research_config.json",
                research_run.request,
                ReportArtifactType.RESEARCH_CONFIG,
            ),
            self.report_store.write_parquet(
                research_run.research_run_id,
                "asset_summary.parquet",
                _asset_summary_frame(research_run),
                ReportArtifactType.RESEARCH_ASSET_SUMMARY,
            ),
            self.report_store.write_parquet(
                research_run.research_run_id,
                "strategy_comparison.parquet",
                _strategy_comparison_frame(research_run),
                ReportArtifactType.RESEARCH_COMPARISON,
            ),
        ]
        if research_run.request.report_format in {ReportFormat.JSON, ReportFormat.BOTH}:
            artifacts.append(
                self.report_store.write_json(
                    research_run.research_run_id,
                    "research_report.json",
                    compose_research_report_json(research_run),
                    ReportArtifactType.RESEARCH_REPORT_JSON,
                )
            )
        if research_run.request.report_format in {ReportFormat.MARKDOWN, ReportFormat.BOTH}:
            artifacts.append(
                self.report_store.write_markdown(
                    research_run.research_run_id,
                    "research_report.md",
                    compose_research_report_markdown(research_run),
                    ReportArtifactType.RESEARCH_REPORT_MARKDOWN,
                )
            )

        metadata_run = research_run.model_copy(update={"artifacts": artifacts})
        metadata_artifact = self.report_store.write_json(
            research_run.research_run_id,
            "research_metadata.json",
            metadata_run,
            ReportArtifactType.RESEARCH_METADATA,
        )
        return metadata_run.model_copy(update={"artifacts": [metadata_artifact, *artifacts]})

    def _list_research_runs(self) -> list[ResearchRun]:
        runs = []
        for run_id in self.report_store.list_run_ids():
            metadata_path = self.report_store.run_path(run_id) / "research_metadata.json"
            if metadata_path.exists():
                runs.append(
                    ResearchRun.model_validate(
                        json.loads(metadata_path.read_text(encoding="utf-8"))
                    )
                )
        return runs


def _asset_summary_frame(research_run: ResearchRun) -> pl.DataFrame:
    records: list[dict[str, Any]] = []
    for asset in research_run.assets:
        preflight = asset.preflight
        records.append(
            {
                "research_run_id": research_run.research_run_id,
                "symbol": asset.symbol,
                "provider": asset.provider,
                "asset_class": asset.asset_class.value,
                "status": asset.status.value,
                "classification": asset.classification.value,
                "preflight_status": preflight.status.value,
                "feature_path": preflight.feature_path,
                "row_count": preflight.row_count,
                "first_timestamp": preflight.first_timestamp,
                "last_timestamp": preflight.last_timestamp,
                "validation_run_id": asset.validation_run_id,
                "instructions": json.dumps(preflight.instructions, sort_keys=True),
                "warnings": json.dumps(asset.warnings, sort_keys=True),
                "limitations": json.dumps(asset.limitations, sort_keys=True),
            }
        )
    return pl.DataFrame(records, strict=False)


def _strategy_comparison_frame(research_run: ResearchRun) -> pl.DataFrame:
    records: list[dict[str, Any]] = []
    for row in collect_strategy_comparison(research_run.assets):
        records.append(
            {
                "research_run_id": research_run.research_run_id,
                "symbol": row.symbol,
                "provider": row.provider,
                "mode": row.mode,
                "category": row.category,
                "total_return_pct": row.total_return_pct,
                "max_drawdown_pct": row.max_drawdown_pct,
                "number_of_trades": row.number_of_trades,
                "profit_factor": row.profit_factor,
                "win_rate": row.win_rate,
                "notes": json.dumps(row.notes, sort_keys=True),
            }
        )
    return pl.DataFrame(
        records,
        schema={
            "research_run_id": pl.Utf8,
            "symbol": pl.Utf8,
            "provider": pl.Utf8,
            "mode": pl.Utf8,
            "category": pl.Utf8,
            "total_return_pct": pl.Float64,
            "max_drawdown_pct": pl.Float64,
            "number_of_trades": pl.Int64,
            "profit_factor": pl.Float64,
            "win_rate": pl.Float64,
            "notes": pl.Utf8,
        },
        strict=False,
    )


def _comparison_rows_from_frame(frame: pl.DataFrame) -> list[StrategyComparisonRow]:
    rows: list[StrategyComparisonRow] = []
    for row in frame.to_dicts():
        notes = row.get("notes") or "[]"
        try:
            parsed_notes = json.loads(notes)
        except json.JSONDecodeError:
            parsed_notes = [str(notes)]
        rows.append(
            StrategyComparisonRow(
                symbol=row["symbol"],
                provider=row["provider"],
                mode=row["mode"],
                category=row["category"],
                total_return_pct=row.get("total_return_pct"),
                max_drawdown_pct=row.get("max_drawdown_pct"),
                number_of_trades=row.get("number_of_trades") or 0,
                profit_factor=row.get("profit_factor"),
                win_rate=row.get("win_rate"),
                notes=parsed_notes,
            )
        )
    return rows
