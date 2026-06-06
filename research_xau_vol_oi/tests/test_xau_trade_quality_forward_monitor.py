from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.xau_trade_quality_forward_monitor import (
    build_bucket_stability,
    build_daily_watchlist,
    build_forward_monitor,
    bucket_order_pass,
    freeze_score_config,
    frozen_score_payload,
    report_text_is_safe,
    run_xau_trade_quality_forward_monitor,
    stable_score_config_hash,
)


def test_score_config_hash_is_stable() -> None:
    payload = frozen_score_payload()

    first = stable_score_config_hash(payload)
    second = stable_score_config_hash(frozen_score_payload())

    assert first == second
    assert payload["tuning_allowed"] is False
    assert payload["threshold_optimization_allowed"] is False


def test_v1_score_cannot_be_silently_overwritten(tmp_path: Path) -> None:
    first = freeze_score_config(
        output_dir=tmp_path,
        frozen_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    original_yaml = first.yaml_path.read_text(encoding="utf-8")

    second = freeze_score_config(
        output_dir=tmp_path,
        frozen_at=datetime(2026, 5, 2, tzinfo=UTC),
    )

    assert second.overwritten is False
    assert second.yaml_path.read_text(encoding="utf-8") == original_yaml


def test_bucket_ordering_calculation_works() -> None:
    stability = build_bucket_stability(
        replay_backtest=_replay_backtest(),
        forward_monitor=_forward_monitor_from_returns(
            {
                "BLOCK": [-2.0],
                "WATCH_ONLY": [-1.0],
                "ALLOW_RESEARCH": [1.0],
                "HIGH_QUALITY_RESEARCH": [2.0],
            }
        ),
    )

    assert bucket_order_pass(stability)
    assert stability.get_column("bucket_order_pass").to_list() == [True, True, True, True]


def test_high_score_bucket_must_be_compared_against_low_score_bucket() -> None:
    stability = build_bucket_stability(
        replay_backtest=_replay_backtest(),
        forward_monitor=_forward_monitor_from_returns(
            {
                "BLOCK": [1.0],
                "WATCH_ONLY": [1.0],
                "ALLOW_RESEARCH": [-1.0],
                "HIGH_QUALITY_RESEARCH": [-1.0],
            }
        ),
    )

    assert not bucket_order_pass(stability)


def test_no_tuning_occurs_in_frozen_config(tmp_path: Path) -> None:
    result = run_xau_trade_quality_forward_monitor(
        output_dir=_write_monitor_inputs(tmp_path),
        frozen_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    yaml_text = result.frozen_config.yaml_path.read_text(encoding="utf-8")

    assert "tuning_allowed: false" in yaml_text
    assert "threshold_optimization_allowed: false" in yaml_text
    assert result.frozen_config.config_hash == stable_score_config_hash()


def test_daily_watchlist_never_outputs_buy_or_sell(tmp_path: Path) -> None:
    output = _write_monitor_inputs(tmp_path)

    run_xau_trade_quality_forward_monitor(
        output_dir=output,
        frozen_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    text = (output / "xau_trade_quality_daily_watchlist.md").read_text(encoding="utf-8")
    csv_text = (output / "xau_trade_quality_daily_watchlist.csv").read_text(encoding="utf-8")

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()
    assert " buy " not in f" {csv_text.lower()} "
    assert " sell " not in f" {csv_text.lower()} "
    assert report_text_is_safe(text)


def test_cme_pilot_only_warning_preserved(tmp_path: Path) -> None:
    output = _write_monitor_inputs(tmp_path)

    run_xau_trade_quality_forward_monitor(
        output_dir=output,
        frozen_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    text = (output / "xau_trade_quality_score_v1.md").read_text(encoding="utf-8")

    assert "PILOT_ONLY" in text
    assert "CME OI/IV remains PILOT_ONLY" in text


def test_guru_context_cannot_create_signal_alone() -> None:
    watchlist = build_daily_watchlist(
        score_rows=_score_rows(guru_latest=True),
        price_frames={"15m": _price_frame()},
    )
    row = watchlist.row(0, named=True)

    assert row["journal_action"] == "WATCH_ONLY"
    assert row["score_bucket"] == "WATCH_ONLY"
    assert "ALLOW_RESEARCH_CANDIDATE" not in row["journal_action"]


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    output = _write_monitor_inputs(tmp_path)

    run_xau_trade_quality_forward_monitor(
        output_dir=output,
        frozen_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    text = (output / "xau_trade_quality_bucket_stability.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert "guaranteed edge" not in text.lower()
    assert report_text_is_safe(text)


def test_reports_use_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_monitor_inputs(tmp_path)

    run_xau_trade_quality_forward_monitor(
        output_dir=output,
        frozen_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    text = (output / "xau_trade_quality_forward_monitor.md").read_text(encoding="utf-8")

    assert str(tmp_path) not in text
    assert "C:" not in text
    assert report_text_is_safe(text)


def test_forward_monitor_uses_prior_score_without_recomputing() -> None:
    monitor = build_forward_monitor(
        score_rows=_score_rows(),
        promoted_outcomes=_promoted_outcomes(),
    )

    assert monitor.height == 4
    assert set(monitor.get_column("score_bucket").to_list()) == {
        "BLOCK",
        "WATCH_ONLY",
        "ALLOW_RESEARCH",
        "HIGH_QUALITY_RESEARCH",
    }


def _write_monitor_inputs(tmp_path: Path) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _score_rows().write_csv(output / "xau_trade_quality_score.csv")
    _replay_backtest().write_csv(output / "xau_trade_quality_score_backtest.csv")
    _score_ablation().write_csv(output / "xau_trade_quality_score_ablation.csv")
    _promoted_outcomes().write_csv(output / "forward_evidence_outcomes_dukascopy_promoted.csv")
    pl.DataFrame([{"independent_event_count": 4}]).write_csv(
        output / "dukascopy_forward_rule_governance.csv"
    )
    _price_frame().write_parquet(output / "dukascopy_xau_15m.parquet")
    _price_frame().write_parquet(output / "dukascopy_xau_1h.parquet")
    _price_frame().write_parquet(output / "dukascopy_xau_4h.parquet")
    return output


def _score_rows(*, guru_latest: bool = False) -> pl.DataFrame:
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    rows = [
        _score_row(
            start,
            bucket="BLOCK",
            score=25,
            positive="",
            negative="fee_spread_hurdle_component",
            blocked="fee/spread hurdle",
            label="BLOCKED_SPREAD_FEE",
        ),
        _score_row(
            start + timedelta(minutes=15),
            bucket="WATCH_ONLY",
            score=50,
            positive="rejection_after_touch_component",
            negative="open_distance_component",
            blocked="",
            label="WATCH_GURU_CONTEXT",
        ),
        _score_row(
            start + timedelta(minutes=30),
            bucket="ALLOW_RESEARCH",
            score=70,
            positive="acceptance_breakout_component",
            negative="",
            blocked="",
            label="ALLOW_RESEARCH_CANDIDATE",
        ),
        _score_row(
            start + timedelta(minutes=45),
            bucket="HIGH_QUALITY_RESEARCH",
            score=85,
            positive="acceptance_breakout_component;cme_wall_context_component",
            negative="",
            blocked="",
            label="ALLOW_RESEARCH_CANDIDATE",
        ),
    ]
    if guru_latest:
        rows.append(
            _score_row(
                start + timedelta(hours=1),
                bucket="WATCH_ONLY",
                score=52,
                positive="guru_filter_component",
                negative="",
                blocked="",
                label="WATCH_GURU_CONTEXT",
                source="GURU_CONTEXT",
                direction="NONE",
            )
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _score_row(
    timestamp: datetime,
    *,
    bucket: str,
    score: int,
    positive: str,
    negative: str,
    blocked: str,
    label: str,
    source: str = "PRICE_ONLY",
    direction: str = "LONG",
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "timeframe": "15m",
        "candidate_direction": direction,
        "base_candidate_source": source,
        "trade_quality_score": score,
        "score_bucket": bucket,
        "active_positive_components": positive,
        "active_negative_components": negative,
        "blocked_reasons": blocked,
        "watch_reasons": "watch context",
        "data_quality_notes": "OK",
        "final_label": label,
    }


def _promoted_outcomes() -> pl.DataFrame:
    start = datetime(2026, 5, 26, 0, 5, tzinfo=UTC)
    return pl.DataFrame(
        [
            _outcome(start, -1.5),
            _outcome(start + timedelta(minutes=15), -0.5),
            _outcome(start + timedelta(minutes=30), 1.0),
            _outcome(start + timedelta(minutes=45), 1.5),
        ],
        infer_schema_length=None,
    )


def _outcome(timestamp: datetime, close_return: float) -> dict[str, object]:
    return {
        "observation_timestamp": timestamp,
        "session_date": timestamp.date().isoformat(),
        "source_interval": "15m",
        "outcome_status": "RESOLVED",
        "close_return": close_return,
        "mfe": max(close_return, 0.0),
        "mae": min(close_return, 0.0),
    }


def _replay_backtest() -> pl.DataFrame:
    return pl.DataFrame(
        [
            _backtest_row("BLOCK", 20, -1.0),
            _backtest_row("WATCH_ONLY", 20, -0.5),
            _backtest_row("ALLOW_RESEARCH", 20, 0.5),
            _backtest_row("HIGH_QUALITY_RESEARCH", 20, 1.0),
        ],
        infer_schema_length=None,
    )


def _backtest_row(bucket: str, count: int, average_return: float) -> dict[str, object]:
    return {
        "score_bucket": bucket,
        "event_count": count,
        "trade_count": count,
        "average_return": average_return,
        "support_rate": 0.5,
        "failure_rate": 0.5,
        "average_mfe": max(average_return, 0.0),
        "average_mae": min(average_return, 0.0),
        "false_block_rate": 0.0 if bucket != "BLOCK" else 0.1,
    }


def _forward_monitor_from_returns(values: dict[str, list[float]]) -> pl.DataFrame:
    rows = []
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    for bucket, returns in values.items():
        for index, value in enumerate(returns):
            rows.append(
                {
                    "timestamp": start + timedelta(minutes=len(rows) * 15 + index),
                    "session_date": "2026-05-26",
                    "timeframe": "15m",
                    "score": 80 if bucket.startswith("HIGH") else 50,
                    "score_bucket": bucket,
                    "active_components": "acceptance_breakout_component",
                    "blocked_reasons": "",
                    "data_quality": "OK",
                    "outcome_status": "RESOLVED",
                    "outcome_return": value,
                    "mfe": max(value, 0.0),
                    "mae": min(value, 0.0),
                    "filter_helped": bucket == "BLOCK" and value <= 0,
                    "false_block": bucket == "BLOCK" and value > 0,
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None)


def _score_ablation() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "ablation": "without_acceptance_breakout",
                "event_count": 4,
                "score_monotonicity_change": -1.0,
                "expectancy_change": -0.2,
                "false_block_change": 0.0,
                "interpretation": "weakened",
            },
            {
                "ablation": "without_fee_spread_hurdle",
                "event_count": 4,
                "score_monotonicity_change": -1.0,
                "expectancy_change": 0.2,
                "false_block_change": 0.1,
                "interpretation": "blocking",
            },
        ],
        infer_schema_length=None,
    )


def _price_frame() -> pl.DataFrame:
    start = datetime(2026, 5, 26, 0, 0, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": start + timedelta(minutes=15 * index),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
            }
            for index in range(8)
        ],
        infer_schema_length=None,
    )
