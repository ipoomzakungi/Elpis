"""Guru-to-CME hypothesis extraction and wall-logic test lab.

The lab compiles structured guru/CME hypotheses, constructs CME wall maps, and
tests wall/range behavior with local data. Guru text is used only as evidence
material for hypotheses; price and CME tables provide the test layer.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl


HYPOTHESIS_IDS = (
    "WALL_AS_TARGET",
    "WALL_AS_REJECTION",
    "WALL_AS_ACCEPTANCE",
    "MAX_OI_PIN",
    "LOW_OI_GAP_SQUEEZE",
    "CALL_WALL_RESISTANCE",
    "PUT_WALL_SUPPORT",
    "PUT_CALL_IMBALANCE_BIAS",
    "OI_CHANGE_FRESHNESS",
    "VOLUME_FRESHNESS",
    "IV_EXPECTED_MOVE_RANGE",
    "ONE_SD_RANGE",
    "TWO_SD_STRESS",
    "TWENTY_FIVE_DOLLAR_GRID",
    "NO_TRADE_MIDDLE_RANGE",
    "OPEN_PRICE_REFERENCE",
    "BASIS_ADJUSTED_STRIKE",
)
FINAL_RECOMMENDATIONS = (
    "CME_HYPOTHESES_READY",
    "WALL_MAGNET_CANDIDATE",
    "WALL_REJECTION_CANDIDATE",
    "CME_ONLY_RULES_READY_FOR_PILOT",
    "NEED_MORE_CME_DATA",
    "INSUFFICIENT_SAMPLE",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only Guru-to-CME hypothesis lab. Guru excerpts generate testable "
    "hypotheses only; CME walls and guru context are not standalone trade triggers."
)
PILOT_WARNING = "Current CME overlap remains too small for validation; collect more CME days."
MIN_CME_SAMPLE = 30
GRID_LEVELS = (25.0, 50.0)
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
class GuruCmeHypothesisLabResult:
    """Frames and final recommendation emitted by the hypothesis lab."""

    hypotheses: pl.DataFrame
    wall_map: pl.DataFrame
    magnet_test: pl.DataFrame
    rejection_acceptance_test: pl.DataFrame
    put_call_behavior: pl.DataFrame
    sd_grid_behavior: pl.DataFrame
    cme_only_rule_candidates: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_guru_cme_hypothesis_lab(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> GuruCmeHypothesisLabResult:
    """Run the Guru-to-CME hypothesis lab and optionally write artifacts."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(paths)
    wall_map = build_cme_wall_map_by_date(inputs=inputs)
    hypotheses = build_guru_wall_logic_hypotheses(inputs=inputs, wall_map=wall_map)
    magnet = build_wall_magnet_target_test(inputs=inputs, wall_map=wall_map)
    rejection_acceptance = build_wall_rejection_acceptance_test(inputs=inputs, wall_map=wall_map)
    put_call = build_put_call_wall_behavior_test(inputs=inputs, wall_map=wall_map)
    sd_grid = build_sd_grid_behavior_test(inputs=inputs)
    rules = build_cme_only_rule_candidates(
        hypotheses=hypotheses,
        wall_map=wall_map,
        magnet_test=magnet,
        rejection_acceptance_test=rejection_acceptance,
        sd_grid_behavior=sd_grid,
    )
    final = choose_final_recommendation(
        wall_map=wall_map,
        magnet_test=magnet,
        rejection_acceptance_test=rejection_acceptance,
        put_call_behavior=put_call,
    )
    result = GuruCmeHypothesisLabResult(
        hypotheses=hypotheses,
        wall_map=wall_map,
        magnet_test=magnet,
        rejection_acceptance_test=rejection_acceptance,
        put_call_behavior=put_call,
        sd_grid_behavior=sd_grid,
        cme_only_rule_candidates=rules,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_guru_cme_hypothesis_lab_outputs(result)
    return result


def build_guru_wall_logic_hypotheses(
    *,
    inputs: dict[str, Any],
    wall_map: pl.DataFrame,
) -> pl.DataFrame:
    """Compile fixed CME hypotheses with structured guru evidence excerpts."""

    evidence = _evidence_rows(inputs)
    cme_status = "CME_PILOT_TESTABLE" if not wall_map.is_empty() else "NEED_MORE_CME_DATA"
    rows = []
    for hypothesis_id in HYPOTHESIS_IDS:
        template = _hypothesis_template(hypothesis_id)
        rows.append(
            {
                **template,
                "hypothesis_id": hypothesis_id,
                "guru_evidence_excerpt": _matched_excerpt(evidence, template["keywords"]),
                "current_validation_status": _hypothesis_status(hypothesis_id, cme_status),
            }
        )
    return _frame(rows, _hypothesis_schema())


def build_cme_wall_map_by_date(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Construct call, put, max-OI, total-OI, and low-OI walls by date."""

    cme_oi = _normalize_cme_oi(_frame_input(inputs, "cme_oi"))
    if cme_oi.is_empty():
        return _frame([], _wall_map_schema())
    basis_by_date = _basis_lookup(_frame_input(inputs, "basis"))
    price_open_by_date = _price_open_lookup(_price_frame(inputs))
    rows = []
    grouped = cme_oi.group_by(["trade_date", "expiry"], maintain_order=True)
    for keys, group in grouped:
        trade_date, expiry = keys
        group = group.sort("strike")
        max_total = _max_value(group, "total_oi")
        max_volume = _max_value(group, "total_volume")
        max_change = _max_abs_value(group, "total_oi_change")
        candidates = [
            ("CALL_WALL", _top_row(group, "call_oi")),
            ("PUT_WALL", _top_row(group, "put_oi")),
            ("TOTAL_OI_WALL", _top_row(group, "total_oi")),
            ("MAX_OI_PIN", _top_row(group, "total_oi")),
            ("LOW_OI_GAP", _low_oi_gap_row(group)),
        ]
        for wall_type, row in candidates:
            if not row:
                continue
            rows.append(
                _wall_map_row(
                    row=row,
                    trade_date=_text(trade_date),
                    expiry=_text(expiry),
                    wall_type=wall_type,
                    basis_by_date=basis_by_date,
                    price_open_by_date=price_open_by_date,
                    max_total=max_total,
                    max_volume=max_volume,
                    max_change=max_change,
                )
            )
    return _frame(rows, _wall_map_schema()).sort(["trade_date", "wall_type", "wall_score"], descending=[False, False, True])


def basis_adjusted_wall_level(strike: float, basis: float) -> float:
    """Map a futures/option strike into spot-equivalent XAUUSD space."""

    return strike - basis


def build_wall_magnet_target_test(
    *,
    inputs: dict[str, Any],
    wall_map: pl.DataFrame,
) -> pl.DataFrame:
    """Test whether price moves closer to nearest or strongest walls."""

    price = _price_frame(inputs)
    events = []
    for trade_date in sorted(_wall_dates(wall_map)):
        bars = _date_price_rows(price, trade_date)
        if not bars:
            continue
        walls = _date_walls(wall_map, trade_date, exclude_gap=True)
        if not walls:
            continue
        start_price = _float(bars[0].get("open"))
        if start_price is None:
            continue
        nearest = min(walls, key=lambda row: abs(start_price - _wall_level(row)))
        strongest = max(walls, key=lambda row: _float(row.get("wall_score")) or 0.0)
        events.append(_magnet_event(bars, nearest, "NEAREST_WALL"))
        if strongest.get("wall_type") != nearest.get("wall_type") or _wall_level(strongest) != _wall_level(nearest):
            events.append(_magnet_event(bars, strongest, "STRONGEST_WALL"))
    rows = [_magnet_summary(events, case) for case in ("NEAREST_WALL", "STRONGEST_WALL")]
    return _frame(rows, _magnet_schema())


def build_wall_rejection_acceptance_test(
    *,
    inputs: dict[str, Any],
    wall_map: pl.DataFrame,
) -> pl.DataFrame:
    """Test touch, rejection, acceptance, and next-wall target behavior."""

    price = _price_frame(inputs)
    events = []
    for row in wall_map.to_dicts():
        if row.get("wall_type") == "LOW_OI_GAP":
            continue
        bars = _date_price_rows(price, _text(row.get("trade_date")))
        if not bars:
            continue
        event = _wall_touch_event(bars, row)
        if event:
            events.append(event)
    return _frame([_rejection_acceptance_summary(events)], _rejection_acceptance_schema())


def build_put_call_wall_behavior_test(
    *,
    inputs: dict[str, Any],
    wall_map: pl.DataFrame,
) -> pl.DataFrame:
    """Separate call-wall, put-wall, total-wall, and imbalance behavior."""

    price = _price_frame(inputs)
    rows = []
    for wall_type in ("CALL_WALL", "PUT_WALL", "TOTAL_OI_WALL"):
        events = []
        for wall in wall_map.filter(pl.col("wall_type") == wall_type).to_dicts() if not wall_map.is_empty() else []:
            event = _wall_touch_event(_date_price_rows(price, _text(wall.get("trade_date"))), wall)
            if event:
                events.append(event)
        rows.append(_put_call_row(wall_type, events, wall_map))
    return _frame(rows, _put_call_schema())


def build_sd_grid_behavior_test(*, inputs: dict[str, Any]) -> pl.DataFrame:
    """Test broad Dukascopy range behavior for IV, realized-vol, grid, and ATR bands."""

    daily = _daily_price_frame(inputs)
    if daily.is_empty():
        return _frame([], _sd_grid_schema())
    ranges = _daily_ranges(daily)
    rows = [
        _range_method_row("TWENTY_FIVE_DOLLAR_GRID", daily, ranges, grid=25.0),
        _range_method_row("FIFTY_DOLLAR_GRID", daily, ranges, grid=50.0),
        _range_method_row("ATR_RANGE", daily, ranges, grid=None),
        _realized_vol_row(daily, ranges),
        _iv_sd_row(daily, _frame_input(inputs, "cme_iv"), ranges),
    ]
    return _frame(rows, _sd_grid_schema())


def build_cme_only_rule_candidates(
    *,
    hypotheses: pl.DataFrame,
    wall_map: pl.DataFrame,
    magnet_test: pl.DataFrame,
    rejection_acceptance_test: pl.DataFrame,
    sd_grid_behavior: pl.DataFrame,
) -> pl.DataFrame:
    """Generate transparent CME-only watchlist rule candidates."""

    evidence = _rule_evidence(
        wall_map=wall_map,
        magnet_test=magnet_test,
        rejection_acceptance_test=rejection_acceptance_test,
        sd_grid_behavior=sd_grid_behavior,
    )
    rows = []
    for rule in _rule_templates():
        status = "NEED_MORE_CME_DATA" if _cme_sample_count(wall_map) < MIN_CME_SAMPLE else "CME_PILOT_TESTABLE"
        if rule["rule_id"] == "USE_25_DOLLAR_GRID_AS_RANGE_REFERENCE":
            status = "PRICE_ONLY_TESTABLE"
        rows.append({**rule, "current_evidence": evidence.get(rule["rule_id"], "pilot evidence only"), "validation_status": status})
    if hypotheses.is_empty():
        return _frame(rows, _rule_schema())
    return _frame(rows, _rule_schema())


def choose_final_recommendation(
    *,
    wall_map: pl.DataFrame,
    magnet_test: pl.DataFrame,
    rejection_acceptance_test: pl.DataFrame,
    put_call_behavior: pl.DataFrame,
) -> str:
    """Choose a conservative final recommendation."""

    sample = _cme_sample_count(wall_map)
    if sample < MIN_CME_SAMPLE:
        return "NEED_MORE_CME_DATA" if sample else "INSUFFICIENT_SAMPLE"
    magnet = _dominant_interpretation(magnet_test)
    rejection = _rejection_interpretation(rejection_acceptance_test)
    put_call = _dominant_interpretation(put_call_behavior)
    if magnet == "MAGNET_CANDIDATE":
        return "WALL_MAGNET_CANDIDATE"
    if rejection == "WALL_REJECTION_CANDIDATE":
        return "WALL_REJECTION_CANDIDATE"
    if put_call not in {"INSUFFICIENT_SAMPLE", "MIXED"}:
        return "CME_ONLY_RULES_READY_FOR_PILOT"
    return "CME_HYPOTHESES_READY"


def write_guru_cme_hypothesis_lab_outputs(result: GuruCmeHypothesisLabResult) -> None:
    """Write CSV and Markdown artifacts."""

    frame_paths = {
        "hypotheses": result.hypotheses,
        "wall_map": result.wall_map,
        "magnet_test": result.magnet_test,
        "rejection_acceptance_test": result.rejection_acceptance_test,
        "put_call_behavior": result.put_call_behavior,
        "sd_grid_behavior": result.sd_grid_behavior,
        "cme_only_rule_candidates": result.cme_only_rule_candidates,
    }
    for key, frame in frame_paths.items():
        frame.write_csv(result.paths[f"{key}_csv"])
        result.paths[f"{key}_md"].write_text(
            _safe_report_text(_artifact_markdown(_artifact_title(key), frame)),
            encoding="utf-8",
        )


def guru_cme_hypothesis_report_lines(result: GuruCmeHypothesisLabResult | None) -> list[str]:
    """Return report lines for research_report.md."""

    if result is None:
        return [
            "## Guru-to-CME Hypothesis Extraction",
            "",
            "Guru-to-CME hypothesis lab was not run.",
        ]
    return [
        "## Guru-to-CME Hypothesis Extraction",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Hypotheses extracted: {result.hypotheses.height}",
        f"- CME wall-map rows: {result.wall_map.height}",
        "- Guardrail: `NOT_READY_FOR_MONEY`",
        "",
        _frame_markdown(result.hypotheses),
        "",
        "## Wall as Target vs Wall as Rejection",
        "",
        _frame_markdown(result.magnet_test),
        "",
        _frame_markdown(result.rejection_acceptance_test),
        "",
        "## Put/Call Wall Behavior",
        "",
        _frame_markdown(result.put_call_behavior),
        "",
        "## 1SD and $25 Grid Behavior",
        "",
        _frame_markdown(result.sd_grid_behavior),
        "",
        "## CME-only Rule Candidates",
        "",
        _frame_markdown(result.cme_only_rule_candidates),
        "",
        "## What the Guru Logic Suggests",
        "",
        "- Treat walls as a market map with separate target, rejection, acceptance, pin-risk, and gap-squeeze hypotheses.",
        "- Use put/call walls, OI change, option volume, IV ranges, open references, and basis mapping as context fields.",
        "",
        "## What the Data Supports So Far",
        "",
        "- Hypothesis extraction and price-only range tests are available now.",
        "- CME wall behavior remains a pilot due limited overlap rows.",
        "",
        "## What Still Needs More CME Data",
        "",
        "- More multi-session CME OI/IV days are needed before promoting any CME-only rule beyond watchlist research.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when generated reports avoid restricted phrases and paths."""

    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES) and "C:\\" not in text


def _load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "clean_transcripts": _read_optional(paths["clean_transcripts"]),
        "guru_logic_knowledge_base": _read_optional(paths["guru_logic_knowledge_base"]),
        "guru_logic_priority_rank": _read_optional(paths["guru_logic_priority_rank"]),
        "same_day_playbook_matches": _read_optional(paths["same_day_playbook_matches"]),
        "price_15m": _read_optional(paths["price_15m"]),
        "price_30m": _read_optional(paths["price_30m"]),
        "price_1h": _read_optional(paths["price_1h"]),
        "price_4h": _read_optional(paths["price_4h"]),
        "price_1d": _read_optional(paths["price_1d"]),
        "cme_oi": _read_optional(paths["cme_oi"]),
        "cme_iv": _read_optional(paths["cme_iv"]),
        "cme_futures": _read_optional(paths["cme_futures"]),
        "basis": _read_optional(paths["basis"]),
        "overlap_validation": _read_optional(paths["overlap_validation"]),
        "cme_overlap_trade_candidates": _read_optional(paths["cme_overlap_trade_candidates"]),
        "cme_wall_filter_effect": _read_optional(paths["cme_wall_filter_effect"]),
        "cme_iv_range_filter_effect": _read_optional(paths["cme_iv_range_filter_effect"]),
        "current_week_cme_guru_replay": _read_optional(paths["current_week_cme_guru_replay"]),
    }


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "clean_transcripts": output_root / "clean_transcript_set.csv",
        "guru_logic_knowledge_base": output_root / "guru_logic_knowledge_base.csv",
        "guru_logic_priority_rank": output_root / "guru_logic_priority_rank.csv",
        "same_day_playbook_matches": output_root / "same_day_playbook_matches.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_30m": output_root / "dukascopy_xau_30m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "price_1d": output_root / "dukascopy_xau_1d.parquet",
        "cme_oi": output_root / "cme_canonical_option_oi_by_strike.parquet",
        "cme_iv": output_root / "cme_canonical_option_iv_by_strike.parquet",
        "cme_futures": output_root / "cme_canonical_futures_price.parquet",
        "basis": output_root / "xau_basis_backfilled.parquet",
        "overlap_validation": output_root / "dukascopy_cme_overlap_validation.csv",
        "cme_overlap_trade_candidates": output_root / "cme_overlap_trade_candidates.csv",
        "cme_wall_filter_effect": output_root / "cme_wall_filter_effect.csv",
        "cme_iv_range_filter_effect": output_root / "cme_iv_range_filter_effect.csv",
        "current_week_cme_guru_replay": output_root / "current_week_cme_guru_replay.csv",
        "hypotheses_csv": output_root / "guru_wall_logic_hypotheses.csv",
        "hypotheses_md": output_root / "guru_wall_logic_hypotheses.md",
        "wall_map_csv": output_root / "cme_wall_map_by_date.csv",
        "wall_map_md": output_root / "cme_wall_map_by_date.md",
        "magnet_test_csv": output_root / "cme_wall_magnet_target_test.csv",
        "magnet_test_md": output_root / "cme_wall_magnet_target_test.md",
        "rejection_acceptance_test_csv": output_root / "cme_wall_rejection_acceptance_test.csv",
        "rejection_acceptance_test_md": output_root / "cme_wall_rejection_acceptance_test.md",
        "put_call_behavior_csv": output_root / "cme_put_call_wall_behavior.csv",
        "put_call_behavior_md": output_root / "cme_put_call_wall_behavior.md",
        "sd_grid_behavior_csv": output_root / "xau_sd_grid_behavior_test.csv",
        "sd_grid_behavior_md": output_root / "xau_sd_grid_behavior_test.md",
        "cme_only_rule_candidates_csv": output_root / "cme_only_rule_candidates.csv",
        "cme_only_rule_candidates_md": output_root / "cme_only_rule_candidates.md",
    }


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - optional research inputs degrade to empty frames.
        return pl.DataFrame()


def _normalize_cme_oi(frame: pl.DataFrame) -> pl.DataFrame:
    schema = {
        "trade_date": pl.Utf8,
        "expiry": pl.Utf8,
        "dte": pl.Float64,
        "strike": pl.Float64,
        "call_oi": pl.Float64,
        "put_oi": pl.Float64,
        "total_oi": pl.Float64,
        "call_volume": pl.Float64,
        "put_volume": pl.Float64,
        "total_volume": pl.Float64,
        "call_oi_change": pl.Float64,
        "put_oi_change": pl.Float64,
        "total_oi_change": pl.Float64,
    }
    if frame.is_empty():
        return pl.DataFrame(schema=schema)
    normalized = frame
    for column, dtype in schema.items():
        if column not in normalized.columns:
            normalized = normalized.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            normalized = normalized.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    normalized = normalized.with_columns(
        [
            pl.col("trade_date").map_elements(_date_text, return_dtype=pl.Utf8),
            pl.col("expiry").cast(pl.Utf8),
            pl.col("call_oi").fill_null(0.0),
            pl.col("put_oi").fill_null(0.0),
            pl.col("total_oi").fill_null(pl.col("call_oi").fill_null(0.0) + pl.col("put_oi").fill_null(0.0)),
            pl.col("call_volume").fill_null(0.0),
            pl.col("put_volume").fill_null(0.0),
            pl.col("total_volume").fill_null(pl.col("call_volume").fill_null(0.0) + pl.col("put_volume").fill_null(0.0)),
            pl.col("call_oi_change").fill_null(0.0),
            pl.col("put_oi_change").fill_null(0.0),
            pl.col("total_oi_change").fill_null(
                pl.col("call_oi_change").fill_null(0.0) + pl.col("put_oi_change").fill_null(0.0)
            ),
        ]
    )
    return (
        normalized.select(list(schema))
        .group_by(["trade_date", "expiry", "dte", "strike"], maintain_order=True)
        .agg(
            [
                pl.sum("call_oi").alias("call_oi"),
                pl.sum("put_oi").alias("put_oi"),
                pl.sum("total_oi").alias("total_oi"),
                pl.sum("call_volume").alias("call_volume"),
                pl.sum("put_volume").alias("put_volume"),
                pl.sum("total_volume").alias("total_volume"),
                pl.sum("call_oi_change").alias("call_oi_change"),
                pl.sum("put_oi_change").alias("put_oi_change"),
                pl.sum("total_oi_change").alias("total_oi_change"),
            ]
        )
    )


def _wall_map_row(
    *,
    row: dict[str, Any],
    trade_date: str,
    expiry: str,
    wall_type: str,
    basis_by_date: dict[str, float],
    price_open_by_date: dict[str, float],
    max_total: float,
    max_volume: float,
    max_change: float,
) -> dict[str, Any]:
    strike = _float(row.get("strike")) or 0.0
    basis = basis_by_date.get(trade_date)
    spot_level = basis_adjusted_wall_level(strike, basis) if basis is not None else None
    price = price_open_by_date.get(trade_date)
    total_oi = _float(row.get("total_oi")) or 0.0
    total_volume = _float(row.get("total_volume")) or 0.0
    total_change = abs(_float(row.get("total_oi_change")) or 0.0)
    dte = _float(row.get("dte")) or 0.0
    freshness = _bounded(0.5 * _safe_div(total_volume, max_volume) + 0.5 * _safe_div(total_change, max_change))
    proximity = _proximity_score(price, spot_level if spot_level is not None else strike)
    near_expiry = 1.0 / (1.0 + max(dte, 0.0) / 30.0)
    imbalance = _safe_div(abs((_float(row.get("call_oi")) or 0.0) - (_float(row.get("put_oi")) or 0.0)), total_oi)
    wall_score = _bounded(
        0.4 * _safe_div(total_oi, max_total)
        + 0.2 * freshness
        + 0.2 * near_expiry
        + 0.1 * proximity
        + 0.1 * imbalance
    )
    return {
        "trade_date": trade_date,
        "expiry": expiry,
        "dte": dte,
        "strike": strike,
        "option_type": _option_type_for_wall(wall_type),
        "call_oi": _float(row.get("call_oi")) or 0.0,
        "put_oi": _float(row.get("put_oi")) or 0.0,
        "total_oi": total_oi,
        "call_volume": _float(row.get("call_volume")) or 0.0,
        "put_volume": _float(row.get("put_volume")) or 0.0,
        "oi_change": _float(row.get("total_oi_change")) or 0.0,
        "wall_type": wall_type,
        "wall_score": wall_score,
        "freshness_score": freshness,
        "spot_equivalent_level": spot_level,
        "basis_used": basis,
        "confidence": _wall_confidence(basis, wall_score),
    }


def _top_row(frame: pl.DataFrame, column: str) -> dict[str, Any]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    rows = frame.filter(pl.col(column) > 0).sort(column, descending=True)
    return rows.row(0, named=True) if not rows.is_empty() else {}


def _low_oi_gap_row(frame: pl.DataFrame) -> dict[str, Any]:
    if frame.height < 3:
        return {}
    ordered = frame.sort("strike")
    max_oi = _max_value(ordered, "total_oi")
    if max_oi <= 0:
        return {}
    inner = ordered.slice(1, max(ordered.height - 2, 0))
    if inner.is_empty():
        return {}
    gap = inner.sort("total_oi").row(0, named=True)
    return gap if (_float(gap.get("total_oi")) or 0.0) <= max_oi * 0.25 else {}


def _magnet_event(bars: list[dict[str, Any]], wall: dict[str, Any], case: str) -> dict[str, Any]:
    level = _wall_level(wall)
    start = _float(bars[0].get("open")) or _float(bars[0].get("close")) or level
    close = _float(bars[-1].get("close")) or start
    start_distance = abs(start - level)
    close_distance = abs(close - level)
    direction = 1.0 if level >= start else -1.0
    toward_values = []
    against_values = []
    touch_index: int | None = None
    for index, bar in enumerate(bars):
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        if high is None or low is None:
            continue
        if low <= level <= high and touch_index is None:
            touch_index = index
        toward_values.append((high - start) * direction if direction > 0 else (start - low))
        against_values.append((start - low) if direction > 0 else (high - start))
    return {
        "case_type": case,
        "trade_date": _text(wall.get("trade_date")),
        "wall_type": _text(wall.get("wall_type")),
        "wall_level": level,
        "wall_touched": touch_index is not None,
        "time_to_wall_touch": touch_index,
        "close_nearer_to_wall": close_distance < start_distance,
        "target_hit": touch_index is not None,
        "mfe_toward_wall": max(toward_values) if toward_values else None,
        "mae_against_wall": max(against_values) if against_values else None,
    }


def _magnet_summary(events: list[dict[str, Any]], case: str) -> dict[str, Any]:
    subset = [event for event in events if event["case_type"] == case]
    touch_times = [_float(event.get("time_to_wall_touch")) for event in subset if event.get("time_to_wall_touch") is not None]
    sample_warning = len(subset) < MIN_CME_SAMPLE
    return {
        "case_type": case,
        "event_count": len(subset),
        "wall_touch_rate": _rate([bool(event.get("wall_touched")) for event in subset]),
        "time_to_wall_touch": _average(touch_times),
        "close_nearer_to_wall_rate": _rate([bool(event.get("close_nearer_to_wall")) for event in subset]),
        "target_hit_rate": _rate([bool(event.get("target_hit")) for event in subset]),
        "average_mfe_toward_wall": _average(
            [_float(event.get("mfe_toward_wall")) for event in subset if _float(event.get("mfe_toward_wall")) is not None]
        ),
        "average_mae_against_wall": _average(
            [
                _float(event.get("mae_against_wall"))
                for event in subset
                if _float(event.get("mae_against_wall")) is not None
            ]
        ),
        "sample_size_warning": sample_warning,
        "interpretation": _magnet_interpretation(subset, sample_warning),
    }


def _wall_touch_event(bars: list[dict[str, Any]], wall: dict[str, Any]) -> dict[str, Any] | None:
    if not bars:
        return None
    level = _wall_level(wall)
    start = _float(bars[0].get("open")) or _float(bars[0].get("close")) or level
    wall_above_start = level >= start
    touched = False
    first_touch_index: int | None = None
    rejection = False
    acceptance = False
    closes_beyond = 0
    for index, bar in enumerate(bars):
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        close = _float(bar.get("close"))
        if high is None or low is None or close is None:
            continue
        if low <= level <= high:
            touched = True
            if first_touch_index is None:
                first_touch_index = index
            if (wall_above_start and close < level) or (not wall_above_start and close > level):
                rejection = True
        beyond = close > level if wall_above_start else close < level
        closes_beyond = closes_beyond + 1 if beyond else 0
        if closes_beyond >= 2:
            acceptance = True
    if not touched:
        return None
    final_close = _float(bars[-1].get("close")) or start
    followthrough = (final_close < start) if wall_above_start and rejection else (final_close > start)
    return {
        "trade_date": _text(wall.get("trade_date")),
        "wall_type": _text(wall.get("wall_type")),
        "touch": touched,
        "rejection": rejection and not acceptance,
        "acceptance": acceptance,
        "rejection_followthrough": rejection and followthrough,
        "acceptance_followthrough": acceptance and abs(final_close - level) > abs(start - level),
        "next_wall_target": False,
        "failed_break": acceptance and rejection,
    }


def _rejection_acceptance_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    date_count = len({_text(event.get("trade_date")) for event in events if _text(event.get("trade_date"))})
    sample_warning = len(events) < MIN_CME_SAMPLE or date_count < MIN_CME_SAMPLE
    return {
        "wall_touch_count": len(events),
        "rejection_count": sum(1 for event in events if event.get("rejection")),
        "acceptance_count": sum(1 for event in events if event.get("acceptance")),
        "rejection_followthrough_rate": _rate([bool(event.get("rejection_followthrough")) for event in events if event.get("rejection")]),
        "acceptance_followthrough_rate": _rate(
            [bool(event.get("acceptance_followthrough")) for event in events if event.get("acceptance")]
        ),
        "next_wall_target_rate": _rate([bool(event.get("next_wall_target")) for event in events]),
        "failed_break_rate": _rate([bool(event.get("failed_break")) for event in events]),
        "sample_size_warning": sample_warning,
        "interpretation": "INSUFFICIENT_SAMPLE" if sample_warning else "WALL_REJECTION_CANDIDATE",
    }


def _put_call_row(wall_type: str, events: list[dict[str, Any]], wall_map: pl.DataFrame) -> dict[str, Any]:
    sample_warning = len(events) < MIN_CME_SAMPLE
    call_events = [event for event in events if wall_type == "CALL_WALL"]
    put_events = [event for event in events if wall_type == "PUT_WALL"]
    return {
        "wall_type": wall_type,
        "event_count": len(events),
        "call_wall_touch_rate": _rate([bool(event.get("touch")) for event in call_events]),
        "call_wall_rejection_rate": _rate([bool(event.get("rejection")) for event in call_events]),
        "call_wall_acceptance_rate": _rate([bool(event.get("acceptance")) for event in call_events]),
        "put_wall_touch_rate": _rate([bool(event.get("touch")) for event in put_events]),
        "put_wall_rejection_rate": _rate([bool(event.get("rejection")) for event in put_events]),
        "put_wall_acceptance_rate": _rate([bool(event.get("acceptance")) for event in put_events]),
        "imbalance_followthrough_rate": _imbalance_followthrough_rate(wall_map),
        "interpretation": "INSUFFICIENT_SAMPLE" if sample_warning else "MIXED",
    }


def _range_method_row(method: str, daily: pl.DataFrame, ranges: list[float], *, grid: float | None) -> dict[str, Any]:
    events = []
    for row in daily.to_dicts():
        open_price = _float(row.get("open"))
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        close = _float(row.get("close"))
        if open_price is None or high is None or low is None or close is None:
            continue
        if grid is None:
            band = _average(ranges[-14:]) or _average(ranges) or 25.0
            upper = open_price + band
            lower = open_price - band
        else:
            upper = math.ceil(open_price / grid) * grid
            lower = math.floor(open_price / grid) * grid
            if upper == lower:
                upper += grid
                lower -= grid
        touched = high >= upper or low <= lower
        accepted = close > upper or close < lower
        rejected = touched and not accepted
        events.append({"touch": touched, "accepted": accepted, "rejected": rejected, "close_inside": lower <= close <= upper})
    return {
        "method": method,
        "event_count": len(events),
        "touch_rate": _rate([event["touch"] for event in events]),
        "rejection_rate": _rate([event["rejected"] for event in events if event["touch"]]),
        "acceptance_rate": _rate([event["accepted"] for event in events if event["touch"]]),
        "close_inside_rate": _rate([event["close_inside"] for event in events]),
        "next_range_hit_rate": _rate([event["touch"] for event in events[1:]]),
        "average_daily_range": _average(ranges),
        "median_daily_range": _percentile(ranges, 0.5),
        "p25": _percentile(ranges, 0.25),
        "p50": _percentile(ranges, 0.5),
        "p75": _percentile(ranges, 0.75),
        "p90": _percentile(ranges, 0.9),
        "sample_size_warning": len(events) < MIN_CME_SAMPLE,
        "interpretation": _grid_interpretation(method, events, ranges),
    }


def _realized_vol_row(daily: pl.DataFrame, ranges: list[float]) -> dict[str, Any]:
    return _range_method_row("REALIZED_VOL_1SD", daily, ranges, grid=None)


def _iv_sd_row(daily: pl.DataFrame, cme_iv: pl.DataFrame, ranges: list[float]) -> dict[str, Any]:
    events = []
    iv_by_date = _iv_lookup(cme_iv)
    for row in daily.to_dicts():
        trade_date = _date_text(row.get("trade_date"))
        iv = iv_by_date.get(trade_date)
        open_price = _float(row.get("open"))
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        close = _float(row.get("close"))
        if iv is None or open_price is None or high is None or low is None or close is None:
            continue
        band = open_price * (iv / 100.0) / math.sqrt(252.0)
        upper = open_price + band
        lower = open_price - band
        touched = high >= upper or low <= lower
        accepted = close > upper or close < lower
        events.append({"touch": touched, "accepted": accepted, "rejected": touched and not accepted, "close_inside": lower <= close <= upper})
    sample_warning = len(events) < MIN_CME_SAMPLE
    return {
        "method": "IV_1SD_RANGE",
        "event_count": len(events),
        "touch_rate": _rate([event["touch"] for event in events]),
        "rejection_rate": _rate([event["rejected"] for event in events if event["touch"]]),
        "acceptance_rate": _rate([event["accepted"] for event in events if event["touch"]]),
        "close_inside_rate": _rate([event["close_inside"] for event in events]),
        "next_range_hit_rate": _rate([event["touch"] for event in events[1:]]),
        "average_daily_range": _average(ranges),
        "median_daily_range": _percentile(ranges, 0.5),
        "p25": _percentile(ranges, 0.25),
        "p50": _percentile(ranges, 0.5),
        "p75": _percentile(ranges, 0.75),
        "p90": _percentile(ranges, 0.9),
        "sample_size_warning": sample_warning,
        "interpretation": "INSUFFICIENT_SAMPLE" if sample_warning else "IV_SD_USEFUL",
    }


def _hypothesis_template(hypothesis_id: str) -> dict[str, Any]:
    templates = {
        "WALL_AS_TARGET": (
            "Wall as target or magnet",
            "Strong or nearby OI walls may act as reference targets when price starts between walls.",
            "CME OI by strike, basis, futures/spot reference",
            "Dukascopy intraday OHLC",
            "CME snapshot must be available before the tested price window.",
            "Price closes nearer to, or touches, nearest/strongest wall more often than not.",
            "Measure wall-touch rate, close-nearer-to-wall rate, and MFE toward wall.",
            ("target", "wall", "magnet", "market map"),
        ),
        "WALL_AS_REJECTION": (
            "Wall as rejection zone",
            "A wall touch followed by close back inside may mark rejection behavior.",
            "CME OI walls and basis mapping",
            "Intraday high/low/close around wall touch",
            "Wall level must be known before touch.",
            "Touch then close back inside with followthrough away from wall.",
            "Count touch, rejection, and rejection followthrough.",
            ("reject", "rejection", "wall", "not pass"),
        ),
        "WALL_AS_ACCEPTANCE": (
            "Wall as acceptance break",
            "Close and hold beyond a wall may convert the wall into continuation context.",
            "CME OI walls and basis mapping",
            "Two or more closes beyond wall",
            "No post-event wall updates.",
            "Acceptance through wall followed by move toward next reference.",
            "Count close-and-hold events and next-wall target hits.",
            ("acceptance", "break", "close", "hold"),
        ),
        "MAX_OI_PIN": (
            "Max OI pin",
            "The maximum-OI strike may act as pin/magnet risk, especially near expiry.",
            "Strike-level total OI, expiry, DTE, basis",
            "Session open/high/low/close",
            "OI snapshot must be as-of safe.",
            "Price gravitates toward max-OI level or stays inside pin band.",
            "Detect max-OI wall and compare open/close distance.",
            ("pin", "max oi", "highest oi", "settle"),
        ),
        "LOW_OI_GAP_SQUEEZE": (
            "Low-OI gap squeeze",
            "Low-OI areas between larger walls may allow faster movement toward next wall.",
            "OI by strike, neighboring wall levels",
            "Intraday followthrough bars",
            "Gap must be visible before event.",
            "Break into low-OI gap travels farther before rejection.",
            "Detect low-OI gaps and compare gap followthrough.",
            ("squeeze", "gap", "low oi", "thin"),
        ),
        "CALL_WALL_RESISTANCE": (
            "Call wall resistance or target",
            "Large call OI above price may be resistance or target context.",
            "Call OI, call volume, call OI change",
            "Price relative to call wall",
            "Call wall must be mapped to spot-equivalent level.",
            "Call wall touch has measurable rejection/acceptance behavior.",
            "Separate call wall touch, rejection, and acceptance rates.",
            ("call wall", "call", "resistance"),
        ),
        "PUT_WALL_SUPPORT": (
            "Put wall support or target",
            "Large put OI below price may be support or target context.",
            "Put OI, put volume, put OI change",
            "Price relative to put wall",
            "Put wall must be mapped to spot-equivalent level.",
            "Put wall touch has measurable rejection/acceptance behavior.",
            "Separate put wall touch, rejection, and acceptance rates.",
            ("put wall", "put", "support"),
        ),
        "PUT_CALL_IMBALANCE_BIAS": (
            "Put/call imbalance bias",
            "Large put/call imbalance may describe skewed positioning context.",
            "Call OI, put OI, volume and changes",
            "Forward price path after imbalance",
            "Imbalance measured before price outcome.",
            "Followthrough differs by imbalance side.",
            "Compare imbalance direction with subsequent price movement.",
            ("imbalance", "put call", "skew"),
        ),
        "OI_CHANGE_FRESHNESS": (
            "OI change freshness",
            "Fresh OI change may matter more than stale absolute OI.",
            "OI change by strike and expiry",
            "Wall touch or approach behavior",
            "OI change must be as-of safe.",
            "Fresh walls show different behavior than stale walls.",
            "Compare high-change walls to low-change walls.",
            ("oi change", "fresh", "change"),
        ),
        "VOLUME_FRESHNESS": (
            "Option volume freshness",
            "Same-day option volume may identify newly active levels.",
            "Option volume by strike and expiry",
            "Price path near active strikes",
            "Volume snapshot must precede outcome window.",
            "Fresh-volume levels attract or reject price more often.",
            "Compare high-volume walls to low-volume walls.",
            ("volume", "fresh", "active"),
        ),
        "IV_EXPECTED_MOVE_RANGE": (
            "IV expected move range",
            "IV-derived expected ranges provide scale for target and blocker logic.",
            "CME IV by strike or ATM proxy",
            "Dukascopy realized range",
            "IV snapshot before session.",
            "Price respects or breaks IV-derived bands.",
            "Compare realized range to IV 1SD/2SD bands.",
            ("iv", "expected move", "volatility"),
        ),
        "ONE_SD_RANGE": (
            "One standard-deviation range",
            "1SD bands can act as review range boundaries.",
            "CME IV or realized-vol proxy",
            "Daily/intraday OHLC",
            "Band computed before outcome.",
            "Touch/rejection/acceptance around 1SD bands is measurable.",
            "Compute 1SD bands and range-touch metrics.",
            ("1sd", "one sd", "standard deviation"),
        ),
        "TWO_SD_STRESS": (
            "Two standard-deviation stress",
            "2SD breaks mark stretched conditions that may need separate handling.",
            "CME IV or realized-vol proxy",
            "High/low/close around 2SD bands",
            "Band computed before outcome.",
            "2SD excursions behave differently from normal range touches.",
            "Count 2SD touches and close-back-inside behavior.",
            ("2sd", "two sd", "stress"),
        ),
        "TWENTY_FIVE_DOLLAR_GRID": (
            "$25 grid reference",
            "$25 increments may describe practical XAU range references.",
            "No CME required",
            "Dukascopy OHLC and session open",
            "Grid known before session.",
            "Price touches, rejects, or accepts $25/$50 grid bands at measurable rates.",
            "Measure grid touch/rejection/acceptance across full Dukascopy sample.",
            ("25", "twenty five", "$25", "grid"),
        ),
        "NO_TRADE_MIDDLE_RANGE": (
            "No-trade middle range",
            "Middle between major walls or range bands may be watch-only context.",
            "Wall or range boundaries",
            "Price location inside range",
            "Boundaries known before event.",
            "Middle-zone events have weaker followthrough than boundary events.",
            "Compare middle-zone candidates with boundary candidates.",
            ("no trade", "middle", "range"),
        ),
        "OPEN_PRICE_REFERENCE": (
            "Open price reference",
            "Session open anchors distance, chase, and range-band logic.",
            "Optional CME context",
            "Dukascopy session open and intraday OHLC",
            "Open known at session start.",
            "Open-distance bucket changes event quality.",
            "Compare outcomes by open-distance buckets.",
            ("open", "session open", "reference"),
        ),
        "BASIS_ADJUSTED_STRIKE": (
            "Basis-adjusted strike",
            "CME futures strikes must be mapped into spot-equivalent XAUUSD levels.",
            "CME futures price and spot basis",
            "Dukascopy spot OHLC",
            "Basis timestamp must precede tested decision.",
            "Mapped walls align better than raw strikes.",
            "Compare raw strike distance to basis-adjusted distance.",
            ("basis", "strike", "spot equivalent"),
        ),
    }
    name, logic, cme_data, price_data, timing, behavior, method, keywords = templates[hypothesis_id]
    return {
        "name": name,
        "plain_english_logic": logic,
        "required_cme_data": cme_data,
        "required_price_data": price_data,
        "required_timing": timing,
        "expected_behavior": behavior,
        "test_method": method,
        "keywords": keywords,
    }


def _hypothesis_status(hypothesis_id: str, cme_status: str) -> str:
    if hypothesis_id in {"TWENTY_FIVE_DOLLAR_GRID", "OPEN_PRICE_REFERENCE", "NO_TRADE_MIDDLE_RANGE"}:
        return "PRICE_ONLY_TESTABLE"
    if hypothesis_id in {"IV_EXPECTED_MOVE_RANGE", "ONE_SD_RANGE", "TWO_SD_STRESS"}:
        return cme_status
    if hypothesis_id == "PUT_CALL_IMBALANCE_BIAS":
        return "NEED_MORE_CME_DATA"
    return cme_status


def _rule_templates() -> list[dict[str, str]]:
    return [
        {
            "rule_id": "TRADE_TOWARD_STRONG_WALL",
            "condition": "Price starts between mapped walls and strongest wall is closer than the opposite wall.",
            "action_label": "WATCH_ONLY",
            "target_logic": "Use strongest/nearest wall as a target reference only.",
            "invalidation_logic": "Invalidate if price rejects before reaching wall or context is stale.",
            "required_data": "CME OI wall map, basis, Dukascopy intraday price.",
        },
        {
            "rule_id": "TP_AT_NEAREST_WALL",
            "condition": "A separate price candidate already exists and nearest wall is ahead of the candidate path.",
            "action_label": "TARGET_REFERENCE",
            "target_logic": "Nearest wall becomes a research take-reference, not an entry.",
            "invalidation_logic": "Do not use when wall is missing, stale, or already accepted through.",
            "required_data": "Candidate row, CME wall map, basis-adjusted wall distance.",
        },
        {
            "rule_id": "FADE_REJECTED_WALL",
            "condition": "Price touches wall and closes back inside the prior range.",
            "action_label": "ALLOW_RESEARCH_CANDIDATE",
            "target_logic": "Middle range or opposite wall is a research reference.",
            "invalidation_logic": "Two closes beyond the wall means acceptance, not rejection.",
            "required_data": "Intraday high/low/close and CME wall map.",
        },
        {
            "rule_id": "FOLLOW_ACCEPTED_WALL",
            "condition": "Price closes and holds beyond a mapped wall.",
            "action_label": "ALLOW_RESEARCH_CANDIDATE",
            "target_logic": "Next wall or low-OI gap boundary is the research reference.",
            "invalidation_logic": "Failed hold back inside wall blocks the candidate.",
            "required_data": "CME wall map, next-wall map, intraday close sequence.",
        },
        {
            "rule_id": "AVOID_TRADE_INTO_WALL",
            "condition": "Candidate path points directly into nearby wall without acceptance or rejection evidence.",
            "action_label": "BLOCK",
            "target_logic": "No target; wall is blocker context.",
            "invalidation_logic": "Acceptance through wall removes the direct-wall blocker.",
            "required_data": "Candidate direction, distance to wall, wall type.",
        },
        {
            "rule_id": "PIN_RISK_NO_TRADE",
            "condition": "Price is near max-OI pin wall into short-dated expiry.",
            "action_label": "WATCH_ONLY",
            "target_logic": "Max OI wall is a pin-risk reference.",
            "invalidation_logic": "Strong acceptance away from pin reduces pin-risk interpretation.",
            "required_data": "Max OI strike, DTE, basis, spot price.",
        },
        {
            "rule_id": "LOW_OI_GAP_CONTINUATION",
            "condition": "Price accepts through a wall into a low-OI gap between larger walls.",
            "action_label": "ALLOW_RESEARCH_CANDIDATE",
            "target_logic": "Next high-OI wall is research target reference.",
            "invalidation_logic": "Failed acceptance back inside wall blocks continuation.",
            "required_data": "OI distribution by strike, gap detection, intraday closes.",
        },
        {
            "rule_id": "NO_TRADE_MIDDLE_BETWEEN_WALLS",
            "condition": "Price is in the middle between major walls without acceptance/rejection behavior.",
            "action_label": "BLOCK",
            "target_logic": "No target; wait for boundary behavior.",
            "invalidation_logic": "Boundary touch, rejection, or acceptance creates a new review state.",
            "required_data": "Upper/lower wall map and price location.",
        },
        {
            "rule_id": "USE_25_DOLLAR_GRID_AS_RANGE_REFERENCE",
            "condition": "CME IV is missing or pilot-only and price is near $25/$50 range increment.",
            "action_label": "TARGET_REFERENCE",
            "target_logic": "$25/$50 bands become range references only.",
            "invalidation_logic": "Use IV/ATR bands when they provide clearer timestamp-safe scale.",
            "required_data": "Dukascopy OHLC and session open.",
        },
    ]


def _rule_evidence(
    *,
    wall_map: pl.DataFrame,
    magnet_test: pl.DataFrame,
    rejection_acceptance_test: pl.DataFrame,
    sd_grid_behavior: pl.DataFrame,
) -> dict[str, str]:
    magnet = _dominant_interpretation(magnet_test)
    rejection = _rejection_interpretation(rejection_acceptance_test)
    grid = _grid_result(sd_grid_behavior)
    sample = _cme_sample_count(wall_map)
    return {
        "TRADE_TOWARD_STRONG_WALL": f"wall sample dates={sample}; magnet={magnet}",
        "TP_AT_NEAREST_WALL": f"wall sample dates={sample}; target test={magnet}",
        "FADE_REJECTED_WALL": f"wall sample dates={sample}; rejection={rejection}",
        "FOLLOW_ACCEPTED_WALL": f"wall sample dates={sample}; acceptance={rejection}",
        "AVOID_TRADE_INTO_WALL": f"wall sample dates={sample}; direct-wall backtest remains pilot-only",
        "PIN_RISK_NO_TRADE": f"max-OI pin rows={_wall_type_count(wall_map, 'MAX_OI_PIN')}",
        "LOW_OI_GAP_CONTINUATION": f"low-OI gap rows={_wall_type_count(wall_map, 'LOW_OI_GAP')}",
        "NO_TRADE_MIDDLE_BETWEEN_WALLS": "middle-range logic is watchlist/filter context only",
        "USE_25_DOLLAR_GRID_AS_RANGE_REFERENCE": grid,
    }


def _evidence_rows(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    frames = [
        _frame_input(inputs, "guru_logic_knowledge_base"),
        _frame_input(inputs, "guru_logic_priority_rank"),
        _frame_input(inputs, "same_day_playbook_matches"),
        _frame_input(inputs, "current_week_cme_guru_replay"),
    ]
    rows: list[dict[str, Any]] = []
    for frame in frames:
        rows.extend(frame.head(500).to_dicts() if not frame.is_empty() else [])
    return rows


def _matched_excerpt(rows: list[dict[str, Any]], keywords: Iterable[str]) -> str:
    tokens = tuple(keyword.lower() for keyword in keywords)
    for row in rows:
        text = " ".join(
            _text(row.get(column))
            for column in (
                "logic_name",
                "logic_type",
                "description",
                "representative_excerpts",
                "matched_text_excerpt",
                "active_guru_logic",
                "plain_english_summary",
            )
        )
        if any(token in text.lower() for token in tokens):
            return _redact_paths(text[:500])
    return ""


def _price_frame(inputs: dict[str, Any]) -> pl.DataFrame:
    for key in ("price_1h", "price_30m", "price_15m", "price_4h"):
        frame = _frame_input(inputs, key)
        if not frame.is_empty():
            return _normalize_price(frame)
    return pl.DataFrame()


def _daily_price_frame(inputs: dict[str, Any]) -> pl.DataFrame:
    daily = _frame_input(inputs, "price_1d")
    if not daily.is_empty():
        return _normalize_price(daily)
    frame = _price_frame(inputs)
    if frame.is_empty() or "trade_date" not in frame.columns:
        return pl.DataFrame()
    return (
        frame.group_by("trade_date", maintain_order=True)
        .agg(
            [
                pl.first("timestamp").alias("timestamp"),
                pl.first("open").alias("open"),
                pl.max("high").alias("high"),
                pl.min("low").alias("low"),
                pl.last("close").alias("close"),
            ]
        )
        .with_columns(pl.lit("1d").alias("timeframe"))
    )


def _normalize_price(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame()
    normalized = frame
    if "trade_date" not in normalized.columns and "timestamp" in normalized.columns:
        normalized = normalized.with_columns(pl.col("timestamp").map_elements(_date_text, return_dtype=pl.Utf8).alias("trade_date"))
    for column in ("open", "high", "low", "close"):
        if column not in normalized.columns and f"mid_{column}" in normalized.columns:
            normalized = normalized.with_columns(pl.col(f"mid_{column}").alias(column))
        if column not in normalized.columns:
            normalized = normalized.with_columns(pl.lit(None).cast(pl.Float64).alias(column))
        else:
            normalized = normalized.with_columns(pl.col(column).cast(pl.Float64, strict=False).alias(column))
    if "timestamp" not in normalized.columns:
        normalized = normalized.with_columns(pl.col("trade_date").alias("timestamp"))
    return normalized.select(["timestamp", "trade_date", "open", "high", "low", "close"])


def _basis_lookup(frame: pl.DataFrame) -> dict[str, float]:
    if frame.is_empty() or "trade_date" not in frame.columns or "basis" not in frame.columns:
        return {}
    out: dict[str, float] = {}
    for row in frame.select(["trade_date", "basis"]).to_dicts():
        trade_date = _date_text(row.get("trade_date"))
        value = _float(row.get("basis"))
        if trade_date and value is not None:
            out[trade_date] = value
    return out


def _price_open_lookup(frame: pl.DataFrame) -> dict[str, float]:
    if frame.is_empty():
        return {}
    out = {}
    for row in frame.group_by("trade_date", maintain_order=True).agg(pl.first("open").alias("open")).to_dicts():
        value = _float(row.get("open"))
        if value is not None:
            out[_date_text(row.get("trade_date"))] = value
    return out


def _iv_lookup(frame: pl.DataFrame) -> dict[str, float]:
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
        _text(row.get("trade_date")): _float(row.get("iv_value")) or 0.0
        for row in grouped.to_dicts()
        if _float(row.get("iv_value")) is not None
    }


def _date_price_rows(frame: pl.DataFrame, trade_date: str) -> list[dict[str, Any]]:
    if frame.is_empty() or "trade_date" not in frame.columns:
        return []
    return frame.filter(pl.col("trade_date").cast(pl.Utf8) == trade_date).sort("timestamp").to_dicts()


def _date_walls(wall_map: pl.DataFrame, trade_date: str, *, exclude_gap: bool) -> list[dict[str, Any]]:
    if wall_map.is_empty():
        return []
    rows = wall_map.filter(pl.col("trade_date") == trade_date)
    if exclude_gap:
        rows = rows.filter(pl.col("wall_type") != "LOW_OI_GAP")
    return [row for row in rows.to_dicts() if _wall_level(row) is not None]


def _wall_dates(wall_map: pl.DataFrame) -> set[str]:
    if wall_map.is_empty() or "trade_date" not in wall_map.columns:
        return set()
    return set(wall_map.get_column("trade_date").cast(pl.Utf8).to_list())


def _wall_level(row: dict[str, Any]) -> float:
    return _float(row.get("spot_equivalent_level")) or _float(row.get("strike")) or 0.0


def _daily_ranges(daily: pl.DataFrame) -> list[float]:
    ranges = []
    for row in daily.to_dicts():
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        if high is not None and low is not None and high >= low:
            ranges.append(high - low)
    return ranges


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join(["# " + title, RESEARCH_WARNING, PILOT_WARNING, _frame_markdown(frame)])


def _artifact_title(key: str) -> str:
    return {
        "hypotheses": "Guru Wall Logic Hypotheses",
        "wall_map": "CME Wall Map By Date",
        "magnet_test": "CME Wall Magnet Target Test",
        "rejection_acceptance_test": "CME Wall Rejection Acceptance Test",
        "put_call_behavior": "CME Put/Call Wall Behavior",
        "sd_grid_behavior": "XAU SD Grid Behavior Test",
        "cme_only_rule_candidates": "CME-only Rule Candidates",
    }[key]


def _safe_report_text(text: str) -> str:
    safe = _redact_paths(text)
    for phrase in FORBIDDEN_REPORT_PHRASES:
        safe = re.sub(re.escape(phrase.strip()), "[redacted research-safety phrase]", safe, flags=re.IGNORECASE)
    return safe


def _redact_paths(text: str) -> str:
    safe = re.sub(r"[A-Za-z]:\\[^\s|)<>]+", "<REDACTED_PATH>", text)
    return re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>]+", "<REDACTED_PATH>", safe)


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
    return _redact_paths(str(value).replace("|", "\\|").replace("\n", " "))[:700]


def _hypothesis_schema() -> dict[str, Any]:
    return {
        "hypothesis_id": pl.Utf8,
        "name": pl.Utf8,
        "plain_english_logic": pl.Utf8,
        "guru_evidence_excerpt": pl.Utf8,
        "required_cme_data": pl.Utf8,
        "required_price_data": pl.Utf8,
        "required_timing": pl.Utf8,
        "expected_behavior": pl.Utf8,
        "test_method": pl.Utf8,
        "current_validation_status": pl.Utf8,
    }


def _wall_map_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.Utf8,
        "expiry": pl.Utf8,
        "dte": pl.Float64,
        "strike": pl.Float64,
        "option_type": pl.Utf8,
        "call_oi": pl.Float64,
        "put_oi": pl.Float64,
        "total_oi": pl.Float64,
        "call_volume": pl.Float64,
        "put_volume": pl.Float64,
        "oi_change": pl.Float64,
        "wall_type": pl.Utf8,
        "wall_score": pl.Float64,
        "freshness_score": pl.Float64,
        "spot_equivalent_level": pl.Float64,
        "basis_used": pl.Float64,
        "confidence": pl.Utf8,
    }


def _magnet_schema() -> dict[str, Any]:
    return {
        "case_type": pl.Utf8,
        "event_count": pl.Int64,
        "wall_touch_rate": pl.Float64,
        "time_to_wall_touch": pl.Float64,
        "close_nearer_to_wall_rate": pl.Float64,
        "target_hit_rate": pl.Float64,
        "average_mfe_toward_wall": pl.Float64,
        "average_mae_against_wall": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "interpretation": pl.Utf8,
    }


def _rejection_acceptance_schema() -> dict[str, Any]:
    return {
        "wall_touch_count": pl.Int64,
        "rejection_count": pl.Int64,
        "acceptance_count": pl.Int64,
        "rejection_followthrough_rate": pl.Float64,
        "acceptance_followthrough_rate": pl.Float64,
        "next_wall_target_rate": pl.Float64,
        "failed_break_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "interpretation": pl.Utf8,
    }


def _put_call_schema() -> dict[str, Any]:
    return {
        "wall_type": pl.Utf8,
        "event_count": pl.Int64,
        "call_wall_touch_rate": pl.Float64,
        "call_wall_rejection_rate": pl.Float64,
        "call_wall_acceptance_rate": pl.Float64,
        "put_wall_touch_rate": pl.Float64,
        "put_wall_rejection_rate": pl.Float64,
        "put_wall_acceptance_rate": pl.Float64,
        "imbalance_followthrough_rate": pl.Float64,
        "interpretation": pl.Utf8,
    }


def _sd_grid_schema() -> dict[str, Any]:
    return {
        "method": pl.Utf8,
        "event_count": pl.Int64,
        "touch_rate": pl.Float64,
        "rejection_rate": pl.Float64,
        "acceptance_rate": pl.Float64,
        "close_inside_rate": pl.Float64,
        "next_range_hit_rate": pl.Float64,
        "average_daily_range": pl.Float64,
        "median_daily_range": pl.Float64,
        "p25": pl.Float64,
        "p50": pl.Float64,
        "p75": pl.Float64,
        "p90": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "interpretation": pl.Utf8,
    }


def _rule_schema() -> dict[str, Any]:
    return {
        "rule_id": pl.Utf8,
        "condition": pl.Utf8,
        "action_label": pl.Utf8,
        "target_logic": pl.Utf8,
        "invalidation_logic": pl.Utf8,
        "required_data": pl.Utf8,
        "current_evidence": pl.Utf8,
        "validation_status": pl.Utf8,
    }


def _frame_input(inputs: dict[str, Any], key: str) -> pl.DataFrame:
    value = inputs.get(key)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


def _option_type_for_wall(wall_type: str) -> str:
    if wall_type == "CALL_WALL":
        return "call"
    if wall_type == "PUT_WALL":
        return "put"
    if wall_type == "LOW_OI_GAP":
        return "gap"
    return "total"


def _wall_confidence(basis: float | None, wall_score: float) -> str:
    if basis is None:
        return "MISSING_BASIS"
    if wall_score >= 0.6:
        return "HIGH"
    if wall_score >= 0.35:
        return "MEDIUM"
    return "LOW"


def _proximity_score(price: float | None, level: float | None) -> float:
    if price is None or level is None:
        return 0.0
    return _bounded(1.0 - min(abs(price - level), 200.0) / 200.0)


def _magnet_interpretation(events: list[dict[str, Any]], sample_warning: bool) -> str:
    if sample_warning:
        return "INSUFFICIENT_SAMPLE"
    close_rate = _rate([bool(event.get("close_nearer_to_wall")) for event in events]) or 0.0
    touch_rate = _rate([bool(event.get("wall_touched")) for event in events]) or 0.0
    if close_rate >= 0.55 and touch_rate >= 0.35:
        return "MAGNET_CANDIDATE"
    if close_rate < 0.45 and touch_rate < 0.25:
        return "NOT_MAGNET"
    return "MIXED"


def _grid_interpretation(method: str, events: list[dict[str, bool]], ranges: list[float]) -> str:
    if len(events) < MIN_CME_SAMPLE:
        return "INSUFFICIENT_SAMPLE"
    touch = _rate([event["touch"] for event in events]) or 0.0
    close_inside = _rate([event["close_inside"] for event in events]) or 0.0
    median_range = _percentile(ranges, 0.5) or 0.0
    if method == "TWENTY_FIVE_DOLLAR_GRID" and 20.0 <= median_range <= 40.0 and touch >= 0.35:
        return "$25_GRID_USEFUL"
    if method == "ATR_RANGE" and close_inside >= 0.45:
        return "ATR_BETTER"
    return "MIXED"


def _dominant_interpretation(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "interpretation" not in frame.columns:
        return "INSUFFICIENT_SAMPLE"
    values = [_text(value) for value in frame.get_column("interpretation").drop_nulls().to_list()]
    if not values:
        return "INSUFFICIENT_SAMPLE"
    if "INSUFFICIENT_SAMPLE" in values:
        return "INSUFFICIENT_SAMPLE"
    return values[0]


def _rejection_interpretation(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "INSUFFICIENT_SAMPLE"
    row = frame.row(0, named=True)
    if bool(row.get("sample_size_warning")):
        return "INSUFFICIENT_SAMPLE"
    rejection = _float(row.get("rejection_followthrough_rate")) or 0.0
    acceptance = _float(row.get("acceptance_followthrough_rate")) or 0.0
    if rejection > acceptance:
        return "WALL_REJECTION_CANDIDATE"
    return "MIXED"


def _grid_result(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "method" not in frame.columns:
        return "grid behavior not available"
    rows = frame.filter(pl.col("method") == "TWENTY_FIVE_DOLLAR_GRID")
    if rows.is_empty():
        return "grid behavior not available"
    row = rows.row(0, named=True)
    return f"$25 grid interpretation={_text(row.get('interpretation'))}; events={_int(row.get('event_count'))}"


def _imbalance_followthrough_rate(wall_map: pl.DataFrame) -> float | None:
    if wall_map.is_empty():
        return None
    rows = wall_map.filter(pl.col("wall_type").is_in(["CALL_WALL", "PUT_WALL"]))
    if rows.is_empty():
        return None
    return _rate([abs((_float(row.get("call_oi")) or 0.0) - (_float(row.get("put_oi")) or 0.0)) > 0 for row in rows.to_dicts()])


def _wall_type_count(wall_map: pl.DataFrame, wall_type: str) -> int:
    if wall_map.is_empty() or "wall_type" not in wall_map.columns:
        return 0
    return wall_map.filter(pl.col("wall_type") == wall_type).height


def _cme_sample_count(wall_map: pl.DataFrame) -> int:
    return len(_wall_dates(wall_map))


def _max_value(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    value = frame.select(pl.max(column)).item()
    return _float(value) or 0.0


def _max_abs_value(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    value = frame.select(pl.col(column).abs().max()).item()
    return _float(value) or 0.0


def _safe_div(numerator: float | None, denominator: float | None) -> float:
    if numerator is None or denominator in (None, 0):
        return 0.0
    return numerator / denominator


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _average(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(max(int(round((len(ordered) - 1) * quantile)), 0), len(ordered) - 1)
    return ordered[index]


def _date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return match.group(0) if match else ""


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


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
