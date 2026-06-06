import polars as pl

from research_xau_vol_oi.guru_rule_backtest_lab import (
    build_formation_test_results,
    build_guru_rule_backtest_lab,
    build_guru_rule_library,
    build_range_period_scorecard,
    build_rule_backtest_events,
    guru_rule_backtest_report_markdown,
    range_period_rule_backtest_report_markdown,
    summarize_rule_backtest_events,
)


def test_rule_library_contains_required_rule_families() -> None:
    library = build_guru_rule_library(
        knowledge_base=_knowledge_base(),
        dependency_matrix=_dependency_matrix(),
        availability=pl.DataFrame(),
    )

    families = set(library.get_column("rule_family").to_list())

    assert "PRICE_ONLY" in families
    assert "CME_MARKET_MAP" in families
    assert "CME_FILTER" in families
    assert "GURU_SAME_DAY_FILTER" in families
    assert library.height == 10


def test_price_only_rules_can_run_without_cme() -> None:
    result = build_guru_rule_backtest_lab(
        _inputs(price=_price_features(), cme=pl.DataFrame(), availability=pl.DataFrame())
    )

    modes = set(result.guru_rule_backtest_events.get_column("mode").to_list())

    assert "PRICE_ONLY_RULES" in modes
    assert "CME_PILOT_RULES" not in modes
    assert result.guru_rule_backtest_events.filter(pl.col("rule_id") == "NO_TRADE_MIDDLE_RANGE").height > 0


def test_cme_pilot_rules_run_only_when_cme_data_exists() -> None:
    no_cme = build_rule_backtest_events(
        rule_library=_library(),
        price_features=_price_features(),
        cme_replay=pl.DataFrame(),
        transcript_availability=pl.DataFrame(),
        same_day_matches=pl.DataFrame(),
    )
    with_cme = build_rule_backtest_events(
        rule_library=_library(),
        price_features=_price_features(),
        cme_replay=_cme_replay(),
        transcript_availability=pl.DataFrame(),
        same_day_matches=pl.DataFrame(),
    )

    assert no_cme.filter(pl.col("mode") == "CME_PILOT_RULES").height == 0
    assert with_cme.filter(pl.col("mode") == "CME_PILOT_RULES").height > 0


def test_same_day_confirmed_mode_refuses_unknown_transcript_timing() -> None:
    events = build_rule_backtest_events(
        rule_library=_library(),
        price_features=_price_features(),
        cme_replay=pl.DataFrame(),
        transcript_availability=_availability(confirmed=False),
        same_day_matches=_same_day_matches(),
    )
    summary = summarize_rule_backtest_events(events, rule_library=_library())
    row = summary.filter(pl.col("rule_id") == "GURU_SAME_DAY_FILTER_CONFIRMED").row(
        0,
        named=True,
    )

    assert events.filter(pl.col("mode") == "SAME_DAY_CONFIRMED_GURU_RULES").height == 0
    assert row["recommended_next_action"] == "WAIT_FOR_TRANSCRIPT_METADATA"


def test_historical_playbook_mode_emits_leakage_warning() -> None:
    events = build_rule_backtest_events(
        rule_library=_library(),
        price_features=_price_features(),
        cme_replay=pl.DataFrame(),
        transcript_availability=pl.DataFrame(),
        same_day_matches=pl.DataFrame(),
    )
    formation = build_formation_test_results(
        rule_library=_library(),
        events=events,
    )

    assert events.filter(pl.col("mode") == "HISTORICAL_PLAYBOOK_RULES").height > 0
    assert formation.filter(pl.col("leakage_warning")).height > 0


def test_rule_first_seen_date_prevents_future_transcript_leakage() -> None:
    library = _library().with_columns(
        pl.when(pl.col("rule_id") == "NO_TRADE_MIDDLE_RANGE")
        .then(pl.lit("2026-05-99"))
        .otherwise(pl.col("first_seen_date"))
        .alias("first_seen_date")
    )
    events = build_rule_backtest_events(
        rule_library=library,
        price_features=_price_features(),
        cme_replay=pl.DataFrame(),
        transcript_availability=pl.DataFrame(),
        same_day_matches=pl.DataFrame(),
    )

    historical_no_trade = events.filter(
        (pl.col("mode") == "HISTORICAL_PLAYBOOK_RULES")
        & (pl.col("rule_id") == "NO_TRADE_MIDDLE_RANGE")
    )

    assert historical_no_trade.height == 0


def test_formation_test_split_freezes_rules() -> None:
    events = build_rule_backtest_events(
        rule_library=_library(),
        price_features=_price_features(),
        cme_replay=pl.DataFrame(),
        transcript_availability=pl.DataFrame(),
        same_day_matches=pl.DataFrame(),
    )
    formation = build_formation_test_results(rule_library=_library(), events=events)

    assert formation.filter(~pl.col("rules_frozen_before_test")).height == 0
    assert {"formation_start", "test_start", "test_end"}.issubset(set(formation.columns))


def test_no_trade_filter_metrics_calculated() -> None:
    events = build_rule_backtest_events(
        rule_library=_library(),
        price_features=_price_features(),
        cme_replay=pl.DataFrame(),
        transcript_availability=pl.DataFrame(),
        same_day_matches=pl.DataFrame(),
    )
    summary = summarize_rule_backtest_events(events, rule_library=_library())
    row = summary.filter(pl.col("rule_id") == "NO_TRADE_MIDDLE_RANGE").row(0, named=True)

    assert row["event_count"] > 0
    assert row["blocked_trade_count"] > 0
    assert row["net_filter_value_proxy"] is not None


def test_market_map_metrics_calculated() -> None:
    events = build_rule_backtest_events(
        rule_library=_library(),
        price_features=_price_features(),
        cme_replay=_cme_replay(),
        transcript_availability=pl.DataFrame(),
        same_day_matches=pl.DataFrame(),
    )
    summary = summarize_rule_backtest_events(events, rule_library=_library())
    row = summary.filter(pl.col("rule_id") == "OI_WALL_WATCH_ZONE").row(0, named=True)

    assert row["event_count"] > 0
    assert row["wall_touch_rate"] is not None
    assert row["wall_rejection_rate"] is not None


def test_range_period_selection_works() -> None:
    result = build_guru_rule_backtest_lab(
        _inputs(price=_price_features(), cme=_cme_replay(), availability=pl.DataFrame()),
        date_start="2026-05-14",
        date_end="2026-05-14",
    )
    scorecard = build_range_period_scorecard(
        rule_library=result.guru_rule_library,
        events=result.guru_rule_backtest_events,
        cme_replay=_cme_replay(),
        price_features=_price_features(),
        availability=pl.DataFrame(),
        date_start="2026-05-14",
        date_end="2026-05-14",
    )

    row = scorecard.row(0, named=True)

    assert row["date_start"] == "2026-05-14"
    assert row["date_end"] == "2026-05-14"


def test_report_does_not_claim_profitability() -> None:
    result = build_guru_rule_backtest_lab(
        _inputs(price=_price_features(), cme=_cme_replay(), availability=pl.DataFrame())
    )
    markdown = guru_rule_backtest_report_markdown(result).lower()

    assert "profitable" not in markdown
    assert "safe to trade" not in markdown
    assert "live ready" not in markdown


def test_redacted_paths_only() -> None:
    scorecard = pl.DataFrame(
        [
            {
                "date_start": "2026-05-14",
                "date_end": "2026-05-14",
                "data_available": r"C:\Users\example\secret.parquet",
                "rule_modes_available": "PRICE_ONLY_RULES",
                "best_supported_rule": "NO_TRADE_MIDDLE_RANGE",
                "weakest_rule": "",
                "rules_blocked_by_missing_data": "",
                "whether_metadata_is_needed": True,
                "whether_more_cme_is_needed": True,
                "whether_result_is_pilot_only": True,
            }
        ]
    )

    markdown = range_period_rule_backtest_report_markdown(scorecard)

    assert r"C:\Users" not in markdown
    assert "<REDACTED_PATH>" in markdown


def _library() -> pl.DataFrame:
    return build_guru_rule_library(
        knowledge_base=_knowledge_base(),
        dependency_matrix=_dependency_matrix(),
        availability=_availability(confirmed=False),
    )


def _inputs(
    *,
    price: pl.DataFrame,
    cme: pl.DataFrame,
    availability: pl.DataFrame,
) -> dict[str, pl.DataFrame]:
    return {
        "guru_logic_knowledge_base": _knowledge_base(),
        "guru_logic_data_dependency_matrix": _dependency_matrix(),
        "same_day_playbook_matches": _same_day_matches(),
        "transcript_availability_classification_after_metadata": availability,
        "current_week_cme_guru_replay": cme,
        "xau_feature_table": price,
    }


def _price_features() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "timestamp": "2026-05-14T04:00:00",
                "session_date": "2026-05-14",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "session_open": 100.0,
                "one_sd_remaining": 2.0,
                "sigma_position": 0.0,
                "bb_upper": 105.0,
                "bb_lower": 95.0,
            },
            {
                "timestamp": "2026-05-14T04:15:00",
                "session_date": "2026-05-14",
                "open": 100.0,
                "high": 106.0,
                "low": 100.0,
                "close": 104.0,
                "session_open": 100.0,
                "one_sd_remaining": 2.0,
                "sigma_position": 1.2,
                "bb_upper": 105.0,
                "bb_lower": 95.0,
            },
            {
                "timestamp": "2026-05-14T04:30:00",
                "session_date": "2026-05-14",
                "open": 104.0,
                "high": 108.0,
                "low": 103.0,
                "close": 106.0,
                "session_open": 100.0,
                "one_sd_remaining": 2.0,
                "sigma_position": 1.6,
                "bb_upper": 105.0,
                "bb_lower": 95.0,
            },
            {
                "timestamp": "2026-05-14T04:45:00",
                "session_date": "2026-05-14",
                "open": 106.0,
                "high": 109.0,
                "low": 105.0,
                "close": 107.0,
                "session_open": 100.0,
                "one_sd_remaining": 2.0,
                "sigma_position": 1.8,
                "bb_upper": 105.0,
                "bb_lower": 95.0,
            },
            {
                "timestamp": "2026-05-15T04:00:00",
                "session_date": "2026-05-15",
                "open": 107.0,
                "high": 107.0,
                "low": 93.0,
                "close": 96.0,
                "session_open": 107.0,
                "one_sd_remaining": 3.0,
                "sigma_position": -1.4,
                "bb_upper": 112.0,
                "bb_lower": 95.0,
            },
            {
                "timestamp": "2026-05-15T04:15:00",
                "session_date": "2026-05-15",
                "open": 96.0,
                "high": 97.0,
                "low": 90.0,
                "close": 94.0,
                "session_open": 107.0,
                "one_sd_remaining": 3.0,
                "sigma_position": -1.8,
                "bb_upper": 112.0,
                "bb_lower": 95.0,
            },
        ]
    )


def _cme_replay() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-14",
                "oi_available": True,
                "basis_available": True,
                "iv_available": True,
                "squeeze_or_pin_logic_active": True,
                "touched_wall": True,
                "rejected_wall": True,
                "accepted_wall": False,
                "broke_range": False,
                "stayed_inside_range": True,
            }
        ]
    )


def _availability(*, confirmed: bool) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": "2026-05-14",
                "resolved_market_session_date": "2026-05-14",
                "availability_relation": "DURING_SESSION" if confirmed else "UNKNOWN",
                "can_use_as_same_session_filter": confirmed,
                "can_use_as_same_session_market_map": confirmed,
            }
        ]
    )


def _same_day_matches() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "clean_transcript_id": "clean_1",
                "transcript_date": "2026-05-14",
                "replay_date": "2026-05-14",
                "usable_as_filter": True,
                "usable_as_market_map": True,
            }
        ]
    )


def _knowledge_base() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "logic_id": "glkb_no_trade_discipline",
                "logic_name": "No-trade discipline",
                "logic_type": "NO_TRADE_FILTER",
                "first_seen_date": "2023-03-30",
            },
            {
                "logic_id": "glkb_oi_wall",
                "logic_name": "Open-interest wall zone",
                "logic_type": "OI_WALL_ZONE",
                "first_seen_date": "2023-05-16",
            },
            {
                "logic_id": "glkb_rejection_confirmation",
                "logic_name": "Rejection confirmation",
                "logic_type": "REJECTION_CONFIRMATION",
                "first_seen_date": "2024-07-09",
            },
            {
                "logic_id": "glkb_acceptance_close_confirmation",
                "logic_name": "Acceptance confirmation",
                "logic_type": "ACCEPTANCE_CONFIRMATION",
                "first_seen_date": "2024-07-09",
            },
            {
                "logic_id": "glkb_squeeze_risk",
                "logic_name": "Squeeze risk",
                "logic_type": "SQUEEZE_RISK",
                "first_seen_date": "2023-11-08",
            },
        ]
    )


def _dependency_matrix() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "logic_id": "glkb_oi_wall",
                "requires_basis": True,
                "requires_cme_oi_by_strike": True,
                "requires_iv": False,
            },
            {
                "logic_id": "glkb_volatility_range",
                "requires_basis": False,
                "requires_cme_oi_by_strike": False,
                "requires_iv": True,
            },
        ]
    )
