import polars as pl

from research_xau_vol_oi.guru_logic_knowledge_base import (
    MINIMUM_VALIDATION_DAYS,
    build_guru_logic_knowledge_base,
    guru_logic_knowledge_base_markdown,
)


def _suggestions() -> pl.DataFrame:
    rows = []
    specs = [
        ("t1", "2026-05-01", "OI_WALL", "OI wall 2400 is the zone to watch."),
        ("t2", "2026-05-02", "OI_WALL", "Watch the OI wall before trusting reaction."),
        ("t3", "2026-05-03", "IV_EXPECTED_MOVE", "Use IV range before judging stretch."),
        ("t4", "2026-05-04", "IV_EXPECTED_MOVE", "Expected move defines the range."),
        ("t5", "2026-05-05", "NO_TRADE_DISCIPLINE", "No trade in the middle unless context improves."),
        ("t6", "2026-05-06", "NO_TRADE_DISCIPLINE", "Wait when data is stale or unclear."),
    ]
    for transcript_id, date, tag, excerpt in specs:
        rows.append(
            {
                "episode_id": f"ep_{transcript_id}_{tag}",
                "transcript_id": transcript_id,
                "transcript_date": date,
                "availability_timestamp": f"{date}T21:01:00Z",
                "source_excerpt": excerpt,
                "normalized_english_summary": excerpt,
                "rule_tag": tag,
                "rule_type": "MARKET_MAP",
                "action_bias": "WATCH_ONLY",
                "condition_text": excerpt,
                "suggested_guru_logic_type": "",
                "has_clear_condition": True,
                "has_clear_level": tag == "OI_WALL",
                "confidence_score": 0.8,
            }
        )
    return pl.DataFrame(rows)


def _cme_days(days: int, *, all_fields: bool = True) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": f"2026-05-{index + 1:02d}",
                "has_xau_spot_price": all_fields,
                "has_gc_futures_price": all_fields,
                "has_basis": all_fields,
                "has_option_oi_by_strike": all_fields,
                "has_option_oi_change": all_fields,
                "has_option_volume": all_fields,
                "has_option_iv": all_fields,
                "has_option_settlement": all_fields,
                "has_macro_event_flag": all_fields,
                "complete_validation_grade": all_fields,
            }
            for index in range(days)
        ]
    )


def _inputs(*, cme_days: int = 0, price_data: bool = True, all_fields: bool = True):
    inputs = {"guru_full_context_review_suggestions": _suggestions()}
    if cme_days:
        inputs["cme_validation_grade_days"] = _cme_days(cme_days, all_fields=all_fields)
    if price_data:
        inputs["xau_vol_oi_validation_dataset"] = pl.DataFrame(
            {"timestamp": ["2026-05-01T00:00:00Z"], "close": [2400.0]}
        )
    return inputs


def _row(frame: pl.DataFrame, logic_id: str) -> dict:
    rows = frame.filter(pl.col("logic_id") == logic_id).to_dicts()
    assert rows
    return rows[0]


def test_logic_extraction_does_not_require_cme_data() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=0, price_data=False))

    assert result.knowledge_base.height >= 3
    assert "glkb_oi_wall" in set(result.knowledge_base.get_column("logic_id").to_list())


def test_validation_status_blocked_when_validation_days_below_threshold() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=2))
    oi_wall = _row(result.knowledge_base, "glkb_oi_wall")

    assert result.current_available_validation_days == 2
    assert oi_wall["validation_status"] == "VALIDATION_BLOCKED_BY_DATA"


def test_oi_wall_logic_requires_oi_by_strike_and_basis() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=2))
    deps = _row(result.dependency_matrix, "glkb_oi_wall")

    assert deps["requires_cme_oi_by_strike"] is True
    assert deps["requires_basis"] is True
    assert deps["requires_xau_spot"] is True


def test_volatility_range_logic_requires_iv() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=2))
    deps = _row(result.dependency_matrix, "glkb_iv_expected_move")

    assert deps["requires_iv"] is True
    assert deps["requires_xau_spot"] is True


def test_no_trade_filter_can_be_price_only_pilot_but_not_full_cme_validated() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=2, price_data=True))
    logic = _row(result.knowledge_base, "glkb_no_trade_discipline")
    deps = _row(result.dependency_matrix, "glkb_no_trade_discipline")

    assert logic["validation_status"] == "READY_FOR_PRICE_ONLY_TEST"
    assert "Only 2 validation-grade CME days" in deps["validation_blocker"]


def test_priority_ranking_handles_missing_cme_data() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=0, price_data=False, all_fields=False))

    assert result.priority_rank.height >= 3
    assert set(result.priority_rank.get_column("recommended_action")).issubset(
        {
            "USE_AS_PLAYBOOK_CONTEXT_NOW",
            "TEST_PRICE_ONLY_NOW",
            "TEST_WITH_CURRENT_CME_PILOT",
            "WAIT_FOR_MORE_CME_DATA",
            "COLLECT_REQUIRED_DATA_FIRST",
            "IGNORE_OR_REJECT",
        }
    )


def test_collection_plan_includes_critical_missing_sources() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=0, price_data=False, all_fields=False))
    critical = result.collection_plan.filter(pl.col("priority") == "CRITICAL")

    names = set(critical.get_column("source_name").to_list())
    assert "XAU/USD intraday spot coverage" in names
    assert "GC futures price for basis" in names
    assert "CME Open Interest Heatmap/Profile by strike and expiry" in names


def test_no_profitability_claim_when_data_is_insufficient() -> None:
    result = build_guru_logic_knowledge_base(_inputs(cme_days=2))
    report = guru_logic_knowledge_base_markdown(result).lower()

    assert result.final_recommendation != "VALIDATION_READY"
    assert "profitable" not in report
    assert "makes money" not in report


def test_reports_use_redacted_paths_only() -> None:
    suggestions = _suggestions()
    suggestions = suggestions.with_columns(
        pl.when(pl.col("transcript_id") == "t1")
        .then(pl.lit(r"C:\Users\someone\private\transcript.txt says OI wall matters."))
        .otherwise(pl.col("source_excerpt"))
        .alias("source_excerpt")
    )
    result = build_guru_logic_knowledge_base(
        {
            "guru_full_context_review_suggestions": suggestions,
            "xau_vol_oi_validation_dataset": pl.DataFrame({"close": [2400.0]}),
        }
    )
    report = guru_logic_knowledge_base_markdown(result)

    assert r"C:\Users" not in report
    assert "<REDACTED_PATH>" in report
    assert result.minimum_validation_days == MINIMUM_VALIDATION_DAYS
