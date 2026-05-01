"""Persistence helpers for grouped multi-asset research reports."""

import json
from typing import Any

import polars as pl

from src.backtest.report_store import ReportStore
from src.models.backtest import ReportArtifactType, ReportFormat
from src.models.research import (
    ConcentrationAssetRow,
    ConcentrationWarningLevel,
    RegimeCoverageAssetRow,
    ResearchAssetSummaryResponse,
    ResearchComparisonResponse,
    ResearchRun,
    ResearchRunListResponse,
    ResearchRunSummary,
    ResearchValidationAggregationResponse,
    StrategyComparisonRow,
    StressSurvivalRow,
    WalkForwardStabilityRow,
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
        try:
            return ResearchValidationAggregationResponse(
                research_run_id=research_run_id,
                stress=_stress_rows_from_frame(
                    self.report_store.read_parquet(research_run_id, "stress_summary.parquet")
                ),
                walk_forward=_walk_forward_rows_from_frame(
                    self.report_store.read_parquet(
                        research_run_id,
                        "walk_forward_summary.parquet",
                    )
                ),
                regime_coverage=_regime_rows_from_frame(
                    self.report_store.read_parquet(
                        research_run_id,
                        "regime_coverage_summary.parquet",
                    )
                ),
                concentration=_concentration_rows_from_frame(
                    self.report_store.read_parquet(
                        research_run_id,
                        "concentration_summary.parquet",
                    )
                ),
            )
        except FileNotFoundError:
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
            self.report_store.write_parquet(
                research_run.research_run_id,
                "stress_summary.parquet",
                _stress_summary_frame(research_run),
                ReportArtifactType.RESEARCH_STRESS_SUMMARY,
            ),
            self.report_store.write_parquet(
                research_run.research_run_id,
                "walk_forward_summary.parquet",
                _walk_forward_summary_frame(research_run),
                ReportArtifactType.RESEARCH_WALK_FORWARD_SUMMARY,
            ),
            self.report_store.write_parquet(
                research_run.research_run_id,
                "regime_coverage_summary.parquet",
                _regime_coverage_summary_frame(research_run),
                ReportArtifactType.RESEARCH_REGIME_COVERAGE_SUMMARY,
            ),
            self.report_store.write_parquet(
                research_run.research_run_id,
                "concentration_summary.parquet",
                _concentration_summary_frame(research_run),
                ReportArtifactType.RESEARCH_CONCENTRATION_SUMMARY,
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


def _stress_summary_frame(research_run: ResearchRun) -> pl.DataFrame:
    records = [
        {
            "research_run_id": research_run.research_run_id,
            "symbol": row.symbol,
            "mode": row.mode,
            "profile": row.profile,
            "outcome": row.outcome,
            "survived": row.survived,
            "notes": json.dumps(row.notes, sort_keys=True),
        }
        for row in collect_stress_survival(research_run.assets)
    ]
    return pl.DataFrame(
        records,
        schema={
            "research_run_id": pl.Utf8,
            "symbol": pl.Utf8,
            "mode": pl.Utf8,
            "profile": pl.Utf8,
            "outcome": pl.Utf8,
            "survived": pl.Boolean,
            "notes": pl.Utf8,
        },
        strict=False,
    )


def _walk_forward_summary_frame(research_run: ResearchRun) -> pl.DataFrame:
    records = [
        {
            "research_run_id": research_run.research_run_id,
            "symbol": row.symbol,
            "split_id": row.split_id,
            "status": row.status,
            "row_count": row.row_count,
            "trade_count": row.trade_count,
            "stable": row.stable,
            "notes": json.dumps(row.notes, sort_keys=True),
        }
        for row in collect_walk_forward_stability(research_run.assets)
    ]
    return pl.DataFrame(
        records,
        schema={
            "research_run_id": pl.Utf8,
            "symbol": pl.Utf8,
            "split_id": pl.Utf8,
            "status": pl.Utf8,
            "row_count": pl.Int64,
            "trade_count": pl.Int64,
            "stable": pl.Boolean,
            "notes": pl.Utf8,
        },
        strict=False,
    )


def _regime_coverage_summary_frame(research_run: ResearchRun) -> pl.DataFrame:
    records = [
        {
            "research_run_id": research_run.research_run_id,
            "symbol": row.symbol,
            "regime": row.regime,
            "bar_count": row.bar_count,
            "trade_count": row.trade_count,
            "return_pct": row.return_pct,
            "notes": json.dumps(row.notes, sort_keys=True),
        }
        for row in collect_regime_coverage(research_run.assets)
    ]
    return pl.DataFrame(
        records,
        schema={
            "research_run_id": pl.Utf8,
            "symbol": pl.Utf8,
            "regime": pl.Utf8,
            "bar_count": pl.Int64,
            "trade_count": pl.Int64,
            "return_pct": pl.Float64,
            "notes": pl.Utf8,
        },
        strict=False,
    )


def _concentration_summary_frame(research_run: ResearchRun) -> pl.DataFrame:
    records = [
        {
            "research_run_id": research_run.research_run_id,
            "symbol": row.symbol,
            "top_1_profit_contribution_pct": row.top_1_profit_contribution_pct,
            "top_5_profit_contribution_pct": row.top_5_profit_contribution_pct,
            "top_10_profit_contribution_pct": row.top_10_profit_contribution_pct,
            "max_consecutive_losses": row.max_consecutive_losses,
            "drawdown_recovery_status": row.drawdown_recovery_status,
            "warning_level": row.warning_level.value,
            "notes": json.dumps(row.notes, sort_keys=True),
        }
        for row in collect_concentration(research_run.assets)
    ]
    return pl.DataFrame(
        records,
        schema={
            "research_run_id": pl.Utf8,
            "symbol": pl.Utf8,
            "top_1_profit_contribution_pct": pl.Float64,
            "top_5_profit_contribution_pct": pl.Float64,
            "top_10_profit_contribution_pct": pl.Float64,
            "max_consecutive_losses": pl.Int64,
            "drawdown_recovery_status": pl.Utf8,
            "warning_level": pl.Utf8,
            "notes": pl.Utf8,
        },
        strict=False,
    )


def _notes_from_json(value) -> list[str]:
    notes = value or "[]"
    try:
        parsed = json.loads(notes)
    except json.JSONDecodeError:
        return [str(notes)]
    return parsed if isinstance(parsed, list) else [str(parsed)]


def _stress_rows_from_frame(frame: pl.DataFrame) -> list[StressSurvivalRow]:
    return [
        StressSurvivalRow(
            symbol=row["symbol"],
            mode=row["mode"],
            profile=row["profile"],
            outcome=row["outcome"],
            survived=row.get("survived"),
            notes=_notes_from_json(row.get("notes")),
        )
        for row in frame.to_dicts()
    ]


def _walk_forward_rows_from_frame(frame: pl.DataFrame) -> list[WalkForwardStabilityRow]:
    return [
        WalkForwardStabilityRow(
            symbol=row["symbol"],
            split_id=row["split_id"],
            status=row["status"],
            row_count=row["row_count"],
            trade_count=row.get("trade_count") or 0,
            stable=row.get("stable"),
            notes=_notes_from_json(row.get("notes")),
        )
        for row in frame.to_dicts()
    ]


def _regime_rows_from_frame(frame: pl.DataFrame) -> list[RegimeCoverageAssetRow]:
    return [
        RegimeCoverageAssetRow(
            symbol=row["symbol"],
            regime=row["regime"],
            bar_count=row["bar_count"],
            trade_count=row.get("trade_count") or 0,
            return_pct=row.get("return_pct"),
            notes=_notes_from_json(row.get("notes")),
        )
        for row in frame.to_dicts()
    ]


def _concentration_rows_from_frame(frame: pl.DataFrame) -> list[ConcentrationAssetRow]:
    return [
        ConcentrationAssetRow(
            symbol=row["symbol"],
            top_1_profit_contribution_pct=row.get("top_1_profit_contribution_pct"),
            top_5_profit_contribution_pct=row.get("top_5_profit_contribution_pct"),
            top_10_profit_contribution_pct=row.get("top_10_profit_contribution_pct"),
            max_consecutive_losses=row.get("max_consecutive_losses") or 0,
            drawdown_recovery_status=row["drawdown_recovery_status"],
            warning_level=ConcentrationWarningLevel(row["warning_level"]),
            notes=_notes_from_json(row.get("notes")),
        )
        for row in frame.to_dicts()
    ]
