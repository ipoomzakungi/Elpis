from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.xau_reaction import (
    XauConfidenceLabel,
    XauReactionLabel,
    XauReactionReport,
    XauReactionReportRequest,
    XauReactionReportStatus,
    XauReactionRow,
    XauRewardRiskState,
    XauRiskPlan,
)
from tests.helpers.test_xau_reaction_data import (
    sample_xau_acceptance_result,
    sample_xau_freshness_result,
    sample_xau_open_regime_result,
    sample_xau_reaction_report_request,
    sample_xau_vol_regime_result,
)


def test_reaction_label_enum_contains_required_six_labels():
    assert {label.value for label in XauReactionLabel} == {
        "REVERSAL_CANDIDATE",
        "BREAKOUT_CANDIDATE",
        "PIN_MAGNET",
        "SQUEEZE_RISK",
        "VACUUM_TO_NEXT_WALL",
        "NO_TRADE",
    }


def test_reaction_report_request_rejects_unsafe_ids_false_ack_and_extra_fields():
    with pytest.raises(ValidationError):
        XauReactionReportRequest(
            source_report_id="../xau_vol_oi",
            research_only_acknowledged=True,
        )
    with pytest.raises(ValidationError):
        XauReactionReportRequest(
            source_report_id="xau_vol_oi_safe",
            research_only_acknowledged=False,
        )
    with pytest.raises(ValidationError):
        XauReactionReportRequest(
            source_report_id="xau_vol_oi_safe",
            research_only_acknowledged=True,
            private_key="forbidden",
        )


def test_reaction_row_requires_no_trade_reason_for_no_trade_label():
    with pytest.raises(ValidationError):
        XauReactionRow(
            reaction_id="reaction_1",
            source_report_id="source_report_1",
            reaction_label=XauReactionLabel.NO_TRADE,
            confidence_label=XauConfidenceLabel.BLOCKED,
            freshness_state=sample_xau_freshness_result(),
            vol_regime_state=sample_xau_vol_regime_result(),
            open_regime_state=sample_xau_open_regime_result(),
        )

    row = XauReactionRow(
        reaction_id="reaction_1",
        source_report_id="source_report_1",
        reaction_label=XauReactionLabel.NO_TRADE,
        confidence_label=XauConfidenceLabel.BLOCKED,
        explanation_notes=["Synthetic no-trade test row."],
        no_trade_reasons=["Missing source context."],
        freshness_state=sample_xau_freshness_result(),
        vol_regime_state=sample_xau_vol_regime_result(),
        open_regime_state=sample_xau_open_regime_result(),
        acceptance_state=sample_xau_acceptance_result(),
    )

    assert row.research_only_warning


def test_risk_plan_rejects_entry_text_for_no_trade():
    with pytest.raises(ValidationError):
        XauRiskPlan(
            plan_id="plan_1",
            reaction_id="reaction_1",
            reaction_label=XauReactionLabel.NO_TRADE,
            entry_condition_text="Should not exist for no-trade.",
            rr_state=XauRewardRiskState.NOT_APPLICABLE,
        )


def test_reaction_report_rejects_negative_counts_and_unsafe_report_ids():
    request = sample_xau_reaction_report_request()
    with pytest.raises(ValidationError):
        XauReactionReport(
            report_id="bad/report",
            source_report_id=request.source_report_id,
            status=XauReactionReportStatus.BLOCKED,
            created_at=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
            request=request,
            source_wall_count=-1,
            freshness_state=sample_xau_freshness_result(),
            vol_regime_state=sample_xau_vol_regime_result(),
            open_regime_state=sample_xau_open_regime_result(),
        )
