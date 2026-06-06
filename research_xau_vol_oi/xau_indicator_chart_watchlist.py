"""Chart-ready and watchlist-ready XAU indicator blueprint outputs."""

from __future__ import annotations

import html
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
    "Research-only chart/watchlist output. SD, grid, CME wall, and price "
    "confirmation layers stay separated."
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
class XauIndicatorChartWatchlistResult:
    """Generated chart/watchlist outputs."""

    levels_latest: pl.DataFrame
    watchlist_latest: pl.DataFrame
    final_recommendation: str
    chart_path: Path
    paths: dict[str, Path]


def run_xau_indicator_chart_watchlist_output(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> XauIndicatorChartWatchlistResult:
    """Build latest chart-ready and watchlist-ready indicator outputs."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(output_root)
    context = _latest_context(inputs)
    levels = build_indicator_levels_latest(inputs=inputs, context=context)
    watchlist = build_indicator_watchlist_latest(levels=levels, context=context)
    final = choose_final_recommendation(watchlist)
    chart_path = paths["chart_html"]
    result = XauIndicatorChartWatchlistResult(
        levels_latest=levels,
        watchlist_latest=watchlist,
        final_recommendation=final,
        chart_path=chart_path,
        paths=paths,
    )
    if write_outputs:
        write_xau_indicator_chart_watchlist_outputs(result)
    return result


def build_indicator_levels_latest(
    *,
    inputs: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Build latest separated SD, grid, CME wall, and confirmation rows."""

    inputs = inputs or {}
    context = context or _latest_context(inputs)
    if not context:
        return _frame([], _levels_schema())
    rows: list[dict[str, Any]] = []
    rows.extend(_sd_level_rows(context))
    rows.extend(_grid_level_rows(context))
    rows.extend(_cme_wall_rows(inputs, context))
    rows.extend(_confirmation_rows(context))
    return _frame([_safe_row(row) for row in rows], _levels_schema())


def build_indicator_watchlist_latest(
    *,
    levels: pl.DataFrame,
    context: dict[str, Any],
) -> pl.DataFrame:
    """Build one-row latest watchlist output from separated levels."""

    if not context:
        row = {
            "as_of_timestamp": "",
            "latest_price": None,
            "latest_timeframe": "",
            "sd_source": "INSUFFICIENT_DATA",
            "sd_state": "INSUFFICIENT_DATA",
            "grid_state": "INSUFFICIENT_DATA",
            "cme_wall_state": "INSUFFICIENT_DATA",
            "confirmation_state": "INSUFFICIENT_DATA",
            "final_action": "INSUFFICIENT_DATA",
            "final_recommendation": "WATCHLIST_ONLY",
            "plain_english_summary": "No latest price data is available.",
        }
        return _frame([_safe_row(row)], _watchlist_schema())
    final_action = _final_action(context)
    final_recommendation = (
        "INDICATOR_BLUEPRINT_READY"
        if final_action != "INSUFFICIENT_DATA"
        else "WATCHLIST_ONLY"
    )
    row = {
        "as_of_timestamp": context["timestamp"],
        "latest_price": context["latest_price"],
        "latest_timeframe": context["timeframe"],
        "sd_source": context["sd_source"],
        "sd_state": context["sd_state"],
        "grid_state": _grid_state_text(levels),
        "cme_wall_state": _cme_state_text(levels),
        "confirmation_state": context["confirmation_state"],
        "final_action": final_action,
        "final_recommendation": final_recommendation,
        "plain_english_summary": _watchlist_summary(context, levels, final_action),
    }
    return _frame([_safe_row(row)], _watchlist_schema())


def choose_final_recommendation(watchlist: pl.DataFrame) -> str:
    """Choose final recommendation for the chart/watchlist layer."""

    if watchlist.is_empty():
        return "WATCHLIST_ONLY"
    row = watchlist.row(0, named=True)
    action = _text(row.get("final_action"))
    if action == "INSUFFICIENT_DATA":
        return "WATCHLIST_ONLY"
    return "INDICATOR_BLUEPRINT_READY"


def write_xau_indicator_chart_watchlist_outputs(
    result: XauIndicatorChartWatchlistResult,
) -> None:
    """Write CSV, Markdown, and HTML chart outputs."""

    result.levels_latest.write_csv(result.paths["levels_csv"])
    result.paths["levels_md"].write_text(
        _safe_report_text(_artifact_markdown("XAU Indicator Levels Latest", result.levels_latest)),
        encoding="utf-8",
    )
    result.watchlist_latest.write_csv(result.paths["watchlist_csv"])
    result.paths["watchlist_md"].write_text(
        _safe_report_text(_artifact_markdown("XAU Indicator Watchlist Latest", result.watchlist_latest)),
        encoding="utf-8",
    )
    result.paths["chart_html"].write_text(
        _safe_report_text(_chart_html(result)),
        encoding="utf-8",
    )


def xau_indicator_chart_watchlist_report_lines(
    result: XauIndicatorChartWatchlistResult | None,
) -> list[str]:
    """Return report lines for research_report.md."""

    if result is None:
        return [
            "## XAU Indicator Chart And Watchlist Output",
            "",
            "XAU indicator chart/watchlist output was not run.",
        ]
    return [
        "## XAU Indicator Chart And Watchlist Output",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Chart artifact: `{_display_path(result.chart_path)}`",
        "",
        "## Latest Indicator Levels",
        "",
        _frame_markdown(result.levels_latest),
        "",
        "## Latest Indicator Watchlist",
        "",
        _frame_markdown(result.watchlist_latest),
        "",
        "- Links: `outputs/xau_indicator_levels_latest.csv`, "
        "`outputs/xau_indicator_watchlist_latest.csv`, "
        "`outputs/charts/xau_indicator_blueprint_latest.html`.",
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
        "levels_csv": output_root / "xau_indicator_levels_latest.csv",
        "levels_md": output_root / "xau_indicator_levels_latest.md",
        "watchlist_csv": output_root / "xau_indicator_watchlist_latest.csv",
        "watchlist_md": output_root / "xau_indicator_watchlist_latest.md",
        "chart_html": output_root / "charts" / "xau_indicator_blueprint_latest.html",
    }


def _load_inputs(output_root: Path) -> dict[str, Any]:
    paths = {
        "blueprint_yaml_text": output_root / "xau_indicator_blueprint_v1.yaml",
        "action_mapping": output_root / "xau_indicator_action_mapping.csv",
        "latest_state": output_root / "xau_indicator_latest_state.csv",
        "concept_map": output_root / "xau_sd_grid_cme_concept_map.csv",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "cme_wall_map": output_root / "cme_wall_map_by_date.csv",
        "basis": output_root / "xau_basis_backfilled.parquet",
    }
    inputs: dict[str, Any] = {}
    for key, path in paths.items():
        if key.endswith("_text"):
            inputs[key] = _read_text(path)
        else:
            inputs[key] = _read_optional(path)
    return inputs


def _latest_context(inputs: dict[str, Any]) -> dict[str, Any]:
    price = _latest_price_frame(inputs)
    if price.is_empty():
        return {}
    rows = price.sort("timestamp").to_dicts()
    latest = rows[-1]
    latest_price = _float(latest.get("close"))
    if latest_price is None:
        return {}
    session_rows = _same_trade_date_rows(rows, latest)
    session_open = _float(session_rows[0].get("open")) if session_rows else latest_price
    one_sd = _realized_one_sd(session_rows)
    sd_source = _sd_source(inputs)
    sigma_close = _sigma(latest_price, session_open, one_sd)
    context = {
        "timestamp": _timestamp_text(latest.get("timestamp")),
        "latest_price": latest_price,
        "timeframe": _text(latest.get("timeframe")) or "15m",
        "latest_bar": latest,
        "session_open": session_open,
        "one_sd": one_sd,
        "sd_source": sd_source,
        "sigma_close": sigma_close,
    }
    context["sd_state"] = _sd_state(context)
    context["confirmation_state"] = _confirmation_state(context)
    return context


def _sd_level_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    session_open = _float(context.get("session_open"))
    one_sd = _float(context.get("one_sd"))
    if session_open is None or one_sd is None:
        return [
            _level_row(
                "SD_BAND",
                "SD_LEVEL",
                "SD_UNAVAILABLE",
                None,
                "INSUFFICIENT_DATA",
                "INSUFFICIENT_DATA",
                "Missing SD source data.",
            )
        ]
    for multiplier in (1.0, 2.0, 3.0, 3.5):
        label = _sd_label(multiplier)
        rows.append(
            _level_row(
                "SD_BAND",
                "SD_LEVEL",
                f"+{label}",
                session_open + multiplier * one_sd,
                "WATCH_ONLY" if multiplier > 1 else "BLOCK",
                context["sd_source"],
                _sd_note(multiplier, "upper"),
            )
        )
        rows.append(
            _level_row(
                "SD_BAND",
                "SD_LEVEL",
                f"-{label}",
                session_open - multiplier * one_sd,
                "WATCH_ONLY" if multiplier > 1 else "BLOCK",
                context["sd_source"],
                _sd_note(multiplier, "lower"),
            )
        )
    return rows


def _grid_level_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    price = _float(context.get("latest_price"))
    if price is None:
        return []
    nearest_25 = round(price / 25.0) * 25.0
    nearest_12 = round(price / 12.5) * 12.5
    return [
        _level_row(
            "GRID",
            "GRID_25",
            "NEAREST_25_FULL_BLOCK",
            nearest_25,
            "TARGET_REFERENCE",
            "PRICE_GRID",
            "25-point grid is target/reference geometry only.",
        ),
        _level_row(
            "GRID",
            "HALF_GRID_12_50",
            "NEAREST_12_50_HALF_BLOCK",
            nearest_12,
            "TARGET_REFERENCE",
            "PRICE_GRID",
            "12.50 half-grid is target/reference geometry only.",
        ),
    ]


def _cme_wall_rows(inputs: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    price = _float(context.get("latest_price"))
    wall_map = _frame_input(inputs, "cme_wall_map")
    if price is None or wall_map.is_empty() or "spot_equivalent_level" not in wall_map.columns:
        return [
            _level_row(
                "CME_WALL",
                "CME_OI_WALL",
                "CME_WALL_UNAVAILABLE",
                None,
                "INSUFFICIENT_DATA",
                "CME_OI",
                "CME wall map is missing or unusable.",
            )
        ]
    latest_date = _latest_date_value(wall_map, "trade_date")
    scoped = wall_map
    if latest_date and "trade_date" in scoped.columns:
        scoped = scoped.filter(pl.col("trade_date").cast(pl.Utf8) == latest_date)
    rows = scoped.to_dicts()
    confidence = _cme_confidence(inputs)
    result_rows = [
        _cme_level_row(
            rows,
            price=price,
            concept="CME_CALL_WALL",
            name="NEAREST_CALL_WALL",
            action="WATCH_ONLY",
            predicate=lambda row: _is_call_wall(row),
            confidence=confidence,
        ),
        _cme_level_row(
            rows,
            price=price,
            concept="CME_PUT_WALL",
            name="NEAREST_PUT_WALL",
            action="WATCH_ONLY",
            predicate=lambda row: _is_put_wall(row),
            confidence=confidence,
        ),
        _max_oi_level_row(rows, price=price, confidence=confidence),
        _low_oi_gap_row(rows, confidence=confidence),
    ]
    return [row for row in result_rows if row is not None]


def _confirmation_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    state = _text(context.get("confirmation_state"))
    action = _final_action(context)
    return [
        _level_row(
            "PRICE_CONFIRMATION",
            "PRICE_REACTION_CONFIRMATION",
            state or "NO_CONFIRMATION",
            _float(context.get("latest_price")),
            action,
            "DUKASCOPY_OHLC",
            _confirmation_note(state),
        )
    ]


def _level_row(
    layer: str,
    concept: str,
    level_name: str,
    level_value: float | None,
    manual_action: str,
    source: str,
    note: str,
) -> dict[str, Any]:
    return {
        "layer": layer,
        "concept": concept,
        "level_name": level_name,
        "level_value": level_value,
        "manual_action": _allowed_action(manual_action),
        "source": source,
        "confidence": _confidence_for(layer, source),
        "valid_use": _valid_use_for(layer),
        "invalid_use": _invalid_use_for(layer),
        "note": note,
    }


def _cme_level_row(
    rows: list[dict[str, Any]],
    *,
    price: float,
    concept: str,
    name: str,
    action: str,
    predicate: Any,
    confidence: str,
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if predicate(row) and _float(row.get("spot_equivalent_level")) is not None
    ]
    if not candidates:
        return _level_row(
            "CME_WALL",
            concept,
            f"{name}_UNAVAILABLE",
            None,
            "INSUFFICIENT_DATA",
            "CME_OI",
            "No matching CME wall row is available.",
        )
    nearest = min(candidates, key=lambda row: abs((_float(row.get("spot_equivalent_level")) or 0.0) - price))
    level = _float(nearest.get("spot_equivalent_level"))
    return {
        **_level_row(
            "CME_WALL",
            concept,
            name,
            level,
            action,
            "CME_OI",
            f"{name} is context only; price reaction is required.",
        ),
        "confidence": confidence,
    }


def _max_oi_level_row(
    rows: list[dict[str, Any]],
    *,
    price: float,
    confidence: str,
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if _float(row.get("spot_equivalent_level")) is not None
    ]
    if not candidates:
        return None
    max_row = max(candidates, key=lambda row: _float(row.get("total_oi")) or 0.0)
    level = _float(max_row.get("spot_equivalent_level"))
    name = "MAX_OI_WALL"
    if _text(max_row.get("wall_type")) == "MAX_OI_PIN":
        name = "MAX_OI_PIN"
    distance = abs((level or price) - price)
    return {
        **_level_row(
            "CME_WALL",
            "CME_MAX_OI",
            name,
            level,
            "WATCH_ONLY",
            "CME_OI",
            f"Max OI wall is market-map context; distance={distance:.2f}.",
        ),
        "confidence": confidence,
    }


def _low_oi_gap_row(rows: list[dict[str, Any]], *, confidence: str) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if "LOW" in _text(row.get("wall_type")).upper()
        and "GAP" in _text(row.get("wall_type")).upper()
        and _float(row.get("spot_equivalent_level")) is not None
    ]
    if not candidates:
        return {
            **_level_row(
                "CME_WALL",
                "CME_LOW_OI_GAP",
                "LOW_OI_GAP_UNAVAILABLE",
                None,
                "INSUFFICIENT_DATA",
                "CME_OI",
                "Low-OI gap is unavailable in the current wall map.",
            ),
            "confidence": "INSUFFICIENT_DATA",
        }
    row = candidates[0]
    return {
        **_level_row(
            "CME_WALL",
            "CME_LOW_OI_GAP",
            "LOW_OI_GAP",
            _float(row.get("spot_equivalent_level")),
            "WATCH_ONLY",
            "CME_OI",
            "Low-OI gap is context only until price reaction confirms behavior.",
        ),
        "confidence": confidence,
    }


def _latest_price_frame(inputs: dict[str, Any]) -> pl.DataFrame:
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


def _sd_source(inputs: dict[str, Any]) -> str:
    blueprint = _text(inputs.get("blueprint_yaml_text"))
    if "CME_IV_AVAILABLE" in blueprint:
        return "CME_IV"
    return "REALIZED_VOL_PROXY"


def _sd_state(context: dict[str, Any]) -> str:
    sigma = _float(context.get("sigma_close"))
    if sigma is None:
        return "INSUFFICIENT_DATA"
    distance = abs(sigma)
    if distance <= 1.0:
        return "INSIDE_1SD"
    if distance < 2.0:
        return "BETWEEN_1SD_2SD"
    if distance < 3.0:
        return "TOUCHING_2SD"
    if distance < 3.5:
        return "TOUCHING_3SD"
    return "BEYOND_3_5SD"


def _confirmation_state(context: dict[str, Any]) -> str:
    latest = context.get("latest_bar") if isinstance(context.get("latest_bar"), dict) else {}
    session_open = _float(context.get("session_open"))
    one_sd = _float(context.get("one_sd"))
    close = _float(latest.get("close"))
    high = _float(latest.get("high"))
    low = _float(latest.get("low"))
    if session_open is None or one_sd is None or close is None:
        return "NO_CONFIRMATION"
    sigma_close = _sigma(close, session_open, one_sd) or 0.0
    sigma_high = _sigma(high, session_open, one_sd) if high is not None else None
    sigma_low = _sigma(low, session_open, one_sd) if low is not None else None
    if abs(sigma_close) <= 1.0:
        return "INSIDE_1SD"
    if sigma_high is not None and sigma_high >= 2.0 and sigma_close < 2.0:
        return "REJECTION_BACK_INSIDE_2SD"
    if sigma_low is not None and sigma_low <= -2.0 and sigma_close > -2.0:
        return "REJECTION_BACK_INSIDE_2SD"
    if sigma_high is not None and sigma_high >= 3.0 and sigma_close < 3.0:
        return "REJECTION_BACK_INSIDE_3SD"
    if sigma_low is not None and sigma_low <= -3.0 and sigma_close > -3.0:
        return "REJECTION_BACK_INSIDE_3SD"
    if abs(sigma_close) >= 3.0:
        return "TOUCHING_3SD_NO_CONFIRMATION"
    if abs(sigma_close) >= 2.0:
        return "TOUCHING_2SD_NO_CONFIRMATION"
    return "NO_CONFIRMATION"


def _final_action(context: dict[str, Any]) -> str:
    confirmation = _text(context.get("confirmation_state"))
    sd_state = _text(context.get("sd_state"))
    if not context:
        return "INSUFFICIENT_DATA"
    if confirmation == "INSIDE_1SD" or sd_state == "INSIDE_1SD":
        return "BLOCK"
    if confirmation == "REJECTION_BACK_INSIDE_2SD":
        return "ALLOW_RESEARCH_CANDIDATE"
    if confirmation in {"TOUCHING_3SD_NO_CONFIRMATION", "REJECTION_BACK_INSIDE_3SD"}:
        return "WATCH_ONLY"
    if confirmation == "TOUCHING_2SD_NO_CONFIRMATION":
        return "WATCH_ONLY"
    return "WATCH_ONLY"


def _grid_state_text(levels: pl.DataFrame) -> str:
    if levels.is_empty():
        return "INSUFFICIENT_DATA"
    rows = levels.filter(pl.col("layer") == "GRID").to_dicts()
    return ";".join(
        f"{row['level_name']}={_format_level(row.get('level_value'))}:{row['manual_action']}"
        for row in rows
    )


def _cme_state_text(levels: pl.DataFrame) -> str:
    if levels.is_empty():
        return "INSUFFICIENT_DATA"
    rows = levels.filter(pl.col("layer") == "CME_WALL").to_dicts()
    return ";".join(
        f"{row['level_name']}={_format_level(row.get('level_value'))}:{row['manual_action']}:{row['confidence']}"
        for row in rows
    )


def _watchlist_summary(context: dict[str, Any], levels: pl.DataFrame, final_action: str) -> str:
    price = _float(context.get("latest_price"))
    price_text = f"{price:.4f}" if price is not None else "n/a"
    return (
        f"Latest price {price_text}; SD state {context.get('sd_state')}; "
        f"confirmation {context.get('confirmation_state')}; "
        f"grid references {_grid_state_text(levels)}; "
        f"CME context {_cme_state_text(levels)}; final action {final_action}."
    )


def _chart_html(result: XauIndicatorChartWatchlistResult) -> str:
    watch = result.watchlist_latest.row(0, named=True) if not result.watchlist_latest.is_empty() else {}
    levels = result.levels_latest.to_dicts()
    price = _float(watch.get("latest_price"))
    chart_rows = [
        row
        for row in levels
        if _float(row.get("level_value")) is not None
    ]
    values = [_float(row.get("level_value")) for row in chart_rows]
    clean_values = [value for value in values if value is not None]
    if price is not None:
        clean_values.append(price)
    minimum = min(clean_values) if clean_values else 0.0
    maximum = max(clean_values) if clean_values else 1.0
    padding = max((maximum - minimum) * 0.08, 5.0)
    minimum -= padding
    maximum += padding
    width = 980
    height = 620
    plot_top = 56
    plot_bottom = height - 70
    plot_height = plot_bottom - plot_top

    def y_pos(value: float) -> float:
        if maximum <= minimum:
            return plot_bottom
        return plot_bottom - ((value - minimum) / (maximum - minimum)) * plot_height

    lines = []
    for row in chart_rows:
        value = _float(row.get("level_value"))
        if value is None:
            continue
        layer = _text(row.get("layer"))
        color = {
            "SD_BAND": "#6366f1",
            "GRID": "#64748b",
            "CME_WALL": "#d97706",
            "PRICE_CONFIRMATION": "#059669",
        }.get(layer, "#334155")
        dash = "6 5" if layer == "GRID" else "2 4" if layer == "CME_WALL" else ""
        y = y_pos(value)
        label = f"{row.get('layer')} {row.get('level_name')} {value:.2f} {row.get('manual_action')}"
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        lines.append(
            f'<line x1="120" x2="{width - 60}" y1="{y:.2f}" y2="{y:.2f}" '
            f'stroke="{color}" stroke-width="1.6"{dash_attr} />'
        )
        lines.append(
            f'<text x="126" y="{max(18, y - 5):.2f}" fill="{color}" '
            f'font-size="12">{html.escape(label)}</text>'
        )
    if price is not None:
        y = y_pos(price)
        lines.append(
            f'<line x1="90" x2="{width - 40}" y1="{y:.2f}" y2="{y:.2f}" '
            'stroke="#0f172a" stroke-width="2.5" />'
        )
        lines.append(
            f'<text x="{width - 250}" y="{max(20, y - 8):.2f}" fill="#0f172a" '
            f'font-size="13" font-weight="700">latest price {price:.2f}</text>'
        )
    table = _html_table(result.levels_latest)
    watch_table = _html_table(result.watchlist_latest)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>XAU Indicator Blueprint Latest</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #172033; background: #f7f8fb; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 26px; margin: 0 0 8px; }}
    h2 {{ font-size: 18px; margin-top: 28px; }}
    .note {{ color: #48556a; margin-bottom: 18px; }}
    svg {{ width: 100%; height: auto; background: white; border: 1px solid #d9dee8; }}
    table {{ border-collapse: collapse; width: 100%; background: white; font-size: 12px; }}
    th, td {{ border: 1px solid #d9dee8; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; }}
  </style>
</head>
<body>
<main>
  <h1>XAU Indicator Blueprint Latest</h1>
  <p class="note">{html.escape(RESEARCH_WARNING)} No execution behavior is included.</p>
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="XAU separated indicator levels">
    <rect x="80" y="{plot_top}" width="{width - 130}" height="{plot_height}" fill="#ffffff" stroke="#cbd5e1" />
    {''.join(lines)}
  </svg>
  <h2>Watchlist State</h2>
  {watch_table}
  <h2>Separated Levels</h2>
  {table}
</main>
</body>
</html>
"""


def _html_table(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "<p>No rows.</p>"
    lines = ["<table><thead><tr>"]
    for column in frame.columns:
        lines.append(f"<th>{html.escape(column)}</th>")
    lines.append("</tr></thead><tbody>")
    for row in frame.to_dicts():
        lines.append("<tr>")
        for column in frame.columns:
            lines.append(f"<td>{html.escape(_markdown_cell(row.get(column)))}</td>")
        lines.append("</tr>")
    lines.append("</tbody></table>")
    return "".join(lines)


def _is_call_wall(row: dict[str, Any]) -> bool:
    return "CALL" in _text(row.get("wall_type")).upper() or _float(row.get("call_oi")) not in (None, 0.0)


def _is_put_wall(row: dict[str, Any]) -> bool:
    return "PUT" in _text(row.get("wall_type")).upper() or _float(row.get("put_oi")) not in (None, 0.0)


def _cme_confidence(inputs: dict[str, Any]) -> str:
    concept = _frame_input(inputs, "concept_map")
    if not concept.is_empty() and "concept" in concept.columns and "current_confidence" in concept.columns:
        rows = concept.filter(pl.col("concept") == "CME_OI_WALL")
        if not rows.is_empty():
            return _text(rows.row(0, named=True).get("current_confidence")) or "PILOT_ONLY"
    return "PILOT_ONLY"


def _sd_label(multiplier: float) -> str:
    return "3.5SD" if multiplier == 3.5 else f"{int(multiplier)}SD"


def _sd_note(multiplier: float, side: str) -> str:
    label = _sd_label(multiplier)
    if multiplier == 1.0:
        return f"{side} {label} boundary is middle/no-trade zone context."
    if multiplier == 2.0:
        return f"{side} {label} boundary requires rejection confirmation."
    if multiplier == 3.0:
        return f"{side} {label} boundary is high-risk watch-only context."
    return f"{side} {label} boundary is invalidation/tail-risk reference."


def _confirmation_note(state: str) -> str:
    if state == "REJECTION_BACK_INSIDE_2SD":
        return "2SD rejection confirmation allows research candidate review."
    if state == "REJECTION_BACK_INSIDE_3SD":
        return "3SD rejection remains high-risk and watch-only."
    if state == "TOUCHING_2SD_NO_CONFIRMATION":
        return "Blind 2SD touch is watch-only."
    if state == "TOUCHING_3SD_NO_CONFIRMATION":
        return "Blind 3SD touch is high-risk watch-only."
    if state == "INSIDE_1SD":
        return "Inside 1SD blocks directional review."
    return "No price confirmation is active."


def _confidence_for(layer: str, source: str) -> str:
    if layer == "SD_BAND":
        return "REALIZED_VOL_PROXY" if source == "REALIZED_VOL_PROXY" else "CME_IV"
    if layer == "GRID":
        return "REFERENCE_ONLY"
    if layer == "PRICE_CONFIRMATION":
        return "CONFIRMATION_REQUIRED"
    return "PILOT_ONLY"


def _valid_use_for(layer: str) -> str:
    return {
        "SD_BAND": "Volatility zone and confirmation boundary.",
        "GRID": "Target/reference geometry only.",
        "CME_WALL": "Market-map context, target/watch zone, reaction zone.",
        "PRICE_CONFIRMATION": "Confirmation or blocker for blind level touches.",
    }.get(layer, "Research context only.")


def _invalid_use_for(layer: str) -> str:
    return {
        "SD_BAND": "Blind SD touch as standalone candidate.",
        "GRID": "Standalone candidate trigger.",
        "CME_WALL": "Automatic candidate from wall proximity.",
        "PRICE_CONFIRMATION": "Post-event narrative without timestamped evidence.",
    }.get(layer, "Unvalidated execution use.")


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


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


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join([f"# {title}", RESEARCH_WARNING, _frame_markdown(frame)])


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 40) -> str:
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


def _display_path(path: Path) -> str:
    parts = path.parts
    if "outputs" in parts:
        index = parts.index("outputs")
        return "/".join(parts[index:])
    return _safe_text(path.name)


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


def _sigma(price: float | None, session_open: float | None, one_sd: float | None) -> float | None:
    if price is None or session_open is None or one_sd is None or one_sd <= 0:
        return None
    return (price - session_open) / one_sd


def _format_level(value: Any) -> str:
    number = _float(value)
    return "n/a" if number is None else f"{number:.2f}"


def _latest_date_value(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    values = [_text(value)[:10] for value in frame.get_column(column).to_list() if _text(value)]
    return max(values) if values else ""


def _allowed_action(value: Any) -> str:
    action = _text(value)
    return action if action in ALLOWED_ACTIONS else "INSUFFICIENT_DATA"


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


def _levels_schema() -> dict[str, Any]:
    return {
        "layer": pl.Utf8,
        "concept": pl.Utf8,
        "level_name": pl.Utf8,
        "level_value": pl.Float64,
        "manual_action": pl.Utf8,
        "source": pl.Utf8,
        "confidence": pl.Utf8,
        "valid_use": pl.Utf8,
        "invalid_use": pl.Utf8,
        "note": pl.Utf8,
    }


def _watchlist_schema() -> dict[str, Any]:
    return {
        "as_of_timestamp": pl.Utf8,
        "latest_price": pl.Float64,
        "latest_timeframe": pl.Utf8,
        "sd_source": pl.Utf8,
        "sd_state": pl.Utf8,
        "grid_state": pl.Utf8,
        "cme_wall_state": pl.Utf8,
        "confirmation_state": pl.Utf8,
        "final_action": pl.Utf8,
        "final_recommendation": pl.Utf8,
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

    result = run_xau_indicator_chart_watchlist_output()
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"chart_path: {_display_path(result.chart_path)}")


if __name__ == "__main__":
    main()
