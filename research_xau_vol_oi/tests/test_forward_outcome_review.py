from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from research_xau_vol_oi.forward_outcome_review import (
    build_evidence_scorecard,
    build_filter_evidence,
    build_market_map_evidence,
    build_pending_outcome_summary,
    build_preview_outcome_audit,
    build_rule_evidence_summary,
    promote_safe_outcomes,
    run_forward_outcome_review,
)


RULEBOOK_HASH = "rulebook-v1"


def test_preview_outcome_audit_rejects_rows_with_missing_coverage() -> None:
    audit = build_preview_outcome_audit(
        preview=_preview_frame([_preview_row("30m")]),
        journal=_journal_frame(),
        coverage=_coverage_frame(coverage_30m=False),
        rule_library=_rule_library(),
        expected_rulebook_hash=RULEBOOK_HASH,
    )

    row = audit.row(0, named=True)
    assert row["coverage_passed"] is False
    assert row["safe_to_promote"] is False
    assert "missing_coverage" in row["reject_reason"]


def test_preview_outcome_audit_rejects_future_leakage_rows() -> None:
    preview = _preview_row("30m")
    preview["observation_timestamp"] = "2026-05-14T04:00:00Z"
    audit = build_preview_outcome_audit(
        preview=_preview_frame([preview]),
        journal=_journal_frame(),
        coverage=_coverage_frame(),
        rule_library=_rule_library(),
        expected_rulebook_hash=RULEBOOK_HASH,
    )

    row = audit.row(0, named=True)
    assert row["observation_precedes_outcome"] is False
    assert row["leakage_check_passed"] is False
    assert row["safe_to_promote"] is False


def test_strict_intraday_windows_require_intraday_or_resampled_intraday_ohlc() -> None:
    rows = [
        _preview_row("30m", source_interval="30m", quality="EXACT_FROM_1M"),
        _preview_row("1h", source_interval="1h", quality="EXACT_FROM_1M"),
        _preview_row("4h", source_interval="1h", quality="RESAMPLED_FROM_1H"),
    ]
    audit = build_preview_outcome_audit(
        preview=_preview_frame(rows),
        journal=_journal_frame(),
        coverage=_coverage_frame(),
        rule_library=_rule_library(),
        expected_rulebook_hash=RULEBOOK_HASH,
    )

    assert audit.get_column("used_intraday_ohlc").to_list() == [True, True, True]
    assert audit.get_column("safe_to_promote").to_list() == [True, True, True]


def test_daily_approximation_cannot_resolve_strict_intraday_windows() -> None:
    audit = build_preview_outcome_audit(
        preview=_preview_frame([
            _preview_row("30m", source_interval="1d", quality="DAILY_APPROX")
        ]),
        journal=_journal_frame(),
        coverage=_coverage_frame(),
        rule_library=_rule_library(),
        expected_rulebook_hash=RULEBOOK_HASH,
    )

    row = audit.row(0, named=True)
    assert row["used_daily_approx"] is True
    assert row["safe_to_promote"] is False
    assert "daily_approx_not_allowed_for_intraday_window" in row["reject_reason"]


def test_promotion_does_not_mutate_original_journal_observations() -> None:
    journal = _journal_frame()
    before = journal.to_dicts()
    audit = build_preview_outcome_audit(
        preview=_preview_frame([_preview_row("30m")]),
        journal=journal,
        coverage=_coverage_frame(),
        rule_library=_rule_library(),
        expected_rulebook_hash=RULEBOOK_HASH,
    )

    promote_safe_outcomes(
        preview=_preview_frame([_preview_row("30m")]),
        preview_audit=audit,
        existing_outcomes=pl.DataFrame(),
        promoted_at=datetime(2026, 5, 24, tzinfo=UTC),
        promotion_source_file="outputs/forward_evidence_outcomes_preview.csv",
    )

    assert journal.to_dicts() == before


def test_promotion_deduplicates_rows() -> None:
    audit = build_preview_outcome_audit(
        preview=_preview_frame([_preview_row("30m")]),
        journal=_journal_frame(),
        coverage=_coverage_frame(),
        rule_library=_rule_library(),
        expected_rulebook_hash=RULEBOOK_HASH,
    )
    batch, existing = promote_safe_outcomes(
        preview=_preview_frame([_preview_row("30m")]),
        preview_audit=audit,
        existing_outcomes=pl.DataFrame(),
        promoted_at=datetime(2026, 5, 24, tzinfo=UTC),
        promotion_source_file="outputs/forward_evidence_outcomes_preview.csv",
    )

    _, official = promote_safe_outcomes(
        preview=_preview_frame([_preview_row("30m")]),
        preview_audit=audit,
        existing_outcomes=existing.vstack(batch),
        promoted_at=datetime(2026, 5, 24, tzinfo=UTC),
        promotion_source_file="outputs/forward_evidence_outcomes_preview.csv",
    )

    assert official.height == 1


def test_rule_evidence_summary_labels_small_sample_as_too_early_or_pilot() -> None:
    promoted = _promoted_batch()

    summary = build_rule_evidence_summary(
        promoted_outcomes=promoted,
        rule_library=_rule_library(),
        rule_events=pl.DataFrame(),
    )

    assert summary.row(0, named=True)["sample_size_warning"] is True
    assert summary.row(0, named=True)["evidence_label"] in {
        "TOO_EARLY",
        "USEFUL_PILOT_EVIDENCE",
    }


def test_filter_evidence_computes_avoided_loss_and_false_block_rate() -> None:
    filter_summary = pl.DataFrame(
        [
            {
                "rule_id": "FILTER_RULE",
                "rule_type": "FILTER",
                "blocked_trade_count": 3,
                "avoided_losing_trade_count": 2,
                "avoided_winning_trade_count": 1,
                "net_filter_value_proxy": 1.0,
            }
        ]
    )

    evidence = build_filter_evidence(
        rule_library=_rule_library(),
        rule_backtest_summary=filter_summary,
        rule_events=pl.DataFrame(),
    )

    row = evidence.row(0, named=True)
    assert row["avoided_losing_count"] == 2
    assert row["blocked_winning_count"] == 1
    assert row["false_block_rate"] == 1 / 3
    assert row["useful_filter_candidate"] is True


def test_market_map_evidence_computes_wall_touch_rejection_acceptance() -> None:
    map_summary = pl.DataFrame(
        [
            {
                "rule_id": "MAP_RULE",
                "rule_type": "MARKET_MAP",
                "event_count": 4,
                "wall_touch_rate": 0.5,
                "wall_rejection_rate": 0.25,
                "wall_acceptance_rate": 0.25,
            }
        ]
    )

    evidence = build_market_map_evidence(
        rule_library=_rule_library(),
        rule_backtest_summary=map_summary,
        rule_events=pl.DataFrame(),
    )

    row = evidence.row(0, named=True)
    assert row["wall_touch_count"] == 2
    assert row["wall_rejection_count"] == 1
    assert row["wall_acceptance_count"] == 1
    assert row["map_hit_rate"] == 0.5


def test_pending_rows_summary_reports_missing_windows() -> None:
    partial = pl.DataFrame(
        [
            {
                "journal_id": "journal_pending",
                "observation_timestamp": "2026-05-24T10:00:00Z",
                "windows_remaining_pending": "30m|1h",
                "can_resolve_full": False,
                "reason": "Latest intraday OHLC is before observation.",
            }
        ]
    )
    coverage = _coverage_frame(journal_id="journal_pending", coverage_30m=False, coverage_1h=False)

    pending = build_pending_outcome_summary(
        partial_resolution=partial,
        coverage=coverage,
        rule_library=_rule_library(),
    )

    row = pending.row(0, named=True)
    assert row["missing_windows"] == "30m|1h"
    assert "Strict intraday" in row["next_data_needed"]


def test_evidence_scorecard_does_not_claim_profitability() -> None:
    scorecard = build_evidence_scorecard(
        preview=_preview_frame([_preview_row("30m")]),
        preview_audit=build_preview_outcome_audit(
            preview=_preview_frame([_preview_row("30m")]),
            journal=_journal_frame(),
            coverage=_coverage_frame(),
            rule_library=_rule_library(),
            expected_rulebook_hash=RULEBOOK_HASH,
        ),
        promoted_outcomes=_promoted_batch(),
        pending_summary=pl.DataFrame(),
        rule_summary=pl.DataFrame(),
        status_scorecard=pl.DataFrame(),
    )

    reason = scorecard.row(0, named=True)["reason"].lower()
    assert "profitable" not in reason
    assert "predicts price" not in reason
    assert "live ready" not in reason


def test_reports_use_redacted_paths(tmp_path: Path) -> None:
    output = tmp_path / "outputs"
    output.mkdir()
    _preview_frame([_preview_row("30m")]).write_csv(
        output / "forward_evidence_outcomes_preview.csv"
    )
    _coverage_frame().write_csv(output / "outcome_coverage_check.csv")
    pl.DataFrame(
        [
            {
                "journal_id": "journal_1",
                "observation_timestamp": "2026-05-14T03:08:00Z",
                "windows_remaining_pending": "",
                "can_resolve_full": True,
                "reason": "",
            }
        ]
    ).write_csv(output / "partial_outcome_resolution.csv")
    _rule_library().write_csv(output / "guru_rule_library.csv")
    (output / "frozen_rulebook_v1_hash.txt").write_text(RULEBOOK_HASH, encoding="utf-8")

    run_forward_outcome_review(
        output_dir=output,
        current_time=datetime(2026, 5, 24, tzinfo=UTC),
    )

    report_text = "\n".join(
        path.read_text(encoding="utf-8") for path in output.glob("forward_*.md")
    )
    assert str(tmp_path) not in report_text
    assert "C:\\" not in report_text


def _preview_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows, infer_schema_length=None)


def _preview_row(
    window: str,
    *,
    source_interval: str | None = None,
    quality: str = "EXACT_FROM_1M",
) -> dict[str, object]:
    start_by_window = {
        "30m": ("2026-05-14T03:08:00Z", "2026-05-14T03:38:00Z", "2026-05-14T03:30:00Z"),
        "1h": ("2026-05-14T03:08:00Z", "2026-05-14T04:08:00Z", "2026-05-14T04:00:00Z"),
        "4h": ("2026-05-14T03:08:00Z", "2026-05-14T07:08:00Z", "2026-05-14T07:00:00Z"),
        "session_close": (
            "2026-05-14T03:08:00Z",
            "2026-05-14T21:00:00Z",
            "2026-05-14T20:00:00Z",
        ),
        "next_day": ("2026-05-14T03:08:00Z", "2026-05-15T03:08:00Z", "2026-05-15T03:00:00Z"),
    }
    window_start, window_end, observed_end = start_by_window[window]
    return {
        "journal_id": "journal_1",
        "observation_timestamp": "2026-05-14T03:08:00Z",
        "trade_date": "2026-05-14",
        "session_date": "2026-05-14",
        "window": window,
        "window_start": window_start,
        "window_end": window_end,
        "outcome_status": "resolved_preview",
        "resolution_action": "preview_resolve",
        "source_symbol": "GC=F",
        "source_interval": source_interval or ("30m" if window == "30m" else "1h"),
        "quality": quality,
        "observed_start": window_start,
        "observed_end": observed_end,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 104.0,
        "row_count": 1,
        "notes": "Preview only.",
    }


def _coverage_frame(
    *,
    journal_id: str = "journal_1",
    coverage_30m: bool = True,
    coverage_1h: bool = True,
    coverage_4h: bool = True,
    coverage_session_close: bool = True,
    coverage_next_day: bool = True,
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "journal_id": journal_id,
                "observation_timestamp": "2026-05-14T03:08:00Z",
                "trade_date": "2026-05-14",
                "session_date": "2026-05-14",
                "coverage_30m": coverage_30m,
                "coverage_1h": coverage_1h,
                "coverage_4h": coverage_4h,
                "coverage_session_close": coverage_session_close,
                "coverage_next_day": coverage_next_day,
                "latest_available_ohlc_timestamp": "2026-05-14T21:00:00Z",
                "missing_coverage_reason": "",
                "next_check_recommended_at": "2026-05-15T22:00:00Z",
            }
        ],
        infer_schema_length=None,
    )


def _journal_frame() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "journal_id": "journal_1",
                "window": "30m",
                "rule_id": "RULE_1",
                "rule_name": "Rule one",
                "rule_family": "PRICE_ONLY",
                "signal_context": "FORWARD_TEST",
                "rule_type": "ENTRY_TRIGGER",
                "rulebook_hash": RULEBOOK_HASH,
            },
            {
                "journal_id": "journal_1",
                "window": "1h",
                "rule_id": "RULE_1",
                "rule_name": "Rule one",
                "rule_family": "PRICE_ONLY",
                "signal_context": "FORWARD_TEST",
                "rule_type": "ENTRY_TRIGGER",
                "rulebook_hash": RULEBOOK_HASH,
            },
            {
                "journal_id": "journal_1",
                "window": "4h",
                "rule_id": "RULE_1",
                "rule_name": "Rule one",
                "rule_family": "PRICE_ONLY",
                "signal_context": "FORWARD_TEST",
                "rule_type": "ENTRY_TRIGGER",
                "rulebook_hash": RULEBOOK_HASH,
            },
        ]
    )


def _rule_library() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "rule_id": "RULE_1",
                "rule_name": "Rule one",
                "rule_family": "PRICE_ONLY",
                "logic_source": "FORWARD_TEST",
                "rule_type": "ENTRY_TRIGGER",
            },
            {
                "rule_id": "FILTER_RULE",
                "rule_name": "Filter rule",
                "rule_family": "PRICE_ONLY",
                "logic_source": "FORWARD_TEST",
                "rule_type": "FILTER",
            },
            {
                "rule_id": "MAP_RULE",
                "rule_name": "Map rule",
                "rule_family": "CME_MARKET_MAP",
                "logic_source": "FORWARD_TEST",
                "rule_type": "MARKET_MAP",
            },
        ]
    )


def _promoted_batch() -> pl.DataFrame:
    audit = build_preview_outcome_audit(
        preview=_preview_frame([_preview_row("30m")]),
        journal=_journal_frame(),
        coverage=_coverage_frame(),
        rule_library=_rule_library(),
        expected_rulebook_hash=RULEBOOK_HASH,
    )
    batch, _ = promote_safe_outcomes(
        preview=_preview_frame([_preview_row("30m")]),
        preview_audit=audit,
        existing_outcomes=pl.DataFrame(),
        promoted_at=datetime(2026, 5, 24, tzinfo=UTC),
        promotion_source_file="outputs/forward_evidence_outcomes_preview.csv",
    )
    return batch
