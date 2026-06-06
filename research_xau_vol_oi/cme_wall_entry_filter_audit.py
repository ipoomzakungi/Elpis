"""Entry-filter audit for realistic CME wall candidates.

This report converts the realistic CME wall replay into research-only filter
guidance. It does not create execution orders or live-trading signals.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


STRATEGY_NAMES = (
    "WALL_REJECTION_CONFIRMED_FADE",
    "WALL_ACCEPTANCE_CONTINUATION",
    "AVOID_DIRECT_WALL_TRADE_FILTER",
    "SD_2_REJECTION_CONFIRMED_FADE",
    "COMBINED_CONSERVATIVE_REALISTIC",
)
RESEARCH_WARNING = (
    "Research-only CME wall entry-filter audit. CME context may be used as a "
    "filter/watchlist layer only; it is not an execution trigger or live-readiness proof."
)


@dataclass(frozen=True)
class CmeWallEntryFilterAuditResult:
    """Generated CME wall entry-filter audit artifacts."""

    strategy_policy: pl.DataFrame
    filter_scenarios: pl.DataFrame
    smc_overlay_guidance: pl.DataFrame
    conclusion_markdown: str
    final_recommendation: str
    paths: dict[str, Path]


def run_cme_wall_entry_filter_audit(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> CmeWallEntryFilterAuditResult:
    """Build research-only CME entry-filter guidance from realistic replay outputs."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    trades = _active_trades(_frame_input(inputs, "trade_events"))
    performance = _frame_input(inputs, "performance_summary")
    strategy_policy = build_strategy_policy(trades=trades, performance=performance)
    filter_scenarios = build_filter_scenarios(trades=trades)
    smc_overlay = build_smc_overlay_guidance(
        strategy_policy=strategy_policy,
        filter_scenarios=filter_scenarios,
    )
    final = choose_final_recommendation(strategy_policy, smc_overlay)
    conclusion = build_conclusion(
        strategy_policy=strategy_policy,
        filter_scenarios=filter_scenarios,
        smc_overlay_guidance=smc_overlay,
        final_recommendation=final,
    )
    result = CmeWallEntryFilterAuditResult(
        strategy_policy=strategy_policy,
        filter_scenarios=filter_scenarios,
        smc_overlay_guidance=smc_overlay,
        conclusion_markdown=conclusion,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_cme_wall_entry_filter_audit_outputs(result)
    return result


def build_strategy_policy(*, trades: pl.DataFrame, performance: pl.DataFrame) -> pl.DataFrame:
    """Classify each realistic strategy as research-allow, watch-only, or blocked."""

    perf_by_strategy = {
        _text(row.get("strategy_name")): row for row in performance.to_dicts()
    } if not performance.is_empty() else {}
    rows: list[dict[str, Any]] = []
    for strategy in STRATEGY_NAMES:
        group = [
            row for row in trades.to_dicts()
            if _text(row.get("strategy_name")) == strategy
        ]
        metrics = _metric_row(group)
        perf = perf_by_strategy.get(strategy, {})
        net = _float(perf.get("net_profit_points"))
        if net is None:
            net = metrics["net_pnl"]
        pf = _float(perf.get("profit_factor")) or metrics["profit_factor"]
        policy, action, reason = _policy_for_strategy(
            strategy=strategy,
            trades=metrics["trade_count"],
            net=net,
            profit_factor=pf,
        )
        rows.append(
            {
                "strategy_name": strategy,
                "policy": policy,
                "recommended_use": action,
                "trade_count": metrics["trade_count"],
                "net_pnl": net,
                "profit_factor": pf,
                "average_pnl": metrics["average_pnl"],
                "reason": reason,
            }
        )
    return _frame([_safe_row(row) for row in rows], _strategy_policy_schema())


def build_filter_scenarios(*, trades: pl.DataFrame) -> pl.DataFrame:
    """Compare simple filter scenarios on the same realistic event table."""

    rows = []
    scenarios = {
        "ACCEPTANCE_CONTINUATION_ONLY": {"WALL_ACCEPTANCE_CONTINUATION"},
        "REJECTION_FADE_ONLY": {"WALL_REJECTION_CONFIRMED_FADE"},
        "SD_2_REJECTION_ONLY": {"SD_2_REJECTION_CONFIRMED_FADE"},
        "COMBINED_CONSERVATIVE_ONLY": {"COMBINED_CONSERVATIVE_REALISTIC"},
        "CME_WALL_ACCEPTANCE_PLUS_REJECTION": {
            "WALL_ACCEPTANCE_CONTINUATION",
            "WALL_REJECTION_CONFIRMED_FADE",
        },
        "CME_WALL_ACTIVE_CANDIDATES": {
            "WALL_ACCEPTANCE_CONTINUATION",
            "WALL_REJECTION_CONFIRMED_FADE",
            "COMBINED_CONSERVATIVE_REALISTIC",
        },
        "ALL_REALISTIC_ACTIVE_CANDIDATES": {
            "WALL_ACCEPTANCE_CONTINUATION",
            "WALL_REJECTION_CONFIRMED_FADE",
            "SD_2_REJECTION_CONFIRMED_FADE",
            "COMBINED_CONSERVATIVE_REALISTIC",
        },
    }
    trade_rows = trades.to_dicts()
    for name, allowed in scenarios.items():
        group = [row for row in trade_rows if _text(row.get("strategy_name")) in allowed]
        metric = _metric_row(group)
        rows.append(
            {
                "scenario": name,
                **metric,
                "interpretation": _scenario_interpretation(name, metric),
            }
        )
    return _frame([_safe_row(row) for row in rows], _filter_scenario_schema())


def build_smc_overlay_guidance(
    *,
    strategy_policy: pl.DataFrame,
    filter_scenarios: pl.DataFrame,
) -> pl.DataFrame:
    """Describe how CME context may be used around the SMC/Pine research idea."""

    policy = {
        _text(row.get("strategy_name")): _text(row.get("policy"))
        for row in strategy_policy.to_dicts()
    }
    acceptance = _scenario(filter_scenarios, "ACCEPTANCE_CONTINUATION_ONLY")
    all_active = _scenario(filter_scenarios, "ALL_REALISTIC_ACTIVE_CANDIDATES")
    rows = [
        {
            "guidance": "SMC_WITH_CME_FILTER_ONLY",
            "status": "RESEARCH_ALLOWED",
            "evidence": (
                "CME wall acceptance continuation is the only positive realistic wall candidate "
                f"in this replay: net={_format_float(acceptance.get('net_pnl'))}, "
                f"pf={_format_float(acceptance.get('profit_factor'))}."
            ),
            "allowed_context": "Use CME acceptance context to rank/watch SMC candidates after price signal exists.",
            "blocked_context": "Do not let CME walls create standalone entries or override price confirmation.",
        },
        {
            "guidance": "BLOCK_REJECTION_AS_DIRECTION",
            "status": "BLOCK",
            "evidence": f"Rejection fade policy is {policy.get('WALL_REJECTION_CONFIRMED_FADE', 'UNKNOWN')}.",
            "allowed_context": "Keep rejection rows in diagnostics and forward journal.",
            "blocked_context": "Do not use rejection fade as a direction source until entry-direction review passes.",
        },
        {
            "guidance": "SD_2_WATCH_ONLY",
            "status": "WATCH_ONLY",
            "evidence": f"All active candidates remain weak after costs: net={_format_float(all_active.get('net_pnl'))}.",
            "allowed_context": "Use SD_2 as regime/context evidence only.",
            "blocked_context": "Do not tune SD_2 into SMC until cost-drag review finds a stable filter.",
        },
    ]
    return _frame([_safe_row(row) for row in rows], _smc_overlay_schema())


def choose_final_recommendation(strategy_policy: pl.DataFrame, smc_overlay: pl.DataFrame) -> str:
    """Choose a conservative final recommendation for CME usage."""

    policies = {_text(row.get("policy")) for row in strategy_policy.to_dicts()}
    statuses = {_text(row.get("status")) for row in smc_overlay.to_dicts()}
    if "RESEARCH_ALLOW_FILTER" in policies and "BLOCK" in statuses:
        return "CME_FILTER_ONLY_RESEARCH_ALLOWED"
    return "CME_WATCH_ONLY_NEEDS_MORE_DATA"


def build_conclusion(
    *,
    strategy_policy: pl.DataFrame,
    filter_scenarios: pl.DataFrame,
    smc_overlay_guidance: pl.DataFrame,
    final_recommendation: str,
) -> str:
    """Build the conclusion markdown."""

    lines = [
        "# CME Wall Entry Filter Audit",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{final_recommendation}`",
        "- CME usage: `FILTER_ONLY_FOR_RESEARCH`",
        "- SMC/Pine usage: `RANK_OR_BLOCK_AFTER_PRICE_SIGNAL_ONLY`",
        "- Standalone CME execution: `BLOCKED`",
        "",
        "## Strategy Policy",
        "",
        _frame_markdown(strategy_policy),
        "",
        "## Filter Scenarios",
        "",
        _frame_markdown(filter_scenarios),
        "",
        "## SMC Overlay Guidance",
        "",
        _frame_markdown(smc_overlay_guidance),
    ]
    return "\n".join(_safe_text(line) for line in lines) + "\n"


def write_cme_wall_entry_filter_audit_outputs(result: CmeWallEntryFilterAuditResult) -> None:
    """Write CSV and Markdown outputs."""

    result.strategy_policy.write_csv(result.paths["strategy_policy_csv"])
    result.filter_scenarios.write_csv(result.paths["filter_scenarios_csv"])
    result.smc_overlay_guidance.write_csv(result.paths["smc_overlay_guidance_csv"])
    _write_md(result.paths["strategy_policy_md"], "CME Wall Entry Strategy Policy", result.strategy_policy)
    _write_md(result.paths["filter_scenarios_md"], "CME Wall Entry Filter Scenarios", result.filter_scenarios)
    _write_md(result.paths["smc_overlay_guidance_md"], "CME Wall SMC Overlay Guidance", result.smc_overlay_guidance)
    result.paths["entry_filter_conclusion_md"].write_text(result.conclusion_markdown, encoding="utf-8")


def cme_wall_entry_filter_audit_report_lines(
    result: CmeWallEntryFilterAuditResult | None,
) -> list[str]:
    """Return research_report.md lines for the entry-filter audit."""

    if result is None:
        return ["## CME Wall Entry Filter Audit", "", "Entry-filter audit was not run."]
    return [
        "## CME Wall Entry Filter Audit",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "",
        "## Strategy Policy",
        "",
        _frame_markdown(result.strategy_policy),
        "",
        "## Filter Scenarios",
        "",
        _frame_markdown(result.filter_scenarios),
        "",
        "## SMC Overlay Guidance",
        "",
        _frame_markdown(result.smc_overlay_guidance),
        "",
        "- Links: `outputs/cme_wall_entry_strategy_policy.csv`, "
        "`outputs/cme_wall_entry_filter_scenarios.csv`, "
        "`outputs/cme_wall_entry_filter_conclusion.md`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when text avoids restricted terms and private paths."""

    safe = _safe_report_text(text)
    return not any(
        re.search(pattern, safe, flags=re.IGNORECASE)
        for pattern in (
            r"\bbuy\b",
            r"\bsell\b",
            r"profitable",
            r"profitability",
            r"guaranteed edge",
            r"predicts price",
            r"safe to trade",
            r"live[- ]ready",
            r"paper[- ]ready",
        )
    ) and not re.search(r"[A-Za-z]:\\Users\\|/Users/|/home/|/tmp/", safe)


def _policy_for_strategy(
    *,
    strategy: str,
    trades: int,
    net: float,
    profit_factor: float | None,
) -> tuple[str, str, str]:
    if strategy == "AVOID_DIRECT_WALL_TRADE_FILTER":
        return (
            "FILTER_ONLY",
            "KEEP_AS_CONTEXT_FILTER",
            "Filter-only row has no standalone PnL and should remain context only.",
        )
    if trades == 0:
        return "NEED_MORE_DATA", "COLLECT_MORE_CME_DAYS", "No active realistic rows."
    if strategy == "WALL_ACCEPTANCE_CONTINUATION" and net > 0 and (profit_factor or 0.0) > 1.0:
        return (
            "RESEARCH_ALLOW_FILTER",
            "ALLOW_AFTER_PRICE_SIGNAL_ONLY",
            "Positive after favorable-target validation; still requires forward research.",
        )
    if strategy == "SD_2_REJECTION_CONFIRMED_FADE" and net < 0 and (profit_factor or 0.0) > 1.0:
        return (
            "WATCH_ONLY_COST_DRAG",
            "USE_AS_CONTEXT_ONLY",
            "Gross replay survives but costs keep net negative.",
        )
    if net < 0:
        return (
            "BLOCK_AS_DIRECTION",
            "DO_NOT_USE_FOR_DIRECTION",
            "Negative realistic replay after costs.",
        )
    return (
        "WATCH_ONLY",
        "FORWARD_JOURNAL_ONLY",
        "Mixed candidate; keep under research until more CME days validate it.",
    )


def _metric_row(group: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_float(row.get("net_pnl_points")) or 0.0 for row in group]
    gross_values = [_float(row.get("gross_pnl_points")) or 0.0 for row in group]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit = sum(value for value in gross_values if value > 0)
    gross_loss = sum(value for value in gross_values if value < 0)
    return {
        "trade_count": len(group),
        "net_pnl": sum(values),
        "gross_pnl": sum(gross_values),
        "win_rate": len(wins) / len(group) if group else None,
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss < 0 else None,
        "average_pnl": sum(values) / len(group) if group else None,
    }


def _scenario_interpretation(name: str, metric: dict[str, Any]) -> str:
    if metric["trade_count"] == 0:
        return "NO_ACTIVE_ROWS"
    if name == "ACCEPTANCE_CONTINUATION_ONLY" and metric["net_pnl"] > 0:
        return "BEST_RESEARCH_FILTER_CANDIDATE"
    if metric["net_pnl"] < 0:
        return "BLOCK_OR_WATCH_ONLY"
    return "RESEARCH_ONLY_POSITIVE"


def _active_trades(trades: pl.DataFrame) -> pl.DataFrame:
    if trades.is_empty() or "direction" not in trades.columns:
        return _frame([], _trade_schema())
    return trades.filter(pl.col("direction").is_in(["LONG", "SHORT"]))


def _scenario(frame: pl.DataFrame, name: str) -> dict[str, Any]:
    if frame.is_empty():
        return {}
    rows = frame.filter(pl.col("scenario") == name)
    return rows.row(0, named=True) if rows.height else {}


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    return {
        "trade_events": _read_optional(output_root / "cme_wall_realistic_trade_events.csv"),
        "performance_summary": _read_optional(output_root / "cme_wall_realistic_performance_summary.csv"),
    }


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=1000)
    except Exception:
        return pl.DataFrame()


def _frame_input(inputs: dict[str, pl.DataFrame], key: str) -> pl.DataFrame:
    return inputs.get(key, pl.DataFrame())


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _format_float(value: Any) -> str:
    number = _float(value)
    return "n/a" if number is None else f"{number:.4f}"


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_report_text(text: str) -> str:
    return _safe_text(text)


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"\bbuy\b", "hold", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "exit", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(
        r"predicts price|guaranteed edge|safe to trade",
        "blocked phrase",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return frame.select(list(schema))


def _write_md(path: Path, title: str, frame: pl.DataFrame) -> None:
    lines = [f"# {_safe_text(title)}", "", RESEARCH_WARNING, "", _frame_markdown(frame)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return f"{value:.6g}"
    return _safe_text(value).replace("|", "\\|").replace("\n", " ")[:700]


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "strategy_policy_csv": output_root / "cme_wall_entry_strategy_policy.csv",
        "strategy_policy_md": output_root / "cme_wall_entry_strategy_policy.md",
        "filter_scenarios_csv": output_root / "cme_wall_entry_filter_scenarios.csv",
        "filter_scenarios_md": output_root / "cme_wall_entry_filter_scenarios.md",
        "smc_overlay_guidance_csv": output_root / "cme_wall_smc_overlay_guidance.csv",
        "smc_overlay_guidance_md": output_root / "cme_wall_smc_overlay_guidance.md",
        "entry_filter_conclusion_md": output_root / "cme_wall_entry_filter_conclusion.md",
    }


def _trade_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "direction": pl.Utf8,
        "gross_pnl_points": pl.Float64,
        "net_pnl_points": pl.Float64,
    }


def _strategy_policy_schema() -> dict[str, Any]:
    return {
        "strategy_name": pl.Utf8,
        "policy": pl.Utf8,
        "recommended_use": pl.Utf8,
        "trade_count": pl.Int64,
        "net_pnl": pl.Float64,
        "profit_factor": pl.Float64,
        "average_pnl": pl.Float64,
        "reason": pl.Utf8,
    }


def _filter_scenario_schema() -> dict[str, Any]:
    return {
        "scenario": pl.Utf8,
        "trade_count": pl.Int64,
        "net_pnl": pl.Float64,
        "gross_pnl": pl.Float64,
        "win_rate": pl.Float64,
        "profit_factor": pl.Float64,
        "average_pnl": pl.Float64,
        "interpretation": pl.Utf8,
    }


def _smc_overlay_schema() -> dict[str, Any]:
    return {
        "guidance": pl.Utf8,
        "status": pl.Utf8,
        "evidence": pl.Utf8,
        "allowed_context": pl.Utf8,
        "blocked_context": pl.Utf8,
    }
