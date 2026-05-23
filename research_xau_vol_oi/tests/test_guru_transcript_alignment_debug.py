from pathlib import Path

import polars as pl

from research_xau_vol_oi.guru_transcript_alignment_debug import (
    NO_SAME_DATE_REASON,
    OVERLAY_LABEL,
    build_guru_text_interpretation_audit,
    build_guru_transcript_alignment_debug,
    build_historical_guru_playbook_overlay,
    build_missing_xau_spot_basis_fetch_plan,
    build_transcript_coverage_by_cme_date,
    guru_text_interpretation_audit_markdown,
    run_guru_transcript_alignment_debug_layer,
)


def test_transcript_corpus_exists_but_same_date_missing_is_explained() -> None:
    alignment = build_transcript_coverage_by_cme_date(
        replay=_replay(["2026-05-14"]),
        manifest=_manifest(["2026-05-13"]),
        interpretation=pl.DataFrame(),
        knowledge_base=_knowledge_base(),
    )

    row = alignment.row(0, named=True)

    assert row["same_date_transcript_available"] is False
    assert row["reason_plain_english"] == NO_SAME_DATE_REASON


def test_nearest_transcript_before_after_calculation() -> None:
    alignment = build_transcript_coverage_by_cme_date(
        replay=_replay(["2026-05-14"]),
        manifest=_manifest(["2026-05-13", "2026-05-15"]),
        interpretation=pl.DataFrame(),
        knowledge_base=_knowledge_base(),
    )

    row = alignment.row(0, named=True)

    assert row["transcript_nearest_before_date"] == "2026-05-13"
    assert row["transcript_nearest_before_days_gap"] == 1
    assert row["transcript_nearest_after_date"] == "2026-05-15"
    assert row["transcript_nearest_after_days_gap"] == 1


def test_context_only_rule_is_not_treated_as_trade_signal() -> None:
    audit = build_guru_text_interpretation_audit(
        suggestions=pl.DataFrame(
            [
                {
                    "transcript_id": "t1",
                    "transcript_date": "2026-05-14",
                    "rule_tag": "OI_WALL",
                    "suggested_guru_logic_type": "OI_WALL_ZONE",
                    "suggested_decision": "SUGGEST_APPROVE_MARKET_MAP",
                    "has_clear_condition": True,
                    "has_clear_level": True,
                    "has_clear_target": False,
                    "has_clear_invalidation": False,
                    "has_direction_bias": False,
                    "usable_as_context": True,
                    "usable_as_market_map": True,
                    "usable_as_filter": False,
                    "usable_as_trade_rule": False,
                    "is_pre_event_logic": True,
                }
            ]
        ),
        episodes=pl.DataFrame(),
        knowledge_base=pl.DataFrame(),
    )

    row = audit.row(0, named=True)

    assert row["usable_as_market_map"] is True
    assert row["usable_as_trade_rule"] is False
    assert row["reason_not_trade_signal"] == "MARKET_MAP_ONLY"


def test_no_trade_filter_is_classified_as_filter_not_trade_rule() -> None:
    audit = build_guru_text_interpretation_audit(
        suggestions=pl.DataFrame(
            [
                {
                    "transcript_id": "t2",
                    "transcript_date": "2026-05-14",
                    "rule_tag": "NO_TRADE_DISCIPLINE",
                    "suggested_guru_logic_type": "NO_TRADE_FILTER",
                    "suggested_decision": "SUGGEST_APPROVE_FILTER",
                    "has_clear_condition": True,
                    "has_clear_level": False,
                    "has_clear_target": False,
                    "has_clear_invalidation": False,
                    "has_direction_bias": False,
                    "usable_as_context": True,
                    "usable_as_market_map": False,
                    "usable_as_filter": True,
                    "usable_as_trade_rule": False,
                    "is_pre_event_logic": True,
                }
            ]
        ),
        episodes=pl.DataFrame(),
        knowledge_base=pl.DataFrame(),
    )

    row = audit.row(0, named=True)

    assert row["usable_as_filter"] is True
    assert row["usable_as_trade_rule"] is False
    assert row["reason_not_trade_signal"] == "FILTER_ONLY"


def test_historical_playbook_overlay_is_labeled_separately_from_same_day_signal() -> None:
    overlay = build_historical_guru_playbook_overlay(
        replay=_replay(["2026-05-14"]),
        knowledge_base=_knowledge_base(),
        priority_rank=pl.DataFrame(
            [
                {
                    "logic_id": "glkb_no_trade_discipline",
                    "logic_name": "No-trade discipline",
                    "logic_type": "NO_TRADE_FILTER",
                    "priority_score": 0.4,
                }
            ]
        ),
        date_usability=pl.DataFrame(
            [{"trade_date": "2026-05-14", "has_macro_event_flag": False}]
        ),
    )

    labels = set(overlay.get_column("overlay_label").to_list())

    assert labels == {OVERLAY_LABEL}
    assert "HISTORICAL" in overlay.row(0, named=True)["overlay_label"]


def test_missing_xau_spot_basis_fetch_plan_includes_requested_dates() -> None:
    plan = build_missing_xau_spot_basis_fetch_plan(_replay(["2026-05-16", "2026-05-23"]))

    dates = set(plan.get_column("trade_date").to_list())

    assert {"2026-05-16", "2026-05-23"}.issubset(dates)


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    _write_minimal_outputs(tmp_path)

    result = run_guru_transcript_alignment_debug_layer(output_dir=tmp_path)
    report = "\n".join(
        [
            (tmp_path / "guru_transcript_alignment_debug.md").read_text(encoding="utf-8"),
            (tmp_path / "guru_text_interpretation_audit.md").read_text(encoding="utf-8"),
            (tmp_path / "guru_playbook_overlay_for_current_week.md").read_text(encoding="utf-8"),
            result.no_guru_context_explanation,
        ]
    ).lower()

    assert "profitable" not in report
    assert "safe to trade" not in report
    assert "live ready" not in report


def test_redacted_paths_only() -> None:
    audit = build_guru_text_interpretation_audit(
        suggestions=pl.DataFrame(
            [
                {
                    "transcript_id": r"C:\Users\example\secret\transcript.txt",
                    "transcript_date": "2026-05-14",
                    "rule_tag": "NO_TRADE_DISCIPLINE",
                    "suggested_guru_logic_type": "NO_TRADE_FILTER",
                    "suggested_decision": "SUGGEST_APPROVE_FILTER",
                    "has_clear_condition": True,
                    "usable_as_context": True,
                    "usable_as_filter": True,
                    "is_pre_event_logic": True,
                }
            ]
        ),
        episodes=pl.DataFrame(),
        knowledge_base=pl.DataFrame(),
    )
    markdown = guru_text_interpretation_audit_markdown(audit)

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def test_build_result_labels_playbook_overlay_when_no_same_date_context() -> None:
    result = build_guru_transcript_alignment_debug(
        {
            "transcript_corpus_manifest": _manifest(["2026-05-13"]),
            "current_week_cme_guru_replay": _replay(["2026-05-14"]),
            "guru_logic_knowledge_base": _knowledge_base(),
        }
    )

    assert result.transcript_corpus_exists is True
    assert result.same_date_transcripts_exist_for_current_replay is False
    assert result.final_recommendation == "TRANSCRIPTS_EXIST_PLAYBOOK_OVERLAY_READY"


def _write_minimal_outputs(root: Path) -> None:
    _manifest(["2026-05-13"]).write_csv(root / "transcript_corpus_manifest.csv")
    _replay(["2026-05-14"]).write_csv(root / "current_week_cme_guru_replay.csv")
    _knowledge_base().write_csv(root / "guru_logic_knowledge_base.csv")
    pl.DataFrame(
        [{"trade_date": "2026-05-14", "has_macro_event_flag": False}]
    ).write_csv(root / "current_cme_date_usability.csv")


def _manifest(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "source_id_hash": f"h{index}",
                "detected_date": trade_date,
                "redacted_file_path": "<REDACTED_PATH>/<TRANSCRIPT_FILE>.txt",
                "usable_for_logic_extraction": True,
            }
            for index, trade_date in enumerate(dates)
        ]
    )


def _knowledge_base() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "logic_id": "glkb_no_trade_discipline",
                "logic_name": "No-trade discipline",
                "logic_type": "NO_TRADE_FILTER",
                "transcript_count": 10,
            },
            {
                "logic_id": "glkb_basis_adjustment",
                "logic_name": "Basis-adjusted strike mapping",
                "logic_type": "BASIS_MAPPING",
                "transcript_count": 8,
            },
            {
                "logic_id": "glkb_oi_wall",
                "logic_name": "Open-interest wall zone",
                "logic_type": "OI_WALL_ZONE",
                "transcript_count": 8,
            },
        ]
    )


def _replay(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": trade_date,
                "spot_available": trade_date != "2026-05-23",
                "basis_available": trade_date != "2026-05-23",
                "iv_available": True,
                "oi_available": True,
                "oi_change_available": True,
                "option_volume_available": True,
                "futures_available": True,
                "wall_type": "SPOT_EQUIVALENT_LEVEL"
                if trade_date != "2026-05-23"
                else "FUTURES_STRIKE_LEVEL",
                "no_trade_filter_active": True,
            }
            for trade_date in dates
        ]
    )
