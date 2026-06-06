from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from research_xau_vol_oi.guru_semantic_reasoning_lab import (
    build_cme_only_rule_translation_from_guru,
    build_cme_wall_magnet_tp_backtest,
    build_dukascopy_sd_grid_backtest,
    build_sd_grid_rule_family,
    build_semantic_claims,
    build_transcript_semantic_segments,
    report_text_is_safe,
    run_guru_semantic_reasoning_lab,
)


def test_semantic_claims_require_source_excerpts() -> None:
    segments = build_transcript_semantic_segments(inputs=_inputs())
    claims = build_semantic_claims(segments=segments, inputs=_inputs())

    assert claims.height > 0
    assert all(bool(value) for value in claims.get_column("source_excerpt").to_list())


def test_wall_as_magnet_claim_extracted() -> None:
    claims = build_semantic_claims(
        segments=build_transcript_semantic_segments(inputs=_inputs()),
        inputs=_inputs(),
    )

    assert "WALL_AS_MAGNET" in claims.get_column("claim_type").to_list()


def test_3sd_entry_claim_represented() -> None:
    claims = build_semantic_claims(
        segments=build_transcript_semantic_segments(inputs=_inputs()),
        inputs=_inputs(),
    )

    assert "THREE_SD_EXTREME_ENTRY" in claims.get_column("claim_type").to_list()


def test_3_5sd_stop_claim_represented() -> None:
    claims = build_semantic_claims(
        segments=build_transcript_semantic_segments(inputs=_inputs()),
        inputs=_inputs(),
    )

    assert "THREE_POINT_FIVE_SD_STOP" in claims.get_column("claim_type").to_list()


def test_25_grid_rule_represented() -> None:
    claims = build_semantic_claims(
        segments=build_transcript_semantic_segments(inputs=_inputs()),
        inputs=_inputs(),
    )
    family = build_sd_grid_rule_family(claims)

    assert "$25_GRID_ROTATION" in family.get_column("rule_id").to_list()


def test_no_keyword_only_claim_without_context() -> None:
    segments = build_transcript_semantic_segments(
        inputs={
            "transcript_rules": pl.DataFrame(
                [
                    {
                        "transcript_id": "t1",
                        "transcript_date": "2026-05-01",
                        "source_excerpt": "wall",
                        "normalized_english_summary": "",
                        "rule_tag": "OI_WALL",
                        "condition": "",
                    }
                ],
                infer_schema_length=None,
            )
        }
    )
    claims = build_semantic_claims(segments=segments, inputs={})

    assert segments.row(0, named=True)["needs_human_review"]
    assert claims.row(0, named=True)["confidence"] == "LOW"


def test_sd_grid_backtest_output_exists() -> None:
    segments = build_transcript_semantic_segments(inputs=_inputs())
    claims = build_semantic_claims(segments=segments, inputs=_inputs())
    family = build_sd_grid_rule_family(claims)
    backtest = build_dukascopy_sd_grid_backtest(inputs=_inputs(), rule_family=family)

    assert backtest.height > 0
    assert "ENTRY_AT_3SD_WITH_3_5SD_STOP" in backtest.get_column("rule_id").to_list()


def test_cme_wall_magnet_test_labels_insufficient_sample_when_small() -> None:
    result = build_cme_wall_magnet_tp_backtest(inputs=_inputs())

    assert not result.is_empty()
    assert set(result.get_column("interpretation").to_list()) == {"INSUFFICIENT_SAMPLE"}


def test_cme_only_rules_never_output_buy_or_sell() -> None:
    claims = build_semantic_claims(
        segments=build_transcript_semantic_segments(inputs=_inputs()),
        inputs=_inputs(),
    )
    rules = build_cme_only_rule_translation_from_guru(
        claims=claims,
        cme_wall_magnet_tp=build_cme_wall_magnet_tp_backtest(inputs=_inputs()),
    )
    text = rules.write_csv()

    assert "BUY" not in text.upper()
    assert "SELL" not in text.upper()


def test_guru_context_does_not_become_direct_signal() -> None:
    claims = build_semantic_claims(
        segments=build_transcript_semantic_segments(inputs=_inputs()),
        inputs=_inputs(),
    )
    rules = build_cme_only_rule_translation_from_guru(
        claims=claims,
        cme_wall_magnet_tp=build_cme_wall_magnet_tp_backtest(inputs=_inputs()),
    )

    assert set(rules.get_column("action_label").to_list()).issubset(
        {"WATCH_ONLY", "TARGET_REFERENCE", "BLOCK", "ALLOW_RESEARCH_CANDIDATE", "INSUFFICIENT_DATA"}
    )


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    output = _write_inputs(tmp_path)

    run_guru_semantic_reasoning_lab(output_dir=output)
    text = (output / "guru_semantic_claims.md").read_text(encoding="utf-8")

    assert "profitability" not in text.lower()
    assert "profitable" not in text.lower()
    assert report_text_is_safe(text)


def test_redacted_paths_only(tmp_path: Path) -> None:
    output = _write_inputs(tmp_path, path_in_excerpt=True)

    run_guru_semantic_reasoning_lab(output_dir=output)
    text = (output / "guru_semantic_claims.md").read_text(encoding="utf-8")

    assert str(tmp_path) not in text
    assert "C:" not in text
    assert "<REDACTED_PATH>" in text
    assert report_text_is_safe(text)


def _inputs(*, path_in_excerpt: bool = False) -> dict[str, object]:
    return {
        "transcript_rules": _transcript_rules(path_in_excerpt=path_in_excerpt),
        "clean_transcripts": pl.DataFrame(),
        "same_day_debug": pl.DataFrame(),
        "guru_wall_hypotheses": pl.DataFrame(),
        "price_15m": _price_frame("15m", minutes=15),
        "price_30m": _price_frame("30m", minutes=30),
        "price_1h": _price_frame("1h", minutes=60),
        "price_4h": _price_frame("4h", minutes=240),
        "price_1d": _daily_price(),
        "wall_map": _wall_map(),
    }


def _write_inputs(tmp_path: Path, *, path_in_excerpt: bool = False) -> Path:
    output = tmp_path / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    _transcript_rules(path_in_excerpt=path_in_excerpt).write_csv(output / "transcript_llm_extracted_rules.csv")
    _price_frame("15m", minutes=15).write_parquet(output / "dukascopy_xau_15m.parquet")
    _price_frame("30m", minutes=30).write_parquet(output / "dukascopy_xau_30m.parquet")
    _price_frame("1h", minutes=60).write_parquet(output / "dukascopy_xau_1h.parquet")
    _price_frame("4h", minutes=240).write_parquet(output / "dukascopy_xau_4h.parquet")
    _daily_price().write_parquet(output / "dukascopy_xau_1d.parquet")
    _wall_map().write_csv(output / "cme_wall_map_by_date.csv")
    return output


def _transcript_rules(*, path_in_excerpt: bool = False) -> pl.DataFrame:
    path_text = r"C:\Users\example\secret.txt " if path_in_excerpt else ""
    return pl.DataFrame(
        [
            {
                "transcript_id": "t_wall",
                "transcript_date": "2026-05-01",
                "availability_timestamp": "2026-05-01T09:00:00+00:00",
                "source_excerpt": f"{path_text}OI wall is a target magnet and TP reference after context confirmation.",
                "normalized_english_summary": "Use open-interest concentration as wall context and target reference.",
                "rule_tag": "OI_WALL",
                "condition": "Use only with as-of CME wall data.",
                "observable_inputs": "wall_level|price",
                "required_market_data": "cme_oi|basis|dukascopy",
                "notes": "structured research feature only",
            },
            {
                "transcript_id": "t_3sd",
                "transcript_date": "2026-05-02",
                "availability_timestamp": "2026-05-02T09:00:00+00:00",
                "source_excerpt": "3 SD extreme entry needs 3.5 SD outer stop reference and context.",
                "normalized_english_summary": "Treat three standard deviations as extreme zone.",
                "rule_tag": "THREE_SD_EXTREME",
                "condition": "3SD touch with 3.5SD invalidation reference.",
                "observable_inputs": "sd_band|open|high|low|close",
                "required_market_data": "dukascopy",
                "notes": "structured research feature only",
            },
            {
                "transcript_id": "t_25",
                "transcript_date": "2026-05-03",
                "availability_timestamp": "2026-05-03T09:00:00+00:00",
                "source_excerpt": "Every 25 dollars and 50 dollars can be a practical grid reference.",
                "normalized_english_summary": "Use session open side and grid as context.",
                "rule_tag": "OPEN_PRICE_THEORY",
                "condition": "Grid is context and not direct signal.",
                "observable_inputs": "open|grid",
                "required_market_data": "dukascopy",
                "notes": "structured research feature only",
            },
        ],
        infer_schema_length=None,
    )


def _price_frame(timeframe: str, *, minutes: int) -> pl.DataFrame:
    start = datetime(2026, 5, 1, tzinfo=UTC)
    rows = []
    for day in range(4):
        day_start = start + timedelta(days=day)
        for index in range(max(1, int(24 * 60 / minutes))):
            timestamp = day_start + timedelta(minutes=minutes * index)
            open_price = 4500.0 + day * 10 + index * 0.5
            rows.append(
                {
                    "timestamp": timestamp,
                    "trade_date": timestamp.date().isoformat(),
                    "open": open_price,
                    "high": open_price + 20.0,
                    "low": open_price - 18.0,
                    "close": open_price + (5.0 if index % 2 == 0 else -5.0),
                    "spread_points": 0.3,
                    "timeframe": timeframe,
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None)


def _daily_price() -> pl.DataFrame:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    return pl.DataFrame(
        [
            {
                "timestamp": start + timedelta(days=index),
                "trade_date": (start + timedelta(days=index)).date().isoformat(),
                "open": 4400.0 + index,
                "high": 4430.0 + index,
                "low": 4380.0 + index,
                "close": 4410.0 + index,
                "spread_points": 0.4,
            }
            for index in range(40)
        ],
        infer_schema_length=None,
    )


def _wall_map() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "trade_date": "2026-05-01",
                "wall_type": "CALL_WALL",
                "strike": 4525.0,
                "spot_equivalent_level": 4520.0,
                "wall_score": 0.8,
            },
            {
                "trade_date": "2026-05-02",
                "wall_type": "PUT_WALL",
                "strike": 4475.0,
                "spot_equivalent_level": 4470.0,
                "wall_score": 0.7,
            },
        ],
        infer_schema_length=None,
    )
