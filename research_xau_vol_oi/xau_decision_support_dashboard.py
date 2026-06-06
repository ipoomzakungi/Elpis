"""Research-only XAU decision-support dashboard.

This layer turns current Dukascopy price-rule evidence, guru interpretation,
CME pilot coverage, and forward governance into a daily dashboard. It is an
inspection surface only: it does not tune rules, issue trade instructions, or
represent price-only/guru/CME-pilot evidence as validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


ALLOWED_STATE_LABELS = (
    "BLOCKED_NO_TRADE_RANGE",
    "BLOCKED_OPEN_DISTANCE",
    "BLOCKED_SPREAD_FEE",
    "WATCH_ACCEPTANCE_BREAKOUT",
    "WATCH_CME_WALL",
    "WATCH_GURU_CONTEXT",
    "CONTEXT_ONLY",
    "INSUFFICIENT_DATA",
)
FINAL_RECOMMENDATIONS = (
    "WATCHLIST_READY",
    "CONTEXT_ONLY",
    "WAIT_FOR_CME",
    "WAIT_FOR_PRICE_DATA",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only decision support. No live trading, paper trading, broker "
    "integration, rule tuning, execution instruction, or money-readiness claim is included."
)
FORBIDDEN_REPORT_PHRASES = (
    " buy ",
    " sell ",
    "profitability",
    "profitable",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "paper ready",
    "validated money edge",
)


@dataclass(frozen=True)
class XauDecisionSupportDashboardResult:
    """Frames emitted by the decision-support dashboard layer."""

    dashboard: pl.DataFrame
    watchlist_state: pl.DataFrame
    blocking_reasons: pl.DataFrame
    next_session_checklist: pl.DataFrame
    data_status: pl.DataFrame
    current_price_state: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_xau_decision_support_dashboard(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> XauDecisionSupportDashboardResult:
    """Build the research-only dashboard from generated evidence outputs."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    price_rules = _read_csv(paths["price_rule_interpretation"])
    guru_logic = _read_csv(paths["guru_logic_interpretation"])
    cme_overlap = _read_csv(paths["cme_overlap_interpretation"])
    forward_governance = _read_csv(paths["forward_governance"])
    forward_scorecard = _read_csv(paths["forward_scorecard"])
    current_week = _read_csv(paths["current_week_replay"])
    same_day_filter = _read_csv(paths["same_day_filter"])
    same_day_market_map = _read_csv(paths["same_day_market_map"])
    price_frames = {
        timeframe: _read_parquet(paths[f"price_{timeframe}"])
        for timeframe in ("15m", "1h", "4h", "1d")
    }

    data_status = build_data_status(
        price_frames=price_frames,
        current_week=current_week,
        same_day_filter=same_day_filter,
        same_day_market_map=same_day_market_map,
        cme_overlap=cme_overlap,
    )
    current_price_state = build_current_price_state(price_frames=price_frames)
    watchlist_state = build_watchlist_state(
        price_rules=price_rules,
        guru_logic=guru_logic,
        cme_overlap=cme_overlap,
        forward_governance=forward_governance,
        current_price_state=current_price_state,
    )
    blocking_reasons = build_blocking_reasons(watchlist_state)
    checklist = build_next_session_checklist(data_status=data_status)
    final = choose_final_recommendation(
        data_status=data_status,
        watchlist_state=watchlist_state,
        cme_overlap=cme_overlap,
    )
    dashboard = build_dashboard_rows(
        data_status=data_status,
        current_price_state=current_price_state,
        watchlist_state=watchlist_state,
        blocking_reasons=blocking_reasons,
        forward_scorecard=forward_scorecard,
        final_recommendation=final,
    )
    result = XauDecisionSupportDashboardResult(
        dashboard=dashboard,
        watchlist_state=watchlist_state,
        blocking_reasons=blocking_reasons,
        next_session_checklist=checklist,
        data_status=data_status,
        current_price_state=current_price_state,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_xau_decision_support_outputs(result)
    return result


def build_data_status(
    *,
    price_frames: dict[str, pl.DataFrame],
    current_week: pl.DataFrame = pl.DataFrame(),
    same_day_filter: pl.DataFrame = pl.DataFrame(),
    same_day_market_map: pl.DataFrame = pl.DataFrame(),
    cme_overlap: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Summarize latest available data timestamps and missing-data warnings."""

    latest_price = _latest_timestamp(price_frames.get("15m", pl.DataFrame()))
    latest_cme = _latest_date(current_week, "trade_date")
    latest_guru = max(
        (
            _latest_date(same_day_filter, "resolved_market_session_date"),
            _latest_date(same_day_market_map, "resolved_market_session_date"),
        ),
        default="",
    )
    valid_cme_rows = _max_int(cme_overlap, "valid_overlap_rows")
    warnings = []
    if not latest_price:
        warnings.append("MISSING_DUKASCOPY_PRICE_DATA")
    if valid_cme_rows < 60:
        warnings.append("CME_OVERLAP_PILOT_ONLY")
    if not latest_guru:
        warnings.append("GURU_METADATA_MISSING_OR_CONTEXT_ONLY")
    rows = [
        {
            "item": "latest_dukascopy_timestamp",
            "value": latest_price,
            "status": "OK" if latest_price else "MISSING",
            "missing_data_warning": "",
        },
        {
            "item": "latest_cme_snapshot_date",
            "value": latest_cme,
            "status": "PILOT_ONLY" if valid_cme_rows else "MISSING",
            "missing_data_warning": "CME_OVERLAP_PILOT_ONLY" if valid_cme_rows < 60 else "",
        },
        {
            "item": "latest_guru_metadata_date",
            "value": latest_guru,
            "status": "CONTEXT_ONLY" if latest_guru else "MISSING",
            "missing_data_warning": "GURU_METADATA_MISSING_OR_CONTEXT_ONLY" if not latest_guru else "",
        },
        {
            "item": "missing_data_warnings",
            "value": ";".join(warnings) if warnings else "NONE",
            "status": "CHECK" if warnings else "OK",
            "missing_data_warning": ";".join(warnings),
        },
    ]
    return _frame(rows, _data_status_schema())


def build_current_price_state(*, price_frames: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Build latest price state for each timeframe."""

    rows: list[dict[str, Any]] = []
    for timeframe in ("15m", "1h", "4h", "1d"):
        frame = price_frames.get(timeframe, pl.DataFrame())
        if frame.is_empty():
            rows.append(_missing_price_state(timeframe))
            continue
        sorted_frame = frame.sort("timestamp")
        latest = sorted_frame.tail(1).row(0, named=True)
        close = _float_or_none(latest.get("close"))
        open_value = _float_or_none(latest.get("open"))
        spread = _float_or_none(latest.get("spread_points") or latest.get("spread_close"))
        range_state = _range_state(sorted_frame, close)
        open_state = _open_distance_state(close, open_value, sorted_frame)
        spread_state = _spread_state(spread, sorted_frame)
        rows.append(
            {
                "timeframe": timeframe,
                "latest_timestamp": _text(latest.get("timestamp")),
                "last_price": close,
                "range_chop_state": range_state,
                "open_distance_state": open_state,
                "spread_fee_state": spread_state,
                "quality": _text(latest.get("quality")) or "UNKNOWN",
            }
        )
    return _frame(rows, _price_state_schema())


def build_watchlist_state(
    *,
    price_rules: pl.DataFrame,
    guru_logic: pl.DataFrame,
    cme_overlap: pl.DataFrame,
    forward_governance: pl.DataFrame,
    current_price_state: pl.DataFrame,
) -> pl.DataFrame:
    """Create block/watch/context rows from evidence and current price state."""

    rows: list[dict[str, Any]] = []
    no_trade = _rule_row(price_rules, "NO_TRADE_MIDDLE_RANGE")
    open_distance = _rule_row(price_rules, "OPEN_DISTANCE_FILTER")
    fee = _rule_row(price_rules, "FEE_SPREAD_HURDLE")
    acceptance = _rule_row(price_rules, "ACCEPTANCE_BREAKOUT")
    cme_valid_rows = _max_int(cme_overlap, "valid_overlap_rows")
    guru_context_count = (
        int(guru_logic.get_column("event_count").sum())
        if not guru_logic.is_empty() and "event_count" in guru_logic.columns
        else 0
    )

    middle_range_timeframes = _matching_timeframe_states(
        current_price_state,
        "range_chop_state",
        "MIDDLE_RANGE",
    )
    range_active = bool(middle_range_timeframes)
    rows.append(
        _state_row(
            label="BLOCKED_NO_TRADE_RANGE" if range_active else "CONTEXT_ONLY",
            active=range_active,
            rule="NO_TRADE_MIDDLE_RANGE",
            severity="BLOCK" if range_active else "CONTEXT",
            what_it_sees=(
                "; ".join(middle_range_timeframes)
                if range_active
                else _timeframe_state_summary(current_price_state, "range_chop_state")
            ),
            why_it_matters="Middle-range behavior is treated as an avoid/filter context.",
            data_support=_rule_support(no_trade),
            missing_data="CME confirmation remains separate.",
        )
    )
    extended_timeframes = _matching_timeframe_states(
        current_price_state,
        "open_distance_state",
        "EXTENDED_FROM_OPEN",
    )
    open_block = bool(extended_timeframes)
    rows.append(
        _state_row(
            label="BLOCKED_OPEN_DISTANCE" if open_block else "CONTEXT_ONLY",
            active=open_block,
            rule="OPEN_DISTANCE_FILTER",
            severity="BLOCK" if open_block else "CONTEXT",
            what_it_sees=(
                "; ".join(extended_timeframes)
                if open_block
                else _timeframe_state_summary(current_price_state, "open_distance_state")
            ),
            why_it_matters="Extended distance from the current bar open is treated as chase risk.",
            data_support=_rule_support(open_distance),
            missing_data="Forward observation count is still limited.",
        )
    )
    elevated_spread_timeframes = _matching_timeframe_states(
        current_price_state,
        "spread_fee_state",
        "ELEVATED_SPREAD",
    )
    spread_block = bool(elevated_spread_timeframes)
    rows.append(
        _state_row(
            label="BLOCKED_SPREAD_FEE" if spread_block else "CONTEXT_ONLY",
            active=spread_block,
            rule="FEE_SPREAD_HURDLE",
            severity="BLOCK" if spread_block else "CONTEXT",
            what_it_sees=(
                "; ".join(elevated_spread_timeframes)
                if spread_block
                else _timeframe_state_summary(current_price_state, "spread_fee_state")
            ),
            why_it_matters="Elevated spread can make research outcomes less realistic.",
            data_support=_rule_support(fee),
            missing_data="Cost model still needs forward journal tracking.",
        )
    )
    acceptance_watch = _text(acceptance.get("evidence_strength")) == "PROMISING"
    rows.append(
        _state_row(
            label="WATCH_ACCEPTANCE_BREAKOUT" if acceptance_watch else "CONTEXT_ONLY",
            active=acceptance_watch,
            rule="ACCEPTANCE_BREAKOUT",
            severity="WATCH" if acceptance_watch else "CONTEXT",
            what_it_sees="Candidate acceptance/confirmation rule from price-only evidence.",
            why_it_matters="This is the strongest price-only rule candidate so far.",
            data_support=_rule_support(acceptance),
            missing_data="Needs forward evidence and CME context before validation.",
        )
    )
    rows.append(
        _state_row(
            label="WATCH_CME_WALL" if cme_valid_rows else "CONTEXT_ONLY",
            active=bool(cme_valid_rows),
            rule="CME_OI_WALL_CONTEXT",
            severity="WATCH" if cme_valid_rows else "DATA",
            what_it_sees=f"{cme_valid_rows} CME overlap row(s).",
            why_it_matters="CME walls are market-structure context only at current sample size.",
            data_support="CME_OVERLAP_PILOT_ONLY",
            missing_data="More CME OI, IV, option volume, settlements, and basis history.",
        )
    )
    rows.append(
        _state_row(
            label="WATCH_GURU_CONTEXT" if guru_context_count else "INSUFFICIENT_DATA",
            active=bool(guru_context_count),
            rule="GURU_FILTER_CONTEXT",
            severity="WATCH" if guru_context_count else "DATA",
            what_it_sees=f"{guru_context_count} guru price-context event(s).",
            why_it_matters="Guru logic is research context until timing metadata is confirmed.",
            data_support="GURU_PRICE_LOGIC_READY_FOR_RESEARCH",
            missing_data="Transcript timing metadata and same-day confirmation.",
        )
    )
    if forward_governance.is_empty():
        rows.append(
            _state_row(
                label="INSUFFICIENT_DATA",
                active=True,
                rule="FORWARD_GOVERNANCE",
                severity="DATA",
                what_it_sees="No Dukascopy forward governance rows found.",
                why_it_matters="Forward evidence is required before governance interpretation.",
                data_support="MISSING_FORWARD_GOVERNANCE",
                missing_data="Run Dukascopy forward evidence refresh.",
            )
        )
    return _frame(rows, _watchlist_schema())


def build_blocking_reasons(watchlist_state: pl.DataFrame) -> pl.DataFrame:
    """Extract active blocking reasons from the watchlist state."""

    if watchlist_state.is_empty():
        return pl.DataFrame(schema=_blocking_schema())
    rows = []
    for row in watchlist_state.to_dicts():
        label = _text(row.get("state_label"))
        if not label.startswith("BLOCKED_"):
            continue
        rows.append(
            {
                "reason_label": label,
                "active": _bool(row.get("active")),
                "what_it_sees": _text(row.get("what_it_sees")),
                "why_it_matters": _text(row.get("why_it_matters")),
                "data_support": _text(row.get("data_support")),
                "missing_data": _text(row.get("missing_data")),
                "not_recommendation_reason": "Research block state only; no execution instruction.",
            }
        )
    return _frame(rows, _blocking_schema())


def build_next_session_checklist(*, data_status: pl.DataFrame) -> pl.DataFrame:
    """Build next-session operational research checklist."""

    del data_status
    rows = [
        ("collect_new_cme_snapshot", "Collect the next CME snapshot if available.", "PENDING"),
        ("collect_new_ohlc", "Refresh Dukascopy/Yahoo OHLC as applicable.", "PENDING"),
        (
            "collect_guru_metadata",
            "Add guru transcript timing metadata if a new transcript is available.",
            "PENDING",
        ),
        ("rerun_fast_report", "Run python -m research_xau_vol_oi.report --dukascopy-only.", "PENDING"),
        ("journal_observations", "Journal observations only when the research session is valid.", "PENDING"),
    ]
    return _frame(
        [
            {"check_id": check_id, "check_text": text, "status": status}
            for check_id, text, status in rows
        ],
        _checklist_schema(),
    )


def build_dashboard_rows(
    *,
    data_status: pl.DataFrame,
    current_price_state: pl.DataFrame,
    watchlist_state: pl.DataFrame,
    blocking_reasons: pl.DataFrame,
    forward_scorecard: pl.DataFrame,
    final_recommendation: str,
) -> pl.DataFrame:
    """Combine dashboard sections into one flat CSV-friendly table."""

    rows: list[dict[str, Any]] = []
    for row in data_status.to_dicts():
        rows.append(
            _dashboard_row(
                section="Data status",
                item=_text(row.get("item")),
                state_label="CONTEXT_ONLY" if _text(row.get("status")) != "MISSING" else "INSUFFICIENT_DATA",
                value=_text(row.get("value")),
                explanation=_text(row.get("missing_data_warning")) or "Data item available.",
                data_support="generated outputs",
                missing_data=_text(row.get("missing_data_warning")),
                final_recommendation=final_recommendation,
            )
        )
    for row in current_price_state.to_dicts():
        rows.append(
            _dashboard_row(
                section="Current price state",
                item=_text(row.get("timeframe")),
                state_label="CONTEXT_ONLY",
                value=str(row.get("last_price") or ""),
                explanation=(
                    f"range={row.get('range_chop_state')}; "
                    f"open_distance={row.get('open_distance_state')}; "
                    f"spread={row.get('spread_fee_state')}"
                ),
                data_support="Dukascopy resampled OHLC",
                missing_data="" if _text(row.get("quality")) != "MISSING" else "price data",
                final_recommendation=final_recommendation,
            )
        )
    for row in watchlist_state.to_dicts():
        rows.append(
            _dashboard_row(
                section="Active rule candidates",
                item=_text(row.get("rule")),
                state_label=_text(row.get("state_label")),
                value=_text(row.get("severity")),
                explanation=_text(row.get("plain_english_explanation")),
                data_support=_text(row.get("data_support")),
                missing_data=_text(row.get("missing_data")),
                final_recommendation=final_recommendation,
            )
        )
    for row in blocking_reasons.to_dicts():
        rows.append(
            _dashboard_row(
                section="Block/watch/context classification",
                item=_text(row.get("reason_label")),
                state_label=_text(row.get("reason_label")),
                value="ACTIVE" if _bool(row.get("active")) else "INACTIVE",
                explanation=_text(row.get("not_recommendation_reason")),
                data_support=_text(row.get("data_support")),
                missing_data=_text(row.get("missing_data")),
                final_recommendation=final_recommendation,
            )
        )
    if not forward_scorecard.is_empty():
        for row in forward_scorecard.to_dicts():
            rows.append(
                _dashboard_row(
                    section="Forward evidence governance",
                    item=_text(row.get("metric")),
                    state_label="CONTEXT_ONLY",
                    value=_text(row.get("value")),
                    explanation=_text(row.get("notes")),
                    data_support="Dukascopy forward evidence refresh",
                    missing_data="More independent events needed.",
                    final_recommendation=final_recommendation,
                )
            )
    return _frame(rows, _dashboard_schema())


def choose_final_recommendation(
    *,
    data_status: pl.DataFrame,
    watchlist_state: pl.DataFrame,
    cme_overlap: pl.DataFrame,
) -> str:
    """Choose the dashboard-level final status."""

    if _data_status_value(data_status, "latest_dukascopy_timestamp") == "":
        return "WAIT_FOR_PRICE_DATA"
    if watchlist_state.is_empty():
        return "CONTEXT_ONLY"
    cme_valid = _max_int(cme_overlap, "valid_overlap_rows")
    if cme_valid < 60:
        # Keep the money-readiness guardrail stronger than the watchlist state.
        return "NOT_READY_FOR_MONEY"
    if watchlist_state.filter(pl.col("state_label").str.starts_with("WATCH_")).height:
        return "WATCHLIST_READY"
    return "CONTEXT_ONLY"


def write_xau_decision_support_outputs(result: XauDecisionSupportDashboardResult) -> None:
    """Write dashboard CSV/Markdown artifacts."""

    paths = result.paths
    result.dashboard.write_csv(paths["dashboard_csv"])
    result.watchlist_state.write_csv(paths["watchlist_csv"])
    result.blocking_reasons.write_csv(paths["blocking_csv"])
    paths["dashboard_md"].write_text(_dashboard_markdown(result), encoding="utf-8")
    paths["checklist_md"].write_text(_checklist_markdown(result), encoding="utf-8")


def xau_decision_support_report_lines(
    result: XauDecisionSupportDashboardResult | None,
) -> list[str]:
    """Return research_report.md lines for the dashboard layer."""

    if result is None:
        return [
            "## XAU Decision Support Dashboard",
            "",
            "XAU decision-support dashboard was not run.",
        ]
    return [
        "## XAU Decision Support Dashboard",
        "",
        f"Final dashboard recommendation: `{result.final_recommendation}`.",
        "",
        "### Dashboard State",
        "",
        _frame_markdown(result.dashboard),
        "",
        "### Watchlist State",
        "",
        _frame_markdown(result.watchlist_state),
        "",
        "### Blocking Reasons",
        "",
        _frame_markdown(result.blocking_reasons),
    ]


def report_text_is_safe(text: str) -> bool:
    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES)


def _dashboard_markdown(result: XauDecisionSupportDashboardResult) -> str:
    sections = [
        "# XAU Decision Support Dashboard",
        "",
        RESEARCH_WARNING,
        "",
        f"Final recommendation: `{result.final_recommendation}`.",
        "",
        "## Data Status",
        "",
        _frame_markdown(result.data_status),
        "",
        "## Current Price State",
        "",
        _frame_markdown(result.current_price_state),
        "",
        "## Active Rule Candidates",
        "",
        _frame_markdown(result.watchlist_state),
        "",
        "## Block Watch Context Classification",
        "",
        _frame_markdown(result.blocking_reasons),
        "",
        "## Plain-English Explanation",
        "",
        "Each row describes what the dashboard sees, why it matters, what data supports it, "
        "what is missing, and why it is not an execution recommendation.",
        "",
        _frame_markdown(result.dashboard),
        "",
        "## Next Session Checklist",
        "",
        _frame_markdown(result.next_session_checklist),
    ]
    text = "\n".join(sections)
    return _safe_report_text(text)


def _checklist_markdown(result: XauDecisionSupportDashboardResult) -> str:
    lines = [
        "# XAU Next Session Checklist",
        "",
        RESEARCH_WARNING,
        "",
    ]
    for row in result.next_session_checklist.to_dicts():
        lines.append(f"- [{_text(row.get('status'))}] {_text(row.get('check_text'))}")
    lines.extend(
        [
            "",
            f"Final recommendation: `{result.final_recommendation}`.",
        ]
    )
    return _safe_report_text("\n".join(lines))


def _state_row(
    *,
    label: str,
    active: bool,
    rule: str,
    severity: str,
    what_it_sees: str,
    why_it_matters: str,
    data_support: str,
    missing_data: str,
) -> dict[str, Any]:
    if label not in ALLOWED_STATE_LABELS:
        label = "CONTEXT_ONLY"
    return {
        "state_label": label,
        "active": active,
        "rule": rule,
        "severity": severity,
        "what_it_sees": what_it_sees,
        "why_it_matters": why_it_matters,
        "data_support": data_support,
        "missing_data": missing_data,
        "plain_english_explanation": (
            f"Sees {what_it_sees}. {why_it_matters} Supported by {data_support}. "
            f"Missing: {missing_data or 'none listed'}. This is research context, not an execution recommendation."
        ),
    }


def _dashboard_row(
    *,
    section: str,
    item: str,
    state_label: str,
    value: str,
    explanation: str,
    data_support: str,
    missing_data: str,
    final_recommendation: str,
) -> dict[str, Any]:
    return {
        "section": section,
        "item": item,
        "state_label": state_label if state_label in ALLOWED_STATE_LABELS else "CONTEXT_ONLY",
        "value": value,
        "explanation": explanation,
        "data_support": data_support,
        "missing_data": missing_data,
        "not_trade_recommendation": True,
        "final_recommendation": final_recommendation,
    }


def _rule_row(frame: pl.DataFrame, rule: str) -> dict[str, Any]:
    if frame.is_empty() or "rule" not in frame.columns:
        return {}
    filtered = frame.filter(pl.col("rule") == rule)
    return filtered.row(0, named=True) if not filtered.is_empty() else {}


def _rule_support(row: dict[str, Any]) -> str:
    if not row:
        return "MISSING_RULE_INTERPRETATION"
    return (
        f"{row.get('rule')} strength={row.get('evidence_strength')} "
        f"count={row.get('trade_count')} expectancy={row.get('weighted_expectancy')}"
    )


def _matching_timeframe_states(
    frame: pl.DataFrame,
    state_column: str,
    expected_state: str,
) -> list[str]:
    if frame.is_empty() or state_column not in frame.columns:
        return []
    matches = []
    for row in frame.to_dicts():
        state = _text(row.get(state_column))
        if state == expected_state:
            timeframe = _text(row.get("timeframe")) or "unknown_timeframe"
            matches.append(f"{timeframe}={state}")
    return matches


def _timeframe_state_summary(frame: pl.DataFrame, state_column: str) -> str:
    if frame.is_empty() or state_column not in frame.columns:
        return "UNKNOWN"
    states = []
    for row in frame.to_dicts():
        timeframe = _text(row.get("timeframe")) or "unknown_timeframe"
        state = _text(row.get(state_column)) or "UNKNOWN"
        states.append(f"{timeframe}={state}")
    return "; ".join(states) if states else "UNKNOWN"


def _range_state(frame: pl.DataFrame, close: float | None) -> str:
    if close is None or frame.is_empty():
        return "UNKNOWN"
    sample = frame.tail(min(frame.height, 20))
    high = _column_float(sample, "high", "max")
    low = _column_float(sample, "low", "min")
    if high is None or low is None or high <= low:
        return "UNKNOWN"
    position = (close - low) / (high - low)
    if 0.35 <= position <= 0.65:
        return "MIDDLE_RANGE"
    if position > 0.65:
        return "UPPER_RANGE"
    return "LOWER_RANGE"


def _open_distance_state(
    close: float | None,
    open_value: float | None,
    frame: pl.DataFrame,
) -> str:
    if close is None or open_value is None or frame.is_empty():
        return "UNKNOWN"
    latest_range = abs(close - open_value)
    sample = frame.tail(min(frame.height, 20))
    avg_range = sample.select((pl.col("high") - pl.col("low")).mean().alias("avg")).item()
    if avg_range is None or float(avg_range) <= 0:
        return "UNKNOWN"
    return "EXTENDED_FROM_OPEN" if latest_range > float(avg_range) else "NEAR_OPEN"


def _spread_state(spread: float | None, frame: pl.DataFrame) -> str:
    if spread is None or frame.is_empty() or "spread_points" not in frame.columns:
        return "UNKNOWN"
    sample = frame.tail(min(frame.height, 200))
    p95 = sample.select(pl.col("spread_points").quantile(0.95).alias("p95")).item()
    if p95 is None:
        return "UNKNOWN"
    return "ELEVATED_SPREAD" if spread > float(p95) else "NORMAL_SPREAD"


def _missing_price_state(timeframe: str) -> dict[str, Any]:
    return {
        "timeframe": timeframe,
        "latest_timestamp": "",
        "last_price": None,
        "range_chop_state": "UNKNOWN",
        "open_distance_state": "UNKNOWN",
        "spread_fee_state": "UNKNOWN",
        "quality": "MISSING",
    }


def _latest_timestamp(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return ""
    return _text(frame.select(pl.col("timestamp").max()).item())


def _latest_date(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    values = [_text(value) for value in frame.get_column(column).to_list() if _text(value)]
    return max(values) if values else ""


def _data_status_value(data_status: pl.DataFrame, item: str) -> str:
    if data_status.is_empty():
        return ""
    filtered = data_status.filter(pl.col("item") == item)
    return _text(filtered.row(0, named=True).get("value")) if not filtered.is_empty() else ""


def _max_int(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    value = frame.select(pl.col(column).max()).item()
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _column_float(frame: pl.DataFrame, column: str, op: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    expr = getattr(pl.col(column), op)()
    value = frame.select(expr.alias("value")).item()
    return _float_or_none(value)


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - conservative dashboard can run with missing inputs.
        return pl.DataFrame()


def _read_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path)
    except Exception:  # noqa: BLE001 - conservative dashboard can run with missing inputs.
        return pl.DataFrame()


def _write_frame(path: Path, frame: pl.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_csv(path)


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "price_rule_interpretation": output_root / "dukascopy_price_rule_interpretation.csv",
        "guru_logic_interpretation": output_root / "dukascopy_guru_logic_interpretation.csv",
        "cme_overlap_interpretation": output_root / "dukascopy_cme_overlap_interpretation.csv",
        "forward_governance": output_root / "dukascopy_forward_rule_governance.csv",
        "forward_scorecard": output_root / "dukascopy_forward_event_scorecard.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "price_1d": output_root / "dukascopy_xau_1d.parquet",
        "current_week_replay": output_root / "current_week_cme_guru_replay.csv",
        "same_day_filter": output_root / "same_day_filter_evidence_after_metadata.csv",
        "same_day_market_map": output_root / "same_day_market_map_evidence_after_metadata.csv",
        "frozen_rulebook": output_root / "frozen_rulebook_v1.yaml",
        "dashboard_md": output_root / "xau_decision_support_dashboard.md",
        "dashboard_csv": output_root / "xau_decision_support_dashboard.csv",
        "watchlist_csv": output_root / "xau_watchlist_state.csv",
        "blocking_csv": output_root / "xau_blocking_reasons.csv",
        "checklist_md": output_root / "xau_next_session_checklist.md",
    }


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


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns) + " |")
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")[:700]


def _safe_report_text(text: str) -> str:
    safe = text
    for phrase in FORBIDDEN_REPORT_PHRASES:
        safe = safe.replace(phrase.strip(), f"[blocked phrase: {phrase.strip()}]")
        safe = safe.replace(phrase.strip().upper(), f"[blocked phrase: {phrase.strip()}]")
    return safe


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _data_status_schema() -> dict[str, Any]:
    return {
        "item": pl.String,
        "value": pl.String,
        "status": pl.String,
        "missing_data_warning": pl.String,
    }


def _price_state_schema() -> dict[str, Any]:
    return {
        "timeframe": pl.String,
        "latest_timestamp": pl.String,
        "last_price": pl.Float64,
        "range_chop_state": pl.String,
        "open_distance_state": pl.String,
        "spread_fee_state": pl.String,
        "quality": pl.String,
    }


def _watchlist_schema() -> dict[str, Any]:
    return {
        "state_label": pl.String,
        "active": pl.Boolean,
        "rule": pl.String,
        "severity": pl.String,
        "what_it_sees": pl.String,
        "why_it_matters": pl.String,
        "data_support": pl.String,
        "missing_data": pl.String,
        "plain_english_explanation": pl.String,
    }


def _blocking_schema() -> dict[str, Any]:
    return {
        "reason_label": pl.String,
        "active": pl.Boolean,
        "what_it_sees": pl.String,
        "why_it_matters": pl.String,
        "data_support": pl.String,
        "missing_data": pl.String,
        "not_recommendation_reason": pl.String,
    }


def _checklist_schema() -> dict[str, Any]:
    return {
        "check_id": pl.String,
        "check_text": pl.String,
        "status": pl.String,
    }


def _dashboard_schema() -> dict[str, Any]:
    return {
        "section": pl.String,
        "item": pl.String,
        "state_label": pl.String,
        "value": pl.String,
        "explanation": pl.String,
        "data_support": pl.String,
        "missing_data": pl.String,
        "not_trade_recommendation": pl.Boolean,
        "final_recommendation": pl.String,
    }
