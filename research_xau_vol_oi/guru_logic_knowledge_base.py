"""Guru logic knowledge base and CME data dependency matrix.

This layer separates transcript logic extraction from validation readiness.
It can summarize repeated guru concepts without CME data, but it blocks CME
validation labels until enough aligned validation-grade days exist.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl


MINIMUM_VALIDATION_DAYS = 60

LOGIC_TYPES = (
    "MARKET_MAP",
    "VOLATILITY_RANGE",
    "BASIS_MAPPING",
    "OI_WALL_ZONE",
    "OI_FRESHNESS",
    "NO_TRADE_FILTER",
    "ENTRY_TRIGGER",
    "ACCEPTANCE_CONFIRMATION",
    "REJECTION_CONFIRMATION",
    "PIN_RISK",
    "SQUEEZE_RISK",
    "RISK_MANAGEMENT",
    "POST_EVENT_COMMENTARY",
    "UNTESTABLE",
)

VALIDATION_STATUSES = (
    "LOGIC_EXTRACTED_NOT_VALIDATED",
    "VALIDATION_BLOCKED_BY_DATA",
    "READY_FOR_PRICE_ONLY_TEST",
    "READY_FOR_CME_VALIDATION",
    "VALIDATED",
    "FAILED",
)

RECOMMENDED_ACTIONS = (
    "USE_AS_PLAYBOOK_CONTEXT_NOW",
    "TEST_PRICE_ONLY_NOW",
    "TEST_WITH_CURRENT_CME_PILOT",
    "WAIT_FOR_MORE_CME_DATA",
    "COLLECT_REQUIRED_DATA_FIRST",
    "IGNORE_OR_REJECT",
)

FINAL_RECOMMENDATIONS = (
    "EXTRACT_LOGIC_NOW_COLLECT_CME_NEXT",
    "CME_DATA_REQUIRED_BEFORE_VALIDATION",
    "PRICE_ONLY_PILOT_READY",
    "CME_PILOT_READY",
    "VALIDATION_READY",
    "STOP_GURU_LOGIC_PATH",
)

RULE_TAG_TO_LOGIC_TYPE = {
    "BASIS_ADJUSTMENT": "BASIS_MAPPING",
    "IV_EXPECTED_MOVE": "VOLATILITY_RANGE",
    "ONE_SD_RANGE": "VOLATILITY_RANGE",
    "TWO_SD_STRESS": "VOLATILITY_RANGE",
    "THREE_SD_EXTREME": "VOLATILITY_RANGE",
    "IV_RV_VRP": "VOLATILITY_RANGE",
    "VOLATILITY_SMILE_SKEW": "VOLATILITY_RANGE",
    "OI_WALL": "OI_WALL_ZONE",
    "LOW_OI_GAP": "OI_WALL_ZONE",
    "MARKET_MAKER_GAMMA": "OI_WALL_ZONE",
    "OI_CHANGE_FRESHNESS": "OI_FRESHNESS",
    "INTRADAY_VOLUME": "OI_FRESHNESS",
    "NO_TRADE_DISCIPLINE": "NO_TRADE_FILTER",
    "STALE_DATA_WARNING": "NO_TRADE_FILTER",
    "NEWS_EVENT_WARNING": "NO_TRADE_FILTER",
    "ACCEPTANCE_CLOSE_CONFIRMATION": "ACCEPTANCE_CONFIRMATION",
    "REJECTION_AT_WALL": "REJECTION_CONFIRMATION",
    "PIN_RISK": "PIN_RISK",
    "SQUEEZE_RISK": "SQUEEZE_RISK",
    "OPEN_PRICE_THEORY": "MARKET_MAP",
}

LOGIC_DESCRIPTIONS = {
    "MARKET_MAP": "Uses visible market state to frame likely zones or regimes.",
    "VOLATILITY_RANGE": "Uses IV, expected move, or sigma bands to frame ranges.",
    "BASIS_MAPPING": "Maps futures or option strikes into spot-equivalent XAU levels.",
    "OI_WALL_ZONE": "Uses open-interest concentration by strike/expiry as zone context.",
    "OI_FRESHNESS": "Uses OI change or option volume to distinguish stale from fresh zones.",
    "NO_TRADE_FILTER": "Defines conditions where a setup should be filtered or observed only.",
    "ENTRY_TRIGGER": "Describes a conditional reaction trigger that still needs controls.",
    "ACCEPTANCE_CONFIRMATION": "Looks for price acceptance beyond a level before trusting a move.",
    "REJECTION_CONFIRMATION": "Looks for rejection at a level before treating the level as active.",
    "PIN_RISK": "Flags near-expiry pin or magnet behavior around strike concentration.",
    "SQUEEZE_RISK": "Flags low-OI gap or squeeze continuation risk after levels fail.",
    "RISK_MANAGEMENT": "Describes invalidation, sizing, or process limits as research context.",
    "POST_EVENT_COMMENTARY": "Explains behavior after it happened; not usable as a pre-event rule.",
    "UNTESTABLE": "Too vague or underspecified to validate without human rewrite.",
}

RULE_TAG_NAMES = {
    "BASIS_ADJUSTMENT": "Basis-adjusted strike mapping",
    "IV_EXPECTED_MOVE": "IV expected-move range",
    "ONE_SD_RANGE": "One standard-deviation range",
    "TWO_SD_STRESS": "Two standard-deviation stress range",
    "THREE_SD_EXTREME": "Three standard-deviation extreme",
    "IV_RV_VRP": "IV/RV/VRP regime",
    "VOLATILITY_SMILE_SKEW": "Volatility smile and skew context",
    "OI_WALL": "Open-interest wall zone",
    "LOW_OI_GAP": "Low-OI gap map",
    "MARKET_MAKER_GAMMA": "Market-maker gamma context",
    "OI_CHANGE_FRESHNESS": "OI freshness check",
    "INTRADAY_VOLUME": "Option volume freshness check",
    "NO_TRADE_DISCIPLINE": "No-trade discipline",
    "STALE_DATA_WARNING": "Stale-data filter",
    "NEWS_EVENT_WARNING": "Macro/news-event filter",
    "ACCEPTANCE_CLOSE_CONFIRMATION": "Acceptance close confirmation",
    "REJECTION_AT_WALL": "Rejection at wall confirmation",
    "PIN_RISK": "Pin-risk zone",
    "SQUEEZE_RISK": "Squeeze-risk zone",
    "OPEN_PRICE_THEORY": "Session open market map",
}

PRICE_ONLY_PILOT_TYPES = {
    "NO_TRADE_FILTER",
    "ENTRY_TRIGGER",
    "ACCEPTANCE_CONFIRMATION",
    "REJECTION_CONFIRMATION",
    "RISK_MANAGEMENT",
}


@dataclass(frozen=True)
class CmeAvailability:
    """Current availability state for validation-grade CME data."""

    complete_validation_days: int
    has_xau_spot: bool
    has_gc_futures: bool
    has_basis: bool
    has_oi_by_strike: bool
    has_oi_change: bool
    has_option_volume: bool
    has_iv: bool
    has_iv_skew: bool
    has_term_structure: bool
    has_option_settlement: bool
    has_macro_calendar: bool
    has_price_outcome: bool


@dataclass(frozen=True)
class GuruLogicKnowledgeBaseResult:
    """Knowledge-base outputs and conservative recommendation."""

    knowledge_base: pl.DataFrame
    dependency_matrix: pl.DataFrame
    priority_rank: pl.DataFrame
    collection_plan: pl.DataFrame
    validation_path: pl.DataFrame
    final_recommendation: str
    current_available_validation_days: int
    minimum_validation_days: int


def run_guru_logic_knowledge_base_layer(
    *,
    output_dir: str | Path,
    inputs: dict[str, pl.DataFrame] | None = None,
    minimum_validation_days: int = MINIMUM_VALIDATION_DAYS,
) -> GuruLogicKnowledgeBaseResult:
    """Build all Guru Logic Knowledge Base outputs."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    loaded = inputs or load_guru_logic_inputs(output_root)
    result = build_guru_logic_knowledge_base(
        loaded,
        minimum_validation_days=minimum_validation_days,
    )
    result.knowledge_base.write_csv(output_root / "guru_logic_knowledge_base.csv")
    result.dependency_matrix.write_csv(output_root / "guru_logic_data_dependency_matrix.csv")
    result.priority_rank.write_csv(output_root / "guru_logic_priority_rank.csv")
    result.collection_plan.write_csv(output_root / "cme_collection_plan_for_guru_logic.csv")
    result.validation_path.write_csv(output_root / "guru_logic_validation_path.csv")
    (output_root / "guru_logic_knowledge_base.md").write_text(
        guru_logic_knowledge_base_markdown(result),
        encoding="utf-8",
    )
    (output_root / "guru_logic_data_dependency_matrix.md").write_text(
        guru_logic_data_dependency_matrix_markdown(result),
        encoding="utf-8",
    )
    (output_root / "cme_collection_plan_for_guru_logic.md").write_text(
        cme_collection_plan_markdown(result),
        encoding="utf-8",
    )
    (output_root / "guru_logic_validation_path.md").write_text(
        guru_logic_validation_path_markdown(result),
        encoding="utf-8",
    )
    return result


def load_guru_logic_inputs(output_dir: str | Path) -> dict[str, pl.DataFrame]:
    """Load optional generated artifacts from an output directory."""

    root = Path(output_dir)
    inputs: dict[str, pl.DataFrame] = {}
    csv_names = [
        "transcript_corpus_manifest",
        "guru_full_context_review_suggestions",
        "guru_logic_classification_summary",
        "cme_validation_grade_days",
        "cme_data_requirements_checklist",
        "transcript_rule_timeline",
        "transcript_llm_extracted_rules",
        "guru_full_context_review_pack",
        "guru_decision_episodes",
        "guru_episode_outcomes",
        "transcript_market_coverage_alignment",
        "market_data_coverage_manifest",
    ]
    for name in csv_names:
        path = root / f"{name}.csv"
        if not path.exists():
            continue
        try:
            inputs[name] = pl.read_csv(path, infer_schema_length=1000)
        except Exception:  # pragma: no cover - local corrupted artifact
            inputs[name] = pl.DataFrame()
    validation_dataset = root / "xau_vol_oi_validation_dataset.parquet"
    if validation_dataset.exists():
        try:
            inputs["xau_vol_oi_validation_dataset"] = pl.read_parquet(validation_dataset)
        except Exception:  # pragma: no cover - local corrupted artifact
            inputs["xau_vol_oi_validation_dataset"] = pl.DataFrame()
    return inputs


def build_guru_logic_knowledge_base(
    inputs: dict[str, pl.DataFrame],
    *,
    minimum_validation_days: int = MINIMUM_VALIDATION_DAYS,
) -> GuruLogicKnowledgeBaseResult:
    """Build knowledge base, dependency matrix, priority rank, and plans."""

    availability = cme_availability_from_inputs(inputs)
    records = collect_logic_records(inputs)
    knowledge_base = build_knowledge_base_frame(
        records,
        availability=availability,
        minimum_validation_days=minimum_validation_days,
    )
    dependency = build_dependency_matrix(
        knowledge_base,
        availability=availability,
        minimum_validation_days=minimum_validation_days,
    )
    priority = build_priority_rank(knowledge_base, dependency, availability=availability)
    collection_plan = build_collection_plan(
        dependency,
        availability=availability,
        minimum_validation_days=minimum_validation_days,
    )
    validation_path = build_validation_path_by_logic_type(
        availability=availability,
        minimum_validation_days=minimum_validation_days,
    )
    final_recommendation = choose_final_recommendation(
        knowledge_base,
        availability=availability,
        minimum_validation_days=minimum_validation_days,
    )
    return GuruLogicKnowledgeBaseResult(
        knowledge_base=knowledge_base,
        dependency_matrix=dependency,
        priority_rank=priority,
        collection_plan=collection_plan,
        validation_path=validation_path,
        final_recommendation=final_recommendation,
        current_available_validation_days=availability.complete_validation_days,
        minimum_validation_days=minimum_validation_days,
    )


def cme_availability_from_inputs(inputs: dict[str, pl.DataFrame]) -> CmeAvailability:
    """Summarize available validation fields from generated data artifacts."""

    validation_days = _frame(inputs, "cme_validation_grade_days")
    alignment = _frame(inputs, "transcript_market_coverage_alignment")
    market = _frame(inputs, "market_data_coverage_manifest")
    validation_dataset = _frame(inputs, "xau_vol_oi_validation_dataset")
    complete_days = _true_count(validation_days, "complete_validation_grade")
    if complete_days == 0 and not alignment.is_empty():
        complete_days = _true_count(alignment, "can_run_full_vol_oi_validation")
    has_price_outcome = (
        not validation_dataset.is_empty()
        or _any_true(alignment, "can_run_price_only_outcome_test")
        or _market_has_any(market, ["close", "ohlc", "xau", "gc=f"])
    )
    return CmeAvailability(
        complete_validation_days=complete_days,
        has_xau_spot=_any_true(validation_days, "has_xau_spot_price")
        or _any_true(alignment, "has_xau_price_data"),
        has_gc_futures=_any_true(validation_days, "has_gc_futures_price")
        or _any_true(alignment, "has_cme_futures_data"),
        has_basis=_any_true(validation_days, "has_basis") or _any_true(alignment, "has_basis_data"),
        has_oi_by_strike=_any_true(validation_days, "has_option_oi_by_strike")
        or _any_true(alignment, "has_cme_options_oi_data"),
        has_oi_change=_any_true(validation_days, "has_option_oi_change")
        or _market_has_any(market, ["oi_change"]),
        has_option_volume=_any_true(validation_days, "has_option_volume")
        or _market_has_any(market, ["option_volume", "volume"]),
        has_iv=_any_true(validation_days, "has_option_iv") or _any_true(alignment, "has_cme_iv_data"),
        has_iv_skew=_market_has_any(market, ["iv_skew", "skew", "call_iv", "put_iv"]),
        has_term_structure=_any_true(validation_days, "has_expiry_dte")
        or _market_has_any(market, ["term_structure", "expiry", "dte"]),
        has_option_settlement=_any_true(validation_days, "has_option_settlement")
        or _market_has_any(market, ["settlement", "settle"]),
        has_macro_calendar=_any_true(validation_days, "has_macro_event_flag")
        or _market_has_any(market, ["macro", "event", "calendar"]),
        has_price_outcome=has_price_outcome,
    )


def collect_logic_records(inputs: dict[str, pl.DataFrame]) -> list[dict[str, Any]]:
    """Collect normalized logic records without requiring CME data."""

    records: list[dict[str, Any]] = []
    suggestions = _frame(inputs, "guru_full_context_review_suggestions")
    for row in suggestions.to_dicts():
        records.append(_record_from_row(row, source="full_context_review"))
    extracted = _frame(inputs, "transcript_llm_extracted_rules")
    for row in extracted.to_dicts():
        records.append(_record_from_row(row, source="llm_extracted_rule"))
    timeline = _frame(inputs, "transcript_rule_timeline")
    for row in timeline.to_dicts():
        for tag in _split_tags(row.get("detected_rule_tags")):
            derived = {
                **row,
                "rule_tag": tag,
                "source_excerpt": "",
                "normalized_english_summary": "",
                "rule_type": "TIMELINE_TAG",
                "condition": "",
                "testability_score": None,
            }
            records.append(_record_from_row(derived, source="timeline_tag"))
    if records:
        return records
    summary = _frame(inputs, "guru_logic_classification_summary")
    for row in summary.to_dicts():
        count = int(_float_or_zero(row.get("episode_count")))
        for index in range(max(count, 1)):
            logic_type = _normalize_logic_type(row.get("suggested_guru_logic_type"))
            records.append(
                {
                    "logic_key": logic_type,
                    "rule_tag": logic_type,
                    "logic_type": logic_type,
                    "transcript_id": f"classification_summary_{index}",
                    "transcript_date": "",
                    "availability_timestamp": "",
                    "source_excerpt": "",
                    "summary": "",
                    "confidence_score": 0.5,
                    "testability_score": _default_testability(logic_type),
                    "source": "classification_summary",
                }
            )
    return records


def build_knowledge_base_frame(
    records: list[dict[str, Any]],
    *,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> pl.DataFrame:
    """Build the repeated-concept knowledge-base frame."""

    if not records:
        return _empty_knowledge_base()
    grouped = _group_records(records, "logic_key")
    repeated = {key: rows for key, rows in grouped.items() if _transcript_count(rows) >= 2}
    selected = repeated or grouped
    output = []
    for key, rows in selected.items():
        first = rows[0]
        logic_type = _normalize_logic_type(first.get("logic_type"))
        rule_tag = str(first.get("rule_tag") or key)
        transcript_ids = sorted({str(row.get("transcript_id") or "") for row in rows if row.get("transcript_id")})
        dates = sorted({date for row in rows if (date := _date_text(row.get("transcript_date")))})
        excerpts = _representative_excerpts(rows)
        confidence = _average_score([row.get("confidence_score") for row in rows], default=0.55)
        testability = _average_score(
            [row.get("testability_score") for row in rows],
            default=_default_testability(logic_type),
        )
        output.append(
            {
                "logic_id": _logic_id(key),
                "logic_name": _logic_name(rule_tag, logic_type),
                "logic_type": logic_type,
                "description": _description(rule_tag, logic_type),
                "transcript_count": max(_transcript_count(rows), len(rows)),
                "first_seen_date": dates[0] if dates else "",
                "last_seen_date": dates[-1] if dates else "",
                "representative_transcript_ids": "|".join(transcript_ids[:5]),
                "representative_excerpts": " || ".join(excerpts),
                "confidence_score": confidence,
                "testability_score": testability,
                "validation_status": validation_status_for_logic_type(
                    logic_type,
                    availability=availability,
                    minimum_validation_days=minimum_validation_days,
                ),
                "notes": _knowledge_base_notes(logic_type, availability, minimum_validation_days),
            }
        )
    return pl.DataFrame(output, infer_schema_length=None).sort(
        ["transcript_count", "testability_score"],
        descending=[True, True],
    )


def build_dependency_matrix(
    knowledge_base: pl.DataFrame,
    *,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> pl.DataFrame:
    """Build per-logic CME and market-data dependencies."""

    if knowledge_base.is_empty():
        return _empty_dependency_matrix()
    rows = []
    for logic in knowledge_base.to_dicts():
        deps = dependencies_for_logic(
            str(logic["logic_type"]),
            logic_name=str(logic["logic_name"]),
        )
        missing = missing_dependency_fields(deps, availability)
        validation_blocker = dependency_blocker(
            logic_type=str(logic["logic_type"]),
            missing=missing,
            availability=availability,
            minimum_validation_days=minimum_validation_days,
        )
        rows.append(
            {
                "logic_id": logic["logic_id"],
                "logic_name": logic["logic_name"],
                **deps,
                "minimum_validation_days": minimum_validation_days
                if str(logic["logic_type"]) not in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}
                else 0,
                "current_available_validation_days": availability.complete_validation_days,
                "validation_blocker": validation_blocker,
                "next_data_to_collect": next_data_to_collect(missing, availability, minimum_validation_days),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def dependencies_for_logic(logic_type: str, *, logic_name: str = "") -> dict[str, bool]:
    """Return required data flags for a logic type."""

    logic_type = _normalize_logic_type(logic_type)
    lower_name = logic_name.lower()
    deps = {
        "requires_xau_spot": False,
        "requires_gc_futures": False,
        "requires_basis": False,
        "requires_cme_oi_by_strike": False,
        "requires_oi_change": False,
        "requires_option_volume": False,
        "requires_iv": False,
        "requires_iv_skew": False,
        "requires_term_structure": False,
        "requires_option_settlement": False,
        "requires_macro_calendar": False,
        "requires_transcript_timestamp": logic_type not in {"UNTESTABLE"},
        "requires_price_outcome": False,
    }
    if logic_type == "BASIS_MAPPING":
        deps.update(requires_xau_spot=True, requires_gc_futures=True, requires_basis=True)
    elif logic_type == "OI_WALL_ZONE":
        deps.update(
            requires_xau_spot=True,
            requires_gc_futures=True,
            requires_basis=True,
            requires_cme_oi_by_strike=True,
            requires_price_outcome=True,
        )
    elif logic_type == "OI_FRESHNESS":
        deps.update(
            requires_cme_oi_by_strike=True,
            requires_oi_change=True,
            requires_option_volume=True,
            requires_price_outcome=True,
        )
    elif logic_type == "VOLATILITY_RANGE":
        deps.update(requires_xau_spot=True, requires_iv=True, requires_price_outcome=True)
        deps["requires_iv_skew"] = "skew" in lower_name or "smile" in lower_name
        deps["requires_term_structure"] = "term" in lower_name
    elif logic_type == "NO_TRADE_FILTER":
        deps.update(
            requires_xau_spot=True,
            requires_iv=True,
            requires_macro_calendar="news" in lower_name or "macro" in lower_name,
            requires_price_outcome=True,
        )
    elif logic_type in {"ENTRY_TRIGGER", "ACCEPTANCE_CONFIRMATION", "REJECTION_CONFIRMATION"}:
        deps.update(requires_xau_spot=True, requires_price_outcome=True)
    elif logic_type == "PIN_RISK":
        deps.update(
            requires_xau_spot=True,
            requires_cme_oi_by_strike=True,
            requires_option_settlement=True,
            requires_price_outcome=True,
        )
    elif logic_type == "SQUEEZE_RISK":
        deps.update(
            requires_xau_spot=True,
            requires_basis=True,
            requires_cme_oi_by_strike=True,
            requires_oi_change=True,
            requires_option_volume=True,
            requires_price_outcome=True,
        )
    elif logic_type == "RISK_MANAGEMENT":
        deps.update(requires_xau_spot=True, requires_price_outcome=True)
    elif logic_type == "MARKET_MAP":
        deps.update(requires_xau_spot=True, requires_price_outcome=True)
    return deps


def build_priority_rank(
    knowledge_base: pl.DataFrame,
    dependency_matrix: pl.DataFrame,
    *,
    availability: CmeAvailability,
) -> pl.DataFrame:
    """Rank logic by usefulness now, testability, and missing-data pressure."""

    if knowledge_base.is_empty():
        return _empty_priority_rank()
    deps_by_id = {row["logic_id"]: row for row in dependency_matrix.to_dicts()}
    max_count = max(int(row.get("transcript_count") or 0) for row in knowledge_base.to_dicts()) or 1
    rows = []
    for logic in knowledge_base.to_dicts():
        logic_type = str(logic["logic_type"])
        deps = deps_by_id.get(logic["logic_id"], {})
        missing = _missing_from_dependency_row(deps)
        repeat_score = min(1.0, int(logic.get("transcript_count") or 0) / max_count)
        testability = _float_or_zero(logic.get("testability_score"))
        data_score = _current_data_score(
            missing=missing,
            availability=availability,
            logic_type=logic_type,
        )
        usefulness = _usefulness_score(logic_type)
        vagueness_penalty = _vagueness_penalty(logic_type)
        missing_cme_penalty = 0.35 if missing or availability.complete_validation_days < MINIMUM_VALIDATION_DAYS else 0.0
        score = (0.30 * repeat_score) + (0.25 * testability) + (0.20 * data_score) + (
            0.25 * usefulness
        ) - vagueness_penalty - missing_cme_penalty
        action = recommended_action(
            logic_type=logic_type,
            missing=missing,
            availability=availability,
        )
        rows.append(
            {
                "rank": 0,
                "logic_id": logic["logic_id"],
                "logic_name": logic["logic_name"],
                "logic_type": logic_type,
                "transcript_count": logic["transcript_count"],
                "confidence_score": logic["confidence_score"],
                "testability_score": logic["testability_score"],
                "current_data_availability_score": round(data_score, 4),
                "likely_usefulness_as_filter_or_map": round(usefulness, 4),
                "vague_or_post_event_penalty": round(vagueness_penalty, 4),
                "missing_cme_fields_penalty": round(missing_cme_penalty, 4),
                "priority_score": round(max(0.0, min(1.0, score)), 4),
                "recommended_action": action,
                "rationale": _priority_rationale(action, missing, availability),
            }
        )
    sorted_rows = sorted(rows, key=lambda row: row["priority_score"], reverse=True)
    for index, row in enumerate(sorted_rows, start=1):
        row["rank"] = index
    return pl.DataFrame(sorted_rows, infer_schema_length=None)


def build_collection_plan(
    dependency_matrix: pl.DataFrame,
    *,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> pl.DataFrame:
    """Build the CME collection shopping list for guru logic validation."""

    needed_by = _needed_logic_names_by_source(dependency_matrix)
    source_specs = [
        (
            "XAU/USD intraday spot coverage",
            "requires_xau_spot",
            "timestamp, open, high, low, close, source_label",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "CRITICAL",
            availability.has_xau_spot,
            "Export or import true XAUUSD spot or clearly labeled proxy OHLC.",
            "Spot intraday OHLC export; use UTC timestamps.",
        ),
        (
            "GC futures price for basis",
            "requires_gc_futures",
            "timestamp, contract, open, high, low, close, settlement",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "CRITICAL",
            availability.has_gc_futures,
            "Collect GC futures prices aligned to transcript and option snapshots.",
            "CME GC futures intraday/daily price export.",
        ),
        (
            "CME Open Interest Heatmap/Profile by strike and expiry",
            "requires_cme_oi_by_strike",
            "trade_date, timestamp, expiry, dte, strike, call_oi, put_oi, total_oi",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "CRITICAL",
            availability.has_oi_by_strike,
            "Extend OI by strike/expiry coverage across more dates.",
            "Open Interest Heatmap or Profile export.",
        ),
        (
            "OI change",
            "requires_oi_change",
            "trade_date, expiry, strike, call_oi_change, put_oi_change, total_oi_change",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "HIGH",
            availability.has_oi_change,
            "Collect OI change to identify fresh versus stale walls.",
            "Open Interest Profile with change columns.",
        ),
        (
            "Option volume / Most Active Strikes",
            "requires_option_volume",
            "trade_date, timestamp, expiry, strike, call_volume, put_volume, total_volume",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "HIGH",
            availability.has_option_volume,
            "Collect option volume to cross-check OI freshness.",
            "Most Active Strikes or option volume export.",
        ),
        (
            "QuikVol / IV by strike and expiry",
            "requires_iv",
            "trade_date, timestamp, expiry, strike, call_iv, put_iv, atm_iv",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "HIGH",
            availability.has_iv,
            "Collect IV context for expected range and vol filters.",
            "QuikVol by strike/expiry export.",
        ),
        (
            "Option settlements",
            "requires_option_settlement",
            "trade_date, expiry, strike, option_type, settlement, underlying_settlement",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "MEDIUM",
            availability.has_option_settlement,
            "Collect settlements for expiry and pin-risk checks.",
            "Daily option settlement export.",
        ),
        (
            "Macro event calendar",
            "requires_macro_calendar",
            "event_date, event_time, event_name, importance, instrument_scope",
            "60 aligned sessions",
            "120-250 aligned sessions",
            "MEDIUM",
            availability.has_macro_calendar,
            "Add CPI/FOMC/NFP and major event tags for no-trade filters.",
            "Economic calendar CSV with UTC timestamps.",
        ),
        (
            "CFTC COT slower regime context",
            "optional_cot_context",
            "report_date, managed_money_long, managed_money_short, open_interest",
            "26 weekly reports",
            "104 weekly reports",
            "LOW",
            False,
            "Optional slower context after core CME validation fields are extended.",
            "CFTC COT legacy or disaggregated futures report.",
        ),
    ]
    rows = []
    for source_name, dependency_key, fields, minimum_range, recommended_range, priority, available, action, menu in source_specs:
        rows.append(
            {
                "source_name": source_name,
                "needed_for_logic": "; ".join(needed_by.get(dependency_key, [])) or "future robustness context",
                "required_fields": fields,
                "minimum_date_range": minimum_range,
                "recommended_date_range": recommended_range,
                "priority": priority,
                "current_status": _collection_status(available, availability, minimum_validation_days),
                "user_action_required": _collection_user_action(
                    available,
                    availability,
                    minimum_validation_days,
                    action,
                ),
                "example_export_menu": menu,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def build_validation_path_by_logic_type(
    *,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> pl.DataFrame:
    """Build validation path rows for every supported logic type."""

    rows = []
    for logic_type in LOGIC_TYPES:
        rows.append(
            {
                "logic_type": logic_type,
                "what_can_be_done_now": _what_can_be_done_now(logic_type, availability),
                "what_cannot_be_proven_yet": _what_cannot_be_proven_yet(
                    logic_type,
                    availability,
                    minimum_validation_days,
                ),
                "minimum_data_needed": _minimum_data_needed(logic_type, minimum_validation_days),
                "validation_method": _validation_method(logic_type),
                "pass_criteria": _pass_criteria(logic_type, minimum_validation_days),
                "fail_criteria": _fail_criteria(logic_type),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def validation_status_for_logic_type(
    logic_type: str,
    *,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> str:
    """Return a conservative validation status."""

    logic_type = _normalize_logic_type(logic_type)
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "LOGIC_EXTRACTED_NOT_VALIDATED"
    if logic_type in PRICE_ONLY_PILOT_TYPES and availability.has_price_outcome:
        return "READY_FOR_PRICE_ONLY_TEST"
    deps = dependencies_for_logic(logic_type)
    missing = missing_dependency_fields(deps, availability)
    if missing or availability.complete_validation_days < minimum_validation_days:
        return "VALIDATION_BLOCKED_BY_DATA"
    return "READY_FOR_CME_VALIDATION"


def missing_dependency_fields(deps: dict[str, bool], availability: CmeAvailability) -> list[str]:
    """Return missing required fields for a dependency flag row."""

    fields = [
        ("requires_xau_spot", "XAU/USD spot"),
        ("requires_gc_futures", "GC futures"),
        ("requires_basis", "basis"),
        ("requires_cme_oi_by_strike", "CME OI by strike/expiry"),
        ("requires_oi_change", "OI change"),
        ("requires_option_volume", "option volume"),
        ("requires_iv", "IV"),
        ("requires_iv_skew", "IV skew"),
        ("requires_term_structure", "term structure"),
        ("requires_option_settlement", "option settlement"),
        ("requires_macro_calendar", "macro calendar"),
        ("requires_price_outcome", "price outcome"),
    ]
    availability_by_key = {
        "requires_xau_spot": availability.has_xau_spot,
        "requires_gc_futures": availability.has_gc_futures,
        "requires_basis": availability.has_basis,
        "requires_cme_oi_by_strike": availability.has_oi_by_strike,
        "requires_oi_change": availability.has_oi_change,
        "requires_option_volume": availability.has_option_volume,
        "requires_iv": availability.has_iv,
        "requires_iv_skew": availability.has_iv_skew,
        "requires_term_structure": availability.has_term_structure,
        "requires_option_settlement": availability.has_option_settlement,
        "requires_macro_calendar": availability.has_macro_calendar,
        "requires_price_outcome": availability.has_price_outcome,
    }
    return [
        label
        for key, label in fields
        if bool(deps.get(key)) and not bool(availability_by_key.get(key))
    ]


def choose_final_recommendation(
    knowledge_base: pl.DataFrame,
    *,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> str:
    """Choose one final recommendation without approving validation prematurely."""

    if knowledge_base.is_empty():
        return "STOP_GURU_LOGIC_PATH"
    if availability.complete_validation_days >= minimum_validation_days:
        return "CME_PILOT_READY"
    if any(
        str(row.get("validation_status")) == "READY_FOR_PRICE_ONLY_TEST"
        for row in knowledge_base.to_dicts()
    ):
        return "EXTRACT_LOGIC_NOW_COLLECT_CME_NEXT"
    return "CME_DATA_REQUIRED_BEFORE_VALIDATION"


def guru_logic_knowledge_base_markdown(result: GuruLogicKnowledgeBaseResult) -> str:
    """Render the main knowledge-base report."""

    top = result.priority_rank.head(10) if not result.priority_rank.is_empty() else result.priority_rank
    context_now = _actions(result.priority_rank, {"USE_AS_PLAYBOOK_CONTEXT_NOW"})
    price_now = _actions(result.priority_rank, {"TEST_PRICE_ONLY_NOW"})
    wait_cme = _actions(
        result.priority_rank,
        {"WAIT_FOR_MORE_CME_DATA", "COLLECT_REQUIRED_DATA_FIRST"},
    )
    lines = [
        "# Guru Logic Knowledge Base",
        "",
        "Research-only logic extraction. This does not approve live trading, paper trading, "
        "broker integration, order execution, or performance claims.",
        "",
        f"- Repeated guru logic concepts extracted: {result.knowledge_base.height}",
        f"- Current validation-grade CME days: {result.current_available_validation_days}",
        f"- Preliminary validation threshold: {result.minimum_validation_days}",
        f"- Final recommendation: `{result.final_recommendation}`",
        "",
        "## Top 10 Guru Logic Concepts",
        "",
        _frame_markdown(top.select([column for column in [
            "rank",
            "logic_id",
            "logic_name",
            "logic_type",
            "transcript_count",
            "priority_score",
            "recommended_action",
        ] if column in top.columns]) if not top.is_empty() else top),
        "",
        "## Use As Playbook Context Now",
        "",
        _logic_name_list(context_now),
        "",
        "## Price-Only Pilot Candidates Now",
        "",
        _logic_name_list(price_now),
        "",
        "## Requires More CME Data",
        "",
        _logic_name_list(wait_cme),
        "",
        "## Knowledge Base",
        "",
        _frame_markdown(result.knowledge_base),
    ]
    return "\n".join(lines)


def guru_logic_data_dependency_matrix_markdown(result: GuruLogicKnowledgeBaseResult) -> str:
    """Render the data dependency matrix."""

    columns = [
        "logic_id",
        "logic_name",
        "requires_xau_spot",
        "requires_gc_futures",
        "requires_basis",
        "requires_cme_oi_by_strike",
        "requires_oi_change",
        "requires_option_volume",
        "requires_iv",
        "minimum_validation_days",
        "current_available_validation_days",
        "validation_blocker",
        "next_data_to_collect",
    ]
    frame = result.dependency_matrix
    selected = frame.select([column for column in columns if column in frame.columns]) if not frame.is_empty() else frame
    return "\n".join(
        [
            "# Guru Logic Data Dependency Matrix",
            "",
            "Logic extraction can run without CME data. Validation remains blocked when required "
            "fields or aligned validation-grade days are insufficient.",
            "",
            _frame_markdown(selected),
        ]
    )


def cme_collection_plan_markdown(result: GuruLogicKnowledgeBaseResult) -> str:
    """Render the CME collection shopping list."""

    return "\n".join(
        [
            "# CME Collection Plan For Guru Logic",
            "",
            "Priority is based on the data needed to validate extracted logic, not on any "
            "performance claim.",
            "",
            _frame_markdown(result.collection_plan),
        ]
    )


def guru_logic_validation_path_markdown(result: GuruLogicKnowledgeBaseResult) -> str:
    """Render validation path by logic type."""

    return "\n".join(
        [
            "# Guru Logic Validation Path By Logic Type",
            "",
            "Validation paths separate what can be extracted now from what cannot be proven "
            "until data coverage improves.",
            "",
            _frame_markdown(result.validation_path),
            "",
            f"Final recommendation: `{result.final_recommendation}`",
        ]
    )


def _record_from_row(row: dict[str, Any], *, source: str) -> dict[str, Any]:
    rule_tag = str(row.get("rule_tag") or "").strip().upper()
    logic_type = _logic_type_from_row(row, rule_tag)
    logic_key = rule_tag or logic_type
    return {
        "logic_key": logic_key,
        "rule_tag": rule_tag,
        "logic_type": logic_type,
        "transcript_id": row.get("transcript_id"),
        "transcript_date": _date_text(row.get("transcript_date"))
        or _date_text(row.get("availability_timestamp")),
        "availability_timestamp": row.get("availability_timestamp"),
        "source_excerpt": row.get("source_excerpt"),
        "summary": row.get("normalized_english_summary") or row.get("condition_text")
        or row.get("condition"),
        "confidence_score": _float_or_none(row.get("confidence_score")),
        "testability_score": _testability_from_row(row, logic_type),
        "source": source,
    }


def _logic_type_from_row(row: dict[str, Any], rule_tag: str) -> str:
    if rule_tag in RULE_TAG_TO_LOGIC_TYPE:
        return RULE_TAG_TO_LOGIC_TYPE[rule_tag]
    suggested = _normalize_logic_type(row.get("suggested_guru_logic_type"))
    if suggested != "UNTESTABLE":
        return suggested
    rule_type = str(row.get("rule_type") or "").upper()
    action_bias = str(row.get("action_bias") or "").upper()
    text = " ".join(str(row.get(column) or "") for column in [
        "source_excerpt",
        "normalized_english_summary",
        "condition_text",
        "condition",
    ]).lower()
    if "POST_EVENT" in rule_type or "after the move" in text:
        return "POST_EVENT_COMMENTARY"
    if "RISK" in rule_type:
        return "RISK_MANAGEMENT"
    if "ENTRY" in rule_type or action_bias in {"FADE", "BREAKOUT"}:
        return "ENTRY_TRIGGER"
    if "no trade" in text:
        return "NO_TRADE_FILTER"
    return "UNTESTABLE"


def _testability_from_row(row: dict[str, Any], logic_type: str) -> float:
    explicit = _float_or_none(row.get("testability_score"))
    if explicit is not None:
        return explicit
    score = _default_testability(logic_type)
    if _bool_value(row.get("has_clear_condition")):
        score += 0.05
    if _bool_value(row.get("has_clear_level")):
        score += 0.05
    if _bool_value(row.get("has_clear_target")) or _bool_value(row.get("has_clear_invalidation")):
        score += 0.03
    return round(min(0.95, max(0.05, score)), 4)


def _default_testability(logic_type: str) -> float:
    logic_type = _normalize_logic_type(logic_type)
    values = {
        "MARKET_MAP": 0.65,
        "VOLATILITY_RANGE": 0.72,
        "BASIS_MAPPING": 0.82,
        "OI_WALL_ZONE": 0.78,
        "OI_FRESHNESS": 0.75,
        "NO_TRADE_FILTER": 0.70,
        "ENTRY_TRIGGER": 0.62,
        "ACCEPTANCE_CONFIRMATION": 0.70,
        "REJECTION_CONFIRMATION": 0.70,
        "PIN_RISK": 0.67,
        "SQUEEZE_RISK": 0.66,
        "RISK_MANAGEMENT": 0.55,
        "POST_EVENT_COMMENTARY": 0.15,
        "UNTESTABLE": 0.05,
    }
    return values[logic_type]


def _knowledge_base_notes(
    logic_type: str,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> str:
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "Retain only as historical context unless rewritten before the event."
    if availability.complete_validation_days < minimum_validation_days:
        return (
            "Logic extraction is allowed now; CME validation is blocked by insufficient "
            "aligned validation-grade days."
        )
    return "Ready for controlled validation only if all dependency fields are present."


def dependency_blocker(
    *,
    logic_type: str,
    missing: list[str],
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> str:
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "Not a pre-event validation candidate."
    blockers = []
    if missing:
        blockers.append("Missing " + ", ".join(missing))
    if availability.complete_validation_days < minimum_validation_days:
        blockers.append(
            f"Only {availability.complete_validation_days} validation-grade CME days "
            f"available; minimum is {minimum_validation_days}."
        )
    return " ".join(blockers)


def next_data_to_collect(
    missing: list[str],
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> str:
    if missing:
        return missing[0]
    if availability.complete_validation_days < minimum_validation_days:
        return f"Extend aligned validation-grade CME data to at least {minimum_validation_days} days."
    return "No immediate data blocker detected."


def recommended_action(
    *,
    logic_type: str,
    missing: list[str],
    availability: CmeAvailability,
) -> str:
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "IGNORE_OR_REJECT"
    if missing:
        return "COLLECT_REQUIRED_DATA_FIRST"
    if logic_type == "NO_TRADE_FILTER" and availability.has_price_outcome:
        return "TEST_PRICE_ONLY_NOW"
    if logic_type in {"MARKET_MAP", "BASIS_MAPPING", "VOLATILITY_RANGE"}:
        return "USE_AS_PLAYBOOK_CONTEXT_NOW"
    if availability.complete_validation_days < MINIMUM_VALIDATION_DAYS:
        return "WAIT_FOR_MORE_CME_DATA"
    return "TEST_WITH_CURRENT_CME_PILOT"


def _priority_rationale(
    action: str,
    missing: list[str],
    availability: CmeAvailability,
) -> str:
    if action == "COLLECT_REQUIRED_DATA_FIRST":
        return "Required fields are missing: " + ", ".join(missing)
    if action == "TEST_PRICE_ONLY_NOW":
        return "Price-only pilot can test behavior, but full CME validation remains separate."
    if action == "USE_AS_PLAYBOOK_CONTEXT_NOW":
        return "Useful as context while avoiding validation claims."
    if action == "WAIT_FOR_MORE_CME_DATA":
        return (
            f"Current aligned validation-grade day count is {availability.complete_validation_days}, "
            f"below {MINIMUM_VALIDATION_DAYS}."
        )
    if action == "IGNORE_OR_REJECT":
        return "Post-event or untestable logic should not be promoted."
    return "Dependencies are present for a controlled pilot."


def _needed_logic_names_by_source(dependency_matrix: pl.DataFrame) -> dict[str, list[str]]:
    needed: dict[str, list[str]] = {}
    if dependency_matrix.is_empty():
        return needed
    for row in dependency_matrix.to_dicts():
        for key, value in row.items():
            if key.startswith("requires_") and _bool_value(value):
                needed.setdefault(key, []).append(str(row.get("logic_name") or row.get("logic_id")))
    return {key: sorted(set(values))[:8] for key, values in needed.items()}


def _collection_status(
    available: bool,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> str:
    if not available:
        return "MISSING_OR_NOT_DETECTED"
    if availability.complete_validation_days >= minimum_validation_days:
        return "AVAILABLE_FOR_PRELIMINARY_VALIDATION"
    return f"AVAILABLE_FOR_{availability.complete_validation_days}_VALIDATION_DAYS_NEEDS_{minimum_validation_days}"


def _collection_user_action(
    available: bool,
    availability: CmeAvailability,
    minimum_validation_days: int,
    action: str,
) -> str:
    if not available:
        return action
    if availability.complete_validation_days < minimum_validation_days:
        return f"Extend date range to at least {minimum_validation_days} aligned sessions."
    return "Verify timestamp alignment and preserve source labels."


def _what_can_be_done_now(logic_type: str, availability: CmeAvailability) -> str:
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "Extract and quarantine as context."
    if logic_type in PRICE_ONLY_PILOT_TYPES and availability.has_price_outcome:
        return "Extract logic and run a price-only pilot with no validation claim."
    return "Extract repeated wording, examples, and required data fields."


def _what_cannot_be_proven_yet(
    logic_type: str,
    availability: CmeAvailability,
    minimum_validation_days: int,
) -> str:
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "Pre-event validation is not available unless the logic is rewritten."
    if availability.complete_validation_days < minimum_validation_days:
        return "Full CME validation is blocked by insufficient aligned validation-grade days."
    return "Performance use still requires walk-forward, placebo, and bootstrap controls."


def _minimum_data_needed(logic_type: str, minimum_validation_days: int) -> str:
    deps = dependencies_for_logic(logic_type)
    names = [
        label
        for key, label in [
            ("requires_xau_spot", "XAU spot"),
            ("requires_gc_futures", "GC futures"),
            ("requires_basis", "basis"),
            ("requires_cme_oi_by_strike", "CME OI by strike/expiry"),
            ("requires_oi_change", "OI change"),
            ("requires_option_volume", "option volume"),
            ("requires_iv", "IV"),
            ("requires_option_settlement", "option settlement"),
            ("requires_macro_calendar", "macro calendar"),
            ("requires_price_outcome", "price outcome"),
        ]
        if deps.get(key)
    ]
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "A rewritten pre-event hypothesis before quantitative validation."
    return f"{minimum_validation_days} aligned days with " + ", ".join(names)


def _validation_method(logic_type: str) -> str:
    methods = {
        "MARKET_MAP": "market-map precision; placebo",
        "VOLATILITY_RANGE": "price-only outcome test; walk-forward; placebo",
        "BASIS_MAPPING": "market-map precision",
        "OI_WALL_ZONE": "CME pilot test; market-map precision; placebo",
        "OI_FRESHNESS": "CME pilot test; walk-forward; bootstrap",
        "NO_TRADE_FILTER": "price-only outcome test; no-trade avoided-PnL; placebo",
        "ENTRY_TRIGGER": "price-only outcome test; walk-forward; bootstrap",
        "ACCEPTANCE_CONFIRMATION": "price-only outcome test; walk-forward; placebo",
        "REJECTION_CONFIRMATION": "price-only outcome test; walk-forward; placebo",
        "PIN_RISK": "CME pilot test; market-map precision; placebo",
        "SQUEEZE_RISK": "CME pilot test; walk-forward; bootstrap",
        "RISK_MANAGEMENT": "price-only outcome test; walk-forward",
        "POST_EVENT_COMMENTARY": "quarantine",
        "UNTESTABLE": "quarantine",
    }
    return methods[_normalize_logic_type(logic_type)]


def _pass_criteria(logic_type: str, minimum_validation_days: int) -> str:
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "Pass only after human rewrite into a pre-event, timestamped hypothesis."
    return (
        f"At least {minimum_validation_days} aligned days, no lookahead, matched placebo "
        "beaten, and stable walk-forward behavior."
    )


def _fail_criteria(logic_type: str) -> str:
    if logic_type in {"POST_EVENT_COMMENTARY", "UNTESTABLE"}:
        return "Remain post-event or vague after review."
    return "Fails matched placebo, uses future data, or is unstable out of sample."


def _current_data_score(
    *,
    missing: list[str],
    availability: CmeAvailability,
    logic_type: str,
) -> float:
    if logic_type in PRICE_ONLY_PILOT_TYPES and availability.has_price_outcome:
        return 0.55
    if missing:
        return 0.15
    if availability.complete_validation_days >= MINIMUM_VALIDATION_DAYS:
        return 1.0
    if availability.complete_validation_days > 0:
        return 0.35
    return 0.20


def _usefulness_score(logic_type: str) -> float:
    values = {
        "NO_TRADE_FILTER": 0.95,
        "BASIS_MAPPING": 0.82,
        "OI_WALL_ZONE": 0.80,
        "VOLATILITY_RANGE": 0.78,
        "OI_FRESHNESS": 0.76,
        "MARKET_MAP": 0.72,
        "PIN_RISK": 0.68,
        "SQUEEZE_RISK": 0.66,
        "ACCEPTANCE_CONFIRMATION": 0.62,
        "REJECTION_CONFIRMATION": 0.62,
        "ENTRY_TRIGGER": 0.55,
        "RISK_MANAGEMENT": 0.54,
        "POST_EVENT_COMMENTARY": 0.10,
        "UNTESTABLE": 0.02,
    }
    return values[_normalize_logic_type(logic_type)]


def _vagueness_penalty(logic_type: str) -> float:
    if logic_type == "POST_EVENT_COMMENTARY":
        return 0.45
    if logic_type == "UNTESTABLE":
        return 0.55
    if logic_type == "ENTRY_TRIGGER":
        return 0.10
    return 0.0


def _missing_from_dependency_row(row: dict[str, Any]) -> list[str]:
    text = str(row.get("validation_blocker") or "")
    if text.startswith("Missing "):
        return text.removeprefix("Missing ").split(". ")[0].split(", ")
    return []


def _logic_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return f"glkb_{slug or 'unknown'}"


def _logic_name(rule_tag: str, logic_type: str) -> str:
    if rule_tag in RULE_TAG_NAMES:
        return RULE_TAG_NAMES[rule_tag]
    return LOGIC_DESCRIPTIONS.get(logic_type, logic_type).split(".")[0]


def _description(rule_tag: str, logic_type: str) -> str:
    name = _logic_name(rule_tag, logic_type)
    base = LOGIC_DESCRIPTIONS.get(logic_type, LOGIC_DESCRIPTIONS["UNTESTABLE"])
    return f"{name}: {base}"


def _normalize_logic_type(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text == "UNTESTABLE_OPINION":
        return "UNTESTABLE"
    return text if text in LOGIC_TYPES else "UNTESTABLE"


def _representative_excerpts(rows: list[dict[str, Any]]) -> list[str]:
    excerpts = []
    seen = set()
    for row in rows:
        text = _clean_excerpt(row.get("source_excerpt") or row.get("summary") or "")
        if not text or text in seen:
            continue
        seen.add(text)
        excerpts.append(text)
        if len(excerpts) >= 3:
            break
    return excerpts


def _clean_excerpt(value: Any, *, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^`|\s]+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:[\\/]+[^`|\s]+", "<REDACTED_PATH>", text)
    text = text.replace("|", "/")
    return text[:limit]


def _group_records(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or "UNKNOWN"), []).append(row)
    return grouped


def _transcript_count(rows: list[dict[str, Any]]) -> int:
    ids = {str(row.get("transcript_id") or "") for row in rows if row.get("transcript_id")}
    return len(ids) if ids else len(rows)


def _average_score(values: list[Any], *, default: float) -> float:
    parsed = [_float_or_none(value) for value in values]
    clean = [value for value in parsed if value is not None and not math.isnan(value)]
    if not clean:
        return round(default, 4)
    return round(sum(clean) / len(clean), 4)


def _actions(frame: pl.DataFrame, actions: set[str]) -> pl.DataFrame:
    if frame.is_empty() or "recommended_action" not in frame.columns:
        return pl.DataFrame()
    return frame.filter(pl.col("recommended_action").is_in(sorted(actions)))


def _logic_name_list(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    return "\n".join(f"- `{row['logic_id']}`: {row['logic_name']}" for row in frame.head(20).to_dicts())


def _split_tags(value: Any) -> list[str]:
    if value is None:
        return []
    return [part.strip().upper() for part in str(value).split("|") if part.strip()]


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    match = re.search(r"20\d{2}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""


def _frame(inputs: dict[str, pl.DataFrame], name: str) -> pl.DataFrame:
    value = inputs.get(name)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _true_count(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty() or column not in frame.columns:
        return 0
    return sum(1 for value in frame.get_column(column).to_list() if _bool_value(value))


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    return _true_count(frame, column) > 0


def _market_has_any(frame: pl.DataFrame, terms: list[str]) -> bool:
    if frame.is_empty():
        return False
    text = " ".join(str(value).lower() for row in frame.to_dicts() for value in row.values())
    return any(term.lower() in text for term in terms)


def _bool_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"", "0", "false", "f", "no", "n", "none", "null", "nan"}:
        return False
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    return bool(text)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _float_or_zero(value: Any) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else 0.0


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for raw in frame.head(40).to_dicts():
        rows.append("| " + " | ".join(_markdown_cell(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:700]


def _empty_knowledge_base() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "logic_id": pl.String,
            "logic_name": pl.String,
            "logic_type": pl.String,
            "description": pl.String,
            "transcript_count": pl.Int64,
            "first_seen_date": pl.String,
            "last_seen_date": pl.String,
            "representative_transcript_ids": pl.String,
            "representative_excerpts": pl.String,
            "confidence_score": pl.Float64,
            "testability_score": pl.Float64,
            "validation_status": pl.String,
            "notes": pl.String,
        }
    )


def _empty_dependency_matrix() -> pl.DataFrame:
    schema: dict[str, Any] = {
        "logic_id": pl.String,
        "logic_name": pl.String,
    }
    schema.update({key: pl.Boolean for key in dependencies_for_logic("MARKET_MAP")})
    schema.update(
        {
            "minimum_validation_days": pl.Int64,
            "current_available_validation_days": pl.Int64,
            "validation_blocker": pl.String,
            "next_data_to_collect": pl.String,
        }
    )
    return pl.DataFrame(schema=schema)


def _empty_priority_rank() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "rank": pl.Int64,
            "logic_id": pl.String,
            "logic_name": pl.String,
            "logic_type": pl.String,
            "transcript_count": pl.Int64,
            "confidence_score": pl.Float64,
            "testability_score": pl.Float64,
            "current_data_availability_score": pl.Float64,
            "likely_usefulness_as_filter_or_map": pl.Float64,
            "vague_or_post_event_penalty": pl.Float64,
            "missing_cme_fields_penalty": pl.Float64,
            "priority_score": pl.Float64,
            "recommended_action": pl.String,
            "rationale": pl.String,
        }
    )
