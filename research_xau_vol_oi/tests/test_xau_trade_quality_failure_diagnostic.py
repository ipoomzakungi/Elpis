from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.xau_trade_quality_failure_diagnostic import (
    build_bucket_inversion_audit,
    build_component_failure_audit,
    build_failure_decision,
    build_forward_join_audit,
    report_text_is_safe,
    run_xau_trade_quality_failure_diagnostic,
)
from research_xau_vol_oi.xau_trade_quality_forward_monitor import stable_score_config_hash


def test_high_score_underperformance_is_detected() -> None:
    bucket = build_bucket_inversion_audit(
        forward_monitor=_monitor_rows(high_returns=[-2.0] * 30, low_returns=[-1.0] * 30)
    )
    decision = build_failure_decision(
        bucket_inversion=bucket,
        component_failure=build_component_failure_audit(forward_monitor=pl.DataFrame()),
        join_alignment=_empty_join_audit(),
    )
    row = decision.row(0, named=True)

    assert row["high_score_underperformed"]
    assert row["final_recommendation"] == "SCORE_NOT_USEFUL_YET"


def test_outlier_driven_underperformance_is_flagged() -> None:
    bucket = build_bucket_inversion_audit(
        forward_monitor=_monitor_rows(high_returns=[10.0, 10.0, 10.0, -100.0], low_returns=[-10.0] * 4)
    )
    decision = build_failure_decision(
        bucket_inversion=bucket,
        component_failure=build_component_failure_audit(forward_monitor=pl.DataFrame()),
        join_alignment=_empty_join_audit(),
    )
    high_row = bucket.filter(pl.col("bucket") == "ALLOW_RESEARCH").row(0, named=True)
    decision_row = decision.row(0, named=True)

    assert high_row["outlier_count"] == 1
    assert "OUTLIER_CHECK_REQUIRED" in high_row["reason_bucket_underperformed"]
    assert decision_row["outlier_driven"]


def test_tiny_sample_outputs_needs_more_forward_data() -> None:
    bucket = build_bucket_inversion_audit(
        forward_monitor=_monitor_rows(high_returns=[-2.0, -3.0], low_returns=[-1.0] * 30)
    )
    decision = build_failure_decision(
        bucket_inversion=bucket,
        component_failure=build_component_failure_audit(forward_monitor=pl.DataFrame()),
        join_alignment=_empty_join_audit(),
    )

    assert decision.row(0, named=True)["final_recommendation"] == "NEEDS_MORE_FORWARD_DATA"


def test_join_error_outputs_bug_fix_required() -> None:
    join = build_forward_join_audit(
        score_rows=pl.DataFrame(),
        forward_monitor=pl.DataFrame(),
        promoted_outcomes=_promoted_outcome_rows(),
    )
    decision = build_failure_decision(
        bucket_inversion=build_bucket_inversion_audit(forward_monitor=_monitor_rows()),
        component_failure=build_component_failure_audit(forward_monitor=pl.DataFrame()),
        join_alignment=join,
    )

    assert join.filter((pl.col("severity") == "ERROR") & (pl.col("affected_rows") > 0)).height >= 1
    assert decision.row(0, named=True)["final_recommendation"] == "BUG_FIX_REQUIRED"


def test_component_wrong_sign_warning_generated() -> None:
    monitor = _component_wrong_sign_rows()

    component = build_component_failure_audit(forward_monitor=monitor)
    row = component.filter(pl.col("component_name") == "acceptance_breakout_component").row(
        0,
        named=True,
    )

    assert row["effect_direction"] == "HARMFUL"
    assert row["possible_issue"] == "WRONG_SIGN"
    assert row["recommended_action"] == "QUARANTINE_COMPONENT"


def test_no_weights_changed(tmp_path: Path) -> None:
    before = stable_score_config_hash()

    run_xau_trade_quality_failure_diagnostic(
        output_dir=_write_failure_inputs(tmp_path),
    )

    assert stable_score_config_hash() == before


def test_report_never_outputs_buy_or_sell(tmp_path: Path) -> None:
    output = _write_failure_inputs(tmp_path)

    run_xau_trade_quality_failure_diagnostic(output_dir=output)
    text = (output / "xau_score_failure_decision.md").read_text(encoding="utf-8")

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()
    assert report_text_is_safe(text)


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    output = _write_failure_inputs(tmp_path)

    run_xau_trade_quality_failure_diagnostic(output_dir=output)
    text = (output / "xau_score_bucket_inversion_audit.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert "guaranteed edge" not in text.lower()
    assert report_text_is_safe(text)


def test_reports_use_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_failure_inputs(tmp_path)

    run_xau_trade_quality_failure_diagnostic(output_dir=output)
    text = (output / "xau_score_forward_join_audit.md").read_text(encoding="utf-8")

    assert str(tmp_path) not in text
    assert "C:" not in text
    assert report_text_is_safe(text)


def _write_failure_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _score_rows().write_csv(output / "xau_trade_quality_score.csv")
    _monitor_rows(high_returns=[-2.0, -3.0], low_returns=[-1.0] * 10).write_csv(
        output / "xau_trade_quality_forward_monitor.csv"
    )
    _promoted_outcome_rows().write_csv(output / "forward_evidence_outcomes_dukascopy_promoted.csv")
    pl.DataFrame([{"journal_id": "j1", "session_date": "2026-05-26"}]).write_csv(
        output / "dukascopy_forward_event_level_outcomes.csv"
    )
    _price_frame().write_parquet(output / "dukascopy_xau_15m.parquet")
    _price_frame().write_parquet(output / "dukascopy_xau_1h.parquet")
    _price_frame().write_parquet(output / "dukascopy_xau_4h.parquet")
    return output


def _monitor_rows(
    *,
    high_returns: list[float] | None = None,
    low_returns: list[float] | None = None,
) -> pl.DataFrame:
    high_returns = high_returns or [-2.0] * 4
    low_returns = low_returns or [-1.0] * 4
    rows = []
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    for index, value in enumerate(low_returns):
        rows.append(
            _monitor_row(
                start + timedelta(minutes=index),
                bucket="WATCH_ONLY",
                score=47,
                active_components="data_quality_component;guru_filter_component",
                outcome_return=value,
            )
        )
    for index, value in enumerate(high_returns):
        rows.append(
            _monitor_row(
                start + timedelta(hours=1, minutes=index),
                bucket="ALLOW_RESEARCH",
                score=77,
                active_components="data_quality_component;acceptance_breakout_component",
                outcome_return=value,
            )
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _component_wrong_sign_rows() -> pl.DataFrame:
    rows = []
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    for index in range(60):
        rows.append(
            _monitor_row(
                start + timedelta(minutes=index),
                bucket="ALLOW_RESEARCH",
                score=77,
                active_components="acceptance_breakout_component",
                outcome_return=-2.0,
            )
        )
    for index in range(60):
        rows.append(
            _monitor_row(
                start + timedelta(hours=2, minutes=index),
                bucket="WATCH_ONLY",
                score=47,
                active_components="data_quality_component",
                outcome_return=1.0,
            )
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _monitor_row(
    timestamp: datetime,
    *,
    bucket: str,
    score: int,
    active_components: str,
    outcome_return: float,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "session_date": timestamp.date().isoformat(),
        "timeframe": "15m",
        "score": score,
        "score_bucket": bucket,
        "active_components": active_components,
        "blocked_reasons": "",
        "data_quality": "OK",
        "outcome_status": "RESOLVED",
        "outcome_return": outcome_return,
        "mfe": max(outcome_return, 0.0),
        "mae": min(outcome_return, 0.0),
        "filter_helped": False,
        "false_block": False,
    }


def _promoted_outcome_rows() -> pl.DataFrame:
    timestamp = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "journal_id": "j1",
                "observation_timestamp": timestamp,
                "session_date": "2026-05-26",
                "outcome_window": "30m",
                "source_interval": "15m",
                "window_start": timestamp,
                "window_end": timestamp + timedelta(minutes=30),
                "close_return": -1.0,
            }
        ],
        infer_schema_length=None,
    )


def _score_rows() -> pl.DataFrame:
    timestamp = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": timestamp,
                "timeframe": "15m",
                "score_bucket": "WATCH_ONLY",
                "trade_quality_score": 47,
            }
        ],
        infer_schema_length=None,
    )


def _price_frame() -> pl.DataFrame:
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            }
            for index in range(12)
        ],
        infer_schema_length=None,
    )


def _empty_join_audit() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "issue_type": "none",
                "affected_rows": 0,
                "severity": "INFO",
                "recommended_fix": "No action from this check.",
            }
        ],
        infer_schema_length=None,
    )
