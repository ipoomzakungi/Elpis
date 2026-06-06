"""Interpretation guide for frozen XAU Trade Quality Score v1.

The guide turns the frozen score and failure diagnostic into a manual review
checklist. It does not change score weights, thresholds, buckets, or version.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.xau_trade_quality_forward_monitor import SCORE_VERSION
from research_xau_vol_oi.xau_trade_quality_score import COMPONENT_ORDER


FINAL_RECOMMENDATIONS = (
    "USE_AS_MANUAL_CHECKLIST",
    "KEEP_V1_FROZEN",
    "NEEDS_MORE_FORWARD_DATA",
    "DO_NOT_TUNE_YET",
    "NOT_READY_FOR_MONEY",
)
ALLOWED_JOURNAL_ACTIONS = (
    "BLOCK",
    "WATCH_ONLY",
    "ALLOW_RESEARCH_CANDIDATE",
    "INSUFFICIENT_DATA",
)
RESEARCH_WARNING = (
    "Research-only interpretation guide for frozen score v1. It does not modify "
    "score weights, thresholds, components, or score version."
)
PILOT_WARNING = "CME OI/IV remains PILOT_ONLY; guru context remains context/filter only."
FORBIDDEN_REPORT_PHRASES = (
    " buy ",
    " sell ",
    "profitable",
    "profitability",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "paper ready",
    "validated money edge",
)


@dataclass(frozen=True)
class XauTradeQualityUsageGuideResult:
    """Frames and labels emitted by the usage guide."""

    component_guide: pl.DataFrame
    checklist: pl.DataFrame
    guardrail_summary: pl.DataFrame
    latest_watchlist: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_xau_trade_quality_usage_guide(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> XauTradeQualityUsageGuideResult:
    """Build the frozen-v1 usage guide and optionally write artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(paths)
    component_guide = build_component_guide(
        component_failure=inputs["component_failure"],
        price_rule_interpretation=inputs["price_rule_interpretation"],
        cme_interpretation=inputs["cme_interpretation"],
        guru_interpretation=inputs["guru_interpretation"],
    )
    checklist = build_manual_review_checklist(component_guide=component_guide)
    guardrails = build_guardrail_summary(
        score_config_text=_read_text(paths["score_config_yaml"]),
        failure_decision=inputs["failure_decision"],
        bucket_inversion=inputs["bucket_inversion"],
        join_audit=inputs["join_audit"],
    )
    latest = build_latest_watchlist_explanation(
        daily_watchlist=inputs["daily_watchlist"],
        guardrail_summary=guardrails,
    )
    final = choose_final_recommendation(guardrails)
    result = XauTradeQualityUsageGuideResult(
        component_guide=component_guide,
        checklist=checklist,
        guardrail_summary=guardrails,
        latest_watchlist=latest,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_xau_trade_quality_usage_guide_outputs(result)
    return result


def build_component_guide(
    *,
    component_failure: pl.DataFrame = pl.DataFrame(),
    price_rule_interpretation: pl.DataFrame = pl.DataFrame(),
    cme_interpretation: pl.DataFrame = pl.DataFrame(),
    guru_interpretation: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Return component roles and manual interpretation prompts."""

    rows = []
    for component in COMPONENT_ORDER:
        template = _component_template(component)
        confidence = _component_confidence(
            component,
            component_failure=component_failure,
            price_rule_interpretation=price_rule_interpretation,
            cme_interpretation=cme_interpretation,
            guru_interpretation=guru_interpretation,
            fallback=template["current_confidence"],
        )
        rows.append({**template, "current_confidence": confidence})
    return _frame(rows, _component_guide_schema())


def build_manual_review_checklist(*, component_guide: pl.DataFrame) -> pl.DataFrame:
    """Return checklist rows with allowed journal actions only."""

    rows = [
        _check(
            "A_DATA_QUALITY",
            "Dukascopy price coverage is fresh for the review window.",
            "Use INSUFFICIENT_DATA when price coverage, timestamps, or resampling quality are unclear.",
            "INSUFFICIENT_DATA",
        ),
        _check(
            "A_DATA_QUALITY",
            "Spread and fee hurdle are normal for the candidate window.",
            "Use BLOCK when spread or fee hurdle overwhelms the expected research move.",
            "BLOCK",
        ),
        _check(
            "A_DATA_QUALITY",
            "CME context is available and clearly timestamped, or explicitly marked missing.",
            "Use WATCH_ONLY when CME context is missing or pilot-only.",
            "WATCH_ONLY",
        ),
        _check(
            "A_DATA_QUALITY",
            "Guru timing is confirmed as context-only and not treated as a standalone trigger.",
            "Use WATCH_ONLY when guru context is present without price confirmation.",
            "WATCH_ONLY",
        ),
        _check(
            "B_BLOCKER_CHECKS",
            "No-trade middle range is inactive.",
            "Use BLOCK when the row is inside a middle/no-edge range.",
            "BLOCK",
        ),
        _check(
            "B_BLOCKER_CHECKS",
            "Open-distance chase risk is inactive.",
            "Use BLOCK or WATCH_ONLY when price has already moved too far from open.",
            "BLOCK",
        ),
        _check(
            "B_BLOCKER_CHECKS",
            "Stale-data and data-quality blockers are inactive.",
            "Use INSUFFICIENT_DATA when data is stale or incomplete.",
            "INSUFFICIENT_DATA",
        ),
        _check(
            "B_BLOCKER_CHECKS",
            "Candidate is not relying only on a nearby CME wall.",
            "Use WATCH_ONLY when wall context lacks accepted/rejected price behavior.",
            "WATCH_ONLY",
        ),
        _check(
            "C_WATCH_CHECKS",
            "Acceptance breakout is confirmed by close/hold behavior.",
            "Use ALLOW_RESEARCH_CANDIDATE only for journaling when blockers are clear.",
            "ALLOW_RESEARCH_CANDIDATE",
        ),
        _check(
            "C_WATCH_CHECKS",
            "Rejection after touch is confirmed by price behavior, not by the wall alone.",
            "Use WATCH_ONLY until rejection behavior is clear.",
            "WATCH_ONLY",
        ),
        _check(
            "C_WATCH_CHECKS",
            "Volatility/range context supports reviewing the row without stretching the score.",
            "Use WATCH_ONLY when volatility context is unclear or pilot-only.",
            "WATCH_ONLY",
        ),
        _check(
            "D_JOURNAL_ACTION",
            "All hard blockers are clear and at least one positive confirmation is active.",
            "Use ALLOW_RESEARCH_CANDIDATE for research journal review only.",
            "ALLOW_RESEARCH_CANDIDATE",
        ),
        _check(
            "D_JOURNAL_ACTION",
            "Any hard blocker is active.",
            "Use BLOCK.",
            "BLOCK",
        ),
        _check(
            "D_JOURNAL_ACTION",
            "Context exists but confirmation or data coverage is incomplete.",
            "Use WATCH_ONLY.",
            "WATCH_ONLY",
        ),
    ]
    known_components = set(component_guide.get_column("component_name").to_list()) if not component_guide.is_empty() else set()
    if "stale_data_component" not in known_components:
        rows.append(
            _check(
                "A_DATA_QUALITY",
                "Stale-data component is present in the frozen schema.",
                "Use INSUFFICIENT_DATA if stale-data role is missing from artifacts.",
                "INSUFFICIENT_DATA",
            )
        )
    return _frame(rows, _checklist_schema())


def build_guardrail_summary(
    *,
    score_config_text: str,
    failure_decision: pl.DataFrame,
    bucket_inversion: pl.DataFrame,
    join_audit: pl.DataFrame,
) -> pl.DataFrame:
    """Return one-row guardrail summary explaining why v1 stays frozen."""

    decision = failure_decision.row(0, named=True) if not failure_decision.is_empty() else {}
    high_count = _int(decision.get("high_score_resolved_count"))
    low_count = _int(decision.get("low_score_resolved_count"))
    join_error_count = _int(decision.get("join_error_count"))
    warnings = _join_warning_count(join_audit)
    sample_note = _sample_note(bucket_inversion, high_count=high_count, low_count=low_count)
    row = {
        "score_version": SCORE_VERSION,
        "v1_config_present": bool(score_config_text.strip()),
        "v1_tuning_forbidden": _config_forbids_tuning(score_config_text),
        "failure_decision": _text(decision.get("final_recommendation")) or "NEEDS_MORE_FORWARD_DATA",
        "why_not_tune": (
            "Forward failure is dominated by limited high-score rows and clustering; "
            "changing weights now would fit too closely to sparse forward evidence."
        ),
        "minimum_forward_data_needed": (
            "At least 30 resolved high-score rows across multiple sessions/timeframes, "
            "plus event-level rather than only window-level review."
        ),
        "what_would_justify_v2": (
            "A confirmed join/alignment bug, enough multi-session forward evidence, "
            "or a component that remains harmful after sample-size warnings clear."
        ),
        "high_score_resolved_count": high_count,
        "low_score_resolved_count": low_count,
        "join_error_count": join_error_count,
        "join_warning_count": warnings,
        "sample_note": sample_note,
        "final_recommendation": "USE_AS_MANUAL_CHECKLIST",
        "guardrails": "KEEP_V1_FROZEN;NEEDS_MORE_FORWARD_DATA;DO_NOT_TUNE_YET;NOT_READY_FOR_MONEY",
    }
    return _frame([row], _guardrail_schema())


def build_latest_watchlist_explanation(
    *,
    daily_watchlist: pl.DataFrame,
    guardrail_summary: pl.DataFrame,
) -> pl.DataFrame:
    """Return the latest watchlist row with manual interpretation text."""

    guardrail = guardrail_summary.row(0, named=True) if not guardrail_summary.is_empty() else {}
    if daily_watchlist.is_empty():
        row = {
            "session_date": "",
            "timeframe": "",
            "latest_score": None,
            "score_bucket": "INSUFFICIENT_DATA",
            "journal_action": "INSUFFICIENT_DATA",
            "active_blockers": "MISSING_DAILY_WATCHLIST",
            "active_watch_reasons": "",
            "manual_interpretation": (
                "No latest watchlist row is available. Use the checklist only after data coverage is refreshed."
            ),
            "research_only_note": "This is not a recommendation; it is a manual review aid.",
        }
        return _frame([row], _latest_watchlist_schema())
    latest = daily_watchlist.tail(1).row(0, named=True)
    active_negative = _text(latest.get("active_negative_components"))
    blocked = _text(latest.get("blocked_reasons"))
    watch = _text(latest.get("watch_reasons"))
    action = _allowed_action(latest.get("journal_action"))
    bucket = _text(latest.get("score_bucket")) or action
    sample_note = (_text(guardrail.get("sample_note")) or "more forward evidence is needed").rstrip(".")
    manual = (
        f"Latest frozen-score row is {bucket} with score {_text(latest.get('latest_score'))}. "
        f"Manual review should check blockers first, then watch reasons, then data freshness. "
        f"V1 remains frozen because {sample_note}."
    )
    row = {
        "session_date": _text(latest.get("session_date")),
        "timeframe": _text(latest.get("timeframe")),
        "latest_score": _int(latest.get("latest_score")),
        "score_bucket": bucket,
        "journal_action": action,
        "active_blockers": blocked or active_negative or "NONE_LISTED",
        "active_watch_reasons": watch or _text(latest.get("active_positive_components")),
        "manual_interpretation": manual,
        "research_only_note": "This is not a recommendation; it is a manual review aid.",
    }
    return _frame([row], _latest_watchlist_schema())


def choose_final_recommendation(guardrail_summary: pl.DataFrame) -> str:
    """Choose the usage-guide recommendation."""

    if guardrail_summary.is_empty():
        return "NEEDS_MORE_FORWARD_DATA"
    row = guardrail_summary.row(0, named=True)
    if not bool(row.get("v1_tuning_forbidden")):
        return "DO_NOT_TUNE_YET"
    return "USE_AS_MANUAL_CHECKLIST"


def write_xau_trade_quality_usage_guide_outputs(result: XauTradeQualityUsageGuideResult) -> None:
    """Write usage guide CSV and Markdown artifacts."""

    result.component_guide.write_csv(result.paths["component_guide_csv"])
    result.checklist.write_csv(result.paths["manual_checklist_csv"])
    result.paths["usage_guide_md"].write_text(
        _safe_report_text(_usage_guide_markdown(result)),
        encoding="utf-8",
    )
    result.paths["manual_checklist_md"].write_text(
        _safe_report_text(_checklist_markdown(result)),
        encoding="utf-8",
    )
    result.paths["guardrail_summary_md"].write_text(
        _safe_report_text(_guardrail_markdown(result)),
        encoding="utf-8",
    )
    result.paths["latest_watchlist_md"].write_text(
        _safe_report_text(_latest_watchlist_markdown(result)),
        encoding="utf-8",
    )


def xau_trade_quality_usage_guide_report_lines(
    result: XauTradeQualityUsageGuideResult | None,
) -> list[str]:
    """Return research_report.md lines for the usage guide."""

    if result is None:
        return [
            "## XAU Trade Quality Usage Guide",
            "",
            "XAU Trade Quality Score Interpretation Guide was not run.",
        ]
    return [
        "## XAU Trade Quality Usage Guide",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "- Frozen-score guardrail: `KEEP_V1_FROZEN`",
        "- Evidence guardrail: `NEEDS_MORE_FORWARD_DATA`",
        "- Money-readiness guardrail: `NOT_READY_FOR_MONEY`",
        "",
        "## Component Interpretation Guide",
        "",
        _frame_markdown(result.component_guide),
        "",
        "## Manual Trade Review Checklist",
        "",
        _frame_markdown(result.checklist),
        "",
        "## Score Guardrails",
        "",
        _frame_markdown(result.guardrail_summary),
        "",
        "## Latest Watchlist Explanation",
        "",
        _frame_markdown(result.latest_watchlist),
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when guide text avoids forbidden claim/instruction phrases."""

    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES)


def _component_template(component: str) -> dict[str, str]:
    templates = {
        "acceptance_breakout_component": {
            "current_role": "POSITIVE_CONFIRMATION",
            "how_to_interpret": "Positive watch condition when close/hold behavior confirms acceptance.",
            "when_to_ignore": "Ignore as decisive evidence when forward sample is sparse or blockers are active.",
            "required_data": "Dukascopy OHLC, score row, spread/fee context.",
            "current_confidence": "NEEDS_MORE_FORWARD_DATA",
            "manual_review_question": "Did price close and hold beyond the level without active blockers?",
        },
        "rejection_after_touch_component": {
            "current_role": "POSITIVE_CONFIRMATION",
            "how_to_interpret": "Watch condition for failed touch or rejection behavior.",
            "when_to_ignore": "Ignore if the touch is not timestamp-safe or wall context is missing.",
            "required_data": "Dukascopy OHLC and level-touch context.",
            "current_confidence": "TOO_EARLY",
            "manual_review_question": "Is the rejection visible in price behavior rather than inferred from context alone?",
        },
        "no_trade_middle_range_component": {
            "current_role": "HARD_BLOCKER",
            "how_to_interpret": "Avoid interpreting directional edge inside a middle/no-edge range.",
            "when_to_ignore": "Only ignore if the range classification is missing or known stale.",
            "required_data": "Dukascopy OHLC and range-state calculation.",
            "current_confidence": "PROMISING",
            "manual_review_question": "Is price still inside the middle range where the score should block?",
        },
        "open_distance_component": {
            "current_role": "SOFT_BLOCKER",
            "how_to_interpret": "Chase-avoid filter when price has already moved far from the open.",
            "when_to_ignore": "Ignore only for review when open-distance data is unavailable.",
            "required_data": "Session open and current Dukascopy price.",
            "current_confidence": "NEEDS_MORE_FORWARD_DATA",
            "manual_review_question": "Has price already moved far enough from open to make the setup extended?",
        },
        "fee_spread_hurdle_component": {
            "current_role": "HARD_BLOCKER",
            "how_to_interpret": "Hard cost hurdle; research candidate is blocked when spread/fee drag dominates.",
            "when_to_ignore": "Do not ignore when spread data is fresh.",
            "required_data": "Bid/ask spread and fee/slippage assumptions.",
            "current_confidence": "PROMISING",
            "manual_review_question": "Can the expected research move clear the current spread and fee hurdle?",
        },
        "cme_wall_context_component": {
            "current_role": "PILOT_ONLY",
            "how_to_interpret": "Market-map context only; nearby wall is not an automatic candidate.",
            "when_to_ignore": "Ignore as confirmation when CME data is missing, stale, or post-event only.",
            "required_data": "CME OI wall map, as-of timestamp, basis mapping.",
            "current_confidence": "PILOT_ONLY",
            "manual_review_question": "Is wall context timestamp-safe and supported by price acceptance/rejection?",
        },
        "cme_iv_range_component": {
            "current_role": "PILOT_ONLY",
            "how_to_interpret": "Volatility/range context only for scale and review priority.",
            "when_to_ignore": "Ignore as decisive evidence when IV coverage is missing or stale.",
            "required_data": "CME IV/CVOL context and as-of timestamp.",
            "current_confidence": "PILOT_ONLY",
            "manual_review_question": "Does the IV/range context explain whether price is extended or compressed?",
        },
        "guru_filter_component": {
            "current_role": "CONTEXT_ONLY",
            "how_to_interpret": "Context/filter/playbook support only; never standalone signal.",
            "when_to_ignore": "Ignore as confirmation if timing metadata is uncertain.",
            "required_data": "Guru timing metadata and same-day context labels.",
            "current_confidence": "CONTEXT_ONLY",
            "manual_review_question": "Is guru context only supporting an already price-confirmed research row?",
        },
        "data_quality_component": {
            "current_role": "HARD_BLOCKER",
            "how_to_interpret": "Data quality must be checked before using any score row.",
            "when_to_ignore": "Do not ignore when coverage, timestamp, or resample quality is uncertain.",
            "required_data": "Dukascopy coverage, timestamp checks, resample quality.",
            "current_confidence": "CONTEXT_ONLY",
            "manual_review_question": "Are price data, spread, and timestamps clean enough for manual review?",
        },
        "stale_data_component": {
            "current_role": "HARD_BLOCKER",
            "how_to_interpret": "Stale data blocks interpretation until fresh evidence is available.",
            "when_to_ignore": "Do not ignore if the score row or context snapshot is stale.",
            "required_data": "Score timestamp, price timestamp, CME/guru as-of timestamps.",
            "current_confidence": "NEEDS_MORE_FORWARD_DATA",
            "manual_review_question": "Was every input available before the reviewed timestamp?",
        },
    }
    return templates.get(
        component,
        {
            "component_name": component,
            "current_role": "CONTEXT_ONLY",
            "how_to_interpret": "Context-only component not yet assigned stronger evidence status.",
            "when_to_ignore": "Ignore as decisive evidence until forward evidence is sufficient.",
            "required_data": "Frozen score row and related source evidence.",
            "current_confidence": "NEEDS_MORE_FORWARD_DATA",
            "manual_review_question": "Is this component supported by timestamp-safe evidence?",
        },
    ) | {"component_name": component}


def _component_confidence(
    component: str,
    *,
    component_failure: pl.DataFrame,
    price_rule_interpretation: pl.DataFrame,
    cme_interpretation: pl.DataFrame,
    guru_interpretation: pl.DataFrame,
    fallback: str,
) -> str:
    if component.startswith("cme_"):
        return "PILOT_ONLY" if not cme_interpretation.is_empty() else "NEEDS_MORE_FORWARD_DATA"
    if component == "guru_filter_component":
        return "CONTEXT_ONLY" if not guru_interpretation.is_empty() else "NEEDS_MORE_FORWARD_DATA"
    if not component_failure.is_empty() and "component_name" in component_failure.columns:
        rows = component_failure.filter(pl.col("component_name") == component)
        if not rows.is_empty():
            issue = _text(rows.row(0, named=True).get("possible_issue"))
            effect = _text(rows.row(0, named=True).get("effect_direction"))
            if issue == "SAMPLE_TOO_SMALL" or effect == "TOO_EARLY":
                return "TOO_EARLY"
    if component == "acceptance_breakout_component" and _price_rule_has_promise(price_rule_interpretation):
        return "NEEDS_MORE_FORWARD_DATA"
    return fallback


def _price_rule_has_promise(frame: pl.DataFrame) -> bool:
    if frame.is_empty() or "rule" not in frame.columns:
        return False
    rows = frame.filter(pl.col("rule").str.contains("ACCEPTANCE_BREAKOUT", literal=True))
    return not rows.is_empty()


def _check(section: str, item: str, interpretation: str, action: str) -> dict[str, str]:
    return {
        "section": section,
        "check_item": item,
        "manual_interpretation": interpretation,
        "journal_action": _allowed_action(action),
    }


def _config_forbids_tuning(text: str) -> bool:
    lowered = text.lower()
    return "tuning_allowed: false" in lowered and "threshold_optimization_allowed: false" in lowered


def _sample_note(bucket_inversion: pl.DataFrame, *, high_count: int, low_count: int) -> str:
    if high_count < 30:
        return f"High-score forward rows remain sparse: {high_count} resolved high-score rows versus {low_count} low-score rows."
    high_rows = (
        bucket_inversion.filter(pl.col("bucket").is_in(["ALLOW_RESEARCH", "HIGH_QUALITY_RESEARCH"]))
        if not bucket_inversion.is_empty()
        else pl.DataFrame()
    )
    reasons = ";".join(_text(row.get("reason_bucket_underperformed")) for row in high_rows.to_dicts())
    if "SESSION_CLUSTERED" in reasons:
        return "High-score rows are clustered in too few sessions."
    return "Forward evidence still requires multi-session monitoring."


def _join_warning_count(join_audit: pl.DataFrame) -> int:
    if join_audit.is_empty() or "severity" not in join_audit.columns:
        return 0
    return int(join_audit.filter((pl.col("severity") == "WARNING") & (pl.col("affected_rows") > 0)).height)


def _allowed_action(value: Any) -> str:
    action = _text(value)
    return action if action in ALLOWED_JOURNAL_ACTIONS else "INSUFFICIENT_DATA"


def _usage_guide_markdown(result: XauTradeQualityUsageGuideResult) -> str:
    return "\n\n".join(
        [
            "# XAU Trade Quality Usage Guide",
            RESEARCH_WARNING,
            PILOT_WARNING,
            "Use bucket labels as manual research workflow states: BLOCK, WATCH_ONLY, ALLOW_RESEARCH_CANDIDATE, or INSUFFICIENT_DATA.",
            "Frozen v1 stays unchanged until enough forward evidence or a confirmed bug exists.",
            "## Component Guide",
            _frame_markdown(result.component_guide),
        ]
    )


def _checklist_markdown(result: XauTradeQualityUsageGuideResult) -> str:
    return "\n\n".join(
        [
            "# XAU Manual Trade Review Checklist",
            RESEARCH_WARNING,
            "Checklist actions are limited to BLOCK, WATCH_ONLY, ALLOW_RESEARCH_CANDIDATE, and INSUFFICIENT_DATA.",
            _frame_markdown(result.checklist),
        ]
    )


def _guardrail_markdown(result: XauTradeQualityUsageGuideResult) -> str:
    return "\n\n".join(
        [
            "# XAU Score Guardrail Summary",
            RESEARCH_WARNING,
            "Do not tune from one session. Do not quarantine components while sample-size warnings remain active.",
            _frame_markdown(result.guardrail_summary),
        ]
    )


def _latest_watchlist_markdown(result: XauTradeQualityUsageGuideResult) -> str:
    return "\n\n".join(
        [
            "# XAU Latest Watchlist Explanation",
            RESEARCH_WARNING,
            "Latest watchlist interpretation is a manual review aid only.",
            _frame_markdown(result.latest_watchlist),
        ]
    )


def _safe_report_text(text: str) -> str:
    safe = text
    for phrase in FORBIDDEN_REPORT_PHRASES:
        safe = safe.replace(phrase, " [redacted research-safety phrase] ")
        safe = safe.replace(phrase.upper(), " [redacted research-safety phrase] ")
    return safe


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "score_config_yaml": output_root / "xau_trade_quality_score_v1.yaml",
        "score_csv": output_root / "xau_trade_quality_score.csv",
        "daily_watchlist": output_root / "xau_trade_quality_daily_watchlist.csv",
        "bucket_inversion": output_root / "xau_score_bucket_inversion_audit.csv",
        "component_failure": output_root / "xau_score_component_failure_audit.csv",
        "join_audit": output_root / "xau_score_forward_join_audit.csv",
        "failure_decision": output_root / "xau_score_failure_decision.csv",
        "price_rule_interpretation": output_root / "dukascopy_price_rule_interpretation.csv",
        "guru_interpretation": output_root / "dukascopy_guru_logic_interpretation.csv",
        "cme_interpretation": output_root / "dukascopy_cme_overlap_interpretation.csv",
        "forward_governance": output_root / "forward_rule_governance.csv",
        "usage_guide_md": output_root / "xau_trade_quality_usage_guide.md",
        "component_guide_csv": output_root / "xau_trade_quality_component_guide.csv",
        "manual_checklist_md": output_root / "xau_manual_trade_review_checklist.md",
        "manual_checklist_csv": output_root / "xau_manual_trade_review_checklist.csv",
        "guardrail_summary_md": output_root / "xau_score_guardrail_summary.md",
        "latest_watchlist_md": output_root / "xau_latest_watchlist_explanation.md",
    }


def _load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "score_rows": _read_csv(paths["score_csv"]),
        "daily_watchlist": _read_csv(paths["daily_watchlist"]),
        "bucket_inversion": _read_csv(paths["bucket_inversion"]),
        "component_failure": _read_csv(paths["component_failure"]),
        "join_audit": _read_csv(paths["join_audit"]),
        "failure_decision": _read_csv(paths["failure_decision"]),
        "price_rule_interpretation": _read_csv(paths["price_rule_interpretation"]),
        "guru_interpretation": _read_csv(paths["guru_interpretation"]),
        "cme_interpretation": _read_csv(paths["cme_interpretation"]),
        "forward_governance": _read_csv(paths["forward_governance"]),
    }


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - optional guide inputs degrade to empty frames.
        return pl.DataFrame()


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


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 25) -> str:
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


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _component_guide_schema() -> dict[str, Any]:
    return {
        "component_name": pl.String,
        "current_role": pl.String,
        "how_to_interpret": pl.String,
        "when_to_ignore": pl.String,
        "required_data": pl.String,
        "current_confidence": pl.String,
        "manual_review_question": pl.String,
    }


def _checklist_schema() -> dict[str, Any]:
    return {
        "section": pl.String,
        "check_item": pl.String,
        "manual_interpretation": pl.String,
        "journal_action": pl.String,
    }


def _guardrail_schema() -> dict[str, Any]:
    return {
        "score_version": pl.String,
        "v1_config_present": pl.Boolean,
        "v1_tuning_forbidden": pl.Boolean,
        "failure_decision": pl.String,
        "why_not_tune": pl.String,
        "minimum_forward_data_needed": pl.String,
        "what_would_justify_v2": pl.String,
        "high_score_resolved_count": pl.Int64,
        "low_score_resolved_count": pl.Int64,
        "join_error_count": pl.Int64,
        "join_warning_count": pl.Int64,
        "sample_note": pl.String,
        "final_recommendation": pl.String,
        "guardrails": pl.String,
    }


def _latest_watchlist_schema() -> dict[str, Any]:
    return {
        "session_date": pl.String,
        "timeframe": pl.String,
        "latest_score": pl.Int64,
        "score_bucket": pl.String,
        "journal_action": pl.String,
        "active_blockers": pl.String,
        "active_watch_reasons": pl.String,
        "manual_interpretation": pl.String,
        "research_only_note": pl.String,
    }
