from datetime import UTC, date, datetime

from src.models.xau import (
    XauBasisSnapshot,
    XauBasisSource,
    XauExpectedRange,
    XauFreshnessFactorStatus,
    XauOiWall,
    XauOptionsImportReport,
    XauReferencePrice,
    XauReferenceType,
    XauReportStatus,
    XauTimestampAlignmentStatus,
    XauVolatilitySource,
    XauVolOiReport,
    XauVolOiReportRequest,
    XauWallType,
    XauZone,
    XauZoneConfidence,
    XauZoneType,
)
from src.models.xau_reaction import (
    XauAcceptanceDirection,
    XauAcceptanceInput,
    XauAcceptanceResult,
    XauConfidenceLabel,
    XauEventRiskState,
    XauFreshnessResult,
    XauFreshnessState,
    XauInitialMoveDirection,
    XauIntradayFreshnessInput,
    XauIvEdgeState,
    XauOpenFlipState,
    XauOpenRegimeInput,
    XauOpenRegimeResult,
    XauOpenSide,
    XauOpenSupportResistance,
    XauReactionReportRequest,
    XauRvExtensionState,
    XauVolRegimeInput,
    XauVolRegimeResult,
    XauVrpRegime,
)


def sample_xau_reaction_report_request() -> XauReactionReportRequest:
    return XauReactionReportRequest(
        source_report_id="xau_vol_oi_synthetic_20260512",
        current_price=2405.0,
        current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
        event_risk_state=XauEventRiskState.UNKNOWN,
        max_total_risk_per_idea=0.01,
        max_recovery_legs=1,
        minimum_rr=1.5,
        wall_buffer_points=2.0,
        research_only_acknowledged=True,
    )


def sample_xau_reaction_full_context_request() -> XauReactionReportRequest:
    return XauReactionReportRequest(
        source_report_id="xau_vol_oi_synthetic_20260512",
        current_price=2405.0,
        current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
        freshness_input=XauIntradayFreshnessInput(
            intraday_timestamp=datetime(2026, 5, 12, 9, 55, tzinfo=UTC),
            current_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            total_intraday_contracts=12500.0,
            min_contract_threshold=1000.0,
            max_allowed_age_minutes=30,
            session_flag="regular",
        ),
        vol_regime_input=XauVolRegimeInput(
            implied_volatility=0.16,
            realized_volatility=0.12,
            price=2405.0,
            iv_lower=2378.0,
            iv_upper=2428.0,
            rv_lower=2388.0,
            rv_upper=2420.0,
        ),
        open_regime_input=XauOpenRegimeInput(
            session_open=2398.0,
            current_price=2405.0,
            initial_move_direction=XauInitialMoveDirection.UP,
            crossed_open_after_initial_move=False,
            acceptance_beyond_open=False,
        ),
        acceptance_inputs=[
            XauAcceptanceInput(
                wall_id="wall_2400_call",
                zone_id="zone_2400",
                wall_level=2393.0,
                high=2408.0,
                low=2392.0,
                close=2405.0,
                next_bar_open=2406.0,
                buffer_points=2.0,
            )
        ],
        event_risk_state=XauEventRiskState.UNKNOWN,
        max_total_risk_per_idea=0.01,
        max_recovery_legs=1,
        minimum_rr=1.0,
        wall_buffer_points=2.0,
        research_only_acknowledged=True,
    )


def sample_xau_freshness_result() -> XauFreshnessResult:
    return XauFreshnessResult(
        state=XauFreshnessState.VALID,
        age_minutes=5.0,
        confidence_label=XauConfidenceLabel.HIGH,
        notes=["Synthetic freshness context for tests."],
    )


def sample_xau_vol_regime_result() -> XauVolRegimeResult:
    return XauVolRegimeResult(
        realized_volatility=0.12,
        vrp=0.04,
        vrp_regime=XauVrpRegime.IV_PREMIUM,
        iv_edge_state=XauIvEdgeState.INSIDE,
        rv_extension_state=XauRvExtensionState.INSIDE,
        confidence_label=XauConfidenceLabel.MEDIUM,
        notes=["Synthetic volatility context for tests."],
    )


def sample_xau_open_regime_result() -> XauOpenRegimeResult:
    return XauOpenRegimeResult(
        open_side=XauOpenSide.ABOVE_OPEN,
        open_distance_points=7.0,
        open_flip_state=XauOpenFlipState.NO_FLIP,
        open_as_support_or_resistance=XauOpenSupportResistance.SUPPORT_TEST,
        confidence_label=XauConfidenceLabel.HIGH,
        notes=["Synthetic open-regime context for tests."],
    )


def sample_xau_acceptance_result() -> XauAcceptanceResult:
    return XauAcceptanceResult(
        wall_id="wall_2400_call",
        zone_id="zone_2400",
        accepted_beyond_wall=False,
        wick_rejection=True,
        failed_breakout=False,
        confirmed_breakout=False,
        direction=XauAcceptanceDirection.ABOVE,
        confidence_label=XauConfidenceLabel.HIGH,
        notes=["Synthetic candle reaction context for tests."],
    )


def sample_feature006_xau_report() -> XauVolOiReport:
    request = XauVolOiReportRequest(
        options_oi_file_path="C:/synthetic/xau_options.csv",
        spot_reference=XauReferencePrice(
            source="synthetic",
            symbol="XAUUSD",
            price=2403.0,
            reference_type=XauReferenceType.SPOT,
        ),
        futures_reference=XauReferencePrice(
            source="synthetic",
            symbol="GC",
            price=2410.0,
            reference_type=XauReferenceType.FUTURES,
        ),
    )
    return XauVolOiReport(
        report_id="xau_vol_oi_synthetic_20260512",
        status=XauReportStatus.COMPLETED,
        created_at=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
        session_date=date(2026, 5, 12),
        request=request,
        source_validation=XauOptionsImportReport(
            file_path="C:/synthetic/xau_options.csv",
            is_valid=True,
            source_row_count=2,
            accepted_row_count=2,
            rejected_row_count=0,
        ),
        basis_snapshot=XauBasisSnapshot(
            basis=7.0,
            basis_source=XauBasisSource.COMPUTED,
            futures_reference=request.futures_reference,
            spot_reference=request.spot_reference,
            timestamp_alignment_status=XauTimestampAlignmentStatus.ALIGNED,
            mapping_available=True,
        ),
        expected_range=XauExpectedRange(
            source=XauVolatilitySource.IV,
            reference_price=2403.0,
            expected_move=50.0,
            lower_1sd=2353.0,
            upper_1sd=2453.0,
            days_to_expiry=7,
        ),
        source_row_count=2,
        accepted_row_count=2,
        rejected_row_count=0,
        wall_count=1,
        zone_count=1,
        walls=[
            XauOiWall(
                wall_id="wall_2400_call",
                expiry=date(2026, 5, 15),
                strike=2400.0,
                spot_equivalent_level=2393.0,
                basis=7.0,
                option_type=XauWallType.CALL,
                open_interest=12500.0,
                total_expiry_open_interest=25000.0,
                oi_share=0.5,
                expiry_weight=0.8,
                freshness_factor=1.1,
                wall_score=0.44,
                freshness_status=XauFreshnessFactorStatus.CONFIRMED,
            )
        ],
        zones=[
            XauZone(
                zone_id="zone_2400",
                zone_type=XauZoneType.RESISTANCE_CANDIDATE,
                level=2393.0,
                lower_bound=2391.0,
                upper_bound=2395.0,
                linked_wall_ids=["wall_2400_call"],
                wall_score=0.44,
                confidence=XauZoneConfidence.MEDIUM,
                no_trade_warning=False,
                notes=["Synthetic feature 006 zone for reaction tests."],
            )
        ],
        warnings=["Synthetic feature 006 report for tests."],
        limitations=[],
        missing_data_instructions=[],
    )
