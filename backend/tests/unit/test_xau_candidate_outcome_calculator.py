from datetime import UTC, date, datetime, timedelta

import pytest

from src.models.xau_candidate_outcome import (
    XauCandidateOutcomeCoverageStatus,
    XauCandidateOutcomeLabel,
    XauCandidateOutcomeWindow,
    XauCandidatePriceBar,
)
from src.models.xau_sd_oi_candidate import (
    XauSdOiCandidate,
    XauSdOiCandidateSet,
    XauSdOiCandidateSide,
    XauSdOiConfirmationState,
    XauSdOiFlowState,
    XauSdOiIvState,
    XauSdOiReadinessState,
    XauSdOiStretchZone,
    XauSdOiWallState,
)
from src.xau_candidate_outcomes.calculator import build_xau_candidate_outcome_set

TIMESTAMP = datetime(2026, 6, 2, 14, 30, tzinfo=UTC)


def test_short_reversion_candidate_hits_target_1_before_stop() -> None:
    outcome_set = build_xau_candidate_outcome_set(
        _candidate_set(_short_candidate()),
        [
            _bar(0, 112.0, 114.0, 108.0, 109.0),
            _bar(15, 109.0, 110.0, 99.0, 100.0),
            _bar(30, 100.0, 101.0, 98.0, 99.0),
        ],
        windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
        outcome_run_id="outcome_run_short_target",
    )
    outcome = outcome_set.outcomes[0]

    assert outcome.outcome_label == XauCandidateOutcomeLabel.MEAN_REVERTED
    assert outcome.returned_to_1sd is True
    assert outcome.hit_target_1 is True
    assert outcome.hit_stop_reference is False
    assert outcome.signal_allowed is False


def test_short_reversion_candidate_hits_stop_before_target() -> None:
    outcome_set = build_xau_candidate_outcome_set(
        _candidate_set(_short_candidate()),
        [
            _bar(0, 112.0, 126.0, 111.0, 124.0),
            _bar(30, 124.0, 124.0, 99.0, 100.0),
        ],
        windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
        outcome_run_id="outcome_run_short_stop",
    )
    outcome = outcome_set.outcomes[0]

    assert outcome.outcome_label == XauCandidateOutcomeLabel.STOP_HIT
    assert outcome.hit_stop_reference is True
    assert outcome.touched_3_5sd is True


def test_long_reversion_candidate_hits_target_1_and_computes_mfe_mae() -> None:
    outcome_set = build_xau_candidate_outcome_set(
        _candidate_set(_long_candidate()),
        [
            _bar(0, 68.0, 70.0, 65.0, 67.0),
            _bar(30, 67.0, 82.0, 66.0, 81.0),
        ],
        windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
        outcome_run_id="outcome_run_long_target",
    )
    outcome = outcome_set.outcomes[0]

    assert outcome.outcome_label == XauCandidateOutcomeLabel.MEAN_REVERTED
    assert outcome.mfe_points == pytest.approx(14.0)
    assert outcome.mae_points == pytest.approx(3.0)
    assert outcome.returned_to_1sd is True


def test_breakout_risk_candidate_marks_continued_breakout() -> None:
    outcome_set = build_xau_candidate_outcome_set(
        _candidate_set(_breakout_candidate()),
        [
            _bar(0, 122.0, 123.0, 121.0, 122.5),
            _bar(30, 122.5, 126.0, 122.0, 125.5),
        ],
        windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
        outcome_run_id="outcome_run_breakout",
    )
    outcome = outcome_set.outcomes[0]

    assert outcome.outcome_label == XauCandidateOutcomeLabel.BREAKOUT_CONTINUED
    assert outcome.continued_breakout is True
    assert outcome.touched_3_5sd is True


def test_missing_price_bars_produce_unavailable_outcome_without_crash() -> None:
    outcome_set = build_xau_candidate_outcome_set(
        _candidate_set(_short_candidate()),
        [],
        windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
        outcome_run_id="outcome_run_missing",
    )
    outcome = outcome_set.outcomes[0]

    assert outcome.outcome_label == XauCandidateOutcomeLabel.UNAVAILABLE
    assert outcome.coverage_status == XauCandidateOutcomeCoverageStatus.MISSING
    assert outcome.open is None
    assert outcome.high is None
    assert outcome.low is None
    assert outcome.close is None
    assert outcome.signal_allowed is False


def test_partial_window_computes_available_ohlc_and_records_limitation() -> None:
    outcome_set = build_xau_candidate_outcome_set(
        _candidate_set(_short_candidate()),
        [
            _bar(10, 112.0, 113.0, 110.0, 111.0),
            _bar(20, 111.0, 112.0, 109.0, 110.0),
        ],
        windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
        outcome_run_id="outcome_run_partial",
    )
    outcome = outcome_set.outcomes[0]

    assert outcome.coverage_status == XauCandidateOutcomeCoverageStatus.PARTIAL
    assert outcome.open == pytest.approx(112.0)
    assert outcome.high == pytest.approx(113.0)
    assert outcome.low == pytest.approx(109.0)
    assert outcome.close == pytest.approx(110.0)
    assert any("do not fully cover" in limitation for limitation in outcome.limitations)


def _candidate_set(candidate: XauSdOiCandidate) -> XauSdOiCandidateSet:
    return XauSdOiCandidateSet(
        map_id=candidate.map_id,
        session_date=candidate.session_date,
        timestamp=candidate.timestamp,
        candidate_count=1,
        candidates=[candidate],
    )


def _short_candidate() -> XauSdOiCandidate:
    return _candidate(
        candidate_id="short_reversion_candidate",
        side=XauSdOiCandidateSide.SHORT_REVERSION_CANDIDATE,
        stretch_zone=XauSdOiStretchZone.UPPER_2SD_TO_3SD,
        traded_price=112.0,
        target_1=100.0,
        target_2=90.0,
        target_3=80.0,
        stop_reference=125.0,
    )


def _long_candidate() -> XauSdOiCandidate:
    return _candidate(
        candidate_id="long_reversion_candidate",
        side=XauSdOiCandidateSide.LONG_REVERSION_CANDIDATE,
        stretch_zone=XauSdOiStretchZone.LOWER_2SD_TO_3SD,
        traded_price=68.0,
        target_1=80.0,
        target_2=90.0,
        target_3=100.0,
        stop_reference=55.0,
    )


def _breakout_candidate() -> XauSdOiCandidate:
    return _candidate(
        candidate_id="breakout_risk_candidate",
        side=XauSdOiCandidateSide.BREAKOUT_RISK,
        stretch_zone=XauSdOiStretchZone.OUTSIDE_3SD,
        traded_price=122.0,
        target_1=None,
        target_2=None,
        target_3=None,
        stop_reference=None,
    )


def _candidate(
    *,
    candidate_id: str,
    side: XauSdOiCandidateSide,
    stretch_zone: XauSdOiStretchZone,
    traded_price: float,
    target_1: float | None,
    target_2: float | None,
    target_3: float | None,
    stop_reference: float | None,
) -> XauSdOiCandidate:
    return XauSdOiCandidate(
        candidate_id=candidate_id,
        map_id="xau_candidate_outcome_fixture",
        session_date=date(2026, 6, 2),
        timestamp=TIMESTAMP,
        side=side,
        stretch_zone=stretch_zone,
        traded_price=traded_price,
        gc_price=traded_price + 10.0,
        basis=10.0,
        lower_1sd=80.0,
        upper_1sd=100.0,
        lower_2sd=70.0,
        upper_2sd=110.0,
        lower_3sd=60.0,
        upper_3sd=120.0,
        lower_3_5sd=55.0,
        upper_3_5sd=125.0,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        stop_reference=stop_reference,
        confirmation_state=XauSdOiConfirmationState.REJECTION,
        iv_state=XauSdOiIvState.STABLE,
        flow_state=XauSdOiFlowState.NOT_BREAKOUT_CONFIRMED,
        oi_wall_state=XauSdOiWallState.NEAREST_WALL_PRESENT,
        readiness_state=XauSdOiReadinessState.CANDIDATE_READY,
    )


def _bar(
    minute_offset: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> XauCandidatePriceBar:
    return XauCandidatePriceBar(
        timestamp=TIMESTAMP + timedelta(minutes=minute_offset),
        open=open_price,
        high=high,
        low=low,
        close=close,
        source="fixture",
    )
