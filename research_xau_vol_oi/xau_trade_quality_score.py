"""Transparent XAU trade-quality score and indicator edge lab.

This module is research-only. It builds deterministic block/watch/research
classifications from local Dukascopy price behavior, pilot CME/guru context,
and spread/fee hurdles. It does not create orders, position sizes, broker
payloads, live/paper trading state, or direct buy/sell instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import polars as pl


COMPONENT_ORDER = (
    "acceptance_breakout_component",
    "rejection_after_touch_component",
    "no_trade_middle_range_component",
    "open_distance_component",
    "fee_spread_hurdle_component",
    "cme_wall_context_component",
    "cme_iv_range_component",
    "guru_filter_component",
    "data_quality_component",
    "stale_data_component",
)
ABLATION_COMPONENTS = (
    "without_acceptance_breakout",
    "without_no_trade_middle_range",
    "without_open_distance",
    "without_fee_spread_hurdle",
    "without_cme_wall",
    "without_guru_filter",
    "without_data_quality",
)
SCORE_BUCKETS = (
    "BLOCK",
    "WATCH_ONLY",
    "ALLOW_RESEARCH",
    "HIGH_QUALITY_RESEARCH",
)
FINAL_LABELS = (
    "BLOCKED_NO_TRADE_RANGE",
    "BLOCKED_OPEN_DISTANCE",
    "BLOCKED_SPREAD_FEE",
    "WATCH_ACCEPTANCE_BREAKOUT",
    "WATCH_CME_WALL",
    "WATCH_GURU_CONTEXT",
    "ALLOW_RESEARCH_CANDIDATE",
    "INSUFFICIENT_DATA",
)
FINAL_RECOMMENDATIONS = (
    "TRADE_QUALITY_SCORE_READY_FOR_RESEARCH",
    "SCORE_PROMISING_BUT_UNVALIDATED",
    "USE_AS_WATCHLIST_FILTER_ONLY",
    "NEEDS_MORE_FORWARD_DATA",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only watchlist support. No live trading, paper trading, broker "
    "integration, position sizing, direct execution instruction, full-sample "
    "weight tuning, or money-readiness claim is included."
)
FORBIDDEN_REPORT_PHRASES = (
    " buy ",
    " sell ",
    "profitable",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "paper ready",
    "validated money edge",
)
MIN_BUCKET_TRADES = 30
ROLLING_LOOKBACK_BY_TIMEFRAME = {
    "15m": 32,
    "30m": 24,
    "1h": 20,
    "4h": 12,
    "1d": 10,
}
EVALUATION_HORIZON_BY_TIMEFRAME = {
    "15m": 8,
    "30m": 6,
    "1h": 4,
    "4h": 3,
    "1d": 2,
}
EXPECTED_GAP_BY_TIMEFRAME = {
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}
COMPONENT_DELTAS = {
    "acceptance_breakout_component": 30,
    "rejection_after_touch_component": 6,
    "no_trade_middle_range_component": -35,
    "open_distance_component": -28,
    "fee_spread_hurdle_component": -45,
    "cme_wall_context_component": 8,
    "cme_iv_range_component": 4,
    "guru_filter_component": -18,
    "data_quality_component": 8,
    "stale_data_component": -25,
}


@dataclass(frozen=True)
class XauTradeQualityScoreResult:
    """Frames emitted by the trade-quality score lab."""

    components: pl.DataFrame
    scores: pl.DataFrame
    backtest: pl.DataFrame
    ablation: pl.DataFrame
    final_recommendation: str
    high_score_outperformed_low_score: bool
    strongest_positive_component: str
    strongest_negative_component: str
    paths: dict[str, Path]


@dataclass(frozen=True)
class _ScoreBuildResult:
    public_scores: pl.DataFrame
    evaluation_rows: list[dict[str, Any]]


def run_xau_trade_quality_score_lab(
    *,
    output_dir: str | Path = "outputs",
    write_outputs: bool = True,
) -> XauTradeQualityScoreResult:
    """Build score components, scored events, bucket evaluation, and ablation."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    paths = _output_paths(output_root)
    inputs = _load_inputs(paths)
    components = build_score_components(
        price_rule_interpretation=inputs["price_rule_interpretation"],
        cme_overlap_interpretation=inputs["cme_overlap_interpretation"],
        guru_logic_interpretation=inputs["guru_logic_interpretation"],
        price_frames=inputs["price_frames"],
    )
    contexts = _build_contexts(
        current_week=inputs["current_week"],
        same_day_filter=inputs["same_day_filter"],
        same_day_market_map=inputs["same_day_market_map"],
    )
    scored = build_trade_quality_scores(
        price_frames=inputs["price_frames"],
        contexts=contexts,
        components=components,
    )
    backtest = build_score_bucket_backtest(scored.evaluation_rows)
    ablation = build_score_ablation(
        price_frames=inputs["price_frames"],
        contexts=contexts,
        components=components,
        baseline_backtest=backtest,
    )
    high_outperformed = high_score_outperformed_low_score(backtest)
    final = choose_final_recommendation(
        components=components,
        backtest=backtest,
        high_score_outperformed=high_outperformed,
    )
    strongest_positive = strongest_positive_component(scored.evaluation_rows)
    strongest_negative = strongest_negative_component(scored.evaluation_rows)

    result = XauTradeQualityScoreResult(
        components=components,
        scores=scored.public_scores,
        backtest=backtest,
        ablation=ablation,
        final_recommendation=final,
        high_score_outperformed_low_score=high_outperformed,
        strongest_positive_component=strongest_positive,
        strongest_negative_component=strongest_negative,
        paths=paths,
    )
    if write_outputs:
        write_xau_trade_quality_score_outputs(result)
    return result


def build_score_components(
    *,
    price_rule_interpretation: pl.DataFrame = pl.DataFrame(),
    cme_overlap_interpretation: pl.DataFrame = pl.DataFrame(),
    guru_logic_interpretation: pl.DataFrame = pl.DataFrame(),
    price_frames: dict[str, pl.DataFrame] | None = None,
) -> pl.DataFrame:
    """Build one transparent row per score component."""

    price_frames = price_frames or {}
    price_available = any(not frame.is_empty() for frame in price_frames.values())
    rows = [
        _component_row(
            "acceptance_breakout_component",
            data_available=price_available and _has_rule(price_rule_interpretation, "ACCEPTANCE_BREAKOUT"),
            confidence=_rule_confidence(price_rule_interpretation, "ACCEPTANCE_BREAKOUT", default="MISSING_DATA"),
            condition="Current close accepts above or below the prior rolling range.",
            reason="Strongest price-only confirmation candidate; used as candidate context only.",
            required_data="Dukascopy OHLC and price-rule interpretation.",
        ),
        _component_row(
            "rejection_after_touch_component",
            data_available=price_available and _has_rule(price_rule_interpretation, "REJECTION_AFTER_LEVEL_TOUCH"),
            confidence=_rule_confidence(price_rule_interpretation, "REJECTION_AFTER_LEVEL_TOUCH", default="MISSING_DATA"),
            condition="Bar touches a prior range edge but closes back inside the range.",
            reason="Weak/context-only evidence; it cannot override stronger blocks.",
            required_data="Dukascopy OHLC and price-rule interpretation.",
        ),
        _component_row(
            "no_trade_middle_range_component",
            data_available=price_available and _has_rule(price_rule_interpretation, "NO_TRADE_MIDDLE_RANGE"),
            confidence=_rule_confidence(price_rule_interpretation, "NO_TRADE_MIDDLE_RANGE", default="MISSING_DATA"),
            condition="Close is in the middle 35 percent to 65 percent of the prior rolling range.",
            reason="Promising avoid/filter concept from price-only evidence.",
            required_data="Dukascopy OHLC and no-trade rule interpretation.",
        ),
        _component_row(
            "open_distance_component",
            data_available=price_available and _has_rule(price_rule_interpretation, "OPEN_DISTANCE_FILTER"),
            confidence=_rule_confidence(price_rule_interpretation, "OPEN_DISTANCE_FILTER", default="MISSING_DATA"),
            condition="Current open-to-close distance is larger than the prior average bar range.",
            reason="Chase-avoid filter from price-only evidence.",
            required_data="Dukascopy OHLC and open-distance interpretation.",
        ),
        _component_row(
            "fee_spread_hurdle_component",
            data_available=price_available and _spread_available(price_frames),
            confidence="HIGH" if price_available and _spread_available(price_frames) else "MISSING_DATA",
            condition="Spread is elevated versus prior spread history or too large for the bar range.",
            reason="Blocks candidates where fee/spread drag can dominate raw price behavior.",
            required_data="Dukascopy bid/ask spread or spread_points column.",
        ),
        _component_row(
            "cme_wall_context_component",
            data_available=not cme_overlap_interpretation.is_empty(),
            confidence=_cme_confidence(cme_overlap_interpretation),
            condition="Same-day CME wall map exists and price accepted or rejected a wall.",
            reason="Pilot-only market-map context; CME walls are never automatic entries.",
            required_data="CME overlap interpretation plus current-week/same-day wall evidence.",
        ),
        _component_row(
            "cme_iv_range_component",
            data_available=not cme_overlap_interpretation.is_empty(),
            confidence=_cme_confidence(cme_overlap_interpretation),
            condition="CME IV/range context exists for the same-day replay.",
            reason="Pilot-only volatility context until overlap history grows.",
            required_data="CME IV/range or current-week replay IV availability.",
        ),
        _component_row(
            "guru_filter_component",
            data_available=not guru_logic_interpretation.is_empty(),
            confidence=_guru_confidence(guru_logic_interpretation),
            condition="Timing-confirmed guru filter context is active for the session.",
            reason="Guru text is context/filter/playbook evidence, never a standalone signal.",
            required_data="Guru logic interpretation and same-day filter evidence.",
        ),
        _component_row(
            "data_quality_component",
            data_available=price_available,
            confidence="HIGH" if price_available else "MISSING_DATA",
            condition="OHLC row is present, internally usable, and quality is not marked bad.",
            reason="Bad or missing price data blocks the research candidate.",
            required_data="Dukascopy OHLC quality fields.",
        ),
        _component_row(
            "stale_data_component",
            data_available=price_available,
            confidence="HIGH" if price_available else "MISSING_DATA",
            condition="Timestamp gap from the previous candle exceeds the timeframe tolerance.",
            reason="Stale rows must not be upgraded into allowed research candidates.",
            required_data="Sorted timestamped Dukascopy OHLC.",
        ),
    ]
    return _frame(rows, _components_schema())


def build_trade_quality_scores(
    *,
    price_frames: dict[str, pl.DataFrame],
    contexts: dict[str, dict[str, dict[str, Any]]] | None = None,
    components: pl.DataFrame = pl.DataFrame(),
    disabled_components: frozenset[str] | set[str] | None = None,
) -> _ScoreBuildResult:
    """Score all candidate bars using current and prior information only."""

    contexts = contexts or {}
    disabled = frozenset(disabled_components or ())
    rows: list[dict[str, Any]] = []
    evaluation_rows: list[dict[str, Any]] = []
    enabled_components = _enabled_component_lookup(components)
    for timeframe, raw_frame in sorted(price_frames.items()):
        frame = _normalize_price_frame(raw_frame, timeframe)
        if frame.is_empty():
            continue
        records = frame.sort("timestamp").to_dicts()
        lookback = ROLLING_LOOKBACK_BY_TIMEFRAME.get(timeframe, 20)
        horizon = EVALUATION_HORIZON_BY_TIMEFRAME.get(timeframe, 4)
        expected_gap = EXPECTED_GAP_BY_TIMEFRAME.get(timeframe, timedelta(hours=1))
        for index, row in enumerate(records):
            scored = _score_price_row(
                row,
                previous_rows=records[max(0, index - lookback) : index],
                previous_row=records[index - 1] if index > 0 else None,
                future_rows=records[index + 1 : index + 1 + horizon],
                timeframe=timeframe,
                expected_gap=expected_gap,
                contexts=contexts,
                disabled_components=disabled,
                enabled_components=enabled_components,
            )
            public_row = {
                key: scored[key]
                for key in _score_schema()
                if key in scored
            }
            rows.append(public_row)
            evaluation_rows.append(scored)
    public = _frame(rows, _score_schema())
    return _ScoreBuildResult(public_scores=public, evaluation_rows=evaluation_rows)


def build_score_bucket_backtest(
    evaluation_rows: list[dict[str, Any]],
    *,
    min_trade_count: int = MIN_BUCKET_TRADES,
) -> pl.DataFrame:
    """Evaluate score buckets against later price movement after scores are frozen."""

    rows = []
    for bucket in SCORE_BUCKETS:
        bucket_rows = [row for row in evaluation_rows if _text(row.get("score_bucket")) == bucket]
        directional = [
            row
            for row in bucket_rows
            if _text(row.get("candidate_direction")) in {"LONG", "SHORT"}
            and _float_or_none(row.get("_forward_return")) is not None
        ]
        returns = [_float_or_none(row.get("_forward_return")) for row in directional]
        returns = [value for value in returns if value is not None]
        support = [value for value in returns if value > 0]
        failure = [value for value in returns if value <= 0]
        blocked_directional = [row for row in directional if bucket == "BLOCK"]
        false_blocks = [
            row for row in blocked_directional if (_float_or_none(row.get("_forward_return")) or 0.0) > 0
        ]
        helped_blocks = [
            row for row in blocked_directional if (_float_or_none(row.get("_forward_return")) or 0.0) <= 0
        ]
        trade_count = len(directional)
        row = {
            "score_bucket": bucket,
            "event_count": len(bucket_rows),
            "trade_count": trade_count,
            "support_rate": len(support) / trade_count if trade_count else None,
            "failure_rate": len(failure) / trade_count if trade_count else None,
            "average_return": _average(returns),
            "expectancy_proxy": _average(returns),
            "average_mfe": _average([
                _float_or_none(item.get("_mfe")) or 0.0 for item in directional
            ]),
            "average_mae": _average([
                _float_or_none(item.get("_mae")) or 0.0 for item in directional
            ]),
            "filter_helped_rate": (
                len(helped_blocks) / len(blocked_directional)
                if blocked_directional
                else None
            ),
            "false_block_rate": (
                len(false_blocks) / len(blocked_directional)
                if blocked_directional
                else None
            ),
            "sample_size_warning": trade_count < min_trade_count,
            "evidence_label": "TOO_EARLY",
        }
        row["evidence_label"] = _bucket_evidence_label(row)
        rows.append(row)
    return _frame(rows, _backtest_schema())


def build_score_ablation(
    *,
    price_frames: dict[str, pl.DataFrame],
    contexts: dict[str, dict[str, dict[str, Any]]],
    components: pl.DataFrame,
    baseline_backtest: pl.DataFrame,
) -> pl.DataFrame:
    """Remove one component at a time and compare bucket ordering."""

    baseline_monotonicity = _score_monotonicity_value(baseline_backtest)
    baseline_expectancy = _high_minus_low_expectancy(baseline_backtest)
    baseline_false_block = _false_block_rate(baseline_backtest)
    rows: list[dict[str, Any]] = []
    for ablation_name in ABLATION_COMPONENTS:
        disabled = _disabled_components_for_ablation(ablation_name)
        scored = build_trade_quality_scores(
            price_frames=price_frames,
            contexts=contexts,
            components=components,
            disabled_components=disabled,
        )
        ablated = build_score_bucket_backtest(scored.evaluation_rows)
        monotonicity_change = _score_monotonicity_value(ablated) - baseline_monotonicity
        expectancy_change = _high_minus_low_expectancy(ablated) - baseline_expectancy
        false_block_change = _false_block_rate(ablated) - baseline_false_block
        rows.append(
            {
                "ablation": ablation_name,
                "event_count": len(scored.evaluation_rows),
                "score_monotonicity_change": monotonicity_change,
                "expectancy_change": expectancy_change,
                "false_block_change": false_block_change,
                "interpretation": _ablation_interpretation(
                    ablation_name,
                    monotonicity_change=monotonicity_change,
                    expectancy_change=expectancy_change,
                    false_block_change=false_block_change,
                ),
            }
        )
    return _frame(rows, _ablation_schema())


def high_score_outperformed_low_score(backtest: pl.DataFrame) -> bool:
    """Return whether high-score buckets beat low-score buckets on average return."""

    return _high_expectancy(backtest) > _low_expectancy(backtest)


def strongest_positive_component(evaluation_rows: list[dict[str, Any]]) -> str:
    """Return the positive component with the largest average active contribution."""

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in evaluation_rows:
        for item in str(row.get("active_positive_components") or "").split(";"):
            name = item.strip()
            if not name:
                continue
            totals[name] = totals.get(name, 0.0) + max(0.0, float(COMPONENT_DELTAS.get(name, 0.0)))
            counts[name] = counts.get(name, 0) + 1
    if not totals:
        return "none"
    return max(totals, key=lambda name: (totals[name] / max(counts.get(name, 1), 1), counts.get(name, 0)))


def strongest_negative_component(evaluation_rows: list[dict[str, Any]]) -> str:
    """Return the negative component with the largest active blocking contribution."""

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in evaluation_rows:
        for item in str(row.get("active_negative_components") or "").split(";"):
            name = item.strip()
            if not name:
                continue
            totals[name] = totals.get(name, 0.0) + abs(float(COMPONENT_DELTAS.get(name, 0.0)))
            counts[name] = counts.get(name, 0) + 1
    if not totals:
        return "none"
    return max(totals, key=lambda name: (totals[name] / max(counts.get(name, 1), 1), counts.get(name, 0)))


def choose_final_recommendation(
    *,
    components: pl.DataFrame,
    backtest: pl.DataFrame,
    high_score_outperformed: bool,
) -> str:
    """Choose a conservative score-level recommendation."""

    if components.is_empty() or backtest.is_empty():
        return "NEEDS_MORE_FORWARD_DATA"
    price_components = components.filter(
        pl.col("component_name").is_in(
            [
                "acceptance_breakout_component",
                "no_trade_middle_range_component",
                "open_distance_component",
                "fee_spread_hurdle_component",
                "data_quality_component",
            ]
        )
        & pl.col("data_available")
    )
    total_trades = int(backtest.get_column("trade_count").sum()) if "trade_count" in backtest.columns else 0
    if price_components.height < 3 or total_trades < MIN_BUCKET_TRADES:
        return "NEEDS_MORE_FORWARD_DATA"
    if not high_score_outperformed:
        return "USE_AS_WATCHLIST_FILTER_ONLY"
    pilot_rows = components.filter(pl.col("confidence").is_in(["PILOT_ONLY", "MISSING_DATA"]))
    if pilot_rows.height:
        return "USE_AS_WATCHLIST_FILTER_ONLY"
    return "SCORE_PROMISING_BUT_UNVALIDATED"


def write_xau_trade_quality_score_outputs(result: XauTradeQualityScoreResult) -> None:
    """Write CSV and Markdown artifacts for the trade-quality score lab."""

    result.components.write_csv(result.paths["components_csv"])
    result.scores.write_csv(result.paths["score_csv"])
    result.backtest.write_csv(result.paths["backtest_csv"])
    result.ablation.write_csv(result.paths["ablation_csv"])
    result.paths["components_md"].write_text(
        _safe_report_text(_components_markdown(result)),
        encoding="utf-8",
    )
    result.paths["score_md"].write_text(
        _safe_report_text(_score_markdown(result)),
        encoding="utf-8",
    )
    result.paths["backtest_md"].write_text(
        _safe_report_text(_backtest_markdown(result)),
        encoding="utf-8",
    )
    result.paths["ablation_md"].write_text(
        _safe_report_text(_ablation_markdown(result)),
        encoding="utf-8",
    )
    result.paths["forward_usage_md"].write_text(
        _safe_report_text(_forward_usage_markdown(result)),
        encoding="utf-8",
    )


def xau_trade_quality_report_lines(result: XauTradeQualityScoreResult | None) -> list[str]:
    """Return research_report.md lines for the score lab."""

    if result is None:
        return [
            "## XAU Trade Quality Score",
            "",
            "XAU Trade Quality Score lab was not run.",
        ]
    return [
        "## XAU Trade Quality Score",
        "",
        RESEARCH_WARNING,
        "",
        f"Final recommendation: `{result.final_recommendation}`.",
        "Money-readiness guardrail: `NOT_READY_FOR_MONEY`.",
        f"High-score outperformed low-score: `{result.high_score_outperformed_low_score}`.",
        f"Strongest positive component: `{result.strongest_positive_component}`.",
        f"Strongest negative/blocking component: `{result.strongest_negative_component}`.",
        "",
        "## Score Components",
        "",
        _frame_markdown(result.components),
        "",
        "## Score Bucket Backtest",
        "",
        _frame_markdown(result.backtest),
        "",
        "## Score Ablation",
        "",
        _frame_markdown(result.ablation),
        "",
        "## Forward Usage Guide",
        "",
        "- Use the score as watchlist support for research candidates only.",
        "- Block a research candidate when no-trade range, open-distance, spread/fee, data-quality, or stale-data components are active.",
        "- Use watch-only status when CME or guru context is present but price confirmation or coverage remains incomplete.",
        "- Check price coverage, spread, CME pilot status, guru timing, and data staleness before interpreting a row.",
        "- The score is not a trade recommendation and does not establish money readiness.",
        "",
        "## What This Can Improve",
        "",
        "- Keeps acceptance-breakout candidates separate from avoid/filter rows.",
        "- Makes spread and stale-data hurdles visible before research interpretation.",
        "- Keeps CME wall and guru context in pilot/context roles instead of standalone triggers.",
        "",
        "## What Is Still Not Proven",
        "",
        "- CME OI/IV overlap evidence remains pilot-only.",
        "- Guru context still requires timing and same-day evidence before stronger use.",
        "- Bucket ordering must survive fresh forward data before it can change governance.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when report text avoids forbidden claim/instruction phrases."""

    lowered = f" {text.lower()} "
    return not any(phrase in lowered for phrase in FORBIDDEN_REPORT_PHRASES)


def _score_price_row(
    row: dict[str, Any],
    *,
    previous_rows: list[dict[str, Any]],
    previous_row: dict[str, Any] | None,
    future_rows: list[dict[str, Any]],
    timeframe: str,
    expected_gap: timedelta,
    contexts: dict[str, dict[str, dict[str, Any]]],
    disabled_components: frozenset[str],
    enabled_components: dict[str, bool],
) -> dict[str, Any]:
    timestamp = row.get("timestamp")
    trade_date = _trade_date(row, timestamp)
    close = _float_or_none(row.get("close"))
    open_value = _float_or_none(row.get("open"))
    high = _float_or_none(row.get("high"))
    low = _float_or_none(row.get("low"))
    spread = _float_or_none(row.get("spread_points") or row.get("spread_close"))
    quality = _text(row.get("quality") or "GOOD").upper()
    current_range = (high - low) if high is not None and low is not None else None
    prior_high = _max_value(previous_rows, "high")
    prior_low = _min_value(previous_rows, "low")
    prior_close = _float_or_none(previous_row.get("close")) if previous_row else None
    avg_range = _average([
        value
        for value in (
            (_float_or_none(item.get("high")) or 0.0) - (_float_or_none(item.get("low")) or 0.0)
            for item in previous_rows
        )
        if value > 0
    ])
    spread_p95 = _quantile([
        value
        for value in (_float_or_none(item.get("spread_points") or item.get("spread_close")) for item in previous_rows)
        if value is not None
    ], 0.95)
    range_position = _range_position(close, prior_low, prior_high)
    component_deltas: dict[str, int] = {}
    blocked_reasons: list[str] = []
    watch_reasons: list[str] = []
    notes: list[str] = []
    candidate_direction = "NONE"
    base_source = "PRICE_ONLY"

    data_good = (
        close is not None
        and open_value is not None
        and high is not None
        and low is not None
        and high >= low
        and quality not in {"BAD", "MISSING", "INVALID", "STALE"}
    )
    if _component_enabled("data_quality_component", disabled_components, enabled_components):
        if data_good:
            component_deltas["data_quality_component"] = COMPONENT_DELTAS["data_quality_component"]
        else:
            component_deltas["data_quality_component"] = -60
            blocked_reasons.append("DATA_QUALITY")
            notes.append("Price row failed the data-quality gate.")

    if _component_enabled("stale_data_component", disabled_components, enabled_components):
        stale = _is_stale(row, previous_row, expected_gap)
        if stale:
            component_deltas["stale_data_component"] = COMPONENT_DELTAS["stale_data_component"]
            blocked_reasons.append("STALE_DATA")
            notes.append("Timestamp gap exceeded the timeframe tolerance.")

    acceptance_direction = _acceptance_direction(
        close=close,
        prior_close=prior_close,
        prior_high=prior_high,
        prior_low=prior_low,
    )
    if (
        acceptance_direction != "NONE"
        and _component_enabled("acceptance_breakout_component", disabled_components, enabled_components)
    ):
        component_deltas["acceptance_breakout_component"] = COMPONENT_DELTAS["acceptance_breakout_component"]
        candidate_direction = acceptance_direction
        watch_reasons.append("ACCEPTANCE_BREAKOUT")

    rejection_direction = _rejection_direction(
        high=high,
        low=low,
        close=close,
        prior_high=prior_high,
        prior_low=prior_low,
    )
    if (
        candidate_direction == "NONE"
        and rejection_direction != "NONE"
        and _component_enabled("rejection_after_touch_component", disabled_components, enabled_components)
    ):
        component_deltas["rejection_after_touch_component"] = COMPONENT_DELTAS["rejection_after_touch_component"]
        candidate_direction = rejection_direction
        watch_reasons.append("REJECTION_AFTER_TOUCH")

    if (
        range_position is not None
        and 0.35 <= range_position <= 0.65
        and _component_enabled("no_trade_middle_range_component", disabled_components, enabled_components)
    ):
        component_deltas["no_trade_middle_range_component"] = COMPONENT_DELTAS["no_trade_middle_range_component"]
        blocked_reasons.append("NO_TRADE_MIDDLE_RANGE")

    open_distance_active = (
        close is not None
        and open_value is not None
        and avg_range is not None
        and avg_range > 0
        and abs(close - open_value) > avg_range
    )
    if open_distance_active and _component_enabled("open_distance_component", disabled_components, enabled_components):
        component_deltas["open_distance_component"] = COMPONENT_DELTAS["open_distance_component"]
        blocked_reasons.append("OPEN_DISTANCE")

    spread_failed = _spread_hurdle_failed(spread=spread, spread_p95=spread_p95, current_range=current_range)
    if spread_failed and _component_enabled("fee_spread_hurdle_component", disabled_components, enabled_components):
        component_deltas["fee_spread_hurdle_component"] = COMPONENT_DELTAS["fee_spread_hurdle_component"]
        blocked_reasons.append("SPREAD_FEE")
    elif spread is None:
        notes.append("Spread data missing for the fee/spread hurdle.")

    cme_delta, cme_reasons = _cme_context_delta(
        trade_date,
        contexts=contexts,
        disabled_components=disabled_components,
        enabled_components=enabled_components,
    )
    component_deltas.update(cme_delta)
    watch_reasons.extend(cme_reasons)
    if cme_reasons:
        base_source = "CME_MARKET_MAP" if candidate_direction == "NONE" else base_source

    guru_delta, guru_reasons, guru_blocks = _guru_context_delta(
        trade_date,
        contexts=contexts,
        disabled_components=disabled_components,
        enabled_components=enabled_components,
    )
    component_deltas.update(guru_delta)
    watch_reasons.extend(guru_reasons)
    blocked_reasons.extend(guru_blocks)
    if guru_reasons and candidate_direction == "NONE" and base_source == "PRICE_ONLY":
        base_source = "GURU_CONTEXT"

    if candidate_direction == "NONE" and base_source in {"CME_MARKET_MAP", "GURU_CONTEXT"}:
        # Context-only rows cannot become directional candidates by themselves.
        pass
    elif candidate_direction == "NONE":
        base_source = "PRICE_ONLY"

    score = int(max(0, min(100, 45 + sum(component_deltas.values()))))
    bucket = _score_bucket(score, blocked_reasons=blocked_reasons)
    label = _final_label(
        bucket=bucket,
        blocked_reasons=blocked_reasons,
        watch_reasons=watch_reasons,
        candidate_direction=candidate_direction,
        data_good=data_good,
    )
    if label == "INSUFFICIENT_DATA" and data_good and bucket in {"ALLOW_RESEARCH", "HIGH_QUALITY_RESEARCH"}:
        label = "ALLOW_RESEARCH_CANDIDATE"
    active_positive = [name for name, delta in component_deltas.items() if delta > 0]
    active_negative = [name for name, delta in component_deltas.items() if delta < 0]
    future = _future_outcome(
        row,
        future_rows=future_rows,
        direction=candidate_direction,
        spread=spread,
    )
    return {
        "timestamp": timestamp,
        "timeframe": timeframe,
        "candidate_direction": candidate_direction,
        "base_candidate_source": base_source,
        "trade_quality_score": score,
        "score_bucket": bucket,
        "active_positive_components": ";".join(active_positive),
        "active_negative_components": ";".join(active_negative),
        "blocked_reasons": ";".join(dict.fromkeys(blocked_reasons)),
        "watch_reasons": ";".join(dict.fromkeys(watch_reasons)),
        "data_quality_notes": ";".join(dict.fromkeys(notes)),
        "final_label": label,
        "_close": close,
        "_forward_return": future["forward_return"],
        "_mfe": future["mfe"],
        "_mae": future["mae"],
    }


def _future_outcome(
    row: dict[str, Any],
    *,
    future_rows: list[dict[str, Any]],
    direction: str,
    spread: float | None,
) -> dict[str, float | None]:
    close = _float_or_none(row.get("close"))
    if close is None or direction not in {"LONG", "SHORT"} or not future_rows:
        return {"forward_return": None, "mfe": None, "mae": None}
    final_close = _float_or_none(future_rows[-1].get("close"))
    highs = [_float_or_none(item.get("high")) for item in future_rows]
    lows = [_float_or_none(item.get("low")) for item in future_rows]
    highs = [value for value in highs if value is not None]
    lows = [value for value in lows if value is not None]
    if final_close is None or not highs or not lows:
        return {"forward_return": None, "mfe": None, "mae": None}
    cost = float(spread or 0.0)
    if direction == "LONG":
        forward_return = final_close - close - cost
        mfe = max(highs) - close
        mae = min(lows) - close
    else:
        forward_return = close - final_close - cost
        mfe = close - min(lows)
        mae = close - max(highs)
    return {"forward_return": forward_return, "mfe": mfe, "mae": mae}


def _acceptance_direction(
    *,
    close: float | None,
    prior_close: float | None,
    prior_high: float | None,
    prior_low: float | None,
) -> str:
    if close is None or prior_close is None:
        return "NONE"
    if prior_high is not None and prior_close <= prior_high and close > prior_high:
        return "LONG"
    if prior_low is not None and prior_close >= prior_low and close < prior_low:
        return "SHORT"
    return "NONE"


def _rejection_direction(
    *,
    high: float | None,
    low: float | None,
    close: float | None,
    prior_high: float | None,
    prior_low: float | None,
) -> str:
    if close is None:
        return "NONE"
    if high is not None and prior_high is not None and high >= prior_high and close < prior_high:
        return "SHORT"
    if low is not None and prior_low is not None and low <= prior_low and close > prior_low:
        return "LONG"
    return "NONE"


def _cme_context_delta(
    trade_date: str,
    *,
    contexts: dict[str, dict[str, dict[str, Any]]],
    disabled_components: frozenset[str],
    enabled_components: dict[str, bool],
) -> tuple[dict[str, int], list[str]]:
    deltas: dict[str, int] = {}
    reasons: list[str] = []
    week = contexts.get("current_week", {}).get(trade_date, {})
    market = contexts.get("same_day_market_map", {}).get(trade_date, {})
    if _component_enabled("cme_wall_context_component", disabled_components, enabled_components):
        has_wall = any(
            (
                _bool(week.get("oi_available")),
                _bool(market.get("cme_oi_walls_available")),
                _bool(market.get("spot_equivalent_walls_available")),
                _text(week.get("top_oi_wall_1")) != "",
                _text(market.get("top_wall_above")) != "",
                _text(market.get("top_wall_below")) != "",
            )
        )
        accepted = _bool(week.get("accepted_wall")) or _bool(market.get("price_accepted_wall"))
        rejected = _bool(week.get("rejected_wall")) or _bool(market.get("price_rejected_wall"))
        touched = _bool(week.get("touched_wall")) or _bool(market.get("price_touched_wall"))
        if has_wall and (accepted or rejected):
            deltas["cme_wall_context_component"] = COMPONENT_DELTAS["cme_wall_context_component"]
            reasons.append("CME_WALL_CONTEXT")
        elif has_wall and touched:
            deltas["cme_wall_context_component"] = 4
            reasons.append("CME_WALL_WATCH")
    if _component_enabled("cme_iv_range_component", disabled_components, enabled_components):
        if _bool(week.get("iv_available")) or _text(week.get("iv_near_wall")):
            deltas["cme_iv_range_component"] = COMPONENT_DELTAS["cme_iv_range_component"]
            reasons.append("CME_IV_CONTEXT")
    return deltas, reasons


def _guru_context_delta(
    trade_date: str,
    *,
    contexts: dict[str, dict[str, dict[str, Any]]],
    disabled_components: frozenset[str],
    enabled_components: dict[str, bool],
) -> tuple[dict[str, int], list[str], list[str]]:
    if not _component_enabled("guru_filter_component", disabled_components, enabled_components):
        return {}, [], []
    week = contexts.get("current_week", {}).get(trade_date, {})
    same_day = contexts.get("same_day_filter", {}).get(trade_date, {})
    deltas: dict[str, int] = {}
    reasons: list[str] = []
    blocks: list[str] = []
    filter_active = _bool(week.get("no_trade_filter_active")) or _bool(same_day.get("no_trade_filter_active"))
    if filter_active:
        deltas["guru_filter_component"] = COMPONENT_DELTAS["guru_filter_component"]
        blocks.append("GURU_FILTER_CONTEXT")
    elif _bool(week.get("guru_context_available")) or _int(same_day.get("same_day_filter_matches")) > 0:
        deltas["guru_filter_component"] = 3
        reasons.append("GURU_CONTEXT")
    return deltas, reasons, blocks


def _score_bucket(score: int, *, blocked_reasons: list[str]) -> str:
    hard_blocks = {"NO_TRADE_MIDDLE_RANGE", "OPEN_DISTANCE", "SPREAD_FEE", "DATA_QUALITY", "STALE_DATA"}
    if hard_blocks.intersection(blocked_reasons):
        return "BLOCK"
    if score <= 35:
        return "BLOCK"
    if score < 60:
        return "WATCH_ONLY"
    if score < 80:
        return "ALLOW_RESEARCH"
    return "HIGH_QUALITY_RESEARCH"


def _final_label(
    *,
    bucket: str,
    blocked_reasons: list[str],
    watch_reasons: list[str],
    candidate_direction: str,
    data_good: bool,
) -> str:
    if not data_good:
        return "INSUFFICIENT_DATA"
    if "NO_TRADE_MIDDLE_RANGE" in blocked_reasons:
        return "BLOCKED_NO_TRADE_RANGE"
    if "OPEN_DISTANCE" in blocked_reasons:
        return "BLOCKED_OPEN_DISTANCE"
    if "SPREAD_FEE" in blocked_reasons:
        return "BLOCKED_SPREAD_FEE"
    if bucket in {"ALLOW_RESEARCH", "HIGH_QUALITY_RESEARCH"} and candidate_direction != "NONE":
        return "ALLOW_RESEARCH_CANDIDATE"
    if "ACCEPTANCE_BREAKOUT" in watch_reasons:
        return "WATCH_ACCEPTANCE_BREAKOUT"
    if any(reason.startswith("CME_WALL") for reason in watch_reasons):
        return "WATCH_CME_WALL"
    if "GURU_CONTEXT" in watch_reasons or "GURU_FILTER_CONTEXT" in blocked_reasons:
        return "WATCH_GURU_CONTEXT"
    if bucket == "BLOCK":
        return "INSUFFICIENT_DATA"
    return "INSUFFICIENT_DATA"


def _bucket_evidence_label(row: dict[str, Any]) -> str:
    trade_count = int(row.get("trade_count") or 0)
    avg = _float_or_none(row.get("average_return"))
    if trade_count < MIN_BUCKET_TRADES:
        return "TOO_EARLY"
    if _text(row.get("score_bucket")) == "BLOCK":
        helped = _float_or_none(row.get("filter_helped_rate")) or 0.0
        false_block = _float_or_none(row.get("false_block_rate")) or 0.0
        return "FILTER_CANDIDATE" if helped >= false_block else "SCORE_WEAK"
    if avg is not None and avg > 0:
        return "SCORE_PROMISING"
    if avg is not None and avg <= 0:
        return "SCORE_WEAK"
    return "NEEDS_MORE_FORWARD_DATA"


def _ablation_interpretation(
    ablation_name: str,
    *,
    monotonicity_change: float,
    expectancy_change: float,
    false_block_change: float,
) -> str:
    if expectancy_change < 0 or monotonicity_change < 0:
        return f"{ablation_name} weakens score ordering in this replay."
    if false_block_change > 0:
        return f"{ablation_name} increases false-block risk in this replay."
    if expectancy_change > 0:
        return f"{ablation_name} improves this replay, so the component needs more forward review."
    return f"{ablation_name} is neutral in this replay."


def _components_markdown(result: XauTradeQualityScoreResult) -> str:
    return "\n\n".join(
        [
            "# XAU Trade Quality Score Components",
            RESEARCH_WARNING,
            _frame_markdown(result.components),
            "All score deltas are transparent fixed research weights. They are not tuned on the full sample.",
        ]
    )


def _score_markdown(result: XauTradeQualityScoreResult) -> str:
    preview = result.scores.head(25) if not result.scores.is_empty() else result.scores
    return "\n\n".join(
        [
            "# XAU Trade Quality Score",
            RESEARCH_WARNING,
            f"Final recommendation: `{result.final_recommendation}`.",
            "Money-readiness guardrail: `NOT_READY_FOR_MONEY`.",
            f"High-score outperformed low-score: `{result.high_score_outperformed_low_score}`.",
            f"Strongest positive component: `{result.strongest_positive_component}`.",
            f"Strongest negative/blocking component: `{result.strongest_negative_component}`.",
            _frame_markdown(preview),
        ]
    )


def _backtest_markdown(result: XauTradeQualityScoreResult) -> str:
    comparison = (
        "High-score buckets outperformed low-score buckets in this replay."
        if result.high_score_outperformed_low_score
        else "High-score buckets did not outperform low-score buckets in this replay; the score is not useful yet as an evidence claim."
    )
    return "\n\n".join(
        [
            "# XAU Trade Quality Score Bucket Backtest",
            RESEARCH_WARNING,
            comparison,
            _frame_markdown(result.backtest),
            "Bucket evaluation uses later price movement only after the score row is frozen.",
        ]
    )


def _ablation_markdown(result: XauTradeQualityScoreResult) -> str:
    return "\n\n".join(
        [
            "# XAU Trade Quality Score Ablation",
            RESEARCH_WARNING,
            _frame_markdown(result.ablation),
            "Ablation rows remove one component at a time and compare bucket ordering against the baseline score.",
        ]
    )


def _forward_usage_markdown(result: XauTradeQualityScoreResult) -> str:
    return "\n".join(
        [
            "# XAU Trade Quality Forward Usage Guide",
            "",
            RESEARCH_WARNING,
            "",
            f"Final recommendation: `{result.final_recommendation}`.",
            "Money-readiness guardrail: `NOT_READY_FOR_MONEY`.",
            "",
            "## How To Use The Score As Watchlist Support",
            "",
            "Use the score to sort research candidates into block, watch-only, and allowed-for-research buckets. Treat every row as a local research artifact, not as an execution instruction.",
            "",
            "## When To Block A Research Candidate",
            "",
            "- Block when the no-trade middle-range component is active.",
            "- Block when open-distance/chase risk is active.",
            "- Block when the fee/spread hurdle fails.",
            "- Block when data quality fails or the price row is stale.",
            "",
            "## When To Only Watch",
            "",
            "- Watch when acceptance breakout is present but other context is incomplete.",
            "- Watch when CME wall or IV context is pilot-only.",
            "- Watch when guru context is present without timing and same-day confirmation.",
            "",
            "## Data Checks Required",
            "",
            "- Dukascopy OHLC, bid/ask spread, and timeframe coverage.",
            "- CME OI wall, IV, futures, basis, and as-of availability when used.",
            "- Guru timing metadata and same-day filter evidence.",
            "- Freshness and data-quality notes for the scored row.",
            "",
            "## Why This Is Not A Trade Recommendation",
            "",
            "The score does not choose position size, does not connect to a broker, does not create live or paper state, and does not prove a money-ready edge.",
            "",
            "## Evidence Still Needed",
            "",
            "- More CME-overlap dates with OI/IV coverage.",
            "- More forward events after the score is frozen.",
            "- Walk-forward checks showing high-score buckets beat low-score buckets on fresh data.",
            "- Component ablations that remain stable outside the formation sample.",
        ]
    )


def _safe_report_text(text: str) -> str:
    safe = text
    for phrase in FORBIDDEN_REPORT_PHRASES:
        replacement = f" [blocked phrase: {phrase.strip()}] "
        safe = safe.replace(phrase, replacement)
        safe = safe.replace(phrase.upper(), replacement)
    return safe


def _load_inputs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "price_rule_interpretation": _read_csv(paths["price_rule_interpretation"]),
        "price_only_backtest": _read_csv(paths["price_only_backtest"]),
        "rule_backtest_by_timeframe": _read_csv(paths["rule_backtest_by_timeframe"]),
        "guru_logic_interpretation": _read_csv(paths["guru_logic_interpretation"]),
        "cme_overlap_interpretation": _read_csv(paths["cme_overlap_interpretation"]),
        "forward_governance": _read_csv(paths["forward_governance"]),
        "forward_scorecard": _read_csv(paths["forward_scorecard"]),
        "decision_dashboard": _read_csv(paths["decision_dashboard"]),
        "current_week": _read_csv(paths["current_week"]),
        "same_day_filter": _read_csv(paths["same_day_filter"]),
        "same_day_market_map": _read_csv(paths["same_day_market_map"]),
        "price_frames": {
            timeframe: _read_parquet(paths[f"price_{timeframe}"])
            for timeframe in ("15m", "1h", "4h", "1d")
        },
    }


def _build_contexts(
    *,
    current_week: pl.DataFrame,
    same_day_filter: pl.DataFrame,
    same_day_market_map: pl.DataFrame,
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "current_week": _rows_by_date(current_week, "trade_date"),
        "same_day_filter": _rows_by_date(same_day_filter, "resolved_market_session_date"),
        "same_day_market_map": _rows_by_date(same_day_market_map, "resolved_market_session_date"),
    }


def _rows_by_date(frame: pl.DataFrame, column: str) -> dict[str, dict[str, Any]]:
    if frame.is_empty() or column not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in frame.to_dicts():
        date = _text(row.get(column))
        if date:
            rows[date[:10]] = row
    return rows


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "price_rule_interpretation": output_root / "dukascopy_price_rule_interpretation.csv",
        "price_only_backtest": output_root / "dukascopy_price_only_rule_backtest.csv",
        "rule_backtest_by_timeframe": output_root / "dukascopy_rule_backtest_by_timeframe.csv",
        "guru_logic_interpretation": output_root / "dukascopy_guru_logic_interpretation.csv",
        "cme_overlap_interpretation": output_root / "dukascopy_cme_overlap_interpretation.csv",
        "forward_governance": output_root / "dukascopy_forward_rule_governance.csv",
        "forward_scorecard": output_root / "dukascopy_forward_event_scorecard.csv",
        "decision_dashboard": output_root / "xau_decision_support_dashboard.csv",
        "current_week": output_root / "current_week_cme_guru_replay.csv",
        "same_day_filter": output_root / "same_day_filter_evidence_after_metadata.csv",
        "same_day_market_map": output_root / "same_day_market_map_evidence_after_metadata.csv",
        "frozen_rulebook": output_root / "frozen_rulebook_v1.yaml",
        "price_15m": output_root / "dukascopy_xau_15m.parquet",
        "price_1h": output_root / "dukascopy_xau_1h.parquet",
        "price_4h": output_root / "dukascopy_xau_4h.parquet",
        "price_1d": output_root / "dukascopy_xau_1d.parquet",
        "components_csv": output_root / "xau_trade_quality_score_components.csv",
        "components_md": output_root / "xau_trade_quality_score_components.md",
        "score_csv": output_root / "xau_trade_quality_score.csv",
        "score_md": output_root / "xau_trade_quality_score.md",
        "backtest_csv": output_root / "xau_trade_quality_score_backtest.csv",
        "backtest_md": output_root / "xau_trade_quality_score_backtest.md",
        "ablation_csv": output_root / "xau_trade_quality_score_ablation.csv",
        "ablation_md": output_root / "xau_trade_quality_score_ablation.md",
        "forward_usage_md": output_root / "xau_trade_quality_forward_usage.md",
    }


def _component_row(
    component_name: str,
    *,
    data_available: bool,
    confidence: str,
    condition: str,
    reason: str,
    required_data: str,
) -> dict[str, Any]:
    if confidence not in {"HIGH", "MEDIUM", "LOW", "PILOT_ONLY", "MISSING_DATA"}:
        confidence = "LOW"
    if not data_available and confidence != "PILOT_ONLY":
        confidence = "MISSING_DATA"
    return {
        "component_name": component_name,
        "score_delta": COMPONENT_DELTAS[component_name],
        "condition": condition,
        "reason": reason,
        "required_data": required_data,
        "data_available": data_available,
        "confidence": confidence,
    }


def _enabled_component_lookup(components: pl.DataFrame) -> dict[str, bool]:
    if components.is_empty():
        return {name: True for name in COMPONENT_ORDER}
    return {
        _text(row.get("component_name")): _bool(row.get("data_available"))
        or _text(row.get("confidence")) == "PILOT_ONLY"
        for row in components.to_dicts()
    }


def _component_enabled(
    component_name: str,
    disabled_components: frozenset[str],
    enabled_components: dict[str, bool],
) -> bool:
    return component_name not in disabled_components and enabled_components.get(component_name, True)


def _disabled_components_for_ablation(ablation_name: str) -> frozenset[str]:
    mapping = {
        "without_acceptance_breakout": {"acceptance_breakout_component"},
        "without_no_trade_middle_range": {"no_trade_middle_range_component"},
        "without_open_distance": {"open_distance_component"},
        "without_fee_spread_hurdle": {"fee_spread_hurdle_component"},
        "without_cme_wall": {"cme_wall_context_component", "cme_iv_range_component"},
        "without_guru_filter": {"guru_filter_component"},
        "without_data_quality": {"data_quality_component"},
    }
    return frozenset(mapping.get(ablation_name, set()))


def _has_rule(frame: pl.DataFrame, rule: str) -> bool:
    return not _rule_row(frame, rule) == {}


def _rule_confidence(frame: pl.DataFrame, rule: str, *, default: str) -> str:
    row = _rule_row(frame, rule)
    if not row:
        return default
    strength = _text(row.get("evidence_strength")).upper()
    if strength == "PROMISING":
        return "HIGH"
    if strength == "MIXED":
        return "MEDIUM"
    if strength in {"WEAK", "TOO_EARLY"}:
        return "LOW"
    return "MEDIUM"


def _rule_row(frame: pl.DataFrame, rule: str) -> dict[str, Any]:
    if frame.is_empty() or "rule" not in frame.columns:
        return {}
    filtered = frame.filter(pl.col("rule") == rule)
    return filtered.row(0, named=True) if not filtered.is_empty() else {}


def _cme_confidence(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "MISSING_DATA"
    enough = _any_bool_column(frame, "enough_for_validation")
    return "MEDIUM" if enough else "PILOT_ONLY"


def _guru_confidence(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "MISSING_DATA"
    context_only = _any_bool_column(frame, "remain_context_only")
    needs_timing = _any_bool_column(frame, "requires_timing_metadata")
    if context_only or needs_timing:
        return "LOW"
    return "MEDIUM"


def _spread_available(price_frames: dict[str, pl.DataFrame]) -> bool:
    return any(
        not frame.is_empty()
        and ("spread_points" in frame.columns or "spread_close" in frame.columns)
        for frame in price_frames.values()
    )


def _any_bool_column(frame: pl.DataFrame, column: str) -> bool:
    return (
        not frame.is_empty()
        and column in frame.columns
        and any(_bool(value) for value in frame.get_column(column).to_list())
    )


def _normalize_price_frame(frame: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame(schema=_normalized_price_schema())
    result = frame
    if "timestamp" not in result.columns:
        return pl.DataFrame(schema=_normalized_price_schema())
    for column in ("open", "high", "low", "close"):
        if column not in result.columns:
            mid_column = f"mid_{column}"
            if mid_column in result.columns:
                result = result.with_columns(pl.col(mid_column).alias(column))
            else:
                return pl.DataFrame(schema=_normalized_price_schema())
    if "trade_date" not in result.columns:
        result = result.with_columns(pl.col("timestamp").dt.date().cast(pl.String).alias("trade_date"))
    if "timeframe" not in result.columns:
        result = result.with_columns(pl.lit(timeframe).alias("timeframe"))
    if "quality" not in result.columns:
        result = result.with_columns(pl.lit("GOOD").alias("quality"))
    for optional in ("spread_points", "spread_close"):
        if optional not in result.columns:
            result = result.with_columns(pl.lit(None).cast(pl.Float64).alias(optional))
    return result.select(list(_normalized_price_schema()))


def _normalized_price_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "trade_date": pl.String,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "spread_points": pl.Float64,
        "spread_close": pl.Float64,
        "quality": pl.String,
        "timeframe": pl.String,
    }


def _trade_date(row: dict[str, Any], timestamp: Any) -> str:
    date = _text(row.get("trade_date"))
    if date:
        return date[:10]
    if isinstance(timestamp, datetime):
        return timestamp.date().isoformat()
    text = _text(timestamp)
    return text[:10] if text else ""


def _range_position(close: float | None, low: float | None, high: float | None) -> float | None:
    if close is None or low is None or high is None or high <= low:
        return None
    return (close - low) / (high - low)


def _spread_hurdle_failed(
    *,
    spread: float | None,
    spread_p95: float | None,
    current_range: float | None,
) -> bool:
    if spread is None:
        return False
    if spread_p95 is not None and spread_p95 > 0 and spread > spread_p95:
        return True
    return current_range is not None and current_range > 0 and spread > current_range * 0.25


def _is_stale(
    row: dict[str, Any],
    previous_row: dict[str, Any] | None,
    expected_gap: timedelta,
) -> bool:
    timestamp = row.get("timestamp")
    previous_timestamp = previous_row.get("timestamp") if previous_row else None
    if not isinstance(timestamp, datetime) or not isinstance(previous_timestamp, datetime):
        return False
    return timestamp - previous_timestamp > expected_gap * 3


def _score_monotonicity_value(backtest: pl.DataFrame) -> float:
    return _high_expectancy(backtest) - _low_expectancy(backtest)


def _high_minus_low_expectancy(backtest: pl.DataFrame) -> float:
    return _high_expectancy(backtest) - _low_expectancy(backtest)


def _high_expectancy(backtest: pl.DataFrame) -> float:
    if backtest.is_empty():
        return 0.0
    rows = backtest.filter(pl.col("score_bucket").is_in(["ALLOW_RESEARCH", "HIGH_QUALITY_RESEARCH"]))
    return _weighted_average(rows, "expectancy_proxy", "trade_count")


def _low_expectancy(backtest: pl.DataFrame) -> float:
    if backtest.is_empty():
        return 0.0
    rows = backtest.filter(pl.col("score_bucket").is_in(["BLOCK", "WATCH_ONLY"]))
    return _weighted_average(rows, "expectancy_proxy", "trade_count")


def _false_block_rate(backtest: pl.DataFrame) -> float:
    if backtest.is_empty():
        return 0.0
    blocked = backtest.filter(pl.col("score_bucket") == "BLOCK")
    if blocked.is_empty():
        return 0.0
    value = blocked.row(0, named=True).get("false_block_rate")
    return _float_or_none(value) or 0.0


def _weighted_average(frame: pl.DataFrame, value_col: str, weight_col: str) -> float:
    if frame.is_empty() or value_col not in frame.columns or weight_col not in frame.columns:
        return 0.0
    numerator = 0.0
    denominator = 0.0
    for row in frame.to_dicts():
        value = _float_or_none(row.get(value_col))
        weight = _float_or_none(row.get(weight_col)) or 0.0
        if value is not None and weight > 0:
            numerator += value * weight
            denominator += weight
    return numerator / denominator if denominator else 0.0


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001 - missing/corrupt optional inputs degrade to missing data.
        return pl.DataFrame()


def _read_parquet(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_parquet(path)
    except Exception:  # noqa: BLE001 - missing/corrupt optional inputs degrade to missing data.
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


def _max_value(rows: Iterable[dict[str, Any]], column: str) -> float | None:
    values = [_float_or_none(row.get(column)) for row in rows]
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def _min_value(rows: Iterable[dict[str, Any]], column: str) -> float | None:
    values = [_float_or_none(row.get(column)) for row in rows]
    clean = [value for value in values if value is not None]
    return min(clean) if clean else None


def _average(values: Iterable[float]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _components_schema() -> dict[str, Any]:
    return {
        "component_name": pl.String,
        "score_delta": pl.Int64,
        "condition": pl.String,
        "reason": pl.String,
        "required_data": pl.String,
        "data_available": pl.Boolean,
        "confidence": pl.String,
    }


def _score_schema() -> dict[str, Any]:
    return {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "timeframe": pl.String,
        "candidate_direction": pl.String,
        "base_candidate_source": pl.String,
        "trade_quality_score": pl.Int64,
        "score_bucket": pl.String,
        "active_positive_components": pl.String,
        "active_negative_components": pl.String,
        "blocked_reasons": pl.String,
        "watch_reasons": pl.String,
        "data_quality_notes": pl.String,
        "final_label": pl.String,
    }


def _backtest_schema() -> dict[str, Any]:
    return {
        "score_bucket": pl.String,
        "event_count": pl.Int64,
        "trade_count": pl.Int64,
        "support_rate": pl.Float64,
        "failure_rate": pl.Float64,
        "average_return": pl.Float64,
        "expectancy_proxy": pl.Float64,
        "average_mfe": pl.Float64,
        "average_mae": pl.Float64,
        "filter_helped_rate": pl.Float64,
        "false_block_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "evidence_label": pl.String,
    }


def _ablation_schema() -> dict[str, Any]:
    return {
        "ablation": pl.String,
        "event_count": pl.Int64,
        "score_monotonicity_change": pl.Float64,
        "expectancy_change": pl.Float64,
        "false_block_change": pl.Float64,
        "interpretation": pl.String,
    }
