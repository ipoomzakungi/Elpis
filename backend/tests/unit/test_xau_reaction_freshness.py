from datetime import UTC, datetime

from src.models.xau_reaction import XauConfidenceLabel, XauFreshnessInput, XauFreshnessState
from src.xau_reaction.freshness import classify_freshness


def _freshness_input(
    *,
    intraday_timestamp: datetime | None,
    current_timestamp: datetime | None,
    contracts: float | None,
) -> XauFreshnessInput:
    return XauFreshnessInput(
        intraday_timestamp=intraday_timestamp,
        current_timestamp=current_timestamp,
        total_intraday_contracts=contracts,
        min_contract_threshold=100.0,
        max_allowed_age_minutes=30,
    )


def test_classify_freshness_returns_valid_for_current_sufficient_flow():
    result = classify_freshness(
        _freshness_input(
            intraday_timestamp=datetime(2026, 5, 12, 9, 50, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            contracts=150.0,
        )
    )

    assert result.state == XauFreshnessState.VALID
    assert result.age_minutes == 10.0
    assert result.confidence_label == XauConfidenceLabel.HIGH
    assert result.no_trade_reason is None


def test_classify_freshness_returns_thin_for_low_contract_count():
    result = classify_freshness(
        _freshness_input(
            intraday_timestamp=datetime(2026, 5, 12, 9, 50, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            contracts=25.0,
        )
    )

    assert result.state == XauFreshnessState.THIN
    assert result.confidence_label == XauConfidenceLabel.LOW
    assert result.no_trade_reason is None


def test_classify_freshness_blocks_stale_prior_day_and_unknown_inputs():
    stale = classify_freshness(
        _freshness_input(
            intraday_timestamp=datetime(2026, 5, 12, 9, 0, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            contracts=150.0,
        )
    )
    prior_day = classify_freshness(
        _freshness_input(
            intraday_timestamp=datetime(2026, 5, 11, 23, 50, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 0, 5, tzinfo=UTC),
            contracts=150.0,
        )
    )
    unknown = classify_freshness(
        _freshness_input(
            intraday_timestamp=None,
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            contracts=150.0,
        )
    )

    assert stale.state == XauFreshnessState.STALE
    assert stale.confidence_label == XauConfidenceLabel.BLOCKED
    assert stale.no_trade_reason
    assert prior_day.state == XauFreshnessState.PRIOR_DAY
    assert prior_day.confidence_label == XauConfidenceLabel.BLOCKED
    assert prior_day.no_trade_reason
    assert unknown.state == XauFreshnessState.UNKNOWN
    assert unknown.confidence_label == XauConfidenceLabel.BLOCKED
    assert unknown.no_trade_reason


def test_classify_freshness_blocks_future_timestamp_and_zero_contracts():
    future_timestamp = classify_freshness(
        _freshness_input(
            intraday_timestamp=datetime(2026, 5, 12, 10, 1, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            contracts=150.0,
        )
    )
    zero_contracts = classify_freshness(
        _freshness_input(
            intraday_timestamp=datetime(2026, 5, 12, 9, 50, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            contracts=0.0,
        )
    )

    assert future_timestamp.state == XauFreshnessState.UNKNOWN
    assert future_timestamp.confidence_label == XauConfidenceLabel.BLOCKED
    assert future_timestamp.no_trade_reason
    assert zero_contracts.state == XauFreshnessState.UNKNOWN
    assert zero_contracts.confidence_label == XauConfidenceLabel.BLOCKED
    assert zero_contracts.no_trade_reason
