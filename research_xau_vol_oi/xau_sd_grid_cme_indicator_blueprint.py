"""XAU SD/grid/CME wall indicator blueprint.

This layer keeps SD bands, grid levels, CME OI walls, and price confirmation
separate. It writes research-only indicator documentation artifacts and does
not change score weights, create execution behavior, or validate an edge.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
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
    "INDICATOR_BLUEPRINT_READY",
    "USE_SD_AS_ZONE_GRID_AS_TARGET_CME_AS_CONTEXT",
    "NEEDS_CME_IV_FOR_TRUE_SD",
    "WATCHLIST_ONLY",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only indicator blueprint. SD bands are volatility zones, grid "
    "levels are target/reference geometry, CME walls are market-map context, "
    "and price reaction is the confirmation layer."
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
class XauSdGridCmeIndicatorBlueprintResult:
    """Generated SD/grid/CME indicator blueprint artifacts."""

    concept_map: pl.DataFrame
    blueprint_layers: pl.DataFrame
    action_mapping: pl.DataFrame
    latest_state: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_xau_sd_grid_cme_indicator_blueprint(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> XauSdGridCmeIndicatorBlueprintResult:
    """Build the SD/grid/CME wall indicator blueprint."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    concept_map = build_concept_map(inputs=inputs)
    blueprint_layers = build_indicator_blueprint_layers(inputs=inputs)
    action_mapping = build_action_mapping()
    latest_state = build_latest_indicator_state(inputs=inputs)
    final = choose_final_recommendation(
        concept_map=concept_map,
        latest_state=latest_state,
    )
    result = XauSdGridCmeIndicatorBlueprintResult(
        concept_map=concept_map,
        blueprint_layers=blueprint_layers,
        action_mapping=action_mapping,
        latest_state=latest_state,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_xau_sd_grid_cme_indicator_blueprint_outputs(result)
    return result


def build_concept_map(*, inputs: dict[str, pl.DataFrame] | None = None) -> pl.DataFrame:
    """Return the concept separation map."""

    inputs = inputs or {}
    cme_plan = _frame_input(inputs, "cme_wall_test_plan")
    cme_rows = _cme_available_rows(cme_plan)
    rows = [
        {
            "concept": "SD_LEVEL",
            "what_it_is": "Volatility boundary around session/open context.",
            "what_it_is_not": "It is not a fixed 25 or 12.50 structural grid.",
            "source_data": "CME IV when available; otherwise realized-vol proxy.",
            "calculation_method": "1SD, 2SD, 3SD, and 3.5SD bands from volatility scale.",
            "valid_use": "Middle-zone block, rejection watch, extreme/tail-risk context.",
            "invalid_use": "Blind touch as standalone candidate evidence.",
            "current_confidence": "REALIZED_VOL_PROXY_ONLY",
            "needs_more_data": True,
        },
        {
            "concept": "GRID_25",
            "what_it_is": "Fixed 25-point structural reference geometry.",
            "what_it_is_not": "It is not a volatility boundary or CME OI wall.",
            "source_data": "Price ladder arithmetic.",
            "calculation_method": "Nearest multiples of 25.",
            "valid_use": "Target/reference or invalidation geometry.",
            "invalid_use": "Standalone candidate trigger.",
            "current_confidence": "RANDOM_LIKE_REFERENCE_ONLY",
            "needs_more_data": False,
        },
        {
            "concept": "HALF_GRID_12_50",
            "what_it_is": "Fixed 12.50-point midpoint reference geometry.",
            "what_it_is_not": "It is not a true SD band or positioning wall.",
            "source_data": "Price ladder arithmetic.",
            "calculation_method": "Nearest multiples of 12.50.",
            "valid_use": "Midpoint, target/reference, and review annotation.",
            "invalid_use": "Standalone candidate trigger.",
            "current_confidence": "RANDOM_LIKE_REFERENCE_ONLY",
            "needs_more_data": False,
        },
        {
            "concept": "CME_OI_WALL",
            "what_it_is": "Market-positioning level from option open interest by strike.",
            "what_it_is_not": "It is not an automatic candidate and not a volatility band.",
            "source_data": "CME OI by strike, call/put split, basis, and price path.",
            "calculation_method": "Call wall, put wall, total OI wall, max OI, and low-OI gap mapping.",
            "valid_use": "Target/magnet reference, wall watch zone, rejection/acceptance decision zone.",
            "invalid_use": "Automatic candidate trigger without price reaction.",
            "current_confidence": f"PILOT_ONLY_{cme_rows}_CME_ROWS",
            "needs_more_data": True,
        },
        {
            "concept": "CME_IV_EXPECTED_MOVE",
            "what_it_is": "Timestamp-safe IV-derived expected move when IV data is available.",
            "what_it_is_not": "It is not the same as realized-vol proxy SD.",
            "source_data": "CME IV/CVOL or equivalent timestamp-safe IV feed.",
            "calculation_method": "IV-derived daily expected move and SD bands.",
            "valid_use": "True SD validation and volatility scale.",
            "invalid_use": "Assuming realized-vol proxy is final IV validation.",
            "current_confidence": "INSUFFICIENT_DATA",
            "needs_more_data": True,
        },
        {
            "concept": "PRICE_REACTION_CONFIRMATION",
            "what_it_is": "Observed close-back-inside, acceptance close, hold, or failed break behavior.",
            "what_it_is_not": "It is not a level by itself.",
            "source_data": "Timestamp-safe Dukascopy OHLC and level context.",
            "calculation_method": "Closed-candle reaction around SD bands, grids, or CME walls.",
            "valid_use": "Confirmation layer; blocks blind level touches.",
            "invalid_use": "Post-event narrative without timestamped reaction.",
            "current_confidence": "CONFIRMATION_REQUIRED",
            "needs_more_data": True,
        },
    ]
    return _frame([_safe_row(row) for row in rows], _concept_schema())


def build_indicator_blueprint_layers(
    *,
    inputs: dict[str, pl.DataFrame] | None = None,
) -> pl.DataFrame:
    """Return one row per indicator layer."""

    inputs = inputs or {}
    cme_plan = _frame_input(inputs, "cme_wall_test_plan")
    cme_rows = _cme_available_rows(cme_plan)
    rows = [
        _layer(
            "A",
            "SD_BAND_LAYER",
            "1SD;2SD;3SD;3.5SD",
            "CME_IV if available; REALIZED_VOL_PROXY if IV missing",
            "1SD blocks middle-zone review; 2SD watches rejection; 3SD marks high-risk extreme; 3.5SD marks invalidation/tail-risk reference.",
            "Blind SD touch as standalone candidate.",
            "REALIZED_VOL_PROXY_ONLY",
        ),
        _layer(
            "B",
            "GRID_LAYER",
            "GRID_25;HALF_GRID_12_50",
            "Price ladder arithmetic",
            "Target reference, stop/invalidation reference, and midpoint annotation.",
            "Standalone candidate trigger.",
            "TARGET_REFERENCE_ONLY",
        ),
        _layer(
            "C",
            "CME_WALL_LAYER",
            "CALL_WALL;PUT_WALL;TOTAL_OI_WALL;MAX_OI;LOW_OI_GAP",
            "CME OI by strike, basis, and price path",
            "Target/magnet reference, wall watch zone, rejection/acceptance decision zone.",
            "Automatic candidate trigger without price reaction.",
            f"PILOT_ONLY_{cme_rows}_ROWS",
        ),
        _layer(
            "D",
            "PRICE_CONFIRMATION_LAYER",
            "REJECTION_BACK_INSIDE;HOURLY_ACCEPTANCE_CLOSE;CONTINUATION_HOLD;FAILED_BREAK",
            "Dukascopy OHLC close/hold behavior",
            "Confirms research candidates and blocks blind level touches.",
            "Unconfirmed narrative or raw touch-only interpretation.",
            "CONFIRMATION_REQUIRED",
        ),
        _layer(
            "E",
            "DATA_QUALITY_LAYER",
            "STALE_CME_DATA;MISSING_IV;HIGH_SPREAD;MISSING_BASIS",
            "Source freshness, IV availability, spread report, and basis mapping",
            "Block or mark insufficient data.",
            "Ignoring stale or missing context.",
            "REQUIRED_GUARDRAIL",
        ),
    ]
    return _frame([_safe_row(row) for row in rows], _blueprint_schema())


def build_action_mapping() -> pl.DataFrame:
    """Return the conservative action mapping for indicator states."""

    rows = [
        _mapping("inside_1sd", "BLOCK", "NO_TRADE_MIDDLE", "Inside 1SD is a middle/no-direction zone."),
        _mapping("touch_2sd_only", "WATCH_ONLY", "RAW_SD_TOUCH", "Raw 2SD touch needs confirmation."),
        _mapping(
            "touch_2sd_reject_back_inside",
            "ALLOW_RESEARCH_CANDIDATE",
            "CONFIRMED_REJECTION",
            "2SD touch plus close-back-inside is the preferred research candidate.",
        ),
        _mapping("touch_3sd_only", "WATCH_ONLY", "HIGH_RISK_EXTREME", "Raw 3SD touch remains high-risk watch-only."),
        _mapping("touch_3sd_no_rejection", "BLOCK", "HIGH_RISK_NO_CONFIRMATION", "Do not fade a raw 3SD touch."),
        _mapping(
            "acceptance_beyond_sd_or_wall",
            "WATCH_ONLY",
            "WATCH_CONTINUATION",
            "Acceptance says not to fade blindly; wait for continuation evidence.",
        ),
        _mapping("grid_25_nearby", "TARGET_REFERENCE", "GRID_REFERENCE", "25 grid is target/reference only."),
        _mapping(
            "half_grid_12_50_nearby",
            "TARGET_REFERENCE",
            "GRID_REFERENCE",
            "12.50 half-grid is target/reference only.",
        ),
        _mapping("cme_wall_nearby", "WATCH_ONLY", "WATCH_CME_WALL", "CME wall is context and watch zone only."),
        _mapping("cme_wall_accepted", "WATCH_ONLY", "WATCH_NEXT_WALL", "Accepted wall can shift focus toward the next wall."),
        _mapping("cme_wall_rejected", "WATCH_ONLY", "WATCH_REVERSION", "Rejected wall can become reversion context."),
        _mapping("data_stale", "INSUFFICIENT_DATA", "DATA_GUARDRAIL", "Stale or missing data blocks interpretation."),
    ]
    return _frame([_safe_row(row) for row in rows], _action_schema())


def build_latest_indicator_state(
    *,
    inputs: dict[str, pl.DataFrame] | None = None,
) -> pl.DataFrame:
    """Build latest local indicator state from available Dukascopy and CME artifacts."""

    inputs = inputs or {}
    price = _latest_price_frame(inputs)
    cme_wall_map = _frame_input(inputs, "cme_wall_map")
    cme_plan = _frame_input(inputs, "cme_wall_test_plan")
    if price.is_empty():
        row = {
            "as_of_timestamp": "",
            "latest_price": None,
            "latest_timeframe": "",
            "sd_state": "INSUFFICIENT_DATA",
            "grid_state": "INSUFFICIENT_DATA",
            "cme_wall_state": "INSUFFICIENT_DATA",
            "confirmation_state": "INSUFFICIENT_DATA",
            "data_quality_state": "MISSING_PRICE_DATA",
            "final_action": "INSUFFICIENT_DATA",
            "plain_english_summary": "No latest Dukascopy price frame is available.",
        }
        return _frame([_safe_row(row)], _latest_schema())
    rows = price.sort("timestamp").to_dicts()
    latest = rows[-1]
    latest_price = _float(latest.get("close"))
    timestamp = _timestamp_text(latest.get("timestamp"))
    timeframe = _text(latest.get("timeframe")) or "15m"
    session_rows = _same_trade_date_rows(rows, latest)
    session_open = _float(session_rows[0].get("open")) if session_rows else latest_price
    one_sd = _realized_one_sd(session_rows)
    sd_state = _sd_state(
        latest_price=latest_price,
        session_open=session_open,
        one_sd=one_sd,
    )
    grid_state = _grid_state(latest_price)
    cme_state = _cme_wall_state(
        latest_price=latest_price,
        cme_wall_map=cme_wall_map,
        cme_plan=cme_plan,
    )
    confirmation_state = _confirmation_state(sd_state=sd_state, latest=latest)
    data_quality_state = _data_quality_state(
        price=price,
        cme_plan=cme_plan,
        one_sd=one_sd,
    )
    final_action = _final_action(
        sd_state=sd_state,
        cme_wall_state=cme_state,
        confirmation_state=confirmation_state,
        data_quality_state=data_quality_state,
    )
    summary = (
        f"Latest {timeframe} price {latest_price:.4f} is {sd_state}. "
        f"Grid state: {grid_state}. CME wall state: {cme_state}. "
        f"Confirmation: {confirmation_state}. Action: {final_action}."
        if latest_price is not None
        else "Latest price is unavailable."
    )
    row = {
        "as_of_timestamp": timestamp,
        "latest_price": latest_price,
        "latest_timeframe": timeframe,
        "sd_state": sd_state,
        "grid_state": grid_state,
        "cme_wall_state": cme_state,
        "confirmation_state": confirmation_state,
        "data_quality_state": data_quality_state,
        "final_action": final_action,
        "plain_english_summary": summary,
    }
    return _frame([_safe_row(row)], _latest_schema())


def choose_final_recommendation(
    *,
    concept_map: pl.DataFrame,
    latest_state: pl.DataFrame,
) -> str:
    """Choose the final blueprint recommendation."""

    if concept_map.is_empty() or latest_state.is_empty():
        return "WATCHLIST_ONLY"
    latest_action = _text(latest_state.row(0, named=True).get("final_action"))
    if latest_action == "INSUFFICIENT_DATA":
        return "NEEDS_CME_IV_FOR_TRUE_SD"
    return "USE_SD_AS_ZONE_GRID_AS_TARGET_CME_AS_CONTEXT"


def write_xau_sd_grid_cme_indicator_blueprint_outputs(
    result: XauSdGridCmeIndicatorBlueprintResult,
) -> None:
    """Write CSV, Markdown, and YAML blueprint artifacts."""

    result.concept_map.write_csv(result.paths["concept_map_csv"])
    result.paths["concept_map_md"].write_text(
        _safe_report_text(_artifact_markdown("XAU SD Grid CME Concept Map", result.concept_map)),
        encoding="utf-8",
    )
    result.paths["blueprint_yaml"].write_text(
        _safe_report_text(_blueprint_yaml(result)),
        encoding="utf-8",
    )
    result.paths["blueprint_md"].write_text(
        _safe_report_text(_blueprint_markdown(result)),
        encoding="utf-8",
    )
    result.action_mapping.write_csv(result.paths["action_mapping_csv"])
    result.paths["action_mapping_md"].write_text(
        _safe_report_text(_artifact_markdown("XAU Indicator Action Mapping", result.action_mapping)),
        encoding="utf-8",
    )
    result.latest_state.write_csv(result.paths["latest_state_csv"])
    result.paths["latest_state_md"].write_text(
        _safe_report_text(_artifact_markdown("XAU Indicator Latest State", result.latest_state)),
        encoding="utf-8",
    )
    result.paths["chart_spec_md"].write_text(
        _safe_report_text(_chart_annotation_spec_markdown()),
        encoding="utf-8",
    )


def xau_sd_grid_cme_indicator_blueprint_report_lines(
    result: XauSdGridCmeIndicatorBlueprintResult | None,
) -> list[str]:
    """Return report lines for research_report.md."""

    if result is None:
        return [
            "## SD/Grid/CME Concept Map",
            "",
            "XAU SD/Grid/CME indicator blueprint was not run.",
        ]
    return [
        "## SD/Grid/CME Concept Map",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        "- SD layer: volatility zone.",
        "- Grid layer: target/reference geometry.",
        "- CME wall layer: market-map context.",
        "- Price reaction layer: confirmation and blind-touch blocker.",
        "",
        _frame_markdown(result.concept_map),
        "",
        "## Indicator Blueprint v1",
        "",
        _frame_markdown(result.blueprint_layers),
        "",
        "## Action Mapping",
        "",
        _frame_markdown(result.action_mapping),
        "",
        "## Latest Indicator State",
        "",
        _frame_markdown(result.latest_state),
        "",
        "## Chart Annotation Spec",
        "",
        _chart_annotation_spec_markdown(),
        "",
        "- Links: `outputs/xau_sd_grid_cme_concept_map.csv`, "
        "`outputs/xau_indicator_blueprint_v1.yaml`, "
        "`outputs/xau_indicator_action_mapping.csv`, "
        "`outputs/xau_indicator_latest_state.csv`, "
        "`outputs/xau_indicator_chart_annotation_spec.md`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when text avoids restricted phrases and private paths."""

    safe = _safe_report_text(text)
    return safe == text and not any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in FORBIDDEN_PATTERNS
    )


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "concept_map_csv": output_root / "xau_sd_grid_cme_concept_map.csv",
        "concept_map_md": output_root / "xau_sd_grid_cme_concept_map.md",
        "blueprint_yaml": output_root / "xau_indicator_blueprint_v1.yaml",
        "blueprint_md": output_root / "xau_indicator_blueprint_v1.md",
        "action_mapping_csv": output_root / "xau_indicator_action_mapping.csv",
        "action_mapping_md": output_root / "xau_indicator_action_mapping.md",
        "latest_state_csv": output_root / "xau_indicator_latest_state.csv",
        "latest_state_md": output_root / "xau_indicator_latest_state.md",
        "chart_spec_md": output_root / "xau_indicator_chart_annotation_spec.md",
    }


def _load_inputs(output_root: Path) -> dict[str, pl.DataFrame]:
    paths = {
        "sd_grid_decision": output_root / "sd_grid_confirmation_decision_summary.csv",
        "component_guide": output_root / "xau_trade_quality_component_guide_sd_grid_updated.csv",
        "manual_checklist": output_root / "xau_manual_trade_review_checklist_sd_grid_updated.csv",
        "entry_models": output_root / "gemini_sd_grid_entry_model_comparison.csv",
        "tp_sl_models": output_root / "gemini_tp_sl_model_comparison.csv",
        "grid_tests": output_root / "gemini_grid_clustering_test.csv",
        "cme_wall_test_plan": output_root / "gemini_cme_wall_test_plan.csv",
        "cme_wall_map": output_root / "cme_wall_map_by_date.csv",
        "cme_wall_magnet": output_root / "cme_wall_magnet_target_test.csv",
        "cme_wall_reaction": output_root / "cme_wall_rejection_acceptance_test.csv",
        "cme_put_call": output_root / "cme_put_call_wall_behavior.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
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


def _layer(
    layer_id: str,
    layer_name: str,
    components: str,
    source: str,
    valid_use: str,
    invalid_use: str,
    current_status: str,
) -> dict[str, str]:
    return {
        "layer_id": layer_id,
        "layer_name": layer_name,
        "components": components,
        "source": source,
        "valid_use": valid_use,
        "invalid_use": invalid_use,
        "current_status": current_status,
        "allowed_actions": ";".join(ALLOWED_ACTIONS),
    }


def _mapping(
    state: str,
    manual_action: str,
    context_label: str,
    interpretation: str,
) -> dict[str, str]:
    return {
        "indicator_state": state,
        "manual_action": _allowed_action(manual_action),
        "context_label": context_label,
        "interpretation": interpretation,
        "invalid_use_guardrail": "No automatic candidate from level touch alone.",
    }


def _allowed_action(action: Any) -> str:
    text = _text(action)
    return text if text in ALLOWED_ACTIONS else "INSUFFICIENT_DATA"


def _latest_price_frame(inputs: dict[str, pl.DataFrame]) -> pl.DataFrame:
    for key, timeframe in (("price_15m", "15m"), ("price_1h", "1h"), ("price_4h", "4h")):
        frame = _normalize_price(_frame_input(inputs, key), timeframe=timeframe)
        if not frame.is_empty():
            return frame
    return pl.DataFrame(schema=_price_schema())


def _normalize_price(frame: pl.DataFrame, *, timeframe: str) -> pl.DataFrame:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return pl.DataFrame(schema=_price_schema())
    out = frame
    for column in ("open", "high", "low", "close"):
        if column not in out.columns and f"mid_{column}" in out.columns:
            out = out.with_columns(pl.col(f"mid_{column}").alias(column))
        if column not in out.columns:
            return pl.DataFrame(schema=_price_schema())
        out = out.with_columns(pl.col(column).cast(pl.Float64, strict=False).alias(column))
    if "trade_date" not in out.columns:
        out = out.with_columns(pl.col("timestamp").map_elements(_date_text, return_dtype=pl.Utf8).alias("trade_date"))
    if "timeframe" not in out.columns:
        out = out.with_columns(pl.lit(timeframe).alias("timeframe"))
    return out.select(["timestamp", "trade_date", "timeframe", "open", "high", "low", "close"])


def _same_trade_date_rows(rows: list[dict[str, Any]], latest: dict[str, Any]) -> list[dict[str, Any]]:
    trade_date = _date_text(latest.get("trade_date") or latest.get("timestamp"))
    return [row for row in rows if _date_text(row.get("trade_date") or row.get("timestamp")) == trade_date] or rows[-50:]


def _realized_one_sd(rows: list[dict[str, Any]]) -> float | None:
    ranges = []
    for row in rows:
        high = _float(row.get("high"))
        low = _float(row.get("low"))
        if high is not None and low is not None and high >= low:
            ranges.append(high - low)
    if not ranges:
        return None
    return max(sum(ranges) / len(ranges), 1.0)


def _sd_state(
    *,
    latest_price: float | None,
    session_open: float | None,
    one_sd: float | None,
) -> str:
    if latest_price is None or session_open is None or one_sd is None or one_sd <= 0:
        return "INSUFFICIENT_DATA"
    sigma = (latest_price - session_open) / one_sd
    distance = abs(sigma)
    if distance <= 1.0:
        return "INSIDE_1SD"
    if distance <= 2.0:
        return "BETWEEN_1SD_2SD"
    if distance <= 3.0:
        return "TOUCH_2SD_ZONE"
    if distance <= 3.5:
        return "TOUCH_3SD_HIGH_RISK"
    return "BEYOND_3_5SD_TAIL_RISK"


def _grid_state(latest_price: float | None) -> str:
    if latest_price is None:
        return "INSUFFICIENT_DATA"
    nearest_25 = round(latest_price / 25.0) * 25.0
    nearest_12 = round(latest_price / 12.5) * 12.5
    distance_25 = abs(latest_price - nearest_25)
    distance_12 = abs(latest_price - nearest_12)
    if distance_25 <= 2.0:
        return f"GRID_25_TARGET_REFERENCE_NEAR_{nearest_25:.2f}"
    if distance_12 <= 1.5:
        return f"HALF_GRID_12_50_TARGET_REFERENCE_NEAR_{nearest_12:.2f}"
    return f"REFERENCE_ONLY_NEAREST_25_{nearest_25:.2f}_NEAREST_12_50_{nearest_12:.2f}"


def _cme_wall_state(
    *,
    latest_price: float | None,
    cme_wall_map: pl.DataFrame,
    cme_plan: pl.DataFrame,
) -> str:
    if latest_price is None:
        return "INSUFFICIENT_DATA"
    if cme_wall_map.is_empty() or "spot_equivalent_level" not in cme_wall_map.columns:
        return "CME_WALL_INSUFFICIENT_DATA"
    latest_date = _latest_date_value(cme_wall_map, "trade_date")
    frame = cme_wall_map
    if latest_date and "trade_date" in cme_wall_map.columns:
        frame = cme_wall_map.filter(pl.col("trade_date").cast(pl.Utf8) == latest_date)
    rows = frame.to_dicts()
    clean = [
        row
        for row in rows
        if _float(row.get("spot_equivalent_level")) is not None
    ]
    if not clean:
        return "CME_WALL_INSUFFICIENT_DATA"
    nearest = min(clean, key=lambda row: abs((_float(row.get("spot_equivalent_level")) or 0.0) - latest_price))
    level = _float(nearest.get("spot_equivalent_level")) or latest_price
    wall_type = _text(nearest.get("wall_type")) or "CME_WALL"
    distance = abs(latest_price - level)
    pilot = "PILOT_ONLY" if _cme_available_rows(cme_plan) < 30 else "WATCH_ZONE"
    return f"{pilot}_{wall_type}_NEAR_{level:.2f}_DISTANCE_{distance:.2f}"


def _confirmation_state(*, sd_state: str, latest: dict[str, Any]) -> str:
    close = _float(latest.get("close"))
    open_price = _float(latest.get("open"))
    if close is None or open_price is None:
        return "INSUFFICIENT_DATA"
    if sd_state == "INSIDE_1SD":
        return "NO_DIRECTIONAL_CONFIRMATION"
    if sd_state in {"TOUCH_2SD_ZONE", "TOUCH_3SD_HIGH_RISK"} and close < open_price:
        return "POSSIBLE_REJECTION_NEEDS_CLOSED_CONTEXT"
    if sd_state in {"TOUCH_2SD_ZONE", "TOUCH_3SD_HIGH_RISK", "BEYOND_3_5SD_TAIL_RISK"}:
        return "TOUCH_ONLY_CONFIRMATION_REQUIRED"
    return "WATCH_ONLY_NO_LEVEL_CONFIRMATION"


def _data_quality_state(*, price: pl.DataFrame, cme_plan: pl.DataFrame, one_sd: float | None) -> str:
    notes = []
    if price.is_empty():
        notes.append("MISSING_PRICE_DATA")
    if one_sd is None:
        notes.append("MISSING_SD_PROXY")
    if _cme_available_rows(cme_plan) < 30:
        notes.append("CME_WALL_PILOT_ONLY")
    notes.append("TRUE_IV_MISSING")
    return ";".join(notes) if notes else "OK"


def _final_action(
    *,
    sd_state: str,
    cme_wall_state: str,
    confirmation_state: str,
    data_quality_state: str,
) -> str:
    if "MISSING_PRICE_DATA" in data_quality_state or sd_state == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_DATA"
    if sd_state == "INSIDE_1SD":
        return "BLOCK"
    if "TOUCH_3SD" in sd_state and "TOUCH_ONLY" in confirmation_state:
        return "BLOCK"
    if sd_state == "TOUCH_2SD_ZONE" and "POSSIBLE_REJECTION" in confirmation_state:
        return "ALLOW_RESEARCH_CANDIDATE"
    if "PILOT_ONLY" in cme_wall_state:
        return "WATCH_ONLY"
    if "TARGET_REFERENCE" in sd_state:
        return "TARGET_REFERENCE"
    return "WATCH_ONLY"


def _cme_available_rows(cme_plan: pl.DataFrame) -> int:
    if cme_plan.is_empty() or "current_testable_rows" not in cme_plan.columns:
        return 0
    values = [_int(row.get("current_testable_rows")) for row in cme_plan.to_dicts()]
    return max(values) if values else 0


def _latest_date_value(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    values = [_text(value)[:10] for value in frame.get_column(column).to_list() if _text(value)]
    return max(values) if values else ""


def _blueprint_yaml(result: XauSdGridCmeIndicatorBlueprintResult) -> str:
    lines = [
        "version: xau_indicator_blueprint_v1",
        "research_only: true",
        f"final_recommendation: {result.final_recommendation}",
        "allowed_actions:",
        *[f"  - {action}" for action in ALLOWED_ACTIONS],
        "principles:",
        "  sd: 'volatility_zone'",
        "  grid: 'target_reference_geometry'",
        "  cme_wall: 'market_positioning_context'",
        "  price_reaction: 'confirmation_layer'",
        "layers:",
    ]
    for row in result.blueprint_layers.to_dicts():
        lines.extend(
            [
                f"  - layer_id: {_yaml_scalar(row.get('layer_id'))}",
                f"    layer_name: {_yaml_scalar(row.get('layer_name'))}",
                f"    components: {_yaml_scalar(row.get('components'))}",
                f"    source: {_yaml_scalar(row.get('source'))}",
                f"    valid_use: {_yaml_scalar(row.get('valid_use'))}",
                f"    invalid_use: {_yaml_scalar(row.get('invalid_use'))}",
                f"    current_status: {_yaml_scalar(row.get('current_status'))}",
            ]
        )
    return "\n".join(lines) + "\n"


def _blueprint_markdown(result: XauSdGridCmeIndicatorBlueprintResult) -> str:
    return "\n\n".join(
        [
            "# XAU Indicator Blueprint v1",
            RESEARCH_WARNING,
            f"Final recommendation: `{result.final_recommendation}`.",
            "## Layers",
            _frame_markdown(result.blueprint_layers),
        ]
    )


def _chart_annotation_spec_markdown() -> str:
    return "\n".join(
        [
            "# XAU Indicator Chart Annotation Spec",
            "",
            RESEARCH_WARNING,
            "",
            "## SD Bands",
            "- Plot 1SD as the middle/no-trade band around the session/open reference.",
            "- Plot 2SD as the rejection-watch boundary.",
            "- Plot 3SD as the high-risk extreme boundary.",
            "- Plot 3.5SD as invalidation/tail-risk reference.",
            "",
            "## Grid Levels",
            "- Plot 25-point grid lines as thin target/reference levels.",
            "- Plot 12.50 half-grid lines as lighter midpoint reference levels.",
            "- Do not mark grid touches as candidate markers by themselves.",
            "",
            "## CME Walls",
            "- Plot call wall, put wall, total OI wall, and max OI wall as market-map levels.",
            "- Use different styles for call, put, total OI, max OI, and low-OI gap zones.",
            "- Mark wall acceptance or rejection only after closed-candle price reaction.",
            "",
            "## Confirmation Markers",
            "- Mark rejection back inside after a level touch.",
            "- Mark hourly acceptance close and continuation hold separately.",
            "- Mark failed break only after price returns inside the referenced level.",
            "",
            "## Zone Shading",
            "- Shade inside 1SD as no-trade/middle zone.",
            "- Shade raw 2SD or 3SD touch areas as watch-only until confirmation.",
            "- Use allow-research markers only for confirmed 2SD rejection with clear data quality.",
        ]
    )


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


def _yaml_scalar(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return "''"
    return "'" + text.replace("'", "''") + "'"


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


def _frame_input(inputs: dict[str, Any], key: str) -> pl.DataFrame:
    value = inputs.get(key)
    return value if isinstance(value, pl.DataFrame) else pl.DataFrame()


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
    return str(value or "").strip()


def _timestamp_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _concept_schema() -> dict[str, Any]:
    return {
        "concept": pl.Utf8,
        "what_it_is": pl.Utf8,
        "what_it_is_not": pl.Utf8,
        "source_data": pl.Utf8,
        "calculation_method": pl.Utf8,
        "valid_use": pl.Utf8,
        "invalid_use": pl.Utf8,
        "current_confidence": pl.Utf8,
        "needs_more_data": pl.Boolean,
    }


def _blueprint_schema() -> dict[str, Any]:
    return {
        "layer_id": pl.Utf8,
        "layer_name": pl.Utf8,
        "components": pl.Utf8,
        "source": pl.Utf8,
        "valid_use": pl.Utf8,
        "invalid_use": pl.Utf8,
        "current_status": pl.Utf8,
        "allowed_actions": pl.Utf8,
    }


def _action_schema() -> dict[str, Any]:
    return {
        "indicator_state": pl.Utf8,
        "manual_action": pl.Utf8,
        "context_label": pl.Utf8,
        "interpretation": pl.Utf8,
        "invalid_use_guardrail": pl.Utf8,
    }


def _latest_schema() -> dict[str, Any]:
    return {
        "as_of_timestamp": pl.Utf8,
        "latest_price": pl.Float64,
        "latest_timeframe": pl.Utf8,
        "sd_state": pl.Utf8,
        "grid_state": pl.Utf8,
        "cme_wall_state": pl.Utf8,
        "confirmation_state": pl.Utf8,
        "data_quality_state": pl.Utf8,
        "final_action": pl.Utf8,
        "plain_english_summary": pl.Utf8,
    }


def _price_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime,
        "trade_date": pl.Utf8,
        "timeframe": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    }


def main() -> None:
    """CLI entry point."""

    result = run_xau_sd_grid_cme_indicator_blueprint()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"concept_rows: {result.concept_map.height}")


if __name__ == "__main__":
    main()
