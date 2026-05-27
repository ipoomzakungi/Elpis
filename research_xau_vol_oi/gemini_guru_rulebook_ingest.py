"""Ingest Gemini/NotebookLM guru rulebook output into research artifacts.

The Gemini rulebook is treated as transcript-derived hypothesis material only.
This module writes testable artifacts that keep transcript support separate
from Dukascopy/CME market-data validation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl


SUPPORTED_STATUS = "TRANSCRIPT_SUPPORTED"
FINAL_RECOMMENDATIONS = (
    "GEMINI_RULEBOOK_READY_FOR_TESTING",
    "SD_GRID_BACKTEST_READY",
    "CME_WALL_TEST_NEEDS_MORE_CME_DATA",
    "USE_AS_WATCHLIST_RULEBOOK_ONLY",
    "NOT_READY_FOR_MONEY",
)
FORBIDDEN_OUTPUT_PATTERNS = (
    r"buy",
    r"sell",
    r"profitable",
    r"profitability",
    r"predicts price",
    r"safe to trade",
    r"live ready",
    r"live-ready",
)
RESEARCH_WARNING = (
    "Gemini/NotebookLM labels are transcript-support labels only. They are not "
    "market-data validation, execution instructions, money evidence, or live "
    "readiness evidence."
)
MIN_CME_VALIDATION_DATES = 30


@dataclass(frozen=True)
class GeminiGuruRulebookIngestResult:
    """Generated rulebook artifacts and conservative final recommendation."""

    claims: pl.DataFrame
    cme_wall_rule_family: pl.DataFrame
    sd_grid_rule_family: pl.DataFrame
    entry_tp_sl_rule_family: pl.DataFrame
    no_trade_rule_family: pl.DataFrame
    dukascopy_rule_test_plan: pl.DataFrame
    sd_grid_backtest: pl.DataFrame
    cme_wall_test_plan: pl.DataFrame
    caution_audit: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_gemini_guru_rulebook_ingest(
    *,
    output_dir: str | Path = "outputs",
    rulebook_path: str | Path | None = None,
    write_outputs: bool = True,
) -> GeminiGuruRulebookIngestResult:
    """Parse the Gemini rulebook and write conservative research artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    input_path = Path(rulebook_path) if rulebook_path is not None else Path(
        "GEMINI_GURU_CONSOLIDATE.txt"
    )
    rulebook_text = input_path.read_text(encoding="utf-8") if input_path.exists() else ""
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)

    claims = parse_gemini_rulebook_claims(
        rulebook_text,
        guru_wall_logic_hypotheses=_frame_input(inputs, "guru_wall_logic_hypotheses"),
        guru_logic_knowledge_base=_frame_input(inputs, "guru_logic_knowledge_base"),
    )
    families = build_rule_families(claims)
    dukascopy_plan = build_dukascopy_rule_test_plan(claims)
    sd_grid_backtest = build_sd_grid_backtest(inputs=inputs)
    cme_plan = build_cme_wall_test_plan(inputs=inputs)
    caution = build_rulebook_caution_audit(rulebook_text, claims)
    final = choose_final_recommendation(
        sd_grid_backtest=sd_grid_backtest,
        cme_wall_test_plan=cme_plan,
        caution_audit=caution,
    )

    result = GeminiGuruRulebookIngestResult(
        claims=claims,
        cme_wall_rule_family=families["cme_wall"],
        sd_grid_rule_family=families["sd_grid"],
        entry_tp_sl_rule_family=families["entry_tp_sl"],
        no_trade_rule_family=families["no_trade"],
        dukascopy_rule_test_plan=dukascopy_plan,
        sd_grid_backtest=sd_grid_backtest,
        cme_wall_test_plan=cme_plan,
        caution_audit=caution,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_gemini_guru_rulebook_outputs(result)
    return result


def parse_gemini_rulebook_claims(
    rulebook_text: str,
    *,
    guru_wall_logic_hypotheses: pl.DataFrame | None = None,
    guru_logic_knowledge_base: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Convert Gemini rulebook sections into claim rows."""

    blocks = _rule_blocks(rulebook_text)
    supplemental = _supplemental_evidence_rows(
        guru_wall_logic_hypotheses
        if guru_wall_logic_hypotheses is not None
        else pl.DataFrame(),
        guru_logic_knowledge_base if guru_logic_knowledge_base is not None else pl.DataFrame(),
    )
    rows = []
    for spec in _claim_specs():
        evidence = _evidence_for_spec(spec, blocks, rulebook_text, supplemental)
        claimed = _claimed_support_status(evidence["body"])
        corrected = _corrected_support_status(claimed, evidence)
        rows.append(
            _safe_row(
                {
                    "claim_id": spec["claim_id"],
                    "rule_name": spec["rule_name"],
                    "source_section": evidence["source_section"],
                    "plain_english_logic": spec["plain_english_logic"],
                    "source_evidence": evidence["source_evidence"],
                    "transcript_source_id": "|".join(evidence["source_ids"]),
                    "thai_excerpt": evidence["thai_excerpt"],
                    "claimed_support_status": claimed,
                    "corrected_support_status": corrected,
                    "data_validation_status": spec["data_validation_status"],
                    "rule_classification": spec["rule_classification"],
                    "required_data": spec["required_data"],
                    "risk_warning": spec["risk_warning"],
                }
            )
        )
    return _frame(rows, _claims_schema()).sort("claim_id")


def build_rule_families(claims: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """Build four rule-family artifacts from claim rows."""

    by_id = _rows_by_key(claims, "claim_id")
    return {
        "cme_wall": _family_frame(
            by_id,
            [
                "WALL_AS_MAGNET",
                "WALL_AS_TP",
                "WALL_AS_REJECTION",
                "WALL_AS_ACCEPTANCE",
                "MAX_OI_PIN",
                "LOW_OI_GAP_SQUEEZE",
                "CALL_WALL_RESISTANCE",
                "PUT_WALL_SUPPORT",
            ],
            "CME_WALL",
        ),
        "sd_grid": _family_frame(
            by_id,
            [
                "NO_TRADE_1SD",
                "ENTRY_2SD_3SD",
                "ENTRY_3SD_EXTREME",
                "STOP_3_5SD",
                "TP_HALF_BLOCK_12_50",
                "TP_FULL_BLOCK_25",
                "$25_GRID_CLUSTERING",
                "$12_50_HALF_BLOCK_CLUSTERING",
            ],
            "SD_GRID",
        ),
        "entry_tp_sl": _family_frame(
            by_id,
            [
                "ENTRY_2SD_3SD",
                "ENTRY_3SD_EXTREME",
                "STOP_3_5SD",
                "TP_HALF_BLOCK_12_50",
                "TP_FULL_BLOCK_25",
                "ACCEPTANCE_1H_CLOSE",
                "REJECTION_BACK_INSIDE",
            ],
            "ENTRY_TP_SL",
        ),
        "no_trade": _family_frame(
            by_id,
            [
                "NO_TRADE_1SD",
                "SUSPEND_ON_DATA_VOID",
                "WALL_PROXIMITY_100",
            ],
            "NO_TRADE",
        ),
    }


def build_dukascopy_rule_test_plan(claims: pl.DataFrame) -> pl.DataFrame:
    """Create fixed, prioritized Dukascopy-first rule tests."""

    by_id = _rows_by_key(claims, "claim_id")
    rows = []
    for priority, rule_id in enumerate(_dukascopy_priority_rules(), start=1):
        claim = by_id.get(rule_id, _synthetic_claim(rule_id))
        rows.append(
            _safe_row(
                {
                    "priority": priority,
                    "rule_id": rule_id,
                    "test_name": _test_name(rule_id),
                    "data_validation_status": _text(
                        claim.get("data_validation_status")
                    )
                    or "TESTABLE_WITH_DUKASCOPY",
                    "required_inputs": _dukascopy_required_inputs(rule_id),
                    "fixed_parameters": _fixed_parameters(rule_id),
                    "leakage_control": (
                        "Use fixed thresholds from the transcript rulebook; do not "
                        "re-fit parameters on the evaluated sample."
                    ),
                    "expected_outputs": (
                        "event_count, target_hit_rate, stop_hit_rate, MFE, MAE, "
                        "spread-cost estimate, sample-size warning, interpretation."
                    ),
                    "current_testable": True,
                    "caution": _dukascopy_caution(rule_id),
                }
            )
        )
    return _frame(rows, _dukascopy_plan_schema())


def build_sd_grid_backtest(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Run a fixed price-only SD/grid diagnostic on available Dukascopy data."""

    price_15m = _normalize_price_frame(_frame_input(inputs, "price_15m"))
    price_1h = _normalize_price_frame(_frame_input(inputs, "price_1h"))
    price_1d = _normalize_price_frame(_frame_input(inputs, "price_1d"))
    cme_iv = _frame_input(inputs, "cme_iv")
    if price_15m.is_empty():
        return _frame(
            [_empty_backtest_row(rule_id, "NEEDS_CME" if "CME" in rule_id else "TOO_EARLY")
             for rule_id in _sd_backtest_rule_ids()],
            _sd_grid_backtest_schema(),
        )

    sessions = _session_contexts(price_15m, price_1d, cme_iv)
    rows = [
        _simulate_rule("NO_TRADE_1SD", sessions, target_points=12.5, stop_mode="none"),
        _simulate_rule("ENTRY_2SD_3SD", sessions, target_points=12.5, stop_mode="3_5sd"),
        _simulate_rule("ENTRY_3SD_EXTREME", sessions, target_points=12.5, stop_mode="3_5sd"),
        _simulate_rule("STOP_3_5SD", sessions, target_points=12.5, stop_mode="3_5sd"),
        _simulate_rule("TP_HALF_BLOCK_12_50", sessions, target_points=12.5, stop_mode="3_5sd"),
        _simulate_rule("TP_FULL_BLOCK_25", sessions, target_points=25.0, stop_mode="3_5sd"),
        _simulate_rule("REJECTION_BACK_INSIDE", sessions, target_points=12.5, stop_mode="3_5sd"),
        _simulate_acceptance_rule(price_1h, sessions),
        _grid_clustering_row("$25_GRID_CLUSTERING", price_15m, grid=25.0),
        _grid_clustering_row("$12_50_HALF_BLOCK_CLUSTERING", price_15m, grid=12.5),
    ]
    return _frame([_safe_row(row) for row in rows], _sd_grid_backtest_schema())


def build_cme_wall_test_plan(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Build CME wall testability diagnostics without promoting validation."""

    cme_oi = _frame_input(inputs, "cme_oi")
    cme_iv = _frame_input(inputs, "cme_iv")
    basis = _frame_input(inputs, "basis")
    overlap = _frame_input(inputs, "overlap_validation")
    oi_dates = _n_unique(cme_oi, "trade_date")
    rules = [
        (
            "WALL_AS_MAGNET",
            "trade_date|strike|total_oi|basis|price_path",
            "OI wall map plus basis and timestamp-safe price path.",
        ),
        (
            "WALL_AS_TP",
            "trade_date|strike|total_oi|basis|price_path",
            "OI wall targets plus forward price path.",
        ),
        (
            "CALL_WALL_RESISTANCE",
            "trade_date|strike|call_oi|basis|price_path",
            "Call OI by strike with mapped spot-equivalent levels.",
        ),
        (
            "PUT_WALL_SUPPORT",
            "trade_date|strike|put_oi|basis|price_path",
            "Put OI by strike with mapped spot-equivalent levels.",
        ),
        (
            "LOW_OI_GAP_SQUEEZE",
            "trade_date|strike|total_oi|neighbor_strikes|price_velocity",
            "Strike-by-strike OI distribution and next-wall price path.",
        ),
        (
            "MAX_OI_PIN",
            "trade_date|expiry|strike|total_oi|expiry_calendar|price_path",
            "Expiry calendar and max-OI strike by date.",
        ),
        (
            "WALL_AS_REJECTION",
            "trade_date|strike|total_oi|basis|1h_close|price_path",
            "Wall touch plus close-back-inside behavior.",
        ),
        (
            "WALL_AS_ACCEPTANCE",
            "trade_date|strike|total_oi|basis|1h_close|volume",
            "Wall break plus hourly close and volume context.",
        ),
    ]
    rows = []
    for rule_id, fields, next_needed in rules:
        testable_rows = _current_testable_rows(rule_id, cme_oi, basis, overlap)
        can_test_now = testable_rows > 0
        if oi_dates < MIN_CME_VALIDATION_DATES:
            current = (
                f"Pilot rows exist, but only {oi_dates} unique CME OI dates are "
                "available; keep as CME-overlap pilot."
            )
        else:
            current = "CME overlap rows are available for a fixed pilot test."
        rows.append(
            _safe_row(
                {
                    "rule_id": rule_id,
                    "required_cme_fields": fields,
                    "current_available_rows": _available_rows_for_rule(
                        rule_id,
                        cme_oi,
                        cme_iv,
                        basis,
                        overlap,
                    ),
                    "current_testable_rows": testable_rows,
                    "can_test_now": can_test_now,
                    "current_result_if_available": current if can_test_now else "Not testable with current local CME rows.",
                    "next_cme_data_needed": (
                        f"{next_needed} Need at least {MIN_CME_VALIDATION_DATES} "
                        "unique timestamp-safe CME OI dates before validation claims."
                    ),
                }
            )
        )
    return _frame(rows, _cme_plan_schema())


def build_rulebook_caution_audit(rulebook_text: str, claims: pl.DataFrame) -> pl.DataFrame:
    """Flag unsafe or ambiguous interpretation patterns in the rulebook."""

    rows: list[dict[str, Any]] = []
    caution_id = 1
    for pattern, rule_id, caution_type, handling in [
        (
            r"must\s+(?:enter|trade)|ต้องเข้า|ยังไงก็ต้องเทรด",
            "ENTRY_3SD_EXTREME",
            "MUST_ENTER_LANGUAGE",
            "Demote to research candidate requiring rejection/acceptance context.",
        ),
        (
            r"research papers?.{0,30}(?:proved|prove|พิสูจน์)",
            "WALL_AS_REJECTION",
            "UNCITED_RESEARCH_PROOF_CLAIM",
            "Keep as transcript claim unless a cited external paper is attached.",
        ),
        (
            r"wall.{0,60}magnet|magnetic|แรงดึง",
            "WALL_AS_MAGNET",
            "MAGNET_WITHOUT_CONTEXT_RISK",
            "Require proximity, acceptance/rejection, and CME freshness fields.",
        ),
        (
            r"เมื่อเช้า|today|วันเนี้ย|this morning",
            "REJECTION_BACK_INSIDE",
            "POSSIBLE_POST_EVENT_COMMENTARY",
            "Do not use as same-session filter without timestamp metadata.",
        ),
    ]:
        for match in re.finditer(pattern, rulebook_text, flags=re.IGNORECASE | re.DOTALL):
            rows.append(
                _safe_row(
                    {
                        "caution_id": f"CAUTION_{caution_id:03d}",
                        "rule_id": rule_id,
                        "caution_type": caution_type,
                        "source_section": _section_for_offset(rulebook_text, match.start()),
                        "evidence": _window(rulebook_text, match.start(), 360),
                        "severity": "HIGH" if caution_type in {
                            "MUST_ENTER_LANGUAGE",
                            "UNCITED_RESEARCH_PROOF_CLAIM",
                        } else "MEDIUM",
                        "recommended_handling": handling,
                    }
                )
            )
            caution_id += 1
            break

    for row in claims.to_dicts() if not claims.is_empty() else []:
        required = _text(row.get("required_data"))
        status = _text(row.get("data_validation_status"))
        if "CME" in required and status == "TESTABLE_WITH_DUKASCOPY":
            rows.append(
                _safe_row(
                    {
                        "caution_id": f"CAUTION_{caution_id:03d}",
                        "rule_id": row.get("claim_id"),
                        "caution_type": "CME_REQUIRED_BUT_PRICE_ONLY_STATUS",
                        "source_section": row.get("source_section"),
                        "evidence": row.get("plain_english_logic"),
                        "severity": "HIGH",
                        "recommended_handling": (
                            "Split price-only proxy diagnostics from CME wall "
                            "validation; do not promote this as data-validated."
                        ),
                    }
                )
            )
            caution_id += 1

    if not rows:
        rows.append(
            _safe_row(
                {
                    "caution_id": "CAUTION_001",
                    "rule_id": "RULEBOOK",
                    "caution_type": "NO_BLOCKING_CAUTION_FOUND",
                    "source_section": "n/a",
                    "evidence": "No high-risk wording found in supplied text.",
                    "severity": "LOW",
                    "recommended_handling": "Continue transcript-to-data separation.",
                }
            )
        )
    return _frame(rows, _caution_schema())


def choose_final_recommendation(
    *,
    sd_grid_backtest: pl.DataFrame,
    cme_wall_test_plan: pl.DataFrame,
    caution_audit: pl.DataFrame,
) -> str:
    """Choose a conservative final recommendation for the rulebook."""

    if caution_audit.filter(pl.col("severity") == "HIGH").height > 0:
        return "USE_AS_WATCHLIST_RULEBOOK_ONLY"
    cme_rows = cme_wall_test_plan.filter(pl.col("can_test_now")).height
    cme_needs_more = any(
        "Need at least" in _text(row.get("next_cme_data_needed"))
        for row in cme_wall_test_plan.to_dicts()
    )
    price_ready = sd_grid_backtest.filter(pl.col("event_count") > 0).height
    if cme_needs_more and price_ready:
        return "USE_AS_WATCHLIST_RULEBOOK_ONLY"
    if cme_rows == 0:
        return "CME_WALL_TEST_NEEDS_MORE_CME_DATA"
    if price_ready:
        return "SD_GRID_BACKTEST_READY"
    return "NOT_READY_FOR_MONEY"


def write_gemini_guru_rulebook_outputs(result: GeminiGuruRulebookIngestResult) -> None:
    """Write CSV and Markdown artifacts."""

    frame_paths = {
        "claims": result.claims,
        "cme_wall_rule_family": result.cme_wall_rule_family,
        "sd_grid_rule_family": result.sd_grid_rule_family,
        "entry_tp_sl_rule_family": result.entry_tp_sl_rule_family,
        "no_trade_rule_family": result.no_trade_rule_family,
        "dukascopy_rule_test_plan": result.dukascopy_rule_test_plan,
        "sd_grid_backtest": result.sd_grid_backtest,
        "cme_wall_test_plan": result.cme_wall_test_plan,
        "caution_audit": result.caution_audit,
    }
    csv_keys = {
        "claims": "claims_csv",
        "cme_wall_rule_family": "cme_wall_family_csv",
        "sd_grid_rule_family": "sd_grid_family_csv",
        "entry_tp_sl_rule_family": "entry_tp_sl_family_csv",
        "no_trade_rule_family": "no_trade_family_csv",
        "dukascopy_rule_test_plan": "dukascopy_plan_csv",
        "sd_grid_backtest": "sd_grid_backtest_csv",
        "cme_wall_test_plan": "cme_plan_csv",
        "caution_audit": "caution_audit_csv",
    }
    for name, frame in frame_paths.items():
        frame.write_csv(result.paths[csv_keys[name]])

    result.paths["claims_md"].write_text(
        _safe_report_text(_artifact_markdown("Gemini Guru Rulebook Claims", result.claims)),
        encoding="utf-8",
    )
    result.paths["dukascopy_plan_md"].write_text(
        _safe_report_text(
            _artifact_markdown("Gemini Dukascopy Rule Test Plan", result.dukascopy_rule_test_plan)
        ),
        encoding="utf-8",
    )
    result.paths["sd_grid_backtest_md"].write_text(
        _safe_report_text(
            _artifact_markdown("Gemini SD Grid Backtest", result.sd_grid_backtest)
        ),
        encoding="utf-8",
    )
    result.paths["cme_plan_md"].write_text(
        _safe_report_text(
            _artifact_markdown("Gemini CME Wall Test Plan", result.cme_wall_test_plan)
        ),
        encoding="utf-8",
    )
    result.paths["caution_audit_md"].write_text(
        _safe_report_text(
            _artifact_markdown("Gemini Rulebook Caution Audit", result.caution_audit)
        ),
        encoding="utf-8",
    )


def gemini_guru_rulebook_report_lines(
    result: GeminiGuruRulebookIngestResult | None,
) -> list[str]:
    """Return Markdown lines for research_report.md."""

    if result is None:
        return ["## Gemini Guru Rulebook Ingest", "", "Gemini rulebook ingest was not run."]
    strongest = _strongest_transcript_supported_rules(result.claims)
    dukascopy_ready = _dukascopy_ready_rules(result.dukascopy_rule_test_plan)
    cme_needed = _cme_needed_rules(result.cme_wall_test_plan)
    return [
        "## Gemini Guru Rulebook Ingest",
        "",
        RESEARCH_WARNING,
        "",
        f"- Claims parsed: {result.claims.height}",
        f"- Final recommendation: `{result.final_recommendation}`",
        "- Guardrail: `NOT_READY_FOR_MONEY` remains active.",
        "",
        "## Transcript-Supported vs Data-Validated Claims",
        "",
        _frame_markdown(
            result.claims.select(
                [
                    "claim_id",
                    "corrected_support_status",
                    "data_validation_status",
                    "rule_classification",
                ]
            )
        ),
        "",
        "## SD/Grid Backtest From Gemini Rules",
        "",
        _frame_markdown(result.sd_grid_backtest),
        "",
        "## CME Wall Test Plan",
        "",
        _frame_markdown(result.cme_wall_test_plan),
        "",
        "## Caution Audit",
        "",
        _frame_markdown(result.caution_audit),
        "",
        "## What Can Be Used Now",
        "",
        *[f"- `{rule}`" for rule in dukascopy_ready[:12]],
        "",
        "## What Needs More CME Data",
        "",
        *[f"- `{rule}`" for rule in cme_needed[:12]],
        "",
        "## Strongest Transcript-Supported Rules",
        "",
        *[f"- `{rule}`" for rule in strongest[:12]],
        "",
        "- Links: `outputs/gemini_guru_rulebook_claims.csv`, "
        "`outputs/gemini_sd_grid_backtest.csv`, "
        "`outputs/gemini_cme_wall_test_plan.csv`, "
        "`outputs/gemini_rulebook_caution_audit.csv`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when output text avoids restricted words and local paths."""

    safe = _safe_report_text(text)
    lowered = safe.lower()
    return safe == text and not any(
        re.search(pattern, lowered, flags=re.IGNORECASE)
        for pattern in FORBIDDEN_OUTPUT_PATTERNS
    )


def _claim_specs() -> list[dict[str, str]]:
    return [
        _claim(
            "WALL_AS_MAGNET",
            "Wall as magnet or target",
            "Large nearby CME OI walls are transcript-described as possible "
            "magnet/target attractors when price is inside the proximity filter.",
            "CME OI by strike|basis|Dukascopy price path|CME volume freshness",
            "TESTABLE_WITH_CME_OVERLAP",
            "TARGET_REFERENCE",
            aliases=("WALL_AS_MAGNET", "wall a target or magnet", "magnet"),
            keywords=("magnet", "target", "แรงดึง", "ไปที่นั่น"),
        ),
        _claim(
            "WALL_AS_TP",
            "Wall as TP reference",
            "High-OI walls and grid midpoints are transcript-described as TP "
            "references, not validated exit rules.",
            "CME OI walls|basis|Dukascopy forward price path",
            "TESTABLE_WITH_CME_OVERLAP",
            "TARGET_REFERENCE",
            aliases=("WALL_AS_TP", "Wall usage for Entry, TP", "TP_RULE"),
            keywords=("TP", "take-profit", "half-block", "ครึ่งบล็อก"),
        ),
        _claim(
            "WALL_AS_REJECTION",
            "Wall as rejection",
            "A wall touch followed by close-back-inside behavior is transcript-"
            "described as possible rejection context.",
            "CME OI wall|basis|1h or intraday OHLC|volume context",
            "TESTABLE_WITH_CME_OVERLAP",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("WALL_AS_REJECTION", "Institutional Boundary Rejection Zone"),
            keywords=("rejection", "แนวรับแนวต้าน", "support", "resistance"),
        ),
        _claim(
            "WALL_AS_ACCEPTANCE",
            "Wall acceptance or breakout",
            "A sustained hourly close beyond a wall is transcript-described as "
            "acceptance context.",
            "CME OI wall|basis|1h OHLC|volume context",
            "TESTABLE_WITH_CME_OVERLAP",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("WALL_AS_ACCEPTANCE", "ACCEPTANCE_CONFIRMATION"),
            keywords=("acceptance", "1-hour", "1 ชั่วโมง", "close above"),
        ),
        _claim(
            "MAX_OI_PIN",
            "Max OI pin",
            "Near expiry, max-OI strikes are transcript-described as pin-risk "
            "references.",
            "CME OI by strike|expiry calendar|basis|price path",
            "NEED_MORE_CME_DATA",
            "WATCH_ONLY",
            aliases=("MAX_OI_PIN", "Expiration Pin Risk Draw"),
            keywords=("pin", "expiration", "expiry", "วันสุดท้าย"),
        ),
        _claim(
            "LOW_OI_GAP_SQUEEZE",
            "Low-OI gap squeeze",
            "Low-OI areas between larger walls are transcript-described as "
            "possible fast-move corridors.",
            "Full strike-by-strike CME OI distribution|basis|price velocity",
            "NEED_MORE_CME_DATA",
            "WATCH_ONLY",
            aliases=("LOW_OI_GAP_SQUEEZE", "Gamma Squeeze Momentum State"),
            keywords=("LOW_OI_GAP", "low-OI", "void", "contract"),
        ),
        _claim(
            "CALL_WALL_RESISTANCE",
            "Call wall resistance",
            "Large call-OI concentrations above price are transcript-described "
            "as ceiling context.",
            "Call OI by strike|basis|price path",
            "TESTABLE_WITH_CME_OVERLAP",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("CALL_WALL_RESISTANCE",),
            keywords=("Call wall", "Call option", "ceiling"),
        ),
        _claim(
            "PUT_WALL_SUPPORT",
            "Put wall support",
            "Large put-OI concentrations below price are transcript-described "
            "as floor context.",
            "Put OI by strike|basis|price path",
            "TESTABLE_WITH_CME_OVERLAP",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("PUT_WALL_SUPPORT",),
            keywords=("Put wall", "Put option", "floor"),
        ),
        _claim(
            "WALL_PROXIMITY_100",
            "Wall proximity filter",
            "Walls farther than about 100 points are transcript-described as "
            "lower-priority context.",
            "CME wall level|spot price|basis",
            "TESTABLE_WITH_CME_OVERLAP",
            "WATCH_ONLY",
            aliases=("Proximity Decay Boundary", "100-tick Boundary"),
            keywords=("100", "แรงดึง", "proximity"),
        ),
        _claim(
            "EXPECTED_MOVE_IV_DIV_16",
            "Expected move IV divided by 16",
            "Daily expected move is transcript-described as IV divided by 16, "
            "projected from the session open.",
            "CME IV|session open price|timestamp-safe OHLC",
            "TESTABLE_WITH_CME_OVERLAP",
            "WATCH_ONLY",
            aliases=("Baseline Expected Move Divisor", "Baseline Volatility Divisor"),
            keywords=("IV", "16", "หาร"),
        ),
        _claim(
            "NO_TRADE_1SD",
            "1SD no-trade zone",
            "The inner 1SD area is transcript-described as random/no-trade "
            "context, not as a signal.",
            "Dukascopy OHLC|fixed SD proxy or CME IV seed",
            "TESTABLE_WITH_DUKASCOPY",
            "BLOCK",
            aliases=("NO_TRADE_MIDDLE", "The 1SD Central Median Filter"),
            keywords=("1SD", "1 SD", "หัวก้อย", "ไม่เทรด"),
        ),
        _claim(
            "ENTRY_2SD_3SD",
            "2SD to 3SD research candidate",
            "Outer 2SD/3SD zones are transcript-described as candidate zones "
            "that require additional confirmation.",
            "Dukascopy OHLC|fixed SD proxy or CME IV seed",
            "TESTABLE_WITH_DUKASCOPY",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("SD_GRID_ENTRY", "Extreme Statistical Reversion Trigger"),
            keywords=("2 SD", "3 SD", "2SD", "3SD"),
        ),
        _claim(
            "ENTRY_3SD_EXTREME",
            "3SD extreme research candidate",
            "The 3SD perimeter is transcript-described as an extreme zone, but "
            "blind use must be blocked by the caution audit.",
            "Dukascopy OHLC|fixed SD proxy or CME IV seed|rejection confirmation",
            "TESTABLE_WITH_DUKASCOPY",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("3SD_ENTRY", "3SD Primary Execution Rule"),
            keywords=("3SD", "3 SD", "ต้องเข้า", "ต้องเทรด"),
        ),
        _claim(
            "STOP_3_5SD",
            "3.5SD invalidation",
            "A 3.5SD extension is transcript-described as model invalidation "
            "or stop context.",
            "Dukascopy OHLC|fixed SD proxy or CME IV seed",
            "TESTABLE_WITH_DUKASCOPY",
            "BLOCK",
            aliases=("3.5SD_STOP", "Extreme Statistical Stop Limit"),
            keywords=("3.5SD", "3.5 SD", "3.5"),
        ),
        _claim(
            "TP_HALF_BLOCK_12_50",
            "Half-block 12.50 TP reference",
            "The 12.50 half-block is transcript-described as a local target "
            "reference.",
            "Dukascopy OHLC|fixed grid",
            "TESTABLE_WITH_DUKASCOPY",
            "TARGET_REFERENCE",
            aliases=("Half-Block Midpoint", "$12.50", "half-block"),
            keywords=("12.50", "half-block", "ครึ่งบล็อก"),
        ),
        _claim(
            "TP_FULL_BLOCK_25",
            "Full-block 25 TP reference",
            "The 25-point full block is transcript-described as a fixed grid "
            "reference.",
            "Dukascopy OHLC|fixed grid",
            "TESTABLE_WITH_DUKASCOPY",
            "TARGET_REFERENCE",
            aliases=("$25_GRID", "Fixed Structural Strike Blocks"),
            keywords=("25.00", "$25", "บล็อก 25"),
        ),
        _claim(
            "ACCEPTANCE_1H_CLOSE",
            "Hourly close acceptance",
            "A 1h candle close beyond a level is transcript-described as "
            "acceptance confirmation.",
            "Dukascopy 1h OHLC|level map|CME wall context when wall-specific",
            "TESTABLE_WITH_DUKASCOPY",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("ACCEPTANCE_CONFIRMATION", "High Volume Acceptance Continuation"),
            keywords=("1 ชั่วโมง", "1-hour", "hourly candle"),
        ),
        _claim(
            "REJECTION_BACK_INSIDE",
            "Rejection back inside",
            "A pierce and close back inside a boundary is transcript-described "
            "as rejection confirmation.",
            "Dukascopy OHLC|fixed level map",
            "TESTABLE_WITH_DUKASCOPY",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("REJECTION_CONFIRMATION", "Rejection Confirmation Vector"),
            keywords=("rejection", "back inside", "รีเวิร์ส"),
        ),
        _claim(
            "SUSPEND_ON_DATA_VOID",
            "Suspend on data void",
            "Missing CME updates are transcript-described as a watch-only or "
            "blocking state.",
            "CME refresh timestamp|data freshness flags",
            "CONTEXT_ONLY",
            "BLOCK",
            aliases=("SUSPEND_ON_DATA_VOID", "CME Data Delay Disconnection"),
            keywords=("data", "ไม่ได้อัปเดต", "No data"),
        ),
        _claim(
            "$25_GRID_CLUSTERING",
            "25-point grid clustering",
            "The 25-point matrix is testable as a price-only clustering "
            "diagnostic.",
            "Dukascopy OHLC|fixed 25-point grid",
            "TESTABLE_WITH_DUKASCOPY",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("$25_GRID", "Fixed Structural Strike Blocks"),
            keywords=("25.00", "$25", "บล็อก 25"),
        ),
        _claim(
            "$12_50_HALF_BLOCK_CLUSTERING",
            "12.50 half-block clustering",
            "The half-block midpoint is testable as a price-only clustering "
            "diagnostic.",
            "Dukascopy OHLC|fixed 12.50-point grid",
            "TESTABLE_WITH_DUKASCOPY",
            "ALLOW_RESEARCH_CANDIDATE",
            aliases=("half-block", "$12.50", "Half-Block Midpoint"),
            keywords=("12.50", "half-block", "ครึ่งบล็อก"),
        ),
    ]


def _claim(
    claim_id: str,
    rule_name: str,
    plain_english_logic: str,
    required_data: str,
    data_validation_status: str,
    rule_classification: str,
    *,
    aliases: tuple[str, ...],
    keywords: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "rule_name": rule_name,
        "plain_english_logic": plain_english_logic,
        "required_data": required_data,
        "data_validation_status": data_validation_status,
        "rule_classification": rule_classification,
        "aliases": aliases,
        "keywords": keywords,
        "risk_warning": (
            "Transcript-derived hypothesis only; requires timestamp-safe data "
            "testing before any research promotion."
        ),
    }


def _rule_blocks(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?ms)^####\s+(?P<title>[^\n]+)\n(?P<body>.*?)(?=^####\s+|^###\s+|\Z)"
    )
    blocks = []
    for match in pattern.finditer(text):
        title = match.group("title").strip()
        blocks.append(
            {
                "title": title,
                "body": match.group("body").strip(),
                "start": match.start(),
                "norm": _norm(title),
            }
        )
    return blocks


def _evidence_for_spec(
    spec: dict[str, Any],
    blocks: list[dict[str, Any]],
    full_text: str,
    supplemental: list[dict[str, str]],
) -> dict[str, Any]:
    aliases = tuple(_norm(alias) for alias in spec["aliases"])
    keywords = tuple(str(keyword).lower() for keyword in spec["keywords"])
    selected = _best_block(
        [block for block in blocks if any(alias and alias in block["norm"] for alias in aliases)]
    )
    if selected is None:
        selected = _best_block(
            [
                block
                for block in blocks
                if any(
                    keyword.lower() in f"{block['title']} {block['body']}".lower()
                    for keyword in keywords
                )
            ]
        )
    if selected is not None:
        body = selected["body"]
        section = selected["title"]
    else:
        offset = _first_keyword_offset(full_text, keywords)
        body = _window(full_text, offset, 900) if offset >= 0 else ""
        section = _section_for_offset(full_text, offset) if offset >= 0 else "NEEDS_SOURCE_REVIEW"

    source_evidence = _extract_source_evidence(body)
    if not source_evidence:
        source_evidence = _supplemental_evidence(spec, supplemental)
    source_ids = _source_ids(f"{body}\n{source_evidence}")
    thai_excerpt = _thai_excerpt(f"{source_evidence}\n{body}")
    return {
        "source_section": section,
        "body": body,
        "source_evidence": source_evidence or _window(body, 0, 450),
        "source_ids": source_ids,
        "thai_excerpt": thai_excerpt,
    }


def _best_block(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    scored = []
    for index, block in enumerate(candidates):
        body = str(block.get("body", ""))
        score = 0
        if _source_ids(body):
            score += 5
        if "Source Reference" in body or "Source Evidence" in body:
            score += 3
        if "Verification Status" in body:
            score += 2
        scored.append((score, -index, block))
    return max(scored, key=lambda item: (item[0], item[1]))[2]


def _claimed_support_status(body: str) -> str:
    match = re.search(
        r"Verification Status:\*\*\s*\*\*([^*.]+)",
        body,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".")
    if re.search(r"\bSupported\b", body, flags=re.IGNORECASE):
        return "Supported"
    return "Not explicitly labeled"


def _corrected_support_status(claimed: str, evidence: dict[str, Any]) -> str:
    claimed_text = claimed.lower()
    if "supported" in claimed_text and evidence["source_ids"]:
        return SUPPORTED_STATUS
    if evidence["source_ids"] or evidence["thai_excerpt"]:
        return "TRANSCRIPT_WEAK"
    return "NEEDS_SOURCE_REVIEW"


def _supplemental_evidence_rows(
    hypotheses: pl.DataFrame,
    knowledge_base: pl.DataFrame,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for frame in (hypotheses, knowledge_base):
        if frame.is_empty():
            continue
        for row in frame.to_dicts():
            rows.append(
                {
                    "id": _text(
                        row.get("hypothesis_id")
                        or row.get("logic_id")
                        or row.get("rule_id")
                    ),
                    "text": _text(
                        row.get("guru_evidence_excerpt")
                        or row.get("representative_excerpts")
                        or row.get("plain_english_logic")
                        or row.get("description")
                    ),
                }
            )
    return rows


def _supplemental_evidence(spec: dict[str, Any], rows: list[dict[str, str]]) -> str:
    keywords = tuple(str(keyword).lower() for keyword in spec["keywords"])
    for row in rows:
        blob = f"{row.get('id', '')} {row.get('text', '')}".lower()
        if any(keyword.lower() in blob for keyword in keywords):
            return row.get("text", "")[:700]
    return ""


def _extract_source_evidence(body: str) -> str:
    lines = []
    capture = False
    for line in body.splitlines():
        stripped = line.strip()
        if "Source Reference" in stripped or "Source Evidence" in stripped:
            capture = True
            lines.append(stripped)
            continue
        if capture and stripped.startswith("* **"):
            break
        if capture and stripped:
            lines.append(stripped)
        if capture and len(" ".join(lines)) > 900:
            break
    return " ".join(lines)[:1200]


def _source_ids(text: str) -> list[str]:
    ids = re.findall(r"\[([A-Za-z0-9_-]{6,})\]", text)
    return sorted(set(ids))


def _thai_excerpt(text: str) -> str:
    matches = re.findall(r'"([^"]*[\u0e00-\u0e7f][^"]*)"', text)
    if matches:
        return " || ".join(matches[:2])[:900]
    thai_chunks = re.findall(r"[\u0e00-\u0e7f][\u0e00-\u0e7f\s.,!?]{20,}", text)
    return " || ".join(chunk.strip() for chunk in thai_chunks[:2])[:900]


def _family_frame(
    claims_by_id: dict[str, dict[str, Any]],
    rule_ids: list[str],
    family: str,
) -> pl.DataFrame:
    rows = []
    for index, rule_id in enumerate(rule_ids, start=1):
        claim = claims_by_id.get(rule_id, _synthetic_claim(rule_id))
        rows.append(
            _safe_row(
                {
                    "family": family,
                    "priority": index,
                    "rule_id": rule_id,
                    "rule_name": claim.get("rule_name"),
                    "plain_english_logic": claim.get("plain_english_logic"),
                    "corrected_support_status": claim.get("corrected_support_status"),
                    "data_validation_status": claim.get("data_validation_status"),
                    "rule_classification": claim.get("rule_classification"),
                    "required_data": claim.get("required_data"),
                    "current_use": _current_use(claim),
                    "risk_warning": claim.get("risk_warning"),
                }
            )
        )
    return _frame(rows, _family_schema())


def _synthetic_claim(rule_id: str) -> dict[str, Any]:
    return {
        "claim_id": rule_id,
        "rule_name": rule_id.replace("_", " ").title(),
        "plain_english_logic": "Derived test-plan row; source claim should be reviewed.",
        "corrected_support_status": "NEEDS_SOURCE_REVIEW",
        "data_validation_status": "TESTABLE_WITH_DUKASCOPY"
        if "CME" not in rule_id and "WALL" not in rule_id
        else "NEED_MORE_CME_DATA",
        "rule_classification": "ALLOW_RESEARCH_CANDIDATE",
        "required_data": "Dukascopy OHLC",
        "risk_warning": "Review source evidence before use.",
    }


def _current_use(claim: dict[str, Any]) -> str:
    classification = _text(claim.get("rule_classification"))
    status = _text(claim.get("data_validation_status"))
    if classification == "BLOCK":
        return "Block or watch-only filter; not an entry instruction."
    if status == "NEED_MORE_CME_DATA":
        return "CME plan only until more timestamp-safe wall data exists."
    if status == "TESTABLE_WITH_DUKASCOPY":
        return "Price-only diagnostic candidate; not CME validation."
    if status == "TESTABLE_WITH_CME_OVERLAP":
        return "CME-overlap pilot candidate; sample-size limits apply."
    return "Context-only research note."


def _dukascopy_priority_rules() -> list[str]:
    return [
        "NO_TRADE_1SD",
        "ENTRY_2SD_3SD",
        "ENTRY_3SD_EXTREME",
        "STOP_3_5SD",
        "TP_HALF_BLOCK_12_50",
        "TP_FULL_BLOCK_25",
        "REJECTION_BACK_INSIDE",
        "ACCEPTANCE_1H_CLOSE",
        "$25_GRID_CLUSTERING",
        "$12_50_HALF_BLOCK_CLUSTERING",
    ]


def _sd_backtest_rule_ids() -> list[str]:
    return _dukascopy_priority_rules()


def _test_name(rule_id: str) -> str:
    names = {
        "NO_TRADE_1SD": "Measure outcomes inside fixed 1SD proxy zone.",
        "ENTRY_2SD_3SD": "Measure fixed 2SD to 3SD extreme-zone events.",
        "ENTRY_3SD_EXTREME": "Measure fixed 3SD extreme-zone events.",
        "STOP_3_5SD": "Measure 3.5SD invalidation hits after extreme events.",
        "TP_HALF_BLOCK_12_50": "Measure 12.50-point target references.",
        "TP_FULL_BLOCK_25": "Measure 25-point target references.",
        "REJECTION_BACK_INSIDE": "Measure pierce-and-close-back-inside events.",
        "ACCEPTANCE_1H_CLOSE": "Measure hourly close acceptance events.",
        "$25_GRID_CLUSTERING": "Measure price clustering around 25-point grid.",
        "$12_50_HALF_BLOCK_CLUSTERING": "Measure price clustering around 12.50 grid.",
    }
    return names.get(rule_id, rule_id)


def _dukascopy_required_inputs(rule_id: str) -> str:
    if rule_id == "ACCEPTANCE_1H_CLOSE":
        return "outputs/dukascopy_xau_1h.parquet"
    if "GRID" in rule_id:
        return "outputs/dukascopy_xau_15m.parquet|outputs/dukascopy_xau_1d.parquet"
    return "outputs/dukascopy_xau_15m.parquet|outputs/dukascopy_xau_1d.parquet"


def _fixed_parameters(rule_id: str) -> str:
    mapping = {
        "NO_TRADE_1SD": "abs(sigma_position)<=1.0",
        "ENTRY_2SD_3SD": "2.0<=abs(sigma_position)<3.0",
        "ENTRY_3SD_EXTREME": "abs(sigma_position)>=3.0",
        "STOP_3_5SD": "stop boundary at abs(sigma_position)>=3.5",
        "TP_HALF_BLOCK_12_50": "target_points=12.50",
        "TP_FULL_BLOCK_25": "target_points=25.00",
        "REJECTION_BACK_INSIDE": "pierce 2SD/3SD then close back inside",
        "ACCEPTANCE_1H_CLOSE": "1h close beyond 3SD proxy boundary",
        "$25_GRID_CLUSTERING": "grid=25.00,tolerance=1.50",
        "$12_50_HALF_BLOCK_CLUSTERING": "grid=12.50,tolerance=1.50",
    }
    return mapping.get(rule_id, "fixed transcript-derived threshold")


def _dukascopy_caution(rule_id: str) -> str:
    if rule_id in {"ENTRY_2SD_3SD", "ENTRY_3SD_EXTREME"}:
        return "Requires rejection/acceptance context; blind extreme-zone use is blocked."
    if rule_id == "NO_TRADE_1SD":
        return "Block/filter diagnostic only."
    return "Research diagnostic only; not a signal."


def _session_contexts(
    price_15m: pl.DataFrame,
    price_1d: pl.DataFrame,
    cme_iv: pl.DataFrame,
) -> list[dict[str, Any]]:
    iv_by_date = _iv_by_date(cme_iv)
    daily_ranges = _daily_range_by_date(price_1d)
    rows = price_15m.sort("timestamp").to_dicts()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        trade_date = _date_text(row.get("trade_date") or row.get("timestamp"))
        if trade_date:
            grouped.setdefault(trade_date, []).append(row)
    contexts = []
    ordered_dates = sorted(grouped)
    for trade_date in ordered_dates:
        bars = grouped[trade_date]
        session_open = _float(bars[0].get("open"))
        if session_open is None:
            continue
        one_sd, sd_source = _one_sd_for_date(
            trade_date,
            session_open,
            iv_by_date,
            daily_ranges,
            ordered_dates,
        )
        if one_sd <= 0:
            continue
        contexts.append(
            {
                "trade_date": trade_date,
                "session_open": session_open,
                "one_sd": one_sd,
                "sd_source": sd_source,
                "bars": bars,
                "spread_cost": _average_spread(bars),
            }
        )
    return contexts


def _simulate_rule(
    rule_id: str,
    sessions: list[dict[str, Any]],
    *,
    target_points: float,
    stop_mode: str,
) -> dict[str, Any]:
    events: list[dict[str, float | bool]] = []
    for session in sessions:
        bars = session["bars"]
        one_sd = float(session["one_sd"])
        session_open = float(session["session_open"])
        for index, bar in enumerate(bars[:-1]):
            event = _event_for_rule(rule_id, bar, session_open, one_sd)
            if event is None:
                continue
            future = bars[index + 1 : index + 17]
            if not future:
                continue
            events.append(
                _measure_event(
                    event,
                    future,
                    session_open=session_open,
                    one_sd=one_sd,
                    target_points=target_points,
                    stop_mode=stop_mode,
                    spread_cost=float(session["spread_cost"]),
                )
            )
    return _summary_backtest_row(rule_id, events)


def _event_for_rule(
    rule_id: str,
    bar: dict[str, Any],
    session_open: float,
    one_sd: float,
) -> dict[str, float] | None:
    close = _float(bar.get("close"))
    high = _float(bar.get("high"))
    low = _float(bar.get("low"))
    if close is None or high is None or low is None:
        return None
    sigma = (close - session_open) / one_sd
    high_sigma = (high - session_open) / one_sd
    low_sigma = (low - session_open) / one_sd
    if rule_id == "NO_TRADE_1SD" and abs(sigma) <= 1.0:
        return {"entry": close, "direction": 1.0 if sigma < 0 else -1.0}
    if rule_id in {"ENTRY_2SD_3SD", "TP_HALF_BLOCK_12_50", "TP_FULL_BLOCK_25"}:
        if 2.0 <= abs(sigma) < 3.0:
            return {"entry": close, "direction": -1.0 if sigma > 0 else 1.0}
    if rule_id in {"ENTRY_3SD_EXTREME", "STOP_3_5SD"} and abs(sigma) >= 3.0:
        return {"entry": close, "direction": -1.0 if sigma > 0 else 1.0}
    if rule_id == "REJECTION_BACK_INSIDE":
        if high_sigma >= 2.0 and close < session_open + 2.0 * one_sd:
            return {"entry": close, "direction": -1.0}
        if low_sigma <= -2.0 and close > session_open - 2.0 * one_sd:
            return {"entry": close, "direction": 1.0}
    return None


def _measure_event(
    event: dict[str, float],
    future: list[dict[str, Any]],
    *,
    session_open: float,
    one_sd: float,
    target_points: float,
    stop_mode: str,
    spread_cost: float,
) -> dict[str, float | bool]:
    direction = float(event["direction"])
    entry = float(event["entry"])
    highs = [_float(row.get("high")) for row in future]
    lows = [_float(row.get("low")) for row in future]
    clean_highs = [value for value in highs if value is not None]
    clean_lows = [value for value in lows if value is not None]
    if direction > 0:
        mfe = max((value - entry for value in clean_highs), default=0.0)
        mae = min((value - entry for value in clean_lows), default=0.0)
        stop_level = session_open - 3.5 * one_sd
        stop_distance = max(entry - stop_level, target_points)
        stop_hit = any(value <= stop_level for value in clean_lows) if stop_mode == "3_5sd" else False
    else:
        mfe = max((entry - value for value in clean_lows), default=0.0)
        mae = min((entry - value for value in clean_highs), default=0.0)
        stop_level = session_open + 3.5 * one_sd
        stop_distance = max(stop_level - entry, target_points)
        stop_hit = any(value >= stop_level for value in clean_highs) if stop_mode == "3_5sd" else False
    target_hit = mfe >= target_points
    expectancy = (target_points if target_hit else 0.0) - (
        stop_distance if stop_hit else 0.0
    ) - spread_cost
    return {
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "mfe": mfe,
        "mae": mae,
        "max_adverse": mae,
        "expectancy": expectancy,
        "spread_cost": spread_cost,
    }


def _simulate_acceptance_rule(
    price_1h: pl.DataFrame,
    sessions: list[dict[str, Any]],
) -> dict[str, Any]:
    if price_1h.is_empty():
        return _empty_backtest_row("ACCEPTANCE_1H_CLOSE", "TOO_EARLY")
    context_by_date = {session["trade_date"]: session for session in sessions}
    rows = price_1h.sort("timestamp").to_dicts()
    events = []
    for index, bar in enumerate(rows[:-1]):
        trade_date = _date_text(bar.get("trade_date") or bar.get("timestamp"))
        session = context_by_date.get(trade_date)
        if not session:
            continue
        close = _float(bar.get("close"))
        if close is None:
            continue
        session_open = float(session["session_open"])
        one_sd = float(session["one_sd"])
        sigma = (close - session_open) / one_sd
        if abs(sigma) < 3.0:
            continue
        future = rows[index + 1 : index + 9]
        if not future:
            continue
        direction = 1.0 if sigma > 0 else -1.0
        events.append(
            _measure_event(
                {"entry": close, "direction": direction},
                future,
                session_open=session_open,
                one_sd=one_sd,
                target_points=25.0,
                stop_mode="3_5sd",
                spread_cost=float(session["spread_cost"]),
            )
        )
    return _summary_backtest_row("ACCEPTANCE_1H_CLOSE", events)


def _grid_clustering_row(rule_id: str, price: pl.DataFrame, *, grid: float) -> dict[str, Any]:
    if price.is_empty():
        return _empty_backtest_row(rule_id, "TOO_EARLY")
    tolerance = 1.5
    values: list[float] = []
    for row in price.select(["open", "high", "low", "close"]).to_dicts():
        values.extend(_float(row.get(column)) for column in ("open", "high", "low", "close"))
    clean = [value for value in values if value is not None]
    distances = [_distance_to_grid(value, grid) for value in clean]
    hit_count = sum(1 for value in distances if value <= tolerance)
    rate = hit_count / len(clean) if clean else 0.0
    random_band = min(1.0, (2 * tolerance) / grid)
    interpretation = "MIXED"
    if len(clean) < 200:
        interpretation = "TOO_EARLY"
    elif rate <= random_band:
        interpretation = "WEAK"
    elif rate >= random_band * 1.25:
        interpretation = "PROMISING"
    return {
        "rule_id": rule_id,
        "event_count": len(clean),
        "target_hit_rate": rate,
        "stop_hit_rate": 0.0,
        "expectancy_proxy": rate - random_band,
        "average_mfe": _mean([max(0.0, tolerance - value) for value in distances]),
        "average_mae": -_mean(distances),
        "max_adverse_excursion": -max(distances) if distances else 0.0,
        "spread_cost_estimate": _spread_estimate(price),
        "sample_size_warning": len(clean) < 200,
        "interpretation": interpretation,
    }


def _summary_backtest_row(
    rule_id: str,
    events: list[dict[str, float | bool]],
) -> dict[str, Any]:
    if not events:
        return _empty_backtest_row(rule_id, "TOO_EARLY")
    event_count = len(events)
    target_rate = _bool_rate(events, "target_hit")
    stop_rate = _bool_rate(events, "stop_hit")
    expectancy = _mean([float(row.get("expectancy") or 0.0) for row in events])
    sample_warning = event_count < 100
    if rule_id == "NO_TRADE_1SD":
        interpretation = "MIXED" if not sample_warning else "TOO_EARLY"
        expectancy = 0.0
    elif sample_warning:
        interpretation = "TOO_EARLY"
    elif expectancy > 0 and target_rate >= stop_rate:
        interpretation = "PROMISING"
    elif expectancy > -1.0:
        interpretation = "MIXED"
    else:
        interpretation = "WEAK"
    return {
        "rule_id": rule_id,
        "event_count": event_count,
        "target_hit_rate": target_rate,
        "stop_hit_rate": stop_rate,
        "expectancy_proxy": expectancy,
        "average_mfe": _mean([float(row.get("mfe") or 0.0) for row in events]),
        "average_mae": _mean([float(row.get("mae") or 0.0) for row in events]),
        "max_adverse_excursion": min(float(row.get("max_adverse") or 0.0) for row in events),
        "spread_cost_estimate": _mean([float(row.get("spread_cost") or 0.0) for row in events]),
        "sample_size_warning": sample_warning,
        "interpretation": interpretation,
    }


def _empty_backtest_row(rule_id: str, interpretation: str) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "event_count": 0,
        "target_hit_rate": None,
        "stop_hit_rate": None,
        "expectancy_proxy": None,
        "average_mfe": None,
        "average_mae": None,
        "max_adverse_excursion": None,
        "spread_cost_estimate": None,
        "sample_size_warning": True,
        "interpretation": interpretation,
    }


def _normalize_price_frame(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame(schema=_price_schema())
    out = frame
    if "timestamp" not in out.columns:
        return pl.DataFrame(schema=_price_schema())
    for column in ("open", "high", "low", "close"):
        if column not in out.columns and f"mid_{column}" in out.columns:
            out = out.with_columns(pl.col(f"mid_{column}").alias(column))
        if column not in out.columns:
            out = out.with_columns(pl.lit(None).cast(pl.Float64).alias(column))
        else:
            out = out.with_columns(pl.col(column).cast(pl.Float64, strict=False).alias(column))
    if "trade_date" not in out.columns:
        out = out.with_columns(
            pl.col("timestamp").map_elements(_date_text, return_dtype=pl.Utf8).alias("trade_date")
        )
    if "spread_points" not in out.columns:
        out = out.with_columns(pl.lit(None).cast(pl.Float64).alias("spread_points"))
    return out.select(["timestamp", "trade_date", "open", "high", "low", "close", "spread_points"])


def _iv_by_date(frame: pl.DataFrame) -> dict[str, float]:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return {}
    iv_column = "implied_vol" if "implied_vol" in frame.columns else "implied_volatility"
    if iv_column not in frame.columns:
        return {}
    grouped = (
        frame.with_columns(
            [
                pl.col("trade_date").map_elements(_date_text, return_dtype=pl.Utf8),
                pl.col(iv_column).cast(pl.Float64, strict=False).alias("iv_value"),
            ]
        )
        .group_by("trade_date")
        .agg(pl.mean("iv_value").alias("iv_value"))
    )
    return {
        _text(row.get("trade_date")): float(row.get("iv_value"))
        for row in grouped.to_dicts()
        if _float(row.get("iv_value")) is not None
    }


def _daily_range_by_date(frame: pl.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    if frame.is_empty():
        return out
    for row in frame.to_dicts():
        trade_date = _date_text(row.get("trade_date") or row.get("timestamp"))
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        if trade_date and high is not None and low is not None and high >= low:
            out[trade_date] = high - low
    return out


def _one_sd_for_date(
    trade_date: str,
    session_open: float,
    iv_by_date: dict[str, float],
    daily_ranges: dict[str, float],
    ordered_dates: list[str],
) -> tuple[float, str]:
    iv = iv_by_date.get(trade_date)
    if iv is not None and iv > 0:
        return session_open * (iv / 100.0 / 16.0), "CME_IV_DIV_16"
    try:
        index = ordered_dates.index(trade_date)
    except ValueError:
        index = 0
    prior = [
        daily_ranges[day]
        for day in ordered_dates[max(0, index - 20) : index]
        if day in daily_ranges and daily_ranges[day] > 0
    ]
    if prior:
        return _median(prior) / 2.0, "REALIZED_RANGE_PROXY_20D"
    current = daily_ranges.get(trade_date)
    if current and current > 0:
        return current / 2.0, "SAME_DAY_RANGE_FALLBACK"
    return max(session_open * 0.01, 1.0), "ONE_PERCENT_FALLBACK"


def _current_testable_rows(
    rule_id: str,
    cme_oi: pl.DataFrame,
    basis: pl.DataFrame,
    overlap: pl.DataFrame,
) -> int:
    if cme_oi.is_empty():
        return 0
    required = ["trade_date", "strike"]
    if rule_id == "CALL_WALL_RESISTANCE":
        required.append("call_oi")
    elif rule_id == "PUT_WALL_SUPPORT":
        required.append("put_oi")
    elif rule_id == "MAX_OI_PIN":
        required.extend(["total_oi", "expiry"])
    else:
        required.append("total_oi")
    if any(column not in cme_oi.columns for column in required):
        return 0
    testable = cme_oi.drop_nulls(required).height
    if not basis.is_empty() and "trade_date" in basis.columns:
        testable = min(testable, basis.height)
    if not overlap.is_empty():
        overlap_rows = _overlap_testable_rows(overlap)
        if overlap_rows:
            testable = min(testable, overlap_rows)
    return int(testable)


def _available_rows_for_rule(
    rule_id: str,
    cme_oi: pl.DataFrame,
    cme_iv: pl.DataFrame,
    basis: pl.DataFrame,
    overlap: pl.DataFrame,
) -> int:
    if rule_id in {"WALL_AS_ACCEPTANCE", "WALL_AS_REJECTION"} and not overlap.is_empty():
        return overlap.height
    if rule_id == "WALL_PROXIMITY_100" and not basis.is_empty():
        return basis.height
    if rule_id == "EXPECTED_MOVE_IV_DIV_16" and not cme_iv.is_empty():
        return cme_iv.height
    return cme_oi.height if not cme_oi.is_empty() else 0


def _overlap_testable_rows(overlap: pl.DataFrame) -> int:
    if overlap.is_empty():
        return 0
    if "can_test_oi_wall" in overlap.columns:
        return overlap.filter(pl.col("can_test_oi_wall").cast(pl.Boolean, strict=False)).height
    return overlap.height


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    paths = {
        "guru_wall_logic_hypotheses": output_root / "guru_wall_logic_hypotheses.csv",
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_30m": output_root / "dukascopy_xau_30m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "price_1d": output_root / "dukascopy_xau_1d.parquet",
        "cme_oi": output_root / "cme_canonical_option_oi_by_strike.parquet",
        "cme_iv": output_root / "cme_canonical_option_iv_by_strike.parquet",
        "basis": output_root / "xau_basis_backfilled.parquet",
        "overlap_validation": output_root / "dukascopy_cme_overlap_validation.csv",
    }
    return {name: _read_optional(path) for name, path in paths.items()}


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "claims_csv": output_root / "gemini_guru_rulebook_claims.csv",
        "claims_md": output_root / "gemini_guru_rulebook_claims.md",
        "cme_wall_family_csv": output_root / "gemini_cme_wall_rule_family.csv",
        "sd_grid_family_csv": output_root / "gemini_sd_grid_rule_family.csv",
        "entry_tp_sl_family_csv": output_root / "gemini_entry_tp_sl_rule_family.csv",
        "no_trade_family_csv": output_root / "gemini_no_trade_rule_family.csv",
        "dukascopy_plan_csv": output_root / "gemini_dukascopy_rule_test_plan.csv",
        "dukascopy_plan_md": output_root / "gemini_dukascopy_rule_test_plan.md",
        "sd_grid_backtest_csv": output_root / "gemini_sd_grid_backtest.csv",
        "sd_grid_backtest_md": output_root / "gemini_sd_grid_backtest.md",
        "cme_plan_csv": output_root / "gemini_cme_wall_test_plan.csv",
        "cme_plan_md": output_root / "gemini_cme_wall_test_plan.md",
        "caution_audit_csv": output_root / "gemini_rulebook_caution_audit.csv",
        "caution_audit_md": output_root / "gemini_rulebook_caution_audit.md",
    }


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join(["# " + title, RESEARCH_WARNING, _frame_markdown(frame)])


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
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
    return _safe_text(str(value if value is not None else "")).replace("|", "\\|")[:700]


def _safe_report_text(text: str) -> str:
    safe = _safe_text(text)
    for pattern in FORBIDDEN_OUTPUT_PATTERNS:
        safe = re.sub(pattern, _replacement_for_pattern(pattern), safe, flags=re.IGNORECASE)
    return safe


def _replacement_for_pattern(pattern: str) -> str:
    if pattern in {r"buy", r"sell"}:
        return "direction"
    if "profit" in pattern:
        return "money-result"
    if "predicts" in pattern:
        return "forecasts"
    if "safe" in pattern or "live" in pattern:
        return "blocked"
    return "redacted"


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = _redact_paths(text)
    text = re.sub(r"buy", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"sell", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"profitability|profitable|profit factor|profit", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(r"safe to trade", "blocked phrase", text, flags=re.IGNORECASE)
    text = re.sub(r"live[- ]ready", "blocked phrase", text, flags=re.IGNORECASE)
    return text.strip()


def _redact_paths(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    safe = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", safe)
    return re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", safe)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _first_keyword_offset(text: str, keywords: Iterable[str]) -> int:
    lowered = text.lower()
    offsets = [lowered.find(keyword.lower()) for keyword in keywords if lowered.find(keyword.lower()) >= 0]
    return min(offsets) if offsets else -1


def _window(text: str, offset: int, width: int) -> str:
    if not text:
        return ""
    start = max(offset - width // 3, 0)
    end = min(start + width, len(text))
    return text[start:end].replace("\r", " ").replace("\n", " ")


def _section_for_offset(text: str, offset: int) -> str:
    if offset < 0:
        return "NEEDS_SOURCE_REVIEW"
    headings = list(re.finditer(r"(?m)^#{3,4}\s+(.+)$", text))
    selected = "Rulebook"
    for heading in headings:
        if heading.start() <= offset:
            selected = heading.group(1).strip()
        else:
            break
    return selected


def _strongest_transcript_supported_rules(claims: pl.DataFrame) -> list[str]:
    if claims.is_empty():
        return []
    rows = claims.filter(pl.col("corrected_support_status") == SUPPORTED_STATUS)
    if rows.is_empty():
        return []
    return rows.get_column("claim_id").to_list()


def _dukascopy_ready_rules(plan: pl.DataFrame) -> list[str]:
    if plan.is_empty() or "current_testable" not in plan.columns:
        return []
    return plan.filter(pl.col("current_testable")).get_column("rule_id").to_list()


def _cme_needed_rules(plan: pl.DataFrame) -> list[str]:
    if plan.is_empty():
        return []
    return plan.filter(
        pl.col("next_cme_data_needed").cast(pl.Utf8).str.contains("Need at least")
    ).get_column("rule_id").to_list()


def _distance_to_grid(value: float, grid: float) -> float:
    remainder = abs(value) % grid
    return min(remainder, grid - remainder)


def _average_spread(rows: list[dict[str, Any]]) -> float:
    values = [_float(row.get("spread_points")) for row in rows]
    clean = [value for value in values if value is not None and value >= 0]
    return _mean(clean) if clean else 0.5


def _spread_estimate(frame: pl.DataFrame) -> float:
    if frame.is_empty() or "spread_points" not in frame.columns:
        return 0.5
    values = [
        _float(value)
        for value in frame.get_column("spread_points").drop_nulls().to_list()
    ]
    clean = [value for value in values if value is not None and value >= 0]
    return _mean(clean) if clean else 0.5


def _bool_rate(rows: list[dict[str, Any]], key: str) -> float:
    return sum(1 for row in rows if bool(row.get(key))) / len(rows) if rows else 0.0


def _mean(values: Iterable[float]) -> float:
    clean = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    return sum(clean) / len(clean) if clean else 0.0


def _median(values: list[float]) -> float:
    clean = sorted(values)
    if not clean:
        return 0.0
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def _n_unique(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return int(frame.select(pl.col(column).n_unique()).item())


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows_by_key(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    return {_text(row.get(column)): row for row in frame.to_dicts()}


def _frame_input(inputs: dict[str, Any], key: str) -> pl.DataFrame:
    value = inputs.get(key)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


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


def _claims_schema() -> dict[str, Any]:
    return {
        "claim_id": pl.Utf8,
        "rule_name": pl.Utf8,
        "source_section": pl.Utf8,
        "plain_english_logic": pl.Utf8,
        "source_evidence": pl.Utf8,
        "transcript_source_id": pl.Utf8,
        "thai_excerpt": pl.Utf8,
        "claimed_support_status": pl.Utf8,
        "corrected_support_status": pl.Utf8,
        "data_validation_status": pl.Utf8,
        "rule_classification": pl.Utf8,
        "required_data": pl.Utf8,
        "risk_warning": pl.Utf8,
    }


def _family_schema() -> dict[str, Any]:
    return {
        "family": pl.Utf8,
        "priority": pl.Int64,
        "rule_id": pl.Utf8,
        "rule_name": pl.Utf8,
        "plain_english_logic": pl.Utf8,
        "corrected_support_status": pl.Utf8,
        "data_validation_status": pl.Utf8,
        "rule_classification": pl.Utf8,
        "required_data": pl.Utf8,
        "current_use": pl.Utf8,
        "risk_warning": pl.Utf8,
    }


def _dukascopy_plan_schema() -> dict[str, Any]:
    return {
        "priority": pl.Int64,
        "rule_id": pl.Utf8,
        "test_name": pl.Utf8,
        "data_validation_status": pl.Utf8,
        "required_inputs": pl.Utf8,
        "fixed_parameters": pl.Utf8,
        "leakage_control": pl.Utf8,
        "expected_outputs": pl.Utf8,
        "current_testable": pl.Boolean,
        "caution": pl.Utf8,
    }


def _sd_grid_backtest_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "event_count": pl.Int64,
        "target_hit_rate": pl.Float64,
        "stop_hit_rate": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "max_adverse_excursion": pl.Float64,
        "spread_cost_estimate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "interpretation": pl.Utf8,
    }


def _cme_plan_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "required_cme_fields": pl.Utf8,
        "current_available_rows": pl.Int64,
        "current_testable_rows": pl.Int64,
        "can_test_now": pl.Boolean,
        "current_result_if_available": pl.Utf8,
        "next_cme_data_needed": pl.Utf8,
    }


def _caution_schema() -> dict[str, Any]:
    return {
        "caution_id": pl.Utf8,
        "rule_id": pl.Utf8,
        "caution_type": pl.Utf8,
        "source_section": pl.Utf8,
        "evidence": pl.Utf8,
        "severity": pl.Utf8,
        "recommended_handling": pl.Utf8,
    }


def _price_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime,
        "trade_date": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "spread_points": pl.Float64,
    }


def main() -> None:
    """CLI entry point."""

    result = run_gemini_guru_rulebook_ingest()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"claims_parsed: {result.claims.height}")
    print(f"sd_grid_rows: {result.sd_grid_backtest.height}")


if __name__ == "__main__":
    main()
