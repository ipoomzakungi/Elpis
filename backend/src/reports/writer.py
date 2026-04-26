from typing import Any

from pydantic import BaseModel

from src.models.backtest import BacktestRun, MetricsSummary


RESEARCH_ONLY_WARNING = (
    "Backtest results are historical simulation outputs under documented assumptions only; "
    "they do not imply profitability, predictive power, safety, or live-trading readiness."
)

NO_INTRABAR_LIMITATION = (
    "v0 uses OHLC bars without intrabar tick ordering; when stop loss and take profit are both "
    "reachable in the same bar, the conservative stop-first policy is used."
)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def compose_report_json(
    run: BacktestRun | dict[str, Any],
    metrics: MetricsSummary | dict[str, Any] | None = None,
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    notes = [RESEARCH_ONLY_WARNING, NO_INTRABAR_LIMITATION]
    if extra_notes:
        notes.extend(extra_notes)

    return {
        "run": _to_jsonable(run),
        "metrics": _to_jsonable(metrics) if metrics is not None else None,
        "notes": notes,
    }


def compose_report_markdown(
    run: BacktestRun | dict[str, Any],
    metrics: MetricsSummary | dict[str, Any] | None = None,
    extra_notes: list[str] | None = None,
) -> str:
    report = compose_report_json(run=run, metrics=metrics, extra_notes=extra_notes)
    run_payload = report["run"]
    metrics_payload = report["metrics"] or {}
    lines = [
        "# Backtest Report",
        "",
        f"Run ID: {run_payload.get('run_id', 'unknown')}",
        f"Status: {run_payload.get('status', 'unknown')}",
        f"Symbol: {run_payload.get('symbol', 'unknown')}",
        f"Timeframe: {run_payload.get('timeframe', 'unknown')}",
        "",
        "## Summary Metrics",
        "",
        f"Total return %: {metrics_payload.get('total_return_pct')}",
        f"Max drawdown %: {metrics_payload.get('max_drawdown_pct')}",
        f"Trades: {metrics_payload.get('number_of_trades')}",
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"