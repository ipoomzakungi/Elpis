"""Integrate Gemini SD/grid confirmation results into XAU score guidance.

This module is an artifact integration layer only. It reads the completed
Gemini SD/grid confirmation outputs, updates manual interpretation artifacts,
and keeps frozen score v1 unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


ALLOWED_ACTIONS = (
    "BLOCK",
    "WATCH_ONLY",
    "TARGET_REFERENCE",
    "ALLOW_RESEARCH_CANDIDATE",
    "INSUFFICIENT_DATA",
)
FINAL_RECOMMENDATIONS = (
    "CONFIRMATION_REQUIRED",
    "USE_GRID_AS_REFERENCE_ONLY",
    "REJECTION_CONFIRMED_2SD_CANDIDATE",
    "NEEDS_CME_IV_FOR_TRUE_SD",
    "WATCHLIST_ONLY",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only SD/grid result integration. It updates interpretation "
    "artifacts only; frozen score v1 weights and thresholds are unchanged."
)
FORBIDDEN_PATTERNS = (
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


@dataclass(frozen=True)
class SdGridResultIntegrationResult:
    """Frames and paths emitted by the SD/grid integration layer."""

    decision_summary: pl.DataFrame
    updated_component_guide: pl.DataFrame
    updated_checklist: pl.DataFrame
    rulebook: pl.DataFrame
    latest_watchlist_overlay: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_sd_grid_result_integration(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> SdGridResultIntegrationResult:
    """Build SD/grid integration artifacts and optionally write outputs."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    decision_summary = build_sd_grid_confirmation_decision_summary(
        entry_models=inputs["entry_models"],
        tp_sl_models=inputs["tp_sl_models"],
        grid_tests=inputs["grid_tests"],
        rule_decision=inputs["rule_decision"],
    )
    component_guide = build_updated_component_guide(
        base_component_guide=inputs["component_guide"],
        decision_summary=decision_summary,
    )
    checklist = build_updated_manual_checklist(
        base_checklist=inputs["manual_checklist"],
    )
    rulebook = build_sd_grid_rulebook(decision_summary=decision_summary)
    latest_overlay = build_latest_watchlist_overlay(
        events=inputs["events"],
        daily_watchlist=inputs["daily_watchlist"],
        score_rows=inputs["score_rows"],
    )
    final = choose_final_recommendation(decision_summary=decision_summary)
    result = SdGridResultIntegrationResult(
        decision_summary=decision_summary,
        updated_component_guide=component_guide,
        updated_checklist=checklist,
        rulebook=rulebook,
        latest_watchlist_overlay=latest_overlay,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_sd_grid_result_integration_outputs(result)
    return result


def build_sd_grid_confirmation_decision_summary(
    *,
    entry_models: pl.DataFrame = pl.DataFrame(),
    tp_sl_models: pl.DataFrame = pl.DataFrame(),
    grid_tests: pl.DataFrame = pl.DataFrame(),
    rule_decision: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Summarize the completed Gemini confirmation result."""

    entries = _rows_by_key(entry_models, "model_id")
    tp_sl = _rows_by_key(tp_sl_models, "model_id")
    rules = _rows_by_key(rule_decision, "rule_id")
    blind_2 = entries.get("BLIND_2SD_FADE", {})
    blind_3 = entries.get("BLIND_3SD_FADE", {})
    rejection_2 = entries.get("REJECTION_CONFIRMED_2SD_FADE", {})
    rejection_3 = entries.get("REJECTION_CONFIRMED_3SD_FADE", {})
    acceptance = entries.get("ACCEPTANCE_CONTINUATION", {})
    best_tp_sl = tp_sl.get("TP_FULL_BLOCK_25_SL_3_5SD", {})
    grid_random_like = _grid_random_like(grid_tests)
    overall = rules.get("OVERALL", {})
    rows = [
        {
            "decision_id": "BLIND_ENTRIES_WEAK",
            "manual_action": "WATCH_ONLY",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": (
                f"Blind 2SD {_model_metrics(blind_2)}; "
                f"blind 3SD {_model_metrics(blind_3)}."
            ),
            "interpretation": "Do not treat a raw SD touch as a research candidate.",
            "limitation": "Realized-vol proxy bands only.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "REJECTION_CONFIRMED_2SD_CANDIDATE",
            "manual_action": "ALLOW_RESEARCH_CANDIDATE",
            "decision_label": "REJECTION_CONFIRMED_2SD_CANDIDATE",
            "evidence_summary": _model_metrics(rejection_2),
            "interpretation": "2SD close-back-inside is the preferred research candidate.",
            "limitation": "Candidate status is not validated edge.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "BLIND_3SD_DANGEROUS",
            "manual_action": "BLOCK",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": _model_metrics(blind_3),
            "interpretation": "3SD touch without rejection confirmation is high-risk.",
            "limitation": "Tail-risk count is elevated in price-only replay.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "REJECTION_CONFIRMED_3SD_STILL_WEAK",
            "manual_action": "WATCH_ONLY",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": _model_metrics(rejection_3),
            "interpretation": "3SD rejection remains watch-only until stronger evidence exists.",
            "limitation": "Expectancy proxy stayed weak in this run.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "ACCEPTANCE_CONTINUATION_MILD",
            "manual_action": "WATCH_ONLY",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": _model_metrics(acceptance),
            "interpretation": "Acceptance continuation is mild context with tail-risk review.",
            "limitation": "Requires close and hold beyond the SD level.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "GRID_REFERENCE_ONLY",
            "manual_action": "TARGET_REFERENCE",
            "decision_label": "USE_GRID_AS_REFERENCE_ONLY",
            "evidence_summary": (
                "25 and 12.50 grids are random-like as standalone levels."
                if grid_random_like
                else _grid_summary(grid_tests)
            ),
            "interpretation": "Grid levels can frame targets or invalidation references only.",
            "limitation": "Do not use grid touch alone as a candidate trigger.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "TP_SL_REFERENCE_ONLY",
            "manual_action": "TARGET_REFERENCE",
            "decision_label": "USE_GRID_AS_REFERENCE_ONLY",
            "evidence_summary": _tp_sl_metrics(best_tp_sl),
            "interpretation": "Best TP/SL proxy is reference geometry only.",
            "limitation": "This does not change score weights or prove a tradable edge.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "TRUE_IV_NEEDED",
            "manual_action": "INSUFFICIENT_DATA",
            "decision_label": "NEEDS_CME_IV_FOR_TRUE_SD",
            "evidence_summary": "All SD bands are REALIZED_VOL_PROXY.",
            "interpretation": "True SD validation needs timestamp-safe CME IV.",
            "limitation": "Final SD validation cannot use price-only proxy bands.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
        {
            "decision_id": "OVERALL",
            "manual_action": "WATCH_ONLY",
            "decision_label": "CONFIRMATION_REQUIRED",
            "evidence_summary": _text(overall.get("evidence_summary"))
            or "Most promising=REJECTION_CONFIRMED_2SD_FADE; dangerous=BLIND_3SD_FADE.",
            "interpretation": "Use confirmation-first rules for research review only.",
            "limitation": "Not money-ready and not score-v1 tuning evidence.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        },
    ]
    return _frame([_safe_row(row) for row in rows], _decision_summary_schema())


def build_updated_component_guide(
    *,
    base_component_guide: pl.DataFrame = pl.DataFrame(),
    decision_summary: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Create an SD/grid-updated component interpretation guide."""

    rows = [_component_from_base(row) for row in base_component_guide.to_dicts()]
    by_name = {row["component_name"]: row for row in rows}
    updates = {
        "acceptance_breakout_component": {
            "current_role": "POSITIVE_CONFIRMATION",
            "manual_action": "WATCH_ONLY",
            "current_confidence": "TOO_EARLY",
            "sd_grid_result": "Acceptance continuation was mildly positive but tail-risk remains.",
            "how_to_interpret": (
                "Treat close-and-hold acceptance as confirmation context only."
            ),
            "when_to_ignore": "Ignore as decisive evidence when blockers or stale data exist.",
            "required_data": "Dukascopy OHLC, 1h close/hold evidence, spread context.",
            "manual_review_question": "Did price close and hold beyond the SD or wall level?",
        },
        "rejection_after_touch_component": {
            "current_role": "POSITIVE_CONFIRMATION",
            "manual_action": "WATCH_ONLY",
            "current_confidence": "TOO_EARLY",
            "sd_grid_result": "Generic rejection remains watch-only; use the 2SD-specific row when present.",
            "how_to_interpret": "Treat generic rejection as context until the 2SD rule is active.",
            "when_to_ignore": "Ignore when the touch is not timestamp-safe or does not close back inside.",
            "required_data": "Dukascopy OHLC and level-touch context.",
            "manual_review_question": "Is this the 2SD-specific confirmed rejection candidate?",
        },
        "rejection_confirmed_2sd_component": {
            "component_name": "rejection_confirmed_2sd_component",
            "current_role": "POSITIVE_CONFIRMATION",
            "manual_action": "ALLOW_RESEARCH_CANDIDATE",
            "current_confidence": "REALIZED_VOL_PROXY_PROMISING",
            "sd_grid_result": _decision_evidence(
                decision_summary,
                "REJECTION_CONFIRMED_2SD_CANDIDATE",
            ),
            "how_to_interpret": "Allow research review only after touch and close-back-inside.",
            "when_to_ignore": "Ignore when the event is only a raw SD touch.",
            "required_data": "Dukascopy OHLC, realized-vol proxy SD band, rejection close.",
            "manual_review_question": "Did 2SD touch reject back inside on a closed candle?",
        },
        "blind_2sd_touch": {
            "component_name": "blind_2sd_touch",
            "current_role": "WATCH_ONLY",
            "manual_action": "WATCH_ONLY",
            "current_confidence": "WEAK",
            "sd_grid_result": _decision_evidence(decision_summary, "BLIND_ENTRIES_WEAK"),
            "how_to_interpret": "A 2SD touch alone is a watch state, not a candidate.",
            "when_to_ignore": "Ignore if no close-back-inside or acceptance confirmation follows.",
            "required_data": "Dukascopy OHLC and SD touch event.",
            "manual_review_question": "Was this only a 2SD touch?",
        },
        "blind_3sd_touch": {
            "component_name": "blind_3sd_touch",
            "current_role": "BLOCK_IF_NO_REJECTION",
            "manual_action": "BLOCK",
            "current_confidence": "HIGH_RISK_WATCH_ONLY",
            "sd_grid_result": _decision_evidence(decision_summary, "BLIND_3SD_DANGEROUS"),
            "how_to_interpret": "A raw 3SD touch is blocked unless stronger confirmation appears.",
            "when_to_ignore": "Ignore as a candidate when rejection is absent.",
            "required_data": "Dukascopy OHLC and SD touch or rejection evidence.",
            "manual_review_question": "Is 3SD involved without a confirmed rejection?",
        },
        "grid_25_component": {
            "component_name": "grid_25_component",
            "current_role": "TARGET_REFERENCE",
            "manual_action": "TARGET_REFERENCE",
            "current_confidence": "RANDOM_LIKE",
            "sd_grid_result": _decision_evidence(decision_summary, "GRID_REFERENCE_ONLY"),
            "how_to_interpret": "Use the 25 grid only as target or invalidation reference.",
            "when_to_ignore": "Ignore as standalone candidate evidence.",
            "required_data": "Dukascopy OHLC and grid distance.",
            "manual_review_question": "Is the 25 grid used only as a reference level?",
        },
        "half_grid_12_50_component": {
            "component_name": "half_grid_12_50_component",
            "current_role": "TARGET_REFERENCE",
            "manual_action": "TARGET_REFERENCE",
            "current_confidence": "RANDOM_LIKE",
            "sd_grid_result": _decision_evidence(decision_summary, "GRID_REFERENCE_ONLY"),
            "how_to_interpret": "Use the 12.50 half-grid only as target/reference geometry.",
            "when_to_ignore": "Ignore as standalone candidate evidence.",
            "required_data": "Dukascopy OHLC and half-grid distance.",
            "manual_review_question": "Is the 12.50 half-grid only a reference?",
        },
        "true_iv_sd_component": {
            "component_name": "true_iv_sd_component",
            "current_role": "NEEDS_CME_IV",
            "manual_action": "INSUFFICIENT_DATA",
            "current_confidence": "INSUFFICIENT_DATA",
            "sd_grid_result": _decision_evidence(decision_summary, "TRUE_IV_NEEDED"),
            "how_to_interpret": "Treat realized-vol SD as proxy until CME IV exists.",
            "when_to_ignore": "Ignore true-SD claims when timestamp-safe IV is missing.",
            "required_data": "Timestamp-safe CME IV, price path, and basis alignment.",
            "manual_review_question": "Is true CME IV available for this timestamp?",
        },
    }
    for name, update in updates.items():
        current = by_name.get(name, {"component_name": name})
        current.update(update)
        by_name[name] = current
    ordered_names = [
        *[row["component_name"] for row in rows],
        "rejection_confirmed_2sd_component",
        "blind_2sd_touch",
        "blind_3sd_touch",
        "grid_25_component",
        "half_grid_12_50_component",
        "true_iv_sd_component",
    ]
    output_rows = []
    seen = set()
    for name in ordered_names:
        if name in seen or name not in by_name:
            continue
        seen.add(name)
        output_rows.append(by_name[name])
    return _frame([_safe_row(row) for row in output_rows], _component_schema())


def build_updated_manual_checklist(
    *,
    base_checklist: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Append SD/grid confirmation checks to the manual checklist."""

    rows = [_check_from_base(row) for row in base_checklist.to_dicts()]
    rows.extend(
        [
            _check(
                "E_SD_GRID_CONFIRMATION",
                "Did price only touch 2SD or 3SD, or did it reject back inside?",
                "Use WATCH_ONLY for a raw touch; require close-back-inside for research review.",
                "WATCH_ONLY",
            ),
            _check(
                "E_SD_GRID_CONFIRMATION",
                "Is this a blind SD entry?",
                "Use BLOCK or WATCH_ONLY when no rejection or acceptance confirmation exists.",
                "BLOCK",
            ),
            _check(
                "E_SD_GRID_CONFIRMATION",
                "Is rejection-confirmed 2SD active?",
                "Use ALLOW_RESEARCH_CANDIDATE for research journal review only.",
                "ALLOW_RESEARCH_CANDIDATE",
            ),
            _check(
                "E_SD_GRID_CONFIRMATION",
                "Is 3SD involved?",
                "Use BLOCK unless stronger confirmation and data quality are present.",
                "BLOCK",
            ),
            _check(
                "E_SD_GRID_CONFIRMATION",
                "Is price accepted beyond SD or wall context?",
                "Use WATCH_ONLY and do not fade blindly against acceptance.",
                "WATCH_ONLY",
            ),
            _check(
                "E_SD_GRID_CONFIRMATION",
                "Is the 25 or 12.50 grid being used only as target/reference?",
                "Use TARGET_REFERENCE; grid touch alone is not candidate evidence.",
                "TARGET_REFERENCE",
            ),
            _check(
                "E_SD_GRID_CONFIRMATION",
                "Is true CME IV available, or only realized-vol proxy?",
                "Use INSUFFICIENT_DATA for true-SD validation when CME IV is missing.",
                "INSUFFICIENT_DATA",
            ),
        ]
    )
    return _frame([_safe_row(row) for row in rows], _checklist_schema())


def build_sd_grid_rulebook(
    *,
    decision_summary: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Build rulebook rows from the Gemini confirmation result."""

    rows = [
        _rule(
            "NO_TRADE_1SD",
            "BLOCK",
            "BLOCK_OR_WATCH_ONLY",
            "Inside 1SD is a middle/no-direction research zone.",
            "No directional research candidate while inside the middle band.",
            "Realized-vol proxy SD events.",
        ),
        _rule(
            "BLIND_2SD_TOUCH",
            "WATCH_ONLY",
            "WEAK",
            "A 2SD touch alone remains watch-only.",
            "Requires rejection or acceptance confirmation.",
            _decision_evidence(decision_summary, "BLIND_ENTRIES_WEAK"),
        ),
        _rule(
            "BLIND_3SD_TOUCH",
            "BLOCK",
            "HIGH_RISK_WATCH_ONLY",
            "A 3SD touch alone is blocked as a research candidate.",
            "Requires stronger rejection confirmation and tail-risk review.",
            _decision_evidence(decision_summary, "BLIND_3SD_DANGEROUS"),
        ),
        _rule(
            "REJECTION_CONFIRMED_2SD_FADE",
            "ALLOW_RESEARCH_CANDIDATE",
            "PREFERRED_CANDIDATE",
            "2SD touch plus close-back-inside is the preferred candidate.",
            "Must show rejection on a closed candle.",
            _decision_evidence(decision_summary, "REJECTION_CONFIRMED_2SD_CANDIDATE"),
        ),
        _rule(
            "REJECTION_CONFIRMED_3SD_FADE",
            "WATCH_ONLY",
            "HIGH_RISK",
            "3SD rejection remains weak and watch-only.",
            "Needs stronger confirmation and tail-risk review.",
            _decision_evidence(decision_summary, "REJECTION_CONFIRMED_3SD_STILL_WEAK"),
        ),
        _rule(
            "ACCEPTANCE_CONTINUATION",
            "WATCH_ONLY",
            "MILD_CONFIRMATION",
            "Acceptance continuation is watch-only unless broader confirmation exists.",
            "Requires close and hold beyond the SD or wall level.",
            _decision_evidence(decision_summary, "ACCEPTANCE_CONTINUATION_MILD"),
        ),
        _rule(
            "GRID_25",
            "TARGET_REFERENCE",
            "REFERENCE_ONLY",
            "The 25 grid is reference geometry only.",
            "Must not be used alone as candidate evidence.",
            _decision_evidence(decision_summary, "GRID_REFERENCE_ONLY"),
        ),
        _rule(
            "GRID_12_50",
            "TARGET_REFERENCE",
            "REFERENCE_ONLY",
            "The 12.50 half-grid is reference geometry only.",
            "Must not be used alone as candidate evidence.",
            _decision_evidence(decision_summary, "GRID_REFERENCE_ONLY"),
        ),
        _rule(
            "TP_FULL_BLOCK_25_SL_3_5SD",
            "TARGET_REFERENCE",
            "TARGET_INVALIDATION_REFERENCE_ONLY",
            "Full-block target and 3.5SD invalidation are reference geometry.",
            "Do not convert proxy geometry into score tuning.",
            _decision_evidence(decision_summary, "TP_SL_REFERENCE_ONLY"),
        ),
        _rule(
            "TRUE_IV_SD",
            "INSUFFICIENT_DATA",
            "NEEDS_CME_IV",
            "True SD validation is unavailable until CME IV exists.",
            "Requires timestamp-safe CME IV and basis alignment.",
            _decision_evidence(decision_summary, "TRUE_IV_NEEDED"),
        ),
    ]
    return _frame([_safe_row(row) for row in rows], _rulebook_schema())


def build_latest_watchlist_overlay(
    *,
    events: pl.DataFrame = pl.DataFrame(),
    daily_watchlist: pl.DataFrame = pl.DataFrame(),
    score_rows: pl.DataFrame = pl.DataFrame(),
) -> pl.DataFrame:
    """Build latest SD/grid overlay using the latest available local outputs."""

    latest_score = _latest_score_row(daily_watchlist, score_rows)
    if events.is_empty() or "timestamp" not in events.columns:
        row = {
            "as_of_timestamp": "",
            "timeframe": _text(latest_score.get("timeframe")),
            "current_score": _int_or_none(latest_score.get("latest_score")),
            "current_bucket": _text(latest_score.get("score_bucket")) or "INSUFFICIENT_DATA",
            "sd_grid_state": "MISSING_SD_GRID_EVENTS",
            "blind_sd_touch_active": False,
            "rejection_confirmed_2sd_active": False,
            "acceptance_continuation_active": False,
            "grid_target_reference_nearby": False,
            "sd_proxy_source": "",
            "nearest_grid_reference": "",
            "manual_action": "INSUFFICIENT_DATA",
            "interpretation": "No SD/grid event output is available.",
            "final_recommendation": "CONFIRMATION_REQUIRED",
        }
        return _frame([_safe_row(row)], _latest_overlay_schema())
    event_rows = _latest_event_rows(events)
    event_types = {_text(row.get("event_type")) for row in event_rows}
    level_types = {_text(row.get("level_type")) for row in event_rows}
    blind_sd = bool(event_types & {"REACH_2SD", "REACH_3SD", "REACH_3_5SD"})
    rejection_2sd = any(
        _text(row.get("event_type")) == "REJECTION_BACK_INSIDE"
        and _text(row.get("level_type")) == "2SD"
        for row in event_rows
    )
    acceptance = "ACCEPTANCE_1H_CLOSE" in event_types
    grid_near = bool(event_types & {"TOUCH_25_GRID", "TOUCH_12_50_HALF_GRID"})
    inside_1sd = "INSIDE_1SD" in event_types
    manual_action = _latest_manual_action(
        inside_1sd=inside_1sd,
        blind_sd=blind_sd,
        level_types=level_types,
        rejection_2sd=rejection_2sd,
        acceptance=acceptance,
        grid_near=grid_near,
    )
    row = {
        "as_of_timestamp": _text(event_rows[0].get("timestamp")),
        "timeframe": _text(event_rows[0].get("timeframe")),
        "current_score": _int_or_none(latest_score.get("latest_score")),
        "current_bucket": _text(latest_score.get("score_bucket")) or "INSUFFICIENT_DATA",
        "sd_grid_state": ";".join(sorted(event_types)),
        "blind_sd_touch_active": blind_sd,
        "rejection_confirmed_2sd_active": rejection_2sd,
        "acceptance_continuation_active": acceptance,
        "grid_target_reference_nearby": grid_near,
        "sd_proxy_source": _text(event_rows[0].get("sd_proxy_source")),
        "nearest_grid_reference": _grid_reference_text(event_rows),
        "manual_action": manual_action,
        "interpretation": _latest_interpretation(
            inside_1sd=inside_1sd,
            blind_sd=blind_sd,
            rejection_2sd=rejection_2sd,
            acceptance=acceptance,
            grid_near=grid_near,
            manual_action=manual_action,
        ),
        "final_recommendation": "CONFIRMATION_REQUIRED",
    }
    return _frame([_safe_row(row)], _latest_overlay_schema())


def choose_final_recommendation(*, decision_summary: pl.DataFrame) -> str:
    """Return the conservative final integration recommendation."""

    if decision_summary.is_empty():
        return "WATCHLIST_ONLY"
    labels = set(decision_summary.get_column("decision_label").to_list())
    if "CONFIRMATION_REQUIRED" in labels:
        return "CONFIRMATION_REQUIRED"
    if "NEEDS_CME_IV_FOR_TRUE_SD" in labels:
        return "NEEDS_CME_IV_FOR_TRUE_SD"
    return "WATCHLIST_ONLY"


def write_sd_grid_result_integration_outputs(result: SdGridResultIntegrationResult) -> None:
    """Write all requested CSV, Markdown, and YAML outputs."""

    result.decision_summary.write_csv(result.paths["decision_summary_csv"])
    result.paths["decision_summary_md"].write_text(
        _safe_report_text(
            _artifact_markdown(
                "SD Grid Confirmation Decision Summary",
                result.decision_summary,
            )
        ),
        encoding="utf-8",
    )
    result.updated_component_guide.write_csv(result.paths["component_guide_csv"])
    result.paths["component_guide_md"].write_text(
        _safe_report_text(
            _artifact_markdown(
                "XAU Trade Quality Component Guide SD Grid Updated",
                result.updated_component_guide,
            )
        ),
        encoding="utf-8",
    )
    result.updated_checklist.write_csv(result.paths["checklist_csv"])
    result.paths["checklist_md"].write_text(
        _safe_report_text(
            _artifact_markdown(
                "XAU Manual Trade Review Checklist SD Grid Updated",
                result.updated_checklist,
            )
        ),
        encoding="utf-8",
    )
    result.paths["rulebook_yaml"].write_text(
        _safe_report_text(_rulebook_yaml(result)),
        encoding="utf-8",
    )
    result.paths["rulebook_md"].write_text(
        _safe_report_text(
            _artifact_markdown("SD Grid Rulebook v1 From Gemini Result", result.rulebook)
        ),
        encoding="utf-8",
    )
    result.latest_watchlist_overlay.write_csv(result.paths["latest_overlay_csv"])
    result.paths["latest_overlay_md"].write_text(
        _safe_report_text(
            _artifact_markdown(
                "XAU Latest Watchlist SD Grid Overlay",
                result.latest_watchlist_overlay,
            )
        ),
        encoding="utf-8",
    )


def sd_grid_result_integration_report_lines(
    result: SdGridResultIntegrationResult | None,
) -> list[str]:
    """Return report lines for research_report.md."""

    if result is None:
        return [
            "## SD/Grid Confirmation Result Integration",
            "",
            "SD/grid result integration was not run.",
        ]
    return [
        "## SD/Grid Confirmation Result Integration",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "- Frozen score v1: unchanged.",
        "- Grid interpretation: `TARGET_REFERENCE` only.",
        "- True SD status: `INSUFFICIENT_DATA` until CME IV exists.",
        "",
        "## Updated Component Guide",
        "",
        _frame_markdown(result.updated_component_guide),
        "",
        "## Updated Manual Checklist",
        "",
        _frame_markdown(result.updated_checklist),
        "",
        "## SD/Grid Rulebook v1",
        "",
        _frame_markdown(result.rulebook),
        "",
        "## Latest SD/Grid Watchlist Overlay",
        "",
        _frame_markdown(result.latest_watchlist_overlay),
        "",
        "- Links: `outputs/sd_grid_confirmation_decision_summary.csv`, "
        "`outputs/xau_trade_quality_component_guide_sd_grid_updated.csv`, "
        "`outputs/xau_manual_trade_review_checklist_sd_grid_updated.csv`, "
        "`outputs/sd_grid_rulebook_v1_from_gemini_result.yaml`, "
        "`outputs/xau_latest_watchlist_sd_grid_overlay.csv`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when generated text avoids restricted phrases and local paths."""

    safe = _safe_report_text(text)
    return safe == text and not any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in FORBIDDEN_PATTERNS
    )


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "decision_summary_csv": output_root / "sd_grid_confirmation_decision_summary.csv",
        "decision_summary_md": output_root / "sd_grid_confirmation_decision_summary.md",
        "component_guide_csv": output_root
        / "xau_trade_quality_component_guide_sd_grid_updated.csv",
        "component_guide_md": output_root
        / "xau_trade_quality_component_guide_sd_grid_updated.md",
        "checklist_csv": output_root / "xau_manual_trade_review_checklist_sd_grid_updated.csv",
        "checklist_md": output_root / "xau_manual_trade_review_checklist_sd_grid_updated.md",
        "rulebook_yaml": output_root / "sd_grid_rulebook_v1_from_gemini_result.yaml",
        "rulebook_md": output_root / "sd_grid_rulebook_v1_from_gemini_result.md",
        "latest_overlay_csv": output_root / "xau_latest_watchlist_sd_grid_overlay.csv",
        "latest_overlay_md": output_root / "xau_latest_watchlist_sd_grid_overlay.md",
    }


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    paths = {
        "entry_models": output_root / "gemini_sd_grid_entry_model_comparison.csv",
        "tp_sl_models": output_root / "gemini_tp_sl_model_comparison.csv",
        "grid_tests": output_root / "gemini_grid_clustering_test.csv",
        "rule_decision": output_root / "gemini_sd_grid_rule_decision.csv",
        "events": output_root / "gemini_sd_grid_events.csv",
        "component_guide": output_root / "xau_trade_quality_component_guide.csv",
        "manual_checklist": output_root / "xau_manual_trade_review_checklist.csv",
        "daily_watchlist": output_root / "xau_trade_quality_daily_watchlist.csv",
        "score_rows": output_root / "xau_trade_quality_score.csv",
    }
    return {name: _read_csv(path) for name, path in paths.items()}


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - optional integration inputs degrade to empty frames.
        return pl.DataFrame()


def _component_from_base(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "component_name": _text(row.get("component_name")),
        "current_role": _text(row.get("current_role")),
        "manual_action": _role_to_action(row.get("current_role")),
        "current_confidence": _text(row.get("current_confidence")),
        "sd_grid_result": "UNCHANGED_BASE_COMPONENT",
        "how_to_interpret": _text(row.get("how_to_interpret")),
        "when_to_ignore": _text(row.get("when_to_ignore")),
        "required_data": _text(row.get("required_data")),
        "manual_review_question": _text(row.get("manual_review_question")),
    }


def _check_from_base(row: dict[str, Any]) -> dict[str, Any]:
    return _check(
        _text(row.get("section")),
        _text(row.get("check_item")),
        _text(row.get("manual_interpretation")),
        _text(row.get("journal_action")),
    )


def _check(section: str, item: str, interpretation: str, action: str) -> dict[str, str]:
    return {
        "section": section,
        "check_item": item,
        "manual_interpretation": interpretation,
        "journal_action": _allowed_action(action),
    }


def _rule(
    rule_id: str,
    manual_action: str,
    rule_status: str,
    plain_english_logic: str,
    required_confirmation: str,
    source_evidence: str,
) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "manual_action": _allowed_action(manual_action),
        "rule_status": rule_status,
        "plain_english_logic": plain_english_logic,
        "required_confirmation": required_confirmation,
        "source_evidence": source_evidence,
        "limitation": "Research-only; not validated edge; score v1 unchanged.",
        "score_v1_change": "NONE",
    }


def _role_to_action(role: Any) -> str:
    text = _text(role)
    if text in ALLOWED_ACTIONS:
        return text
    if "BLOCK" in text or text == "HARD_BLOCKER":
        return "BLOCK"
    if "POSITIVE" in text:
        return "ALLOW_RESEARCH_CANDIDATE"
    if "TARGET" in text:
        return "TARGET_REFERENCE"
    if "MISSING" in text or "INSUFFICIENT" in text:
        return "INSUFFICIENT_DATA"
    return "WATCH_ONLY"


def _allowed_action(value: Any) -> str:
    action = _text(value)
    return action if action in ALLOWED_ACTIONS else "INSUFFICIENT_DATA"


def _decision_evidence(decision_summary: pl.DataFrame, decision_id: str) -> str:
    if decision_summary.is_empty() or "decision_id" not in decision_summary.columns:
        return "No decision summary row."
    row = decision_summary.filter(pl.col("decision_id") == decision_id)
    if row.is_empty():
        return "No decision summary row."
    return _text(row.row(0, named=True).get("evidence_summary"))


def _rows_by_key(frame: pl.DataFrame, key: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or key not in frame.columns:
        return {}
    return {_text(row.get(key)): row for row in frame.to_dicts()}


def _model_metrics(row: dict[str, Any]) -> str:
    if not row:
        return "events=0; expectancy_proxy=n/a; tail_risk_count=0"
    return (
        f"events={_int(row.get('event_count'))}; "
        f"expectancy_proxy={_float_text(row.get('expectancy_proxy'))}; "
        f"tail_risk_count={_int(row.get('tail_risk_count'))}"
    )


def _tp_sl_metrics(row: dict[str, Any]) -> str:
    if not row:
        return "No TP/SL proxy row."
    return (
        f"{_text(row.get('model_id'))}: "
        f"expectancy_proxy={_float_text(row.get('expectancy_proxy'))}; "
        f"target_hit_rate={_float_text(row.get('target_hit_rate'))}; "
        f"stop_hit_rate={_float_text(row.get('stop_hit_rate'))}"
    )


def _grid_random_like(grid_tests: pl.DataFrame) -> bool:
    if grid_tests.is_empty() or "interpretation" not in grid_tests.columns:
        return False
    return set(grid_tests.get_column("interpretation").to_list()) == {
        "GRID_CLUSTERING_RANDOM_LIKE"
    }


def _grid_summary(grid_tests: pl.DataFrame) -> str:
    if grid_tests.is_empty():
        return "No grid rows."
    counts = (
        grid_tests.group_by("interpretation").len().sort("interpretation").to_dicts()
        if "interpretation" in grid_tests.columns
        else []
    )
    return "; ".join(f"{row['interpretation']}={row['len']}" for row in counts)


def _latest_score_row(
    daily_watchlist: pl.DataFrame,
    score_rows: pl.DataFrame,
) -> dict[str, Any]:
    if not daily_watchlist.is_empty():
        return daily_watchlist.tail(1).row(0, named=True)
    if not score_rows.is_empty():
        row = score_rows.tail(1).row(0, named=True)
        return {
            "timeframe": row.get("timeframe"),
            "latest_score": row.get("trade_quality_score"),
            "score_bucket": row.get("score_bucket"),
        }
    return {}


def _latest_event_rows(events: pl.DataFrame) -> list[dict[str, Any]]:
    if events.is_empty() or "timestamp" not in events.columns:
        return []
    timestamps = [_text(value) for value in events.get_column("timestamp").to_list()]
    latest_timestamp = max(timestamps) if timestamps else ""
    if not latest_timestamp:
        return []
    return events.filter(pl.col("timestamp").cast(pl.Utf8) == latest_timestamp).to_dicts()


def _latest_manual_action(
    *,
    inside_1sd: bool,
    blind_sd: bool,
    level_types: set[str],
    rejection_2sd: bool,
    acceptance: bool,
    grid_near: bool,
) -> str:
    if inside_1sd:
        return "BLOCK"
    if blind_sd and "3SD" in level_types:
        return "BLOCK"
    if rejection_2sd:
        return "ALLOW_RESEARCH_CANDIDATE"
    if acceptance or blind_sd:
        return "WATCH_ONLY"
    if grid_near:
        return "TARGET_REFERENCE"
    return "WATCH_ONLY"


def _latest_interpretation(
    *,
    inside_1sd: bool,
    blind_sd: bool,
    rejection_2sd: bool,
    acceptance: bool,
    grid_near: bool,
    manual_action: str,
) -> str:
    notes = []
    if inside_1sd:
        notes.append("Latest SD state is inside 1SD; directional review is blocked.")
    if blind_sd:
        notes.append("Blind SD touch is not sufficient for candidate status.")
    if rejection_2sd:
        notes.append("Rejection-confirmed 2SD is active.")
    if acceptance:
        notes.append("Acceptance continuation context is active.")
    if grid_near:
        notes.append("Nearby grid is target/reference only.")
    if not notes:
        notes.append("No active SD/grid confirmation row at the latest timestamp.")
    notes.append(f"Manual action: {manual_action}.")
    return " ".join(notes)


def _grid_reference_text(event_rows: list[dict[str, Any]]) -> str:
    refs = []
    for row in event_rows:
        event_type = _text(row.get("event_type"))
        if event_type not in {"TOUCH_25_GRID", "TOUCH_12_50_HALF_GRID"}:
            continue
        refs.append(f"{event_type}:{_text(row.get('grid_level'))}")
    return ";".join(refs)


def _rulebook_yaml(result: SdGridResultIntegrationResult) -> str:
    lines = [
        "version: sd_grid_rulebook_v1_from_gemini_result",
        "research_only: true",
        "score_v1_change: NONE",
        f"final_recommendation: {result.final_recommendation}",
        "allowed_actions:",
        *[f"  - {action}" for action in ALLOWED_ACTIONS],
        "rules:",
    ]
    for row in result.rulebook.to_dicts():
        lines.extend(
            [
                f"  - rule_id: {_yaml_scalar(row.get('rule_id'))}",
                f"    manual_action: {_yaml_scalar(row.get('manual_action'))}",
                f"    rule_status: {_yaml_scalar(row.get('rule_status'))}",
                f"    plain_english_logic: {_yaml_scalar(row.get('plain_english_logic'))}",
                f"    required_confirmation: {_yaml_scalar(row.get('required_confirmation'))}",
                f"    source_evidence: {_yaml_scalar(row.get('source_evidence'))}",
                f"    limitation: {_yaml_scalar(row.get('limitation'))}",
                f"    score_v1_change: {_yaml_scalar(row.get('score_v1_change'))}",
            ]
        )
    return "\n".join(lines) + "\n"


def _yaml_scalar(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return "''"
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join([f"# {title}", RESEARCH_WARNING, _frame_markdown(frame)])


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 30) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append(
            "| "
            + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns)
            + " |"
        )
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|").replace("\n", " ")[:700]


def _safe_report_text(text: str) -> str:
    safe = _safe_text(text)
    for pattern in FORBIDDEN_PATTERNS:
        safe = re.sub(pattern, _replacement_for(pattern), safe, flags=re.IGNORECASE)
    return safe


def _replacement_for(pattern: str) -> str:
    if "buy" in pattern or "sell" in pattern:
        return "direction"
    if "profit" in pattern:
        return "money-result"
    return "blocked phrase"


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = _redact_paths(text)
    text = re.sub(r"\bbuy\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(r"safe to trade|live[- ]ready|paper[- ]ready", "blocked phrase", text, flags=re.IGNORECASE)
    return text.strip()


def _redact_paths(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    safe = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", safe)
    return re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", safe)


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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_text(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def _decision_summary_schema() -> dict[str, Any]:
    return {
        "decision_id": pl.Utf8,
        "manual_action": pl.Utf8,
        "decision_label": pl.Utf8,
        "evidence_summary": pl.Utf8,
        "interpretation": pl.Utf8,
        "limitation": pl.Utf8,
        "final_recommendation": pl.Utf8,
    }


def _component_schema() -> dict[str, Any]:
    return {
        "component_name": pl.Utf8,
        "current_role": pl.Utf8,
        "manual_action": pl.Utf8,
        "current_confidence": pl.Utf8,
        "sd_grid_result": pl.Utf8,
        "how_to_interpret": pl.Utf8,
        "when_to_ignore": pl.Utf8,
        "required_data": pl.Utf8,
        "manual_review_question": pl.Utf8,
    }


def _checklist_schema() -> dict[str, Any]:
    return {
        "section": pl.Utf8,
        "check_item": pl.Utf8,
        "manual_interpretation": pl.Utf8,
        "journal_action": pl.Utf8,
    }


def _rulebook_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "manual_action": pl.Utf8,
        "rule_status": pl.Utf8,
        "plain_english_logic": pl.Utf8,
        "required_confirmation": pl.Utf8,
        "source_evidence": pl.Utf8,
        "limitation": pl.Utf8,
        "score_v1_change": pl.Utf8,
    }


def _latest_overlay_schema() -> dict[str, Any]:
    return {
        "as_of_timestamp": pl.Utf8,
        "timeframe": pl.Utf8,
        "current_score": pl.Int64,
        "current_bucket": pl.Utf8,
        "sd_grid_state": pl.Utf8,
        "blind_sd_touch_active": pl.Boolean,
        "rejection_confirmed_2sd_active": pl.Boolean,
        "acceptance_continuation_active": pl.Boolean,
        "grid_target_reference_nearby": pl.Boolean,
        "sd_proxy_source": pl.Utf8,
        "nearest_grid_reference": pl.Utf8,
        "manual_action": pl.Utf8,
        "interpretation": pl.Utf8,
        "final_recommendation": pl.Utf8,
    }


def main() -> None:
    """CLI entry point."""

    result = run_sd_grid_result_integration()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"rulebook_rows: {result.rulebook.height}")


if __name__ == "__main__":
    main()
