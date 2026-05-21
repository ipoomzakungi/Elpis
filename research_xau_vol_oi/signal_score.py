"""Research-only signal scoring for XAU Vol-OI labels.

The scorer ranks deterministic research labels from 0 to 100. It does not
create orders, position sizes, broker payloads, or live-trading instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig, Signal, VolRegime, WallSide


LONG_SIGNALS = {Signal.FADE_WALL_LONG.value, Signal.BREAK_WALL_LONG.value}
SHORT_SIGNALS = {Signal.FADE_WALL_SHORT.value, Signal.BREAK_WALL_SHORT.value}
DIRECTIONAL_SIGNALS = LONG_SIGNALS | SHORT_SIGNALS
SIGNAL_VALUES = {signal.value for signal in Signal}


@dataclass(frozen=True)
class SignalScoreResult:
    """Scored research signal payload."""

    event_timestamp: Any
    source_bar_timestamp: Any
    source_signal: str
    source_reason: str
    signal_label: str
    signal_score: int
    trade_direction: str
    entry_reason: str
    invalidation_level: float | None
    target_level: float | None
    risk_warning: str
    close: float | None
    sigma_position: float | None
    distance_to_nearest_wall: float | None
    wall_score: float | None
    freshness_weight: float | None
    dte_weight: float | None
    vol_regime: str | None
    session_open_side: str
    research_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable row dictionary."""

        return {
            "event_timestamp": self.event_timestamp,
            "source_bar_timestamp": self.source_bar_timestamp,
            "source_signal": self.source_signal,
            "source_reason": self.source_reason,
            "signal_label": self.signal_label,
            "signal_score": self.signal_score,
            "trade_direction": self.trade_direction,
            "entry_reason": self.entry_reason,
            "invalidation_level": self.invalidation_level,
            "target_level": self.target_level,
            "risk_warning": self.risk_warning,
            "close": self.close,
            "sigma_position": self.sigma_position,
            "distance_to_nearest_wall": self.distance_to_nearest_wall,
            "wall_score": self.wall_score,
            "freshness_weight": self.freshness_weight,
            "dte_weight": self.dte_weight,
            "vol_regime": self.vol_regime,
            "session_open_side": self.session_open_side,
            "research_only": self.research_only,
        }


def score_signal_events(
    feature_table: pl.DataFrame,
    signal_events: pl.DataFrame,
    *,
    config: ResearchConfig | None = None,
) -> pl.DataFrame:
    """Score signal events using feature rows known at the source bar timestamp."""

    if signal_events.is_empty():
        return _empty_scores()
    cfg = config or ResearchConfig()
    feature_rows = feature_table.sort("timestamp").to_dicts() if not feature_table.is_empty() else []
    by_timestamp = {row.get("timestamp"): row for row in feature_rows}
    previous_by_timestamp = {
        row.get("timestamp"): feature_rows[index - 1] if index > 0 else None
        for index, row in enumerate(feature_rows)
    }
    next_by_timestamp = {
        row.get("timestamp"): feature_rows[index + 1] if index < len(feature_rows) - 1 else None
        for index, row in enumerate(feature_rows)
    }

    rows = []
    for event in signal_events.sort("event_timestamp").to_dicts():
        source_timestamp = event.get("source_bar_timestamp") or event.get("event_timestamp")
        bar = by_timestamp.get(source_timestamp, event)
        rows.append(
            score_signal_event(
                event,
                bar=bar,
                previous_bar=previous_by_timestamp.get(source_timestamp),
                next_bar=next_by_timestamp.get(source_timestamp),
                config=cfg,
            ).as_dict()
        )
    return pl.DataFrame(rows) if rows else _empty_scores()


def score_signal_event(
    event: dict[str, Any],
    *,
    bar: dict[str, Any] | None = None,
    previous_bar: dict[str, Any] | None = None,
    next_bar: dict[str, Any] | None = None,
    config: ResearchConfig | None = None,
) -> SignalScoreResult:
    """Score one deterministic event under conservative research gates."""

    cfg = config or ResearchConfig()
    source = str(event.get("signal") or Signal.NO_TRADE.value)
    reason = str(event.get("reason") or "")
    bar = bar or event
    warnings = ["research-only; not a trade instruction"]

    quality_issue = _quality_issue(event, bar)
    if quality_issue is not None:
        warnings.append(quality_issue)
        return _result(
            event,
            bar,
            source_signal=source,
            source_reason=reason,
            label=Signal.NO_TRADE.value,
            score=0,
            direction="NONE",
            entry_reason="bad_data_quality_gate",
            warnings=warnings,
            config=cfg,
        )

    wall_level = _float(_field(event, bar, "wall_level"))
    sigma_position = _float(_field(event, bar, "sigma_position"))
    wall_score = _float(_field(event, bar, "wall_score")) or 0.0
    rejection = _rejection_confirmed(event, bar, config=cfg)
    acceptance = _acceptance_confirmed(event, bar, next_bar, config=cfg)
    vol_expanded = _volatility_expanded(bar, previous_bar, config=cfg)
    inside_middle = sigma_position is not None and abs(sigma_position) <= 1.0
    extreme_sigma = sigma_position is not None and abs(sigma_position) >= 2.0

    label = source if source in SIGNAL_VALUES else Signal.NO_TRADE.value
    direction = _direction_for_label(label)

    if wall_level is None and source not in {Signal.NO_TRADE.value, Signal.NO_TRADE_MIDDLE.value}:
        label = Signal.NO_TRADE.value
        direction = "NONE"
        warnings.append("missing nearest wall")
    elif source in {Signal.FADE_WALL_LONG.value, Signal.FADE_WALL_SHORT.value} and not rejection:
        label = Signal.NO_TRADE.value
        direction = "NONE"
        warnings.append("reversal signal blocked: rejection not confirmed")
    elif source in {Signal.BREAK_WALL_LONG.value, Signal.BREAK_WALL_SHORT.value}:
        if not acceptance:
            label = Signal.NO_TRADE.value
            direction = "NONE"
            warnings.append("breakout signal blocked: acceptance not confirmed")
        elif not vol_expanded:
            label = Signal.NO_TRADE.value
            direction = "NONE"
            warnings.append("breakout signal blocked: volatility expansion not confirmed")

    confirmed_reaction = rejection or (acceptance and vol_expanded)
    if inside_middle and label in DIRECTIONAL_SIGNALS:
        if wall_score < cfg.signal_score_middle_override_wall_score or not confirmed_reaction:
            label = Signal.NO_TRADE_MIDDLE.value
            direction = "NONE"
            warnings.append("inside middle 1SD without high-score confirmed reaction")
    elif inside_middle and label not in DIRECTIONAL_SIGNALS:
        label = Signal.NO_TRADE_MIDDLE.value
        direction = "NONE"
        warnings.append("inside middle 1SD")

    if extreme_sigma and label in DIRECTIONAL_SIGNALS:
        warnings.append("2SD/3SD zone: smaller size warning and stronger confirmation required")
        if wall_score < cfg.signal_score_extreme_min_wall_score or not confirmed_reaction:
            label = Signal.NO_TRADE.value
            direction = "NONE"
            warnings.append("extreme sigma confirmation gate failed")

    if source == Signal.PIN_RISK.value:
        label = Signal.PIN_RISK.value
        direction = "NONE"
        warnings.append("pin-risk: do not chase direction")
    elif source == Signal.SQUEEZE_RISK.value and label not in DIRECTIONAL_SIGNALS:
        label = Signal.SQUEEZE_RISK.value
        direction = "NONE"
        warnings.append("squeeze-risk watch only until acceptance/rejection confirms")
    elif source == Signal.WATCH_WALL.value and label not in DIRECTIONAL_SIGNALS:
        label = Signal.WATCH_WALL.value
        direction = "NONE"

    score = _score_components(
        event,
        bar,
        source_signal=source,
        label=label,
        direction=direction,
        rejection=rejection,
        acceptance=acceptance,
        vol_expanded=vol_expanded,
        config=cfg,
    )

    if label in {Signal.NO_TRADE.value, Signal.NO_TRADE_MIDDLE.value}:
        score = min(score, 35)
        direction = "NONE"
    elif label == Signal.PIN_RISK.value:
        score = min(score, 45)
    elif label in {Signal.WATCH_WALL.value, Signal.SQUEEZE_RISK.value}:
        score = min(score, 55)
    elif label in DIRECTIONAL_SIGNALS and score < cfg.signal_score_directional_threshold:
        warnings.append("score below directional threshold")
        label = Signal.WATCH_WALL.value if wall_level is not None else Signal.NO_TRADE.value
        direction = "NONE"
        score = min(score, 55)

    return _result(
        event,
        bar,
        source_signal=source,
        source_reason=reason,
        label=label,
        score=score,
        direction=direction,
        entry_reason=_entry_reason(label, reason, rejection, acceptance, vol_expanded),
        warnings=warnings,
        config=cfg,
    )


def write_signal_dashboard(path: Path, scores: pl.DataFrame) -> None:
    """Write a small static HTML dashboard for local score inspection."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if scores.is_empty():
        path.write_text(
            "<!doctype html><title>XAU Signal Scores</title><p>No signal scores.</p>",
            encoding="utf-8",
        )
        return

    distribution = scores.group_by(["signal_label", "trade_direction"]).len().sort(
        ["signal_label", "trade_direction"]
    )
    top = (
        scores.filter(pl.col("trade_direction") != "NONE")
        .sort("signal_score", descending=True)
        .head(25)
    )
    html = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>XAU Signal Score Dashboard</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;margin:24px;color:#111827;background:#f9fafb}",
        "table{border-collapse:collapse;width:100%;margin:12px 0;background:white}",
        "th,td{border:1px solid #d1d5db;padding:6px 8px;text-align:left;font-size:13px}",
        "th{background:#e5e7eb}.warn{color:#92400e}.note{color:#374151}",
        "</style></head><body>",
        "<h1>XAU Vol-OI Signal Score Dashboard</h1>",
        "<p class='note'>Research-only scoring layer. This is not a live trading bot, order "
        "router, position-sizing engine, or execution recommendation.</p>",
        "<h2>Score Distribution</h2>",
        _html_table(distribution),
        "<h2>Top Directional Research Examples</h2>",
        _html_table(
            top.select(
                [
                    "event_timestamp",
                    "signal_label",
                    "signal_score",
                    "trade_direction",
                    "entry_reason",
                    "invalidation_level",
                    "target_level",
                    "risk_warning",
                ]
            )
            if not top.is_empty()
            else top
        ),
        "</body></html>",
    ]
    path.write_text("\n".join(html), encoding="utf-8")


def _score_components(
    event: dict[str, Any],
    bar: dict[str, Any],
    *,
    source_signal: str,
    label: str,
    direction: str,
    rejection: bool,
    acceptance: bool,
    vol_expanded: bool,
    config: ResearchConfig,
) -> int:
    score = 10.0
    score += _sigma_component(_float(_field(event, bar, "sigma_position")))
    score += _distance_component(
        distance=_distance_to_wall(event, bar),
        one_sd=_float(_field(event, bar, "one_sd_remaining")),
        config=config,
    )
    score += _wall_component(_float(_field(event, bar, "wall_score")), config=config)
    score += _freshness_component(_float(_field(event, bar, "freshness_weight")))
    score += _dte_component(_float(_field(event, bar, "dte_weight")))
    score += _vol_regime_component(str(_field(event, bar, "vol_regime") or ""), source_signal)
    score += _reaction_component(
        label=label,
        rejection=rejection,
        acceptance=acceptance,
        vol_expanded=vol_expanded,
    )
    score += _session_component(event, bar, direction=direction)
    if label in {Signal.NO_TRADE.value, Signal.NO_TRADE_MIDDLE.value}:
        score *= 0.55
    return int(round(max(0.0, min(100.0, score))))


def _quality_issue(event: dict[str, Any], bar: dict[str, Any]) -> str | None:
    state = str(_field(event, bar, "data_quality_state") or "VALID").upper()
    if state != "VALID":
        return f"bad data quality: {state}"
    one_sd = _float(_field(event, bar, "one_sd_remaining"))
    if one_sd is None or one_sd <= 0:
        return "missing IV expected-move input"
    event_timestamp = event.get("event_timestamp")
    available_wall_timestamp = event.get("available_wall_timestamp")
    if (
        event_timestamp is not None
        and available_wall_timestamp is not None
        and available_wall_timestamp > event_timestamp
    ):
        return "future wall timestamp blocked"
    basis_available = _field(event, bar, "basis_available")
    source = str(event.get("signal") or "")
    if source in DIRECTIONAL_SIGNALS and basis_available is False:
        return "missing basis-adjusted wall"
    return None


def _rejection_confirmed(
    event: dict[str, Any],
    bar: dict[str, Any],
    *,
    config: ResearchConfig,
) -> bool:
    side = str(_field(event, bar, "wall_side") or WallSide.UNKNOWN.value)
    high = _float(_field(event, bar, "high"))
    low = _float(_field(event, bar, "low"))
    close = _float(_field(event, bar, "close"))
    level = _float(_field(event, bar, "wall_level"))
    if close is None or level is None:
        return False
    resistance = (
        side in {WallSide.RESISTANCE.value, WallSide.MIXED.value}
        and high is not None
        and high >= level
        and close < level - config.acceptance_buffer_points
    )
    support = (
        side in {WallSide.SUPPORT.value, WallSide.MIXED.value}
        and low is not None
        and low <= level
        and close > level + config.acceptance_buffer_points
    )
    return resistance or support


def _acceptance_confirmed(
    event: dict[str, Any],
    bar: dict[str, Any],
    next_bar: dict[str, Any] | None,
    *,
    config: ResearchConfig,
) -> bool:
    source = str(event.get("signal") or "")
    close = _float(_field(event, bar, "close"))
    next_close = _float(next_bar.get("close")) if next_bar else None
    level = _float(_field(event, bar, "wall_level"))
    if close is None or next_close is None or level is None:
        return False
    if source == Signal.BREAK_WALL_LONG.value:
        return close > level + config.acceptance_buffer_points and next_close > level + config.acceptance_buffer_points
    if source == Signal.BREAK_WALL_SHORT.value:
        return close < level - config.acceptance_buffer_points and next_close < level - config.acceptance_buffer_points
    return False


def _volatility_expanded(
    bar: dict[str, Any],
    previous_bar: dict[str, Any] | None,
    *,
    config: ResearchConfig,
) -> bool:
    if previous_bar is None:
        return False
    rv = _float(bar.get("rv_percent"))
    prior_rv = _float(previous_bar.get("rv_percent"))
    if rv is not None and prior_rv is not None and prior_rv > 0:
        return rv >= prior_rv * config.vol_expansion_multiple
    volume = _float(bar.get("volume"))
    prior_volume = _float(previous_bar.get("volume"))
    return volume is not None and prior_volume is not None and volume > prior_volume


def _result(
    event: dict[str, Any],
    bar: dict[str, Any],
    *,
    source_signal: str,
    source_reason: str,
    label: str,
    score: int,
    direction: str,
    entry_reason: str,
    warnings: list[str],
    config: ResearchConfig,
) -> SignalScoreResult:
    return SignalScoreResult(
        event_timestamp=event.get("event_timestamp"),
        source_bar_timestamp=event.get("source_bar_timestamp"),
        source_signal=source_signal,
        source_reason=source_reason,
        signal_label=label,
        signal_score=int(max(0, min(100, score))),
        trade_direction=direction,
        entry_reason=entry_reason,
        invalidation_level=_invalidation_level(event, bar, direction=direction, config=config),
        target_level=_target_level(event, bar, direction=direction, config=config),
        risk_warning="; ".join(dict.fromkeys(warnings)),
        close=_float(_field(event, bar, "close")),
        sigma_position=_float(_field(event, bar, "sigma_position")),
        distance_to_nearest_wall=_distance_to_wall(event, bar),
        wall_score=_float(_field(event, bar, "wall_score")),
        freshness_weight=_float(_field(event, bar, "freshness_weight")),
        dte_weight=_float(_field(event, bar, "dte_weight")),
        vol_regime=_field(event, bar, "vol_regime"),
        session_open_side=_session_open_side(event, bar),
    )


def _entry_reason(
    label: str,
    source_reason: str,
    rejection: bool,
    acceptance: bool,
    vol_expanded: bool,
) -> str:
    parts = [label.lower()]
    if source_reason:
        parts.append(source_reason)
    if rejection:
        parts.append("rejection_confirmed")
    if acceptance:
        parts.append("acceptance_confirmed")
    if vol_expanded:
        parts.append("volatility_expanded")
    return "|".join(parts)


def _invalidation_level(
    event: dict[str, Any],
    bar: dict[str, Any],
    *,
    direction: str,
    config: ResearchConfig,
) -> float | None:
    if direction == "NONE":
        return None
    close = _float(_field(event, bar, "close"))
    wall_level = _float(_field(event, bar, "wall_level"))
    one_sd = _float(_field(event, bar, "one_sd_remaining"))
    buffer = config.acceptance_buffer_points
    if direction == "LONG":
        return (wall_level - buffer) if wall_level is not None else _offset(close, -(one_sd or buffer))
    return (wall_level + buffer) if wall_level is not None else _offset(close, one_sd or buffer)


def _target_level(
    event: dict[str, Any],
    bar: dict[str, Any],
    *,
    direction: str,
    config: ResearchConfig,
) -> float | None:
    if direction == "NONE":
        return None
    close = _float(_field(event, bar, "close"))
    if close is None:
        return None
    next_wall_distance = _float(_field(event, bar, "next_wall_distance"))
    one_sd = _float(_field(event, bar, "one_sd_remaining")) or config.proximity_points
    session_open = _float(_field(event, bar, "session_open"))
    source = str(event.get("signal") or "")
    if direction == "LONG":
        if source == Signal.FADE_WALL_LONG.value and session_open is not None and session_open > close:
            return session_open
        return close + (next_wall_distance if next_wall_distance and next_wall_distance > 0 else one_sd)
    if source == Signal.FADE_WALL_SHORT.value and session_open is not None and session_open < close:
        return session_open
    return close - (next_wall_distance if next_wall_distance and next_wall_distance > 0 else one_sd)


def _distance_to_wall(event: dict[str, Any], bar: dict[str, Any]) -> float | None:
    existing = _float(_field(event, bar, "distance_to_nearest_wall"))
    if existing is not None:
        return existing
    close = _float(_field(event, bar, "close"))
    wall_level = _float(_field(event, bar, "wall_level"))
    if close is None or wall_level is None:
        return None
    return abs(close - wall_level)


def _direction_for_label(label: str) -> str:
    if label in LONG_SIGNALS:
        return "LONG"
    if label in SHORT_SIGNALS:
        return "SHORT"
    return "NONE"


def _sigma_component(value: float | None) -> float:
    if value is None:
        return 0.0
    absolute = abs(value)
    if absolute <= 0.5:
        return 2.0
    if absolute <= 1.0:
        return 5.0
    if absolute <= 2.0:
        return 13.0
    if absolute <= 3.0:
        return 10.0
    return 6.0


def _distance_component(
    *,
    distance: float | None,
    one_sd: float | None,
    config: ResearchConfig,
) -> float:
    if distance is None:
        return 0.0
    scale = max(config.proximity_points, (one_sd or config.proximity_points) * config.proximity_sd_fraction)
    return 15.0 * max(0.0, 1.0 - min(distance / (scale * 2.0), 1.0))


def _wall_component(value: float | None, *, config: ResearchConfig) -> float:
    if value is None:
        return 0.0
    denominator = max(config.signal_score_middle_override_wall_score, config.strong_wall_score, 0.01)
    return min(20.0, 20.0 * max(0.0, value) / denominator)


def _freshness_component(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(10.0, ((value - 1.0) / 0.75) * 10.0))


def _dte_component(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(8.0, value * 8.0))


def _vol_regime_component(regime: str, source_signal: str) -> float:
    if source_signal in {Signal.BREAK_WALL_LONG.value, Signal.BREAK_WALL_SHORT.value}:
        if regime in {VolRegime.RV_PREMIUM.value, VolRegime.STRESS.value}:
            return 10.0
        if regime == VolRegime.BALANCED.value:
            return 5.0
        return 2.0
    if source_signal in {Signal.FADE_WALL_LONG.value, Signal.FADE_WALL_SHORT.value}:
        if regime in {VolRegime.IV_PREMIUM.value, VolRegime.BALANCED.value}:
            return 8.0
        if regime in {VolRegime.RV_PREMIUM.value, VolRegime.STRESS.value}:
            return 3.0
    return 4.0 if regime != VolRegime.UNKNOWN.value else 0.0


def _reaction_component(
    *,
    label: str,
    rejection: bool,
    acceptance: bool,
    vol_expanded: bool,
) -> float:
    if label in {Signal.FADE_WALL_LONG.value, Signal.FADE_WALL_SHORT.value}:
        return 20.0 if rejection else 0.0
    if label in {Signal.BREAK_WALL_LONG.value, Signal.BREAK_WALL_SHORT.value}:
        return 20.0 if acceptance and vol_expanded else 8.0 if acceptance else 0.0
    if label in {Signal.WATCH_WALL.value, Signal.SQUEEZE_RISK.value, Signal.PIN_RISK.value}:
        return 5.0
    return 0.0


def _session_component(event: dict[str, Any], bar: dict[str, Any], *, direction: str) -> float:
    side = _session_open_side(event, bar)
    if direction == "LONG" and side == "above_session_open":
        return 5.0
    if direction == "SHORT" and side == "below_session_open":
        return 5.0
    if direction != "NONE" and side != "unknown":
        return 2.0
    return 0.0


def _session_open_side(event: dict[str, Any], bar: dict[str, Any]) -> str:
    close = _float(_field(event, bar, "close"))
    session_open = _float(_field(event, bar, "session_open"))
    if close is None or session_open is None:
        return "unknown"
    if close > session_open:
        return "above_session_open"
    if close < session_open:
        return "below_session_open"
    return "at_session_open"


def _field(event: dict[str, Any], bar: dict[str, Any], key: str) -> Any:
    value = bar.get(key)
    if value is not None:
        return value
    return event.get(key)


def _offset(value: float | None, amount: float) -> float | None:
    if value is None:
        return None
    return value + amount


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _html_table(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "<p>No rows.</p>"
    rows = ["<table><thead><tr>"]
    for column in frame.columns:
        rows.append(f"<th>{escape(column)}</th>")
    rows.append("</tr></thead><tbody>")
    for raw in frame.to_dicts():
        rows.append("<tr>")
        for column in frame.columns:
            rows.append(f"<td>{escape(str(raw.get(column, '')))}</td>")
        rows.append("</tr>")
    rows.append("</tbody></table>")
    return "".join(rows)


def _empty_scores() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "event_timestamp": pl.Datetime(time_zone="UTC"),
            "source_bar_timestamp": pl.Datetime(time_zone="UTC"),
            "source_signal": pl.String,
            "source_reason": pl.String,
            "signal_label": pl.String,
            "signal_score": pl.Int64,
            "trade_direction": pl.String,
            "entry_reason": pl.String,
            "invalidation_level": pl.Float64,
            "target_level": pl.Float64,
            "risk_warning": pl.String,
            "close": pl.Float64,
            "sigma_position": pl.Float64,
            "distance_to_nearest_wall": pl.Float64,
            "wall_score": pl.Float64,
            "freshness_weight": pl.Float64,
            "dte_weight": pl.Float64,
            "vol_regime": pl.String,
            "session_open_side": pl.String,
            "research_only": pl.Boolean,
        }
    )
