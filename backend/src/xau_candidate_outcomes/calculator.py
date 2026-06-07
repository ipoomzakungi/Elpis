from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from src.models.xau_candidate_outcome import (
    XAU_CANDIDATE_OUTCOME_RESEARCH_LIMITATION,
    XauCandidateOutcome,
    XauCandidateOutcomeCoverageStatus,
    XauCandidateOutcomeLabel,
    XauCandidateOutcomeSet,
    XauCandidateOutcomeWindow,
    XauCandidatePriceBar,
    XauCandidatePriceSeriesSource,
    XauCandidatePriceSourceKind,
    candidate_outcome_limitations,
    candidate_outcome_no_signal_reasons,
)
from src.models.xau_sd_oi_candidate import (
    XauSdOiCandidate,
    XauSdOiCandidateSet,
    XauSdOiCandidateSide,
    XauSdOiStretchZone,
)

SESSION_CLOSE_UTC = time(hour=21, minute=0, tzinfo=UTC)
SUPPORTED_OUTCOME_WINDOWS = (
    XauCandidateOutcomeWindow.THIRTY_MINUTES,
    XauCandidateOutcomeWindow.ONE_HOUR,
    XauCandidateOutcomeWindow.FOUR_HOURS,
    XauCandidateOutcomeWindow.SESSION_CLOSE,
    XauCandidateOutcomeWindow.NEXT_DAY,
)


def build_xau_candidate_outcome_set(
    candidate_set: XauSdOiCandidateSet,
    price_bars: list[XauCandidatePriceBar],
    *,
    windows: list[XauCandidateOutcomeWindow] | None = None,
    next_wall_levels: dict[str, float] | None = None,
    outcome_run_id: str | None = None,
    candidate_set_id: str | None = None,
    price_source: XauCandidatePriceSeriesSource | None = None,
) -> XauCandidateOutcomeSet:
    """Attach forward price outcomes to a Feature 021 candidate set."""

    resolved_windows = _resolved_windows(windows)
    sorted_bars = sorted(price_bars, key=lambda bar: bar.timestamp)
    resolved_outcome_run_id = outcome_run_id or _default_outcome_run_id(candidate_set)
    resolved_candidate_set_id = candidate_set_id or _default_candidate_set_id(candidate_set)
    resolved_price_source = price_source or XauCandidatePriceSeriesSource(
        source_kind=XauCandidatePriceSourceKind.STATIC_FIXTURE,
        source_path="static_fixture",
        row_count=len(sorted_bars),
        first_timestamp=sorted_bars[0].timestamp if sorted_bars else None,
        last_timestamp=sorted_bars[-1].timestamp if sorted_bars else None,
        limitations=["Static fixture price bars are for local tests only."],
    )
    outcomes = [
        _outcome_for_candidate_window(
            candidate,
            window=window,
            price_bars=sorted_bars,
            outcome_run_id=resolved_outcome_run_id,
            price_source=resolved_price_source,
            next_wall_level=(next_wall_levels or {}).get(candidate.candidate_id),
        )
        for candidate in candidate_set.candidates
        for window in resolved_windows
    ]
    unavailable_count = sum(
        1 for outcome in outcomes if outcome.outcome_label == XauCandidateOutcomeLabel.UNAVAILABLE
    )
    return XauCandidateOutcomeSet(
        outcome_run_id=resolved_outcome_run_id,
        map_id=candidate_set.map_id,
        candidate_set_id=resolved_candidate_set_id,
        session_date=candidate_set.session_date,
        windows=resolved_windows,
        candidate_count=candidate_set.candidate_count,
        outcome_count=len(outcomes),
        unavailable_count=unavailable_count,
        price_source=resolved_price_source,
        outcomes=outcomes,
        no_signal_reasons=candidate_outcome_no_signal_reasons(*candidate_set.no_signal_reasons),
        limitations=candidate_outcome_limitations(
            *candidate_set.limitations,
            *resolved_price_source.limitations,
        ),
        research_only=True,
        signal_allowed=False,
    )


def _outcome_for_candidate_window(
    candidate: XauSdOiCandidate,
    *,
    window: XauCandidateOutcomeWindow,
    price_bars: list[XauCandidatePriceBar],
    outcome_run_id: str,
    price_source: XauCandidatePriceSeriesSource,
    next_wall_level: float | None,
) -> XauCandidateOutcome:
    start, end = _window_range(candidate.timestamp, window)
    overlap = [bar for bar in price_bars if start <= bar.timestamp <= end]
    entry = candidate.traded_price
    limitations = candidate_outcome_limitations(*price_source.limitations)
    if not overlap:
        return XauCandidateOutcome(
            candidate_id=candidate.candidate_id,
            map_id=candidate.map_id,
            run_id=outcome_run_id,
            session_date=candidate.session_date,
            window=window,
            entry_reference=entry,
            stop_reference=candidate.stop_reference,
            target_1=candidate.target_1,
            target_2=candidate.target_2,
            target_3=candidate.target_3,
            outcome_label=XauCandidateOutcomeLabel.UNAVAILABLE,
            price_source=price_source.source_path,
            coverage_status=XauCandidateOutcomeCoverageStatus.MISSING,
            limitations=[
                *limitations,
                f"No usable price bars overlap the {window.value} outcome window.",
            ],
            research_only=True,
            signal_allowed=False,
        )

    coverage_status, coverage_limitations = _coverage_status(start, end, overlap)
    high = max(bar.high for bar in overlap)
    low = min(bar.low for bar in overlap)
    first = overlap[0]
    last = overlap[-1]
    direction = _candidate_direction(candidate, high=high, low=low)
    mfe, mae = _mfe_mae(direction, entry=entry, high=high, low=low)
    hit_target_1 = _hit_target(direction, candidate.target_1, high=high, low=low)
    hit_target_2 = _hit_target(direction, candidate.target_2, high=high, low=low)
    hit_target_3 = _hit_target(direction, candidate.target_3, high=high, low=low)
    hit_stop_reference = _hit_stop(direction, candidate.stop_reference, high=high, low=low)
    returned_to_1sd = hit_target_1
    touched_2sd = _touched_sd(direction, candidate.upper_2sd, candidate.lower_2sd, high, low)
    touched_3sd = _touched_sd(direction, candidate.upper_3sd, candidate.lower_3sd, high, low)
    touched_3_5sd = hit_stop_reference or _touched_sd(
        direction,
        candidate.upper_3_5sd,
        candidate.lower_3_5sd,
        high,
        low,
    )
    touched_next_wall = _touched_next_wall(next_wall_level, entry=entry, high=high, low=low)
    first_hit = _first_hit_event(candidate, direction, overlap)
    continued_breakout = _continued_breakout(
        candidate,
        direction=direction,
        high=high,
        low=low,
        touched_3sd=touched_3sd,
        touched_3_5sd=touched_3_5sd,
    )
    label = _label(
        first_hit=first_hit,
        returned_to_1sd=returned_to_1sd,
        target_hit=hit_target_1 or hit_target_2 or hit_target_3,
        continued_breakout=continued_breakout,
    )
    return XauCandidateOutcome(
        candidate_id=candidate.candidate_id,
        map_id=candidate.map_id,
        run_id=outcome_run_id,
        session_date=candidate.session_date,
        window=window,
        entry_reference=entry,
        stop_reference=candidate.stop_reference,
        target_1=candidate.target_1,
        target_2=candidate.target_2,
        target_3=candidate.target_3,
        open=first.open,
        high=high,
        low=low,
        close=last.close,
        mfe_points=mfe,
        mae_points=mae,
        hit_target_1=hit_target_1,
        hit_target_2=hit_target_2,
        hit_target_3=hit_target_3,
        hit_stop_reference=hit_stop_reference,
        returned_to_1sd=returned_to_1sd,
        touched_2sd=touched_2sd,
        touched_3sd=touched_3sd,
        touched_3_5sd=touched_3_5sd,
        touched_next_wall=touched_next_wall,
        continued_breakout=continued_breakout,
        outcome_label=label,
        price_source=price_source.source_path,
        coverage_status=coverage_status,
        limitations=[*limitations, *coverage_limitations],
        research_only=True,
        signal_allowed=False,
    )


def _window_range(
    timestamp: datetime,
    window: XauCandidateOutcomeWindow,
) -> tuple[datetime, datetime]:
    start = _utc(timestamp)
    if window == XauCandidateOutcomeWindow.THIRTY_MINUTES:
        return start, start + timedelta(minutes=30)
    if window == XauCandidateOutcomeWindow.ONE_HOUR:
        return start, start + timedelta(hours=1)
    if window == XauCandidateOutcomeWindow.FOUR_HOURS:
        return start, start + timedelta(hours=4)
    if window == XauCandidateOutcomeWindow.NEXT_DAY:
        return start, start + timedelta(days=1)
    session_close = datetime.combine(start.date(), SESSION_CLOSE_UTC).astimezone(UTC)
    if session_close <= start:
        session_close += timedelta(days=1)
    return start, session_close


def _coverage_status(
    start: datetime,
    end: datetime,
    overlap: list[XauCandidatePriceBar],
) -> tuple[XauCandidateOutcomeCoverageStatus, list[str]]:
    observed_start = overlap[0].timestamp
    observed_end = overlap[-1].timestamp
    gap_count = _gap_count(overlap)
    complete = (
        observed_start <= start
        and observed_end >= end
        and len(overlap) >= 2
        and gap_count == 0
    )
    if complete:
        return XauCandidateOutcomeCoverageStatus.COMPLETE, []
    reason = "Price bars overlap the window but do not fully cover the required interval."
    if gap_count:
        reason = "Price bars include timestamp gaps inside the required interval."
    return XauCandidateOutcomeCoverageStatus.PARTIAL, [reason]


def _candidate_direction(
    candidate: XauSdOiCandidate,
    *,
    high: float,
    low: float,
) -> str | None:
    if candidate.side == XauSdOiCandidateSide.SHORT_REVERSION_CANDIDATE:
        return "short"
    if candidate.side == XauSdOiCandidateSide.LONG_REVERSION_CANDIDATE:
        return "long"
    if candidate.side != XauSdOiCandidateSide.BREAKOUT_RISK:
        return None
    entry = candidate.traded_price
    if entry is not None:
        if candidate.upper_3sd is not None and entry >= candidate.upper_3sd:
            return "long"
        if candidate.lower_3sd is not None and entry <= candidate.lower_3sd:
            return "short"
    if candidate.stretch_zone == XauSdOiStretchZone.UPPER_2SD_TO_3SD:
        return "long"
    if candidate.stretch_zone == XauSdOiStretchZone.LOWER_2SD_TO_3SD:
        return "short"
    if candidate.upper_3sd is not None and high >= candidate.upper_3sd:
        return "long"
    if candidate.lower_3sd is not None and low <= candidate.lower_3sd:
        return "short"
    return None


def _mfe_mae(
    direction: str | None,
    *,
    entry: float | None,
    high: float,
    low: float,
) -> tuple[float | None, float | None]:
    if direction is None or entry is None:
        return None, None
    if direction == "short":
        return max(0.0, entry - low), max(0.0, high - entry)
    return max(0.0, high - entry), max(0.0, entry - low)


def _hit_target(
    direction: str | None,
    target: float | None,
    *,
    high: float,
    low: float,
) -> bool:
    if direction is None or target is None:
        return False
    if direction == "short":
        return low <= target
    return high >= target


def _hit_stop(
    direction: str | None,
    stop: float | None,
    *,
    high: float,
    low: float,
) -> bool:
    if direction is None or stop is None:
        return False
    if direction == "short":
        return high >= stop
    return low <= stop


def _touched_sd(
    direction: str | None,
    upper_level: float | None,
    lower_level: float | None,
    high: float,
    low: float,
) -> bool:
    if direction == "long":
        return upper_level is not None and high >= upper_level
    if direction == "short":
        return lower_level is not None and low <= lower_level
    return (upper_level is not None and high >= upper_level) or (
        lower_level is not None and low <= lower_level
    )


def _touched_next_wall(
    next_wall_level: float | None,
    *,
    entry: float | None,
    high: float,
    low: float,
) -> bool:
    if next_wall_level is None:
        return False
    if entry is None:
        return low <= next_wall_level <= high
    if next_wall_level >= entry:
        return high >= next_wall_level
    return low <= next_wall_level


def _first_hit_event(
    candidate: XauSdOiCandidate,
    direction: str | None,
    bars: list[XauCandidatePriceBar],
) -> str | None:
    if direction is None:
        return None
    for bar in bars:
        stop_hit = _hit_stop(
            direction,
            candidate.stop_reference,
            high=bar.high,
            low=bar.low,
        )
        target_hit = _hit_target(
            direction,
            candidate.target_1,
            high=bar.high,
            low=bar.low,
        )
        if stop_hit:
            return "stop"
        if target_hit:
            return "target"
    return None


def _continued_breakout(
    candidate: XauSdOiCandidate,
    *,
    direction: str | None,
    high: float,
    low: float,
    touched_3sd: bool,
    touched_3_5sd: bool,
) -> bool:
    if candidate.side != XauSdOiCandidateSide.BREAKOUT_RISK or direction is None:
        return False
    entry = candidate.traded_price
    if direction == "long":
        extended_from_entry = entry is not None and high > entry
    else:
        extended_from_entry = entry is not None and low < entry
    return extended_from_entry and (touched_3sd or touched_3_5sd)


def _label(
    *,
    first_hit: str | None,
    returned_to_1sd: bool,
    target_hit: bool,
    continued_breakout: bool,
) -> XauCandidateOutcomeLabel:
    if first_hit == "stop":
        return XauCandidateOutcomeLabel.STOP_HIT
    if continued_breakout:
        return XauCandidateOutcomeLabel.BREAKOUT_CONTINUED
    if returned_to_1sd:
        return XauCandidateOutcomeLabel.MEAN_REVERTED
    if target_hit:
        return XauCandidateOutcomeLabel.TARGET_HIT
    return XauCandidateOutcomeLabel.UNRESOLVED


def _resolved_windows(
    windows: list[XauCandidateOutcomeWindow] | None,
) -> list[XauCandidateOutcomeWindow]:
    if windows is None:
        return list(SUPPORTED_OUTCOME_WINDOWS)
    resolved = list(dict.fromkeys(windows))
    if not resolved:
        raise ValueError("at least one outcome window is required")
    return resolved


def _default_candidate_set_id(candidate_set: XauSdOiCandidateSet) -> str:
    return f"{candidate_set.map_id}_{candidate_set.timestamp.strftime('%Y%m%dT%H%M%S')}_candidates"


def _default_outcome_run_id(candidate_set: XauSdOiCandidateSet) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    return f"xau_candidate_outcomes_{candidate_set.map_id}_{timestamp}"


def _gap_count(bars: list[XauCandidatePriceBar]) -> int:
    if len(bars) < 3:
        return 0
    deltas = [
        (right.timestamp - left.timestamp).total_seconds()
        for left, right in zip(bars, bars[1:])
    ]
    positive = [delta for delta in deltas if delta > 0]
    if not positive:
        return 0
    expected = min(positive)
    return sum(1 for delta in positive if delta > expected * 1.5)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "SESSION_CLOSE_UTC",
    "SUPPORTED_OUTCOME_WINDOWS",
    "XAU_CANDIDATE_OUTCOME_RESEARCH_LIMITATION",
    "build_xau_candidate_outcome_set",
]
