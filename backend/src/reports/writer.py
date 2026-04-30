from typing import Any

from pydantic import BaseModel

from src.models.backtest import BacktestRun, MetricsSummary, ValidationRun

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

    metrics_payload = _to_jsonable(metrics) if metrics is not None else None
    run_payload = _to_jsonable(run)
    config_payload = run_payload.get("config", {}) if isinstance(run_payload, dict) else {}
    return {
        "run": run_payload,
        "research_disclaimer": RESEARCH_ONLY_WARNING,
        "assumptions": config_payload.get("assumptions", {}),
        "data_identity": run_payload.get("data_identity", {}),
        "config_hash": run_payload.get("config_hash"),
        "limitations": run_payload.get("limitations", [NO_INTRABAR_LIMITATION]),
        "metrics": metrics_payload,
        "return_by_regime": (metrics_payload or {}).get("return_by_regime", {}),
        "return_by_strategy_mode": (metrics_payload or {}).get("return_by_strategy_mode", {}),
        "return_by_symbol_provider": (metrics_payload or {}).get("return_by_symbol_provider", {}),
        "baseline_comparison": (metrics_payload or {}).get("baseline_comparison", []),
        "mode_comparison_label": (
            "Strategy and baseline modes are independent comparisons, not a combined portfolio."
        ),
        "equity_basis_note": (
            "Equity uses total mark-to-market values while positions are open and realized-only "
            "values when no position is open."
        ),
        "notional_cap_note": (
            "No-leverage cap events are recorded in trade assumptions_snapshot.sizing when present."
        ),
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
    total_return_pct = metrics_payload.get("total_return_pct")
    total_return_display = "n/a" if total_return_pct is None else total_return_pct
    lines = [
        "# Backtest Report",
        "",
        f"Run ID: {run_payload.get('run_id', 'unknown')}",
        f"Status: {run_payload.get('status', 'unknown')}",
        f"Symbol: {run_payload.get('symbol', 'unknown')}",
        f"Timeframe: {run_payload.get('timeframe', 'unknown')}",
        f"Config hash: {report.get('config_hash')}",
        "",
        "## Data Identity",
        "",
        f"Provider: {report['data_identity'].get('provider')}",
        f"Feature path: {report['data_identity'].get('feature_path')}",
        f"Rows: {report['data_identity'].get('row_count')}",
        f"Content hash: {report['data_identity'].get('content_hash')}",
        "",
        "## Assumptions",
        "",
        f"Fee rate: {report['assumptions'].get('fee_rate')}",
        f"Slippage rate: {report['assumptions'].get('slippage_rate')}",
        f"Risk per trade: {report['assumptions'].get('risk_per_trade')}",
        f"Max positions: {report['assumptions'].get('max_positions')}",
        f"Leverage: {report['assumptions'].get('leverage')}",
        f"Compounding: {report['assumptions'].get('allow_compounding')}",
        "",
        "## Summary Metrics",
        "",
        f"Total return %: {total_return_display}",
        f"Max drawdown %: {metrics_payload.get('max_drawdown_pct')}",
        f"Trades: {metrics_payload.get('number_of_trades')}",
        "",
        "## Mode Comparison Semantics",
        "",
        report["mode_comparison_label"],
        report["equity_basis_note"],
        report["notional_cap_note"],
        "",
        "## Strategy Mode Performance",
        "",
    ]
    for strategy_mode, summary in report["return_by_strategy_mode"].items():
        lines.append(
            f"- {strategy_mode}: total return % {summary.get('total_return_pct')}, "
            f"trades {summary.get('number_of_trades')}, "
            f"category {summary.get('category')}, "
            f"equity basis {summary.get('equity_basis')}"
        )
    lines.extend(
        [
            "",
            "## Regime Performance",
            "",
        ]
    )
    for regime, summary in report["return_by_regime"].items():
        lines.append(
            f"- {regime}: return % {summary.get('return_pct_display')}, "
            f"trades {summary.get('number_of_trades')}"
        )
    lines.extend(
        [
            "",
            "## Baseline Comparison",
            "",
        ]
    )
    for row in report["baseline_comparison"]:
        lines.append(
            f"- {row.get('strategy_mode')}: {row.get('category')}, "
            f"total return % {row.get('total_return_pct')}, "
            f"max drawdown % {row.get('max_drawdown_pct')}"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(
        [
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"


def compose_validation_report_json(
    validation_run: ValidationRun | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    notes = [RESEARCH_ONLY_WARNING, NO_INTRABAR_LIMITATION]
    if extra_notes:
        notes.extend(extra_notes)

    run_payload = _to_jsonable(validation_run)
    return {
        "validation_run": run_payload,
        "research_disclaimer": RESEARCH_ONLY_WARNING,
        "data_identity": run_payload.get("data_identity", {}),
        "mode_metrics": run_payload.get("mode_metrics", []),
        "stress_results": run_payload.get("stress_results", []),
        "stress_summary": {
            "row_count": len(run_payload.get("stress_results", [])),
            "profiles": sorted(
                {
                    row.get("profile", {}).get("name")
                    for row in run_payload.get("stress_results", [])
                    if row.get("profile", {}).get("name")
                }
            ),
        },
        "sensitivity_results": run_payload.get("sensitivity_results", []),
        "sensitivity_summary": {
            "row_count": len(run_payload.get("sensitivity_results", [])),
            "fragile_count": len(
                [
                    row
                    for row in run_payload.get("sensitivity_results", [])
                    if row.get("fragility_flag")
                ]
            ),
        },
        "walk_forward_results": run_payload.get("walk_forward_results", []),
        "walk_forward_summary": {
            "row_count": len(run_payload.get("walk_forward_results", [])),
            "insufficient_count": len(
                [
                    row
                    for row in run_payload.get("walk_forward_results", [])
                    if row.get("status") == "insufficient_data"
                ]
            ),
        },
        "regime_coverage": run_payload.get("regime_coverage", {}),
        "concentration_report": run_payload.get("concentration_report", {}),
        "notional_cap_events": run_payload.get("notional_cap_events", []),
        "warnings": run_payload.get("warnings", []),
        "notes": notes,
    }


def compose_validation_report_markdown(
    validation_run: ValidationRun | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> str:
    report = compose_validation_report_json(validation_run, extra_notes=extra_notes)
    run_payload = report["validation_run"]
    lines = [
        "# Validation Report",
        "",
        f"Validation Run ID: {run_payload.get('validation_run_id', 'unknown')}",
        f"Status: {run_payload.get('status', 'unknown')}",
        f"Symbol: {run_payload.get('symbol', 'unknown')}",
        f"Timeframe: {run_payload.get('timeframe', 'unknown')}",
        "",
        "## Mode Metrics",
        "",
    ]
    for row in report["mode_metrics"]:
        lines.append(
            f"- {row.get('strategy_mode')}: {row.get('category')}, "
            f"total return % {row.get('total_return_pct')}, "
            f"max drawdown % {row.get('max_drawdown_pct')}"
        )
    lines.extend(
        [
            "",
            "## Cost Stress Results",
            "",
        ]
    )
    for row in report["stress_results"]:
        profile = row.get("profile", {})
        metrics = row.get("metrics", {})
        lines.append(
            f"- {profile.get('name')} / {row.get('strategy_mode')}: "
            f"outcome {row.get('outcome')}, total return % {metrics.get('total_return_pct')}, "
            f"trades {metrics.get('number_of_trades')}"
        )
    lines.extend(
        [
            "",
            "## Parameter Sensitivity",
            "",
        ]
    )
    for row in report["sensitivity_results"]:
        metrics = row.get("metrics", {})
        lines.append(
            f"- {row.get('parameter_set_id')} / {row.get('strategy_mode')}: "
            f"total return % {metrics.get('total_return_pct')}, "
            f"fragile {row.get('fragility_flag')}"
        )
    lines.extend(
        [
            "",
            "## Walk-Forward Splits",
            "",
            "Chronological validation windows only; no model training, paper trading, "
            "shadow trading, or live trading occurred.",
        ]
    )
    for row in report["walk_forward_results"]:
        lines.append(
            f"- {row.get('split_id')}: {row.get('start_timestamp')} to "
            f"{row.get('end_timestamp')}, rows {row.get('row_count')}, "
            f"trades {row.get('trade_count')}, status {row.get('status')}"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"
