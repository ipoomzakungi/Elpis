from typing import Any

from pydantic import BaseModel

from src.models.backtest import BacktestRun, MetricsSummary, ValidationRun
from src.models.research import ResearchRun

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
        "source_identity": run_payload.get("data_identity", {}),
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
        "regime_coverage_summary": {
            "bar_counts": run_payload.get("regime_coverage", {}).get("bar_counts", {}),
            "trades_per_regime": run_payload.get("regime_coverage", {}).get(
                "trades_per_regime", {}
            ),
            "notes": run_payload.get("regime_coverage", {}).get("coverage_notes", []),
        },
        "concentration_report": run_payload.get("concentration_report", {}),
        "concentration_summary": {
            "top_1_profit_contribution_pct": run_payload.get("concentration_report", {}).get(
                "top_1_profit_contribution_pct"
            ),
            "top_5_profit_contribution_pct": run_payload.get("concentration_report", {}).get(
                "top_5_profit_contribution_pct"
            ),
            "top_10_profit_contribution_pct": run_payload.get("concentration_report", {}).get(
                "top_10_profit_contribution_pct"
            ),
            "max_consecutive_losses": run_payload.get("concentration_report", {}).get(
                "max_consecutive_losses", 0
            ),
            "drawdown_recovery_status": run_payload.get("concentration_report", {}).get(
                "drawdown_recovery_status"
            ),
        },
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
        "## Source Identity",
        "",
        f"Source kind: {report['data_identity'].get('source_kind')}",
        f"Feature path: {report['data_identity'].get('feature_path')}",
        f"Rows: {report['data_identity'].get('row_count')}",
        f"First timestamp: {report['data_identity'].get('first_timestamp')}",
        f"Last timestamp: {report['data_identity'].get('last_timestamp')}",
        f"Content hash: {report['data_identity'].get('content_hash')}",
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
            "## Regime Coverage",
            "",
        ]
    )
    coverage = report["regime_coverage"]
    for regime, count in coverage.get("bar_counts", {}).items():
        trade_count = coverage.get("trades_per_regime", {}).get(regime, 0)
        lines.append(f"- {regime}: bars {count}, trades {trade_count}")
    lines.extend(
        [
            "",
            "## Trade Concentration",
            "",
        ]
    )
    concentration = report["concentration_report"]
    lines.extend(
        [
            f"Top 1 profit contribution %: {concentration.get('top_1_profit_contribution_pct')}",
            f"Top 5 profit contribution %: {concentration.get('top_5_profit_contribution_pct')}",
            f"Top 10 profit contribution %: {concentration.get('top_10_profit_contribution_pct')}",
            f"Max consecutive losses: {concentration.get('max_consecutive_losses')}",
            f"Drawdown recovery status: {concentration.get('drawdown_recovery_status')}",
        ]
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


def compose_research_report_json(
    research_run: ResearchRun | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Compose a grouped multi-asset research report payload.

    Phase 1/2 exposes the report contract only; story phases populate the
    asset-level and aggregation sections.
    """
    notes = [RESEARCH_ONLY_WARNING]
    if extra_notes:
        notes.extend(extra_notes)

    run_payload = _to_jsonable(research_run)
    assets = run_payload.get("assets", [])
    strategy_comparison = []
    stress = []
    walk_forward = []
    regime_coverage = []
    concentration = []
    classification_summary = {}
    for asset in assets:
        if isinstance(asset, dict):
            strategy_comparison.extend(asset.get("strategy_comparison", []))
            stress.extend(asset.get("stress_summary", []))
            walk_forward.extend(asset.get("walk_forward_summary", []))
            regime_coverage.extend(asset.get("regime_coverage_summary", []))
            concentration.extend(asset.get("concentration_summary", []))
            classification = asset.get("classification")
            if classification:
                classification_summary[classification] = (
                    classification_summary.get(classification, 0) + 1
                )
    return {
        "research_run": run_payload,
        "research_disclaimer": RESEARCH_ONLY_WARNING,
        "assets": assets,
        "strategy_comparison": strategy_comparison,
        "validation_summary": {
            "stress": stress,
            "walk_forward": walk_forward,
            "regime_coverage": regime_coverage,
            "concentration": concentration,
            "classification_summary": classification_summary,
        },
        "comparison_semantics": (
            "Strategy and baseline rows are independent per-asset comparisons, "
            "not a combined portfolio result."
        ),
        "validation_semantics": (
            "Validation sections are robustness diagnostics only and do not imply "
            "profitability, predictive power, safety, or live readiness."
        ),
        "warnings": run_payload.get("warnings", []),
        "limitations": run_payload.get("limitations", []),
        "notes": notes,
    }


def compose_research_report_markdown(
    research_run: ResearchRun | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> str:
    report = compose_research_report_json(research_run, extra_notes=extra_notes)
    run_payload = report["research_run"]
    lines = [
        "# Multi-Asset Research Report",
        "",
        f"Research Run ID: {run_payload.get('research_run_id', 'unknown')}",
        f"Status: {run_payload.get('status', 'unknown')}",
        f"Completed assets: {run_payload.get('completed_count', 0)}",
        f"Blocked assets: {run_payload.get('blocked_count', 0)}",
        "",
        "## Assets",
        "",
    ]
    for asset in report["assets"]:
        lines.append(
            f"- {asset.get('symbol')} ({asset.get('provider')}): "
            f"{asset.get('status')} / {asset.get('classification')}"
        )
        preflight = asset.get("preflight", {})
        instructions = preflight.get("instructions", []) if isinstance(preflight, dict) else []
        for instruction in instructions:
            lines.append(f"  - {instruction}")
    lines.extend(
        [
            "",
            "## Strategy/Baseline Comparison",
            "",
            report["comparison_semantics"],
            "",
        ]
    )
    if not report["strategy_comparison"]:
        lines.append("- No strategy/baseline comparison rows were generated.")
    for row in report["strategy_comparison"]:
        lines.append(
            f"- {row.get('symbol')} / {row.get('mode')} ({row.get('category')}): "
            f"total return % {row.get('total_return_pct')}, "
            f"max drawdown % {row.get('max_drawdown_pct')}, "
            f"trades {row.get('number_of_trades')}"
        )
    validation = report["validation_summary"]
    lines.extend(
        [
            "",
            "## Validation Aggregation",
            "",
            report["validation_semantics"],
            "",
            "### Stress Survival",
            "",
        ]
    )
    if not validation["stress"]:
        lines.append("- No stress summary rows were generated.")
    for row in validation["stress"]:
        lines.append(
            f"- {row.get('symbol')} / {row.get('mode')} / {row.get('profile')}: "
            f"outcome {row.get('outcome')}, survived {row.get('survived')}"
        )
    lines.extend(["", "### Walk-Forward Stability", ""])
    if not validation["walk_forward"]:
        lines.append("- No walk-forward summary rows were generated.")
    for row in validation["walk_forward"]:
        lines.append(
            f"- {row.get('symbol')} / {row.get('split_id')}: "
            f"status {row.get('status')}, rows {row.get('row_count')}, "
            f"trades {row.get('trade_count')}, stable {row.get('stable')}"
        )
    lines.extend(["", "### Regime Coverage", ""])
    if not validation["regime_coverage"]:
        lines.append("- No regime coverage rows were generated.")
    for row in validation["regime_coverage"]:
        lines.append(
            f"- {row.get('symbol')} / {row.get('regime')}: bars {row.get('bar_count')}, "
            f"trades {row.get('trade_count')}, return % {row.get('return_pct')}"
        )
    lines.extend(["", "### Trade Concentration", ""])
    if not validation["concentration"]:
        lines.append("- No concentration rows were generated.")
    for row in validation["concentration"]:
        lines.append(
            f"- {row.get('symbol')}: warning {row.get('warning_level')}, "
            f"top 1 contribution % {row.get('top_1_profit_contribution_pct')}, "
            f"max consecutive losses {row.get('max_consecutive_losses')}"
        )
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"


def compose_research_execution_evidence_json(
    execution_run: BaseModel | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Compose a research-only execution evidence report payload."""

    notes = [RESEARCH_ONLY_WARNING]
    if extra_notes:
        notes.extend(extra_notes)

    run_payload = _to_jsonable(execution_run)
    evidence = run_payload.get("evidence_summary") or run_payload
    return {
        "execution_run": run_payload,
        "evidence_summary": evidence,
        "research_disclaimer": (
            "Evidence labels are research decisions only and do not imply profitability, "
            "predictive power, safety, or live readiness."
        ),
        "workflow_results": evidence.get("workflow_results", []),
        "crypto_summary": evidence.get("crypto_summary"),
        "missing_data_checklist": evidence.get("missing_data_checklist", []),
        "limitations": evidence.get("limitations", []),
        "research_only_warnings": evidence.get("research_only_warnings", []),
        "notes": notes,
    }


def compose_research_execution_evidence_markdown(
    execution_run: BaseModel | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> str:
    """Compose a research-only execution evidence Markdown report."""

    report = compose_research_execution_evidence_json(execution_run, extra_notes=extra_notes)
    run_payload = report["execution_run"]
    evidence = report["evidence_summary"]
    lines = [
        "# Research Execution Evidence Report",
        "",
        f"Execution Run ID: {run_payload.get('execution_run_id', 'unknown')}",
        f"Status: {evidence.get('status', run_payload.get('status', 'unknown'))}",
        f"Decision: {evidence.get('decision', run_payload.get('decision', 'unknown'))}",
        "",
        "## Research-Only Disclaimer",
        "",
        report["research_disclaimer"],
        "",
        "## Workflow Results",
        "",
    ]
    if not report["workflow_results"]:
        lines.append("- No workflow evidence rows were generated.")
    for workflow in report["workflow_results"]:
        lines.append(
            f"- {workflow.get('workflow_type')}: {workflow.get('status')} / "
            f"{workflow.get('decision')} - {workflow.get('decision_reason')}"
        )
    lines.extend(["", "## Crypto Workflow", ""])
    crypto_summary = report["crypto_summary"] or {}
    if not crypto_summary:
        lines.append("- No crypto workflow summary was generated.")
    else:
        lines.extend(
            [
                f"- Completed assets: {crypto_summary.get('completed_asset_count', 0)}",
                f"- Blocked assets: {crypto_summary.get('blocked_asset_count', 0)}",
                f"- Ready assets: {', '.join(crypto_summary.get('ready_assets', [])) or 'None'}",
                (
                    f"- Blocked asset list: "
                    f"{', '.join(crypto_summary.get('blocked_assets', [])) or 'None'}"
                ),
            ]
        )
    lines.extend(["", "## Missing Data Checklist", ""])
    if not report["missing_data_checklist"]:
        lines.append("- None")
    lines.extend(f"- {item}" for item in report["missing_data_checklist"])
    lines.extend(["", "## Limitations", ""])
    if not report["limitations"]:
        lines.append("- None")
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"


def compose_xau_report_json(
    xau_report: BaseModel | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> dict[str, Any]:
    """Compose a research-only XAU Vol-OI report payload.

    Early feature slices populate source validation and preflight metadata. Later
    slices fill wall and zone rows.
    """

    notes = [RESEARCH_ONLY_WARNING]
    if extra_notes:
        notes.extend(extra_notes)

    report_payload = _to_jsonable(xau_report)
    return {
        "report": report_payload,
        "research_disclaimer": (
            "XAU Vol-OI walls and zones are research annotations only and do not imply "
            "profitability, predictive power, safety, or live readiness."
        ),
        "source_validation": report_payload.get("source_validation", {}),
        "basis_snapshot": report_payload.get("basis_snapshot"),
        "expected_range": report_payload.get("expected_range"),
        "walls": report_payload.get("walls", []),
        "zones": report_payload.get("zones", []),
        "warnings": report_payload.get("warnings", []),
        "limitations": report_payload.get("limitations", []),
        "missing_data_instructions": report_payload.get("missing_data_instructions", []),
        "notes": notes,
    }


def compose_xau_report_markdown(
    xau_report: BaseModel | dict[str, Any],
    extra_notes: list[str] | None = None,
) -> str:
    report = compose_xau_report_json(xau_report, extra_notes=extra_notes)
    report_payload = report["report"]
    source_validation = report["source_validation"]
    basis_snapshot = report["basis_snapshot"] or {}
    expected_range = report["expected_range"] or {}
    lines = [
        "# XAU Vol-OI Wall Report",
        "",
        f"Report ID: {report_payload.get('report_id', 'unknown')}",
        f"Status: {report_payload.get('status', 'unknown')}",
        f"Session date: {report_payload.get('session_date')}",
        "",
        "## Research-Only Disclaimer",
        "",
        report["research_disclaimer"],
        "",
        "## Source Validation",
        "",
        f"Source rows: {source_validation.get('source_row_count', 0)}",
        f"Accepted rows: {source_validation.get('accepted_row_count', 0)}",
        f"Rejected rows: {source_validation.get('rejected_row_count', 0)}",
        "",
        "## Basis Snapshot",
        "",
        f"Basis: {basis_snapshot.get('basis')}",
        f"Basis source: {basis_snapshot.get('basis_source')}",
        f"Mapping available: {basis_snapshot.get('mapping_available')}",
        "",
        "## Expected Range",
        "",
        f"Source: {expected_range.get('source')}",
        f"Expected move: {expected_range.get('expected_move')}",
        f"Lower 1SD: {expected_range.get('lower_1sd')}",
        f"Upper 1SD: {expected_range.get('upper_1sd')}",
        f"Lower 2SD: {expected_range.get('lower_2sd')}",
        f"Upper 2SD: {expected_range.get('upper_2sd')}",
        f"Unavailable reason: {expected_range.get('unavailable_reason')}",
        "",
    ]
    lines.extend(["## Basis-Adjusted OI Walls", ""])
    if not report["walls"]:
        lines.append("- No OI wall rows were generated.")
    for wall in report["walls"]:
        lines.append(
            f"- {wall.get('wall_id')}: {wall.get('option_type')} wall, "
            f"expiry {wall.get('expiry')}, strike {wall.get('strike')}, "
            f"spot-equivalent {wall.get('spot_equivalent_level')}, "
            f"score {wall.get('wall_score')}, freshness {wall.get('freshness_status')}"
        )

    lines.extend(["", "## Zone Classification", ""])
    if not report["zones"]:
        lines.append("- No zone rows were generated.")
    for zone in report["zones"]:
        lines.append(
            f"- {zone.get('zone_id')}: {zone.get('zone_type')}, "
            f"level {zone.get('level')}, confidence {zone.get('confidence')}, "
            f"no-trade warning {zone.get('no_trade_warning')}"
        )
        for note in zone.get("notes", []):
            lines.append(f"  - {note}")

    lines.extend(["", "## Missing Data Instructions", ""])
    if not report["missing_data_instructions"]:
        lines.append("- None")
    lines.extend(f"- {instruction}" for instruction in report["missing_data_instructions"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"
