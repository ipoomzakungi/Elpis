import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel

from src.config import get_reports_path
from src.models.backtest import (
    ArtifactFormat,
    BacktestRun,
    BacktestRunSummary,
    EquityPoint,
    MetricsSummary,
    ReportArtifact,
    ReportArtifactType,
    ReportFormat,
    TradeRecord,
)
from src.reports.writer import (
    NO_INTRABAR_LIMITATION,
    RESEARCH_ONLY_WARNING,
    compose_report_json,
    compose_report_markdown,
)

DEFAULT_LIMITATIONS = [
    RESEARCH_ONLY_WARNING,
    NO_INTRABAR_LIMITATION,
    "Signals are simulated at the next bar open; no intrabar tick order is inferred.",
    "v0 assumes no leverage, no compounding, and at most one open position per strategy mode.",
]


class ReportStoreError(RuntimeError):
    """Raised when report artifacts cannot be read or written safely."""


class ReportStore:
    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or get_reports_path()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def run_path(self, run_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
            raise ReportStoreError("run_id must be filesystem-safe")
        path = self.base_path / run_id
        base = self.base_path.resolve()
        resolved = path.resolve()
        if base != resolved and base not in resolved.parents:
            raise ReportStoreError("run_id resolves outside data/reports")
        return path

    def create_run_dir(self, run_id: str) -> Path:
        path = self.run_path(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(
        self,
        run_id: str,
        filename: str,
        payload: dict[str, Any] | BaseModel,
        artifact_type: ReportArtifactType,
    ) -> ReportArtifact:
        path = self.create_run_dir(run_id) / filename
        content = json.dumps(_to_jsonable(payload), indent=2, sort_keys=True)
        path.write_text(content + "\n", encoding="utf-8")
        return self._artifact(
            artifact_type=artifact_type,
            path=path,
            artifact_format=ArtifactFormat.JSON,
            content=content.encode("utf-8"),
        )

    def read_json(self, run_id: str, filename: str) -> dict[str, Any]:
        path = self.run_path(run_id) / filename
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def write_markdown(
        self,
        run_id: str,
        filename: str,
        content: str,
        artifact_type: ReportArtifactType = ReportArtifactType.REPORT_MARKDOWN,
    ) -> ReportArtifact:
        path = self.create_run_dir(run_id) / filename
        path.write_text(content, encoding="utf-8")
        return self._artifact(
            artifact_type=artifact_type,
            path=path,
            artifact_format=ArtifactFormat.MARKDOWN,
            content=content.encode("utf-8"),
        )

    def write_parquet(
        self,
        run_id: str,
        filename: str,
        data: pl.DataFrame,
        artifact_type: ReportArtifactType,
    ) -> ReportArtifact:
        path = self.create_run_dir(run_id) / filename
        data.write_parquet(path)
        content = path.read_bytes()
        return self._artifact(
            artifact_type=artifact_type,
            path=path,
            artifact_format=ArtifactFormat.PARQUET,
            rows=len(data),
            content=content,
        )

    def read_parquet(self, run_id: str, filename: str) -> pl.DataFrame:
        path = self.run_path(run_id) / filename
        if not path.exists():
            raise FileNotFoundError(path)
        return pl.read_parquet(path)

    def list_run_ids(self) -> list[str]:
        if not self.base_path.exists():
            return []
        return sorted(path.name for path in self.base_path.iterdir() if path.is_dir())

    def list_metadata(self) -> list[dict[str, Any]]:
        runs = []
        for run_id in self.list_run_ids():
            metadata_path = self.run_path(run_id) / "metadata.json"
            if metadata_path.exists():
                runs.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        return runs

    def list_run_summaries(self) -> list[BacktestRunSummary]:
        summaries: list[BacktestRunSummary] = []
        for run in self.list_runs():
            metrics = self._read_optional_metrics(run.run_id)
            summaries.append(
                BacktestRunSummary(
                    run_id=run.run_id,
                    status=run.status,
                    created_at=run.created_at,
                    symbol=run.symbol,
                    provider=run.provider,
                    timeframe=run.timeframe,
                    strategy_modes=[
                        strategy.mode
                        for strategy in run.config.strategies
                        if strategy.enabled
                    ],
                    baseline_modes=list(run.config.baselines),
                    total_return_pct=metrics.total_return_pct if metrics else None,
                    max_drawdown_pct=metrics.max_drawdown_pct if metrics else None,
                )
            )
        return sorted(summaries, key=lambda summary: summary.created_at, reverse=True)

    def list_runs(self) -> list[BacktestRun]:
        runs = []
        for metadata in self.list_metadata():
            runs.append(BacktestRun.model_validate(metadata))
        return runs

    def read_run(self, run_id: str) -> BacktestRun:
        return BacktestRun.model_validate(self.read_json(run_id, "metadata.json"))

    def read_metrics_summary(self, run_id: str) -> MetricsSummary:
        return MetricsSummary.model_validate(self.read_json(run_id, "metrics.json"))

    def read_trades_log(self, run_id: str, limit: int, offset: int) -> tuple[list[TradeRecord], int]:
        frame = self.read_parquet(run_id, "trades.parquet")
        total = frame.height
        rows = frame.slice(offset, limit).to_dicts()
        trades = []
        for row in rows:
            snapshot = row.get("assumptions_snapshot")
            if isinstance(snapshot, str):
                row["assumptions_snapshot"] = json.loads(snapshot)
            trades.append(TradeRecord.model_validate(row))
        return trades, min(max(total - offset, 0), limit)

    def read_equity_curve(self, run_id: str) -> list[EquityPoint]:
        frame = self.read_parquet(run_id, "equity.parquet")
        return [EquityPoint.model_validate(row) for row in frame.to_dicts()]

    def write_run_outputs(
        self,
        run: BacktestRun,
        trades: list[TradeRecord],
        equity_curve: list[EquityPoint],
        metrics: MetricsSummary,
        report_format: ReportFormat,
    ) -> BacktestRun:
        run = self._enrich_run_metadata(run)
        artifacts = [
            self.write_json(
                run.run_id,
                "config.json",
                run.config,
                ReportArtifactType.CONFIG,
            ),
            self.write_parquet(
                run.run_id,
                "trades.parquet",
                _trades_frame(trades),
                ReportArtifactType.TRADES,
            ),
            self.write_parquet(
                run.run_id,
                "equity.parquet",
                _equity_frame(equity_curve),
                ReportArtifactType.EQUITY,
            ),
            self.write_json(run.run_id, "metrics.json", metrics, ReportArtifactType.METRICS),
        ]

        report_payload = compose_report_json(run=run, metrics=metrics, extra_notes=metrics.notes)
        if report_format in {ReportFormat.JSON, ReportFormat.BOTH}:
            artifacts.append(
                self.write_json(
                    run.run_id,
                    "report.json",
                    report_payload,
                    ReportArtifactType.REPORT_JSON,
                )
            )
        if report_format in {ReportFormat.MARKDOWN, ReportFormat.BOTH}:
            artifacts.append(
                self.write_markdown(
                    run.run_id,
                    "report.md",
                    compose_report_markdown(run=run, metrics=metrics, extra_notes=metrics.notes),
                )
            )

        metadata_run = run.model_copy(update={"artifacts": artifacts})
        metadata_artifact = self.write_json(
            run.run_id,
            "metadata.json",
            metadata_run,
            ReportArtifactType.METADATA,
        )
        return run.model_copy(update={"artifacts": [metadata_artifact, *artifacts]})

    def _enrich_run_metadata(self, run: BacktestRun) -> BacktestRun:
        updates: dict[str, Any] = {}
        if run.config_hash is None:
            updates["config_hash"] = _stable_hash(run.config.model_dump(mode="json"))
        if not run.data_identity:
            updates["data_identity"] = _source_data_identity(run)
        if not run.limitations:
            updates["limitations"] = DEFAULT_LIMITATIONS
        if not updates:
            return run
        return run.model_copy(update=updates)

    def _read_optional_metrics(self, run_id: str) -> MetricsSummary | None:
        try:
            return self.read_metrics_summary(run_id)
        except FileNotFoundError:
            return None

    def _artifact(
        self,
        artifact_type: ReportArtifactType,
        path: Path,
        artifact_format: ArtifactFormat,
        content: bytes,
        rows: int | None = None,
    ) -> ReportArtifact:
        return ReportArtifact(
            artifact_type=artifact_type,
            path=_project_relative_path(path),
            format=artifact_format,
            rows=rows,
            created_at=datetime.utcnow(),
            content_hash=hashlib.sha256(content).hexdigest(),
        )


def _to_jsonable(value: dict[str, Any] | BaseModel) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _stable_hash(payload: dict[str, Any]) -> str:
    content = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _source_data_identity(run: BacktestRun) -> dict[str, Any]:
    feature_path = Path(run.feature_path)
    identity: dict[str, Any] = {
        "provider": run.provider,
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "feature_path": run.feature_path,
        "exists": feature_path.exists(),
    }
    if not feature_path.exists():
        return identity

    frame = pl.read_parquet(feature_path)
    sorted_frame = frame.sort("timestamp") if "timestamp" in frame.columns else frame
    identity.update(
        {
            "row_count": frame.height,
            "first_timestamp": _timestamp_to_text(sorted_frame["timestamp"][0])
            if "timestamp" in sorted_frame.columns and frame.height
            else None,
            "last_timestamp": _timestamp_to_text(sorted_frame["timestamp"][-1])
            if "timestamp" in sorted_frame.columns and frame.height
            else None,
            "columns": list(frame.columns),
            "content_hash": hashlib.sha256(feature_path.read_bytes()).hexdigest(),
        }
    )
    return identity


def _timestamp_to_text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _trades_frame(trades: list[TradeRecord]) -> pl.DataFrame:
    records = []
    for trade in trades:
        record = trade.model_dump(mode="python")
        record["strategy_mode"] = str(record["strategy_mode"])
        record["side"] = str(record["side"])
        record["exit_reason"] = str(record["exit_reason"])
        record["assumptions_snapshot"] = json.dumps(record["assumptions_snapshot"], sort_keys=True)
        records.append(record)
    return pl.DataFrame(records, schema=_trade_schema(), strict=False)


def _equity_frame(equity_curve: list[EquityPoint]) -> pl.DataFrame:
    records = []
    for point in equity_curve:
        record = point.model_dump(mode="python")
        record["strategy_mode"] = str(record["strategy_mode"])
        records.append(record)
    return pl.DataFrame(records, schema=_equity_schema(), strict=False)


def _trade_schema() -> dict[str, pl.DataType]:
    return {
        "trade_id": pl.Utf8,
        "run_id": pl.Utf8,
        "strategy_mode": pl.Utf8,
        "provider": pl.Utf8,
        "symbol": pl.Utf8,
        "timeframe": pl.Utf8,
        "side": pl.Utf8,
        "regime_at_signal": pl.Utf8,
        "signal_timestamp": pl.Datetime,
        "entry_timestamp": pl.Datetime,
        "entry_price": pl.Float64,
        "exit_timestamp": pl.Datetime,
        "exit_price": pl.Float64,
        "exit_reason": pl.Utf8,
        "quantity": pl.Float64,
        "notional": pl.Float64,
        "gross_pnl": pl.Float64,
        "fees": pl.Float64,
        "slippage": pl.Float64,
        "net_pnl": pl.Float64,
        "return_pct": pl.Float64,
        "holding_bars": pl.Int64,
        "assumptions_snapshot": pl.Utf8,
    }


def _equity_schema() -> dict[str, pl.DataType]:
    return {
        "timestamp": pl.Datetime,
        "strategy_mode": pl.Utf8,
        "equity": pl.Float64,
        "drawdown": pl.Float64,
        "drawdown_pct": pl.Float64,
        "realized_pnl": pl.Float64,
        "open_position": pl.Boolean,
    }


def _project_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()
