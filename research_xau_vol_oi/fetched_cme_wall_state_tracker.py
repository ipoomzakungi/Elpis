"""Fetched CME wall state tracker and daily wall outcome journal.

This module ranks all fetched QuikStrike/CME wall levels, keeps context-only
walls visible, and journals later price reactions with Dukascopy candles. It is
research-only context generation, not an execution layer.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl


ALLOWED_ACTIONS = (
    "BLOCK",
    "WATCH_ONLY",
    "TARGET_REFERENCE",
    "ALLOW_RESEARCH_CANDIDATE",
    "INSUFFICIENT_DATA",
)
FINAL_RECOMMENDATIONS = (
    "FETCHED_CME_WALL_TRACKER_READY",
    "WALL_CONTEXT_ONLY",
    "WALL_ROLE_INSUFFICIENT_SAMPLE",
    "COLLECT_MORE_CME_DAYS",
    "NOT_READY_FOR_MONEY",
)
RESEARCH_WARNING = (
    "Research-only fetched CME wall tracker. CME walls are context, target/reference, "
    "or reaction zones only; they are not automatic entries."
)
OUTCOME_WINDOWS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "session_close": None,
    "next_session": timedelta(hours=24),
}


@dataclass(frozen=True)
class FetchedCmeWallStateTrackerResult:
    """Generated fetched CME wall tracker artifacts."""

    rankings: pl.DataFrame
    daily_state: pl.DataFrame
    outcome_journal: pl.DataFrame
    role_summary: pl.DataFrame
    latest_state: pl.DataFrame
    final_recommendation: str
    paths: dict[str, Path]


def run_fetched_cme_wall_state_tracker(
    *,
    output_dir: str | Path = "outputs",
    fetched_roots: list[str | Path] | None = None,
    price_paths: dict[str, str | Path] | None = None,
    write_outputs: bool = True,
) -> FetchedCmeWallStateTrackerResult:
    """Build rankings, state summary, outcome journal, and role summary."""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    repo_root = _repo_root_from_output(output_root)
    paths = _output_paths(output_root)
    rankings = build_fetched_cme_wall_rankings(
        output_root=output_root,
        repo_root=repo_root,
        fetched_roots=[Path(root) for root in fetched_roots] if fetched_roots else None,
    )
    price_15m = _load_price_frame(
        price_paths.get("15m") if price_paths and "15m" in price_paths else output_root / "dukascopy_xau_15m.parquet"
    )
    latest_price = _latest_indicator_price(output_root=output_root, price_frame=price_15m)
    daily_state = build_fetched_cme_daily_wall_state(
        rankings=rankings,
        price_frame=price_15m,
        latest_price=latest_price,
    )
    outcome_journal = build_fetched_cme_wall_outcome_journal(
        rankings=rankings,
        price_frame=price_15m,
    )
    role_summary = build_fetched_cme_wall_role_summary(outcome_journal=outcome_journal)
    latest_state = build_latest_indicator_state_with_ranked_cme_walls(
        rankings=rankings,
        daily_state=daily_state,
        role_summary=role_summary,
        latest_price=latest_price,
    )
    final = choose_final_recommendation(
        rankings=rankings,
        role_summary=role_summary,
        latest_state=latest_state,
    )
    result = FetchedCmeWallStateTrackerResult(
        rankings=rankings,
        daily_state=daily_state,
        outcome_journal=outcome_journal,
        role_summary=role_summary,
        latest_state=latest_state,
        final_recommendation=final,
        paths=paths,
    )
    if write_outputs:
        write_fetched_cme_wall_state_tracker_outputs(result)
    return result


def build_fetched_cme_wall_rankings(
    *,
    output_root: Path,
    repo_root: Path | None = None,
    fetched_roots: list[Path] | None = None,
) -> pl.DataFrame:
    """Rank every fetched wall while keeping context-only walls visible."""

    repo = repo_root or _repo_root_from_output(output_root)
    paths = _fetched_input_paths(repo_root=repo, output_root=output_root, fetched_roots=fetched_roots)
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(_rankings_from_fetched_file(path))
    frame = _frame(rows, _ranking_schema())
    if frame.is_empty():
        return frame
    return _add_rank_columns(frame)


def build_fetched_cme_daily_wall_state(
    *,
    rankings: pl.DataFrame,
    price_frame: pl.DataFrame,
    latest_price: float | None,
) -> pl.DataFrame:
    """Summarize latest ranked wall state per trade date."""

    if rankings.is_empty():
        return _frame([_insufficient_daily_state()], _daily_state_schema())
    rows: list[dict[str, Any]] = []
    for trade_date in sorted(set(rankings.get_column("trade_date").to_list())):
        day_rows = rankings.filter(pl.col("trade_date") == trade_date)
        if day_rows.is_empty():
            continue
        latest_snapshot = _latest_snapshot_timestamp(day_rows)
        snapshot = day_rows.filter(pl.col("snapshot_timestamp") == latest_snapshot)
        price = (
            latest_price
            if trade_date == _latest_trade_date(rankings) and latest_price is not None
            else _price_at_or_before(price_frame, _parse_datetime(latest_snapshot))
        )
        if price is None:
            price = _best_float(snapshot, "future_price")
        row = _daily_state_row(snapshot=snapshot, latest_price=price, trade_date=trade_date)
        rows.append(row)
    return _frame([_safe_row(row) for row in rows], _daily_state_schema())


def build_fetched_cme_wall_outcome_journal(
    *,
    rankings: pl.DataFrame,
    price_frame: pl.DataFrame,
) -> pl.DataFrame:
    """Journal wall reactions over fixed outcome windows using Dukascopy price."""

    if rankings.is_empty():
        return _frame([], _outcome_schema())
    price = _normalize_price_frame(price_frame)
    if price.is_empty():
        return _insufficient_price_journal(rankings)
    stats_by_snapshot = _window_stats_by_snapshot(rankings=rankings, price=price)
    rows: list[dict[str, Any]] = []
    for wall in rankings.to_dicts():
        snapshot_dt = _parse_datetime(wall.get("snapshot_timestamp"))
        price_at_snapshot = _float(stats_by_snapshot.get((_dt_key(snapshot_dt), "price_at_snapshot")))
        if price_at_snapshot is None:
            price_at_snapshot = _float(wall.get("future_price"))
        for window in OUTCOME_WINDOWS:
            stats = stats_by_snapshot.get((_dt_key(snapshot_dt), window), {})
            rows.append(
                _outcome_row(
                    wall=wall,
                    outcome_window=window,
                    stats=stats if isinstance(stats, dict) else {},
                    price_at_snapshot=price_at_snapshot,
                )
            )
    return _frame([_safe_row(row) for row in rows], _outcome_schema())


def build_fetched_cme_wall_role_summary(*, outcome_journal: pl.DataFrame) -> pl.DataFrame:
    """Aggregate journal rows into current wall-role context labels."""

    if outcome_journal.is_empty():
        return _frame([], _role_schema())
    resolved = outcome_journal.filter(pl.col("outcome_status") == "RESOLVED")
    if resolved.is_empty():
        return _frame([], _role_schema())
    groups = [
        "wall_type",
        "option_type",
        "distance_bucket",
        "volume_bucket",
        "oi_bucket",
        "dte_bucket",
    ]
    sample_days = len(
        {
            (_parse_datetime(value).date().isoformat() if _parse_datetime(value) else _text(value)[:10])
            for value in resolved.get_column("snapshot_timestamp").to_list()
        }
    )
    rows: list[dict[str, Any]] = []
    for key, group in resolved.group_by(groups, maintain_order=True):
        key_values = key if isinstance(key, tuple) else (key,)
        event_count = group.height
        touch_rate = _bool_rate(group, "touched_wall")
        rejection_rate = _bool_rate(group, "rejected_wall")
        acceptance_rate = _bool_rate(group, "accepted_wall")
        magnet_rate = _bool_rate(group, "wall_acted_as_target")
        ignored_rate = _interpretation_rate(group, "IGNORED")
        sample_warning = sample_days < 30 or event_count < 30
        rows.append(
            {
                "wall_type": key_values[0],
                "option_type": key_values[1],
                "distance_bucket": key_values[2],
                "volume_bucket": key_values[3],
                "oi_bucket": key_values[4],
                "dte_bucket": key_values[5],
                "event_count": event_count,
                "touch_rate": touch_rate,
                "rejection_rate": rejection_rate,
                "acceptance_rate": acceptance_rate,
                "magnet_rate": magnet_rate,
                "ignored_rate": ignored_rate,
                "sample_size_warning": sample_warning,
                "current_role": _current_role(
                    event_count=event_count,
                    sample_days=sample_days,
                    magnet_rate=magnet_rate,
                    rejection_rate=rejection_rate,
                    acceptance_rate=acceptance_rate,
                ),
            }
        )
    return _frame([_safe_row(row) for row in rows], _role_schema()).sort(
        ["event_count", "wall_type"],
        descending=[True, False],
    )


def build_latest_indicator_state_with_ranked_cme_walls(
    *,
    rankings: pl.DataFrame,
    daily_state: pl.DataFrame,
    role_summary: pl.DataFrame,
    latest_price: float | None,
) -> pl.DataFrame:
    """Create latest watchlist-ready state with top ranked wall context."""

    if rankings.is_empty():
        return _frame([_insufficient_latest_state(latest_price)], _latest_state_schema())
    latest_trade_date = _latest_trade_date(rankings)
    latest_snapshot = _latest_snapshot_timestamp(rankings.filter(pl.col("trade_date") == latest_trade_date))
    latest_rankings = rankings.filter(pl.col("snapshot_timestamp") == latest_snapshot)
    price = latest_price or _best_float(latest_rankings, "future_price")
    above = _top_wall_labels(latest_rankings, side="ABOVE", limit=3)
    below = _top_wall_labels(latest_rankings, side="BELOW", limit=3)
    daily = (
        daily_state.filter(pl.col("trade_date") == latest_trade_date).row(0, named=True)
        if not daily_state.filter(pl.col("trade_date") == latest_trade_date).is_empty()
        else {}
    )
    active_wall = _text(daily.get("active_wall"))
    sample_warning = _sample_warning(role_summary)
    role = "INSUFFICIENT_SAMPLE" if sample_warning else _dominant_role(role_summary)
    final_action = "WATCH_ONLY" if active_wall or above or below else "INSUFFICIENT_DATA"
    row = {
        "latest_price": price,
        "top_3_walls_above": "; ".join(above),
        "top_3_walls_below": "; ".join(below),
        "active_wall": active_wall,
        "current_cme_wall_role": role,
        "final_action_label": final_action,
        "sample_size_warning": sample_warning,
        "plain_english_summary": (
            f"Latest price {_format_level(price)}; active wall {active_wall or 'n/a'}; "
            f"above context {', '.join(above) or 'n/a'}; below context {', '.join(below) or 'n/a'}; "
            "wall role remains pilot-only."
        ),
    }
    return _frame([_safe_row(row)], _latest_state_schema())


def choose_final_recommendation(
    *,
    rankings: pl.DataFrame,
    role_summary: pl.DataFrame,
    latest_state: pl.DataFrame,
) -> str:
    """Choose conservative tracker-level recommendation."""

    if rankings.is_empty() or latest_state.is_empty():
        return "COLLECT_MORE_CME_DAYS"
    if role_summary.is_empty() or _sample_warning(role_summary):
        return "WALL_ROLE_INSUFFICIENT_SAMPLE"
    return "FETCHED_CME_WALL_TRACKER_READY"


def write_fetched_cme_wall_state_tracker_outputs(
    result: FetchedCmeWallStateTrackerResult,
) -> None:
    """Write fetched CME wall tracker CSV and Markdown artifacts."""

    _write_artifact(result.rankings, result.paths["rankings_csv"], result.paths["rankings_md"], "Fetched CME Wall Rankings")
    _write_artifact(result.daily_state, result.paths["daily_state_csv"], result.paths["daily_state_md"], "Daily CME Wall State")
    _write_artifact(
        result.outcome_journal,
        result.paths["outcome_journal_csv"],
        result.paths["outcome_journal_md"],
        "Wall Outcome Journal",
    )
    _write_artifact(
        result.role_summary,
        result.paths["role_summary_csv"],
        result.paths["role_summary_md"],
        "Wall Role Summary",
    )
    _write_artifact(
        result.latest_state,
        result.paths["ranked_latest_state_csv"],
        result.paths["ranked_latest_state_md"],
        "Latest Indicator State With Ranked CME Walls",
    )


def fetched_cme_wall_state_tracker_report_lines(
    result: FetchedCmeWallStateTrackerResult | None,
) -> list[str]:
    """Return research_report.md lines for the tracker."""

    if result is None:
        return ["## Fetched CME Wall Rankings", "", "Fetched CME wall tracker was not run."]
    return [
        "## Fetched CME Wall Rankings",
        "",
        RESEARCH_WARNING,
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Ranked wall rows: {result.rankings.height}",
        "",
        _frame_markdown(result.rankings.head(30)),
        "",
        "## Daily CME Wall State",
        "",
        _frame_markdown(result.daily_state.tail(10)),
        "",
        "## Wall Outcome Journal",
        "",
        _frame_markdown(result.outcome_journal.head(30)),
        "",
        "## Wall Role Summary",
        "",
        _frame_markdown(result.role_summary.head(30)),
        "",
        "## Latest Indicator State With Ranked CME Walls",
        "",
        _frame_markdown(result.latest_state),
        "",
        "- Links: `outputs/fetched_cme_wall_rankings.csv`, "
        "`outputs/fetched_cme_daily_wall_state.csv`, "
        "`outputs/fetched_cme_wall_outcome_journal.csv`, "
        "`outputs/fetched_cme_wall_role_summary.csv`, "
        "`outputs/xau_indicator_latest_state_with_ranked_cme_walls.csv`.",
    ]


def report_text_is_safe(text: str) -> bool:
    """Return true when text avoids restricted phrases and private paths."""

    safe = _safe_report_text(text)
    return not any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in (
            r"\bbuy\b",
            r"\bsell\b",
            r"profitable",
            r"profitability",
            r"guaranteed edge",
            r"predicts price",
            r"safe to trade",
            r"live[- ]ready",
            r"paper[- ]ready",
        )
    ) and not re.search(r"[A-Za-z]:\\Users\\|/Users/|/home/|/tmp/", safe)


def _rankings_from_fetched_file(path: Path) -> list[dict[str, Any]]:
    frame = _read_optional(path)
    if frame.is_empty() or "strike" not in frame.columns:
        return []
    snapshot_timestamp = _snapshot_timestamp_from_path(path)
    trade_date = _trade_date_from_path(path) or _date_from_timestamp(snapshot_timestamp)
    volume_column = _first_present(frame, ["intraday_volume", "volume", "eod_volume", "total_volume"])
    if volume_column is None:
        return []
    side_column = _first_present(frame, ["option_type", "put_call", "call_put", "side"])
    if side_column is None and not {"call_volume", "put_volume"}.issubset(set(frame.columns)):
        return []
    working = _normalize_fetched_rows(
        frame=frame,
        volume_column=volume_column,
        side_column=side_column,
        snapshot_timestamp=snapshot_timestamp,
        trade_date=trade_date,
    )
    rows: list[dict[str, Any]] = []
    for keys, group in working.group_by(["expiration", "strike"], maintain_order=True):
        expiration, strike = keys if isinstance(keys, tuple) else ("", keys)
        call_volume = _sum_side(group, "call_volume")
        put_volume = _sum_side(group, "put_volume")
        total_volume = call_volume + put_volume
        open_interest = _sum_side(group, "open_interest")
        iv = _mean_column(group, "implied_volatility")
        future_price = _best_float(group, "future_price")
        dte = _dte(trade_date=trade_date, expiration=_text(expiration))
        active_threshold = _active_threshold(working)
        context_threshold = _context_threshold(working)
        option_type = _dominant_option_type(call_volume=call_volume, put_volume=put_volume)
        wall_type = _wall_type(
            call_volume=call_volume,
            put_volume=put_volume,
            total_volume=total_volume,
            open_interest=open_interest,
            implied_volatility=iv,
        )
        distance = None if future_price is None else (_float(strike) or 0.0) - future_price
        rows.append(
            {
                "snapshot_timestamp": snapshot_timestamp,
                "trade_date": trade_date,
                "expiration": _text(expiration),
                "dte": dte,
                "future_price": future_price,
                "strike": _float(strike),
                "option_type": option_type,
                "call_volume": call_volume,
                "put_volume": put_volume,
                "total_volume": total_volume,
                "open_interest": open_interest,
                "implied_volatility": iv,
                "distance_from_price": distance,
                "side_relative_to_price": _side_relative(distance),
                "wall_type": wall_type,
                "wall_score": _wall_score(total_volume=total_volume, open_interest=open_interest),
                "rank_overall": 0,
                "rank_above": None,
                "rank_below": None,
                "active_threshold_passed": total_volume >= active_threshold and total_volume > 0,
                "context_threshold_passed": total_volume >= context_threshold or open_interest > 0 or iv is not None,
                "notes": _ranking_note(total_volume=total_volume, active_threshold=active_threshold),
            }
        )
    return [_safe_row(row) for row in rows]


def _normalize_fetched_rows(
    *,
    frame: pl.DataFrame,
    volume_column: str,
    side_column: str | None,
    snapshot_timestamp: str,
    trade_date: str,
) -> pl.DataFrame:
    future_column = _first_present(frame, ["underlying_futures_price", "future_price", "futures_price"])
    expiration_column = _first_present(frame, ["expiry", "expiration", "expiration_code"])
    oi_column = _first_present(frame, ["open_interest", "total_oi", "oi"])
    iv_column = _first_present(frame, ["implied_volatility", "volatility", "iv"])
    if {"call_volume", "put_volume"}.issubset(set(frame.columns)):
        return frame.with_columns(
            [
                pl.lit(snapshot_timestamp).alias("snapshot_timestamp"),
                pl.lit(trade_date).alias("trade_date"),
                pl.col("strike").cast(pl.Float64, strict=False).alias("strike"),
                pl.col("call_volume").cast(pl.Float64, strict=False).fill_null(0.0).alias("call_volume"),
                pl.col("put_volume").cast(pl.Float64, strict=False).fill_null(0.0).alias("put_volume"),
                (pl.col(oi_column).cast(pl.Float64, strict=False) if oi_column else pl.lit(0.0)).alias("open_interest"),
                (pl.col(iv_column).cast(pl.Float64, strict=False) if iv_column else pl.lit(None).cast(pl.Float64)).alias("implied_volatility"),
                (pl.col(future_column).cast(pl.Float64, strict=False) if future_column else pl.lit(None).cast(pl.Float64)).alias("future_price"),
                (pl.col(expiration_column).cast(pl.Utf8, strict=False) if expiration_column else pl.lit("")).alias("expiration"),
            ]
        ).filter(pl.col("strike").is_not_null())
    return frame.with_columns(
        [
            pl.lit(snapshot_timestamp).alias("snapshot_timestamp"),
            pl.lit(trade_date).alias("trade_date"),
            pl.col("strike").cast(pl.Float64, strict=False).alias("strike"),
            pl.col(volume_column).cast(pl.Float64, strict=False).fill_null(0.0).alias("volume_value"),
            pl.col(side_column or "").cast(pl.Utf8, strict=False).str.to_lowercase().alias("side_value"),
            (pl.col(oi_column).cast(pl.Float64, strict=False) if oi_column else pl.lit(0.0)).alias("open_interest"),
            (pl.col(iv_column).cast(pl.Float64, strict=False) if iv_column else pl.lit(None).cast(pl.Float64)).alias("implied_volatility"),
            (pl.col(future_column).cast(pl.Float64, strict=False) if future_column else pl.lit(None).cast(pl.Float64)).alias("future_price"),
            (pl.col(expiration_column).cast(pl.Utf8, strict=False) if expiration_column else pl.lit("")).alias("expiration"),
        ]
    ).with_columns(
        [
            pl.when(pl.col("side_value").str.contains("call|c"))
            .then(pl.col("volume_value"))
            .otherwise(0.0)
            .alias("call_volume"),
            pl.when(pl.col("side_value").str.contains("put|p"))
            .then(pl.col("volume_value"))
            .otherwise(0.0)
            .alias("put_volume"),
        ]
    ).filter(pl.col("strike").is_not_null())


def _add_rank_columns(frame: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for snapshot_timestamp in sorted(set(frame.get_column("snapshot_timestamp").to_list())):
        snapshot = frame.filter(pl.col("snapshot_timestamp") == snapshot_timestamp)
        overall = sorted(
            snapshot.to_dicts(),
            key=lambda row: (
                -(_float(row.get("wall_score")) or 0.0),
                abs(_float(row.get("distance_from_price")) or 0.0),
            ),
        )
        above = [row for row in overall if row.get("side_relative_to_price") == "ABOVE"]
        below = [row for row in overall if row.get("side_relative_to_price") == "BELOW"]
        above_rank = {_rank_key(row): index + 1 for index, row in enumerate(above)}
        below_rank = {_rank_key(row): index + 1 for index, row in enumerate(below)}
        for index, row in enumerate(overall, start=1):
            row["rank_overall"] = index
            row["rank_above"] = above_rank.get(_rank_key(row))
            row["rank_below"] = below_rank.get(_rank_key(row))
            rows.append(row)
    return _frame([_safe_row(row) for row in rows], _ranking_schema())


def _daily_state_row(*, snapshot: pl.DataFrame, latest_price: float | None, trade_date: str) -> dict[str, Any]:
    if snapshot.is_empty() or latest_price is None:
        return _insufficient_daily_state(trade_date=trade_date, latest_price=latest_price)
    with_current_price = snapshot.with_columns(
        [
            (pl.col("strike") - pl.lit(latest_price)).alias("current_distance"),
            pl.when(pl.col("strike") > latest_price)
            .then(pl.lit("ABOVE"))
            .when(pl.col("strike") < latest_price)
            .then(pl.lit("BELOW"))
            .otherwise(pl.lit("AT_PRICE"))
            .alias("current_side"),
        ]
    )
    active = with_current_price.filter(pl.col("active_threshold_passed"))
    active_wall = _top_label(active, side=None)
    top_above = _top_label(with_current_price, side="ABOVE")
    top_below = _top_label(with_current_price, side="BELOW")
    max_call = _max_wall_label(with_current_price, "call_volume")
    max_put = _max_wall_label(with_current_price, "put_volume")
    max_total = _max_wall_label(with_current_price, "total_volume")
    nearest_above = _nearest_context_wall(with_current_price, side="ABOVE")
    nearest_below = _nearest_context_wall(with_current_price, side="BELOW")
    gap_above = _nearest_gap(with_current_price, side="ABOVE")
    gap_below = _nearest_gap(with_current_price, side="BELOW")
    wall_state = _daily_wall_state(active=active, price=latest_price)
    action = "WATCH_ONLY" if active_wall or nearest_above or nearest_below else "INSUFFICIENT_DATA"
    summary = (
        f"Latest price {_format_level(latest_price)}; active wall {active_wall or 'n/a'}; "
        f"top above {top_above or 'n/a'}; top below {top_below or 'n/a'}; state {wall_state}."
    )
    return {
        "trade_date": trade_date,
        "latest_price": latest_price,
        "top_wall_above": top_above,
        "top_wall_below": top_below,
        "active_wall": active_wall,
        "max_call_volume_wall": max_call,
        "max_put_volume_wall": max_put,
        "max_total_volume_wall": max_total,
        "nearest_context_wall_above": nearest_above,
        "nearest_context_wall_below": nearest_below,
        "low_volume_gap_above": gap_above,
        "low_volume_gap_below": gap_below,
        "wall_state": wall_state,
        "action_label": action,
        "plain_english_summary": summary,
    }


def _outcome_row(
    *,
    wall: dict[str, Any],
    outcome_window: str,
    stats: dict[str, Any],
    price_at_snapshot: float | None,
) -> dict[str, Any]:
    wall_level = _float(wall.get("strike"))
    distance = None if wall_level is None or price_at_snapshot is None else wall_level - price_at_snapshot
    status = _text(stats.get("status")) or "INSUFFICIENT_PRICE_DATA"
    high = _float(stats.get("high"))
    low = _float(stats.get("low"))
    close = _float(stats.get("close"))
    touched = status == "RESOLVED" and wall_level is not None and high is not None and low is not None and low <= wall_level <= high
    if status == "PENDING":
        interpretation = "TOO_EARLY"
    elif status != "RESOLVED":
        interpretation = "TOO_EARLY"
    else:
        interpretation = _outcome_interpretation(
            touched=touched,
            wall_level=wall_level,
            price_at_snapshot=price_at_snapshot,
            close=close,
        )
    rejected = (
        touched
        and close is not None
        and wall_level is not None
        and price_at_snapshot is not None
        and ((wall_level >= price_at_snapshot and close < wall_level) or (wall_level < price_at_snapshot and close > wall_level))
    )
    accepted = (
        touched
        and close is not None
        and wall_level is not None
        and price_at_snapshot is not None
        and ((wall_level >= price_at_snapshot and close > wall_level) or (wall_level < price_at_snapshot and close < wall_level))
    )
    closed_nearer = (
        close is not None
        and wall_level is not None
        and price_at_snapshot is not None
        and abs(close - wall_level) < abs(price_at_snapshot - wall_level)
    )
    return {
        "snapshot_timestamp": wall.get("snapshot_timestamp"),
        "wall_level": wall_level,
        "wall_type": wall.get("wall_type"),
        "option_type": wall.get("option_type"),
        "distance_bucket": _distance_bucket(distance),
        "volume_bucket": _volume_bucket(_float(wall.get("total_volume"))),
        "oi_bucket": _oi_bucket(_float(wall.get("open_interest"))),
        "dte_bucket": _dte_bucket(_float(wall.get("dte"))),
        "price_at_snapshot": price_at_snapshot,
        "distance_from_price": distance,
        "outcome_window": outcome_window,
        "touched_wall": touched,
        "rejected_wall": rejected,
        "accepted_wall": accepted,
        "closed_nearer_to_wall": closed_nearer,
        "wall_acted_as_target": touched or closed_nearer,
        "wall_acted_as_barrier": rejected,
        "outcome_status": status,
        "interpretation": interpretation,
    }


def _window_stats_by_snapshot(*, rankings: pl.DataFrame, price: pl.DataFrame) -> dict[tuple[str, str], dict[str, Any] | float | None]:
    out: dict[tuple[str, str], dict[str, Any] | float | None] = {}
    max_price_time = _max_datetime(price, "timestamp")
    for timestamp in sorted(set(rankings.get_column("snapshot_timestamp").to_list())):
        snapshot_dt = _parse_datetime(timestamp)
        out[(_dt_key(snapshot_dt), "price_at_snapshot")] = _price_at_or_before(price, snapshot_dt)
        for window, delta in OUTCOME_WINDOWS.items():
            end = _window_end(snapshot_dt, window, delta)
            if snapshot_dt is None or end is None:
                out[(_dt_key(snapshot_dt), window)] = {"status": "INSUFFICIENT_PRICE_DATA"}
                continue
            if max_price_time is not None and max_price_time < end:
                out[(_dt_key(snapshot_dt), window)] = {"status": "PENDING"}
                continue
            window_frame = price.filter(
                (pl.col("timestamp") > snapshot_dt) & (pl.col("timestamp") <= end)
            )
            if window_frame.is_empty():
                out[(_dt_key(snapshot_dt), window)] = {"status": "INSUFFICIENT_PRICE_DATA"}
                continue
            out[(_dt_key(snapshot_dt), window)] = {
                "status": "RESOLVED",
                "high": _best_float(window_frame.select(pl.col("high").max()), "high"),
                "low": _best_float(window_frame.select(pl.col("low").min()), "low"),
                "close": _float(window_frame.sort("timestamp").tail(1).row(0, named=True).get("close")),
            }
    return out


def _window_end(snapshot_dt: datetime | None, window: str, delta: timedelta | None) -> datetime | None:
    if snapshot_dt is None:
        return None
    if window == "session_close":
        close = snapshot_dt.replace(hour=21, minute=0, second=0, microsecond=0)
        return close if close > snapshot_dt else close + timedelta(days=1)
    if delta is None:
        return None
    return snapshot_dt + delta


def _insufficient_price_journal(rankings: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for wall in rankings.to_dicts():
        for window in OUTCOME_WINDOWS:
            rows.append(
                {
                    "snapshot_timestamp": wall.get("snapshot_timestamp"),
                    "wall_level": wall.get("strike"),
                    "wall_type": wall.get("wall_type"),
                    "option_type": wall.get("option_type"),
                    "distance_bucket": _distance_bucket(wall.get("distance_from_price")),
                    "volume_bucket": _volume_bucket(wall.get("total_volume")),
                    "oi_bucket": _oi_bucket(wall.get("open_interest")),
                    "dte_bucket": _dte_bucket(wall.get("dte")),
                    "price_at_snapshot": None,
                    "distance_from_price": wall.get("distance_from_price"),
                    "outcome_window": window,
                    "touched_wall": False,
                    "rejected_wall": False,
                    "accepted_wall": False,
                    "closed_nearer_to_wall": False,
                    "wall_acted_as_target": False,
                    "wall_acted_as_barrier": False,
                    "outcome_status": "INSUFFICIENT_PRICE_DATA",
                    "interpretation": "TOO_EARLY",
                }
            )
    return _frame([_safe_row(row) for row in rows], _outcome_schema())


def _fetched_input_paths(*, repo_root: Path, output_root: Path, fetched_roots: list[Path] | None) -> list[Path]:
    roots = list(fetched_roots or [])
    if not roots:
        roots = [
            repo_root / "backend" / "data" / "reports" / "xau_quikstrike_fusion",
            repo_root / "data" / "reports" / "xau_quikstrike_fusion",
        ]
    paths: list[Path] = []
    for root in roots:
        if root.exists():
            paths.extend(root.rglob("xau_vol_oi_input.csv"))
    fallback = output_root / "quikstrike_intraday_volume_snapshot_from_fetch.csv"
    if not paths and fallback.exists():
        paths.append(fallback)
    return sorted(set(paths), key=lambda path: (path.stat().st_mtime, str(path)))


def _active_threshold(frame: pl.DataFrame) -> float:
    if frame.is_empty():
        return 25.0
    if {"call_volume", "put_volume"}.issubset(set(frame.columns)):
        totals = (frame.get_column("call_volume") + frame.get_column("put_volume")).to_list()
    else:
        totals = frame.get_column("volume_value").to_list() if "volume_value" in frame.columns else []
    clean = [_float(value) or 0.0 for value in totals]
    return max(25.0, (max(clean) if clean else 0.0) * 0.25)


def _context_threshold(frame: pl.DataFrame) -> float:
    return 1.0 if not frame.is_empty() else math.inf


def _wall_type(
    *,
    call_volume: float,
    put_volume: float,
    total_volume: float,
    open_interest: float,
    implied_volatility: float | None,
) -> str:
    if total_volume <= 0 and open_interest > 0:
        return "OI_WALL"
    if total_volume <= 0 and implied_volatility is not None:
        return "IV_CONTEXT"
    if total_volume <= 0:
        return "LOW_VOLUME_GAP"
    if call_volume >= put_volume * 1.2 and call_volume > 0:
        return "CALL_VOLUME_WALL"
    if put_volume >= call_volume * 1.2 and put_volume > 0:
        return "PUT_VOLUME_WALL"
    return "TOTAL_VOLUME_WALL"


def _wall_score(*, total_volume: float, open_interest: float) -> float:
    return total_volume if total_volume > 0 else open_interest


def _ranking_note(*, total_volume: float, active_threshold: float) -> str:
    if total_volume >= active_threshold and total_volume > 0:
        return "Active threshold passed; still context-only pending price reaction."
    if total_volume > 0:
        return "Context wall below active threshold; retained for watchlist geometry."
    return "Low-volume or OI/IV-only context retained; not an entry signal."


def _sum_side(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    value = frame.get_column(column).sum()
    return _float(value) or 0.0


def _mean_column(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    return _float(frame.get_column(column).mean())


def _dominant_option_type(*, call_volume: float, put_volume: float) -> str:
    if call_volume > put_volume:
        return "call"
    if put_volume > call_volume:
        return "put"
    return "mixed"


def _side_relative(distance: float | None) -> str:
    if distance is None or abs(distance) <= 0.01:
        return "AT_PRICE"
    return "ABOVE" if distance > 0 else "BELOW"


def _rank_key(row: dict[str, Any]) -> tuple[str, float, str]:
    return (
        _text(row.get("snapshot_timestamp")),
        _float(row.get("strike")) or 0.0,
        _text(row.get("expiration")),
    )


def _top_wall_labels(frame: pl.DataFrame, *, side: str, limit: int) -> list[str]:
    if frame.is_empty():
        return []
    side_frame = frame.filter(pl.col("side_relative_to_price") == side)
    if side_frame.is_empty():
        return []
    sorted_frame = side_frame.sort(["wall_score", "context_threshold_passed"], descending=[True, True])
    return [_wall_label(row) for row in sorted_frame.head(limit).to_dicts()]


def _top_label(frame: pl.DataFrame, *, side: str | None) -> str:
    if frame.is_empty():
        return ""
    target = frame if side is None else frame.filter(pl.col("current_side") == side)
    if target.is_empty():
        return ""
    return _wall_label(target.sort("wall_score", descending=True).row(0, named=True))


def _max_wall_label(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    value = _float(frame.get_column(column).max()) or 0.0
    if value <= 0:
        return ""
    return _wall_label(frame.filter(pl.col(column) == value).row(0, named=True))


def _nearest_context_wall(frame: pl.DataFrame, *, side: str) -> str:
    if frame.is_empty():
        return ""
    target = frame.filter((pl.col("current_side") == side) & pl.col("context_threshold_passed"))
    if target.is_empty():
        return ""
    target = target.with_columns(pl.col("current_distance").abs().alias("_abs_distance"))
    return _wall_label(target.sort("_abs_distance").row(0, named=True))


def _nearest_gap(frame: pl.DataFrame, *, side: str) -> str:
    if frame.is_empty():
        return ""
    target = frame.filter((pl.col("current_side") == side) & (pl.col("wall_type") == "LOW_VOLUME_GAP"))
    if target.is_empty():
        return ""
    target = target.with_columns(pl.col("current_distance").abs().alias("_abs_distance"))
    return _format_level(target.sort("_abs_distance").row(0, named=True).get("strike"))


def _daily_wall_state(*, active: pl.DataFrame, price: float) -> str:
    if active.is_empty():
        return "NO_CLEAR_WALL"
    above = active.filter(pl.col("strike") > price).height > 0
    below = active.filter(pl.col("strike") < price).height > 0
    at_price = active.filter((pl.col("strike") - price).abs() <= 12.5).height > 0
    if at_price:
        return "ATM_CLUSTER"
    if above and below:
        return "BETWEEN_WALLS"
    if above:
        return "WALL_ABOVE_ACTIVE"
    if below:
        return "WALL_BELOW_ACTIVE"
    return "NO_CLEAR_WALL"


def _outcome_interpretation(
    *,
    touched: bool,
    wall_level: float | None,
    price_at_snapshot: float | None,
    close: float | None,
) -> str:
    if not touched or wall_level is None or price_at_snapshot is None or close is None:
        if wall_level is not None and price_at_snapshot is not None and close is not None:
            if abs(close - wall_level) < abs(price_at_snapshot - wall_level):
                return "MAGNET_CANDIDATE"
        return "IGNORED"
    if (wall_level >= price_at_snapshot and close > wall_level) or (wall_level < price_at_snapshot and close < wall_level):
        return "ACCEPTANCE_CANDIDATE"
    if (wall_level >= price_at_snapshot and close < wall_level) or (wall_level < price_at_snapshot and close > wall_level):
        return "REJECTION_CANDIDATE"
    return "MAGNET_CANDIDATE"


def _current_role(
    *,
    event_count: int,
    sample_days: int,
    magnet_rate: float,
    rejection_rate: float,
    acceptance_rate: float,
) -> str:
    if sample_days < 30 or event_count < 30:
        return "INSUFFICIENT_SAMPLE"
    best = max(magnet_rate, rejection_rate, acceptance_rate)
    if best == magnet_rate and magnet_rate > 0:
        return "TARGET_REFERENCE"
    if best == rejection_rate and rejection_rate > 0:
        return "REJECTION_CONTEXT"
    if best == acceptance_rate and acceptance_rate > 0:
        return "ACCEPTANCE_CONTEXT"
    return "CONTEXT_ONLY"


def _dominant_role(role_summary: pl.DataFrame) -> str:
    if role_summary.is_empty():
        return "INSUFFICIENT_SAMPLE"
    return _text(role_summary.sort("event_count", descending=True).row(0, named=True).get("current_role"))


def _sample_warning(role_summary: pl.DataFrame) -> bool:
    if role_summary.is_empty() or "sample_size_warning" not in role_summary.columns:
        return True
    return bool(role_summary.get_column("sample_size_warning").any())


def _bool_rate(frame: pl.DataFrame, column: str) -> float:
    if frame.is_empty() or column not in frame.columns:
        return 0.0
    return float(frame.get_column(column).sum()) / frame.height


def _interpretation_rate(frame: pl.DataFrame, value: str) -> float:
    if frame.is_empty() or "interpretation" not in frame.columns:
        return 0.0
    return frame.filter(pl.col("interpretation") == value).height / frame.height


def _distance_bucket(value: Any) -> str:
    distance = abs(_float(value) or 0.0)
    if distance <= 25:
        return "0_25"
    if distance <= 50:
        return "25_50"
    if distance <= 100:
        return "50_100"
    return "GT_100"


def _volume_bucket(value: Any) -> str:
    volume = _float(value) or 0.0
    if volume <= 0:
        return "ZERO"
    if volume < 25:
        return "LOW"
    if volume < 100:
        return "MEDIUM"
    return "HIGH"


def _oi_bucket(value: Any) -> str:
    oi = _float(value) or 0.0
    if oi <= 0:
        return "ZERO"
    if oi < 100:
        return "LOW"
    if oi < 500:
        return "MEDIUM"
    return "HIGH"


def _dte_bucket(value: Any) -> str:
    dte = _float(value)
    if dte is None:
        return "UNKNOWN"
    if dte <= 1:
        return "0_1D"
    if dte <= 3:
        return "1_3D"
    return "3D_PLUS"


def _dte(*, trade_date: str, expiration: str) -> float | None:
    try:
        trade = datetime.fromisoformat(trade_date).date()
        expiry = datetime.fromisoformat(expiration).date()
        return float((expiry - trade).days)
    except ValueError:
        return None


def _snapshot_timestamp_from_path(path: Path) -> str:
    text = str(path)
    match = re.search(r"(20\d{6})_(\d{6})", text)
    if match:
        raw_date, raw_time = match.groups()
        return (
            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}T"
            f"{raw_time[:2]}:{raw_time[2:4]}:{raw_time[4:]}+00:00"
        )
    trade_date = _trade_date_from_path(path)
    return f"{trade_date}T00:00:00+00:00" if trade_date else ""


def _trade_date_from_path(path: Path) -> str:
    text = str(path)
    match = re.search(r"data_(20\d{6})", text)
    if not match:
        match = re.search(r"(20\d{6})", text)
    if not match:
        return ""
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _date_from_timestamp(timestamp: str) -> str:
    dt = _parse_datetime(timestamp)
    return dt.date().isoformat() if dt else ""


def _latest_trade_date(rankings: pl.DataFrame) -> str:
    if rankings.is_empty() or "trade_date" not in rankings.columns:
        return ""
    values = sorted(_text(value) for value in rankings.get_column("trade_date").to_list() if _text(value))
    return values[-1] if values else ""


def _latest_snapshot_timestamp(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "snapshot_timestamp" not in frame.columns:
        return ""
    values = sorted(_text(value) for value in frame.get_column("snapshot_timestamp").to_list() if _text(value))
    return values[-1] if values else ""


def _latest_indicator_price(*, output_root: Path, price_frame: pl.DataFrame) -> float | None:
    state = _read_optional(output_root / "xau_indicator_latest_state_with_quikstrike_from_fetch.csv")
    if not state.is_empty() and "latest_price" in state.columns:
        return _float(state.tail(1).row(0, named=True).get("latest_price"))
    price = _normalize_price_frame(price_frame)
    if not price.is_empty():
        return _float(price.sort("timestamp").tail(1).row(0, named=True).get("close"))
    return None


def _normalize_price_frame(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty() or "timestamp" not in frame.columns:
        return pl.DataFrame()
    required = {"high", "low", "close"}
    if not required.issubset(set(frame.columns)):
        return pl.DataFrame()
    return frame.select(
        [
            pl.col("timestamp").cast(pl.Datetime(time_zone="UTC"), strict=False).alias("timestamp"),
            pl.col("high").cast(pl.Float64, strict=False).alias("high"),
            pl.col("low").cast(pl.Float64, strict=False).alias("low"),
            pl.col("close").cast(pl.Float64, strict=False).alias("close"),
        ]
    ).drop_nulls("timestamp").sort("timestamp")


def _price_at_or_before(price_frame: pl.DataFrame, timestamp: datetime | None) -> float | None:
    price = _normalize_price_frame(price_frame)
    if price.is_empty() or timestamp is None:
        return None
    before = price.filter(pl.col("timestamp") <= timestamp)
    if before.is_empty():
        after = price.filter(pl.col("timestamp") >= timestamp)
        return _float(after.head(1).row(0, named=True).get("close")) if not after.is_empty() else None
    return _float(before.tail(1).row(0, named=True).get("close"))


def _max_datetime(frame: pl.DataFrame, column: str) -> datetime | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    value = frame.get_column(column).max()
    return value if isinstance(value, datetime) else None


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _dt_key(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _load_price_frame(path: str | Path) -> pl.DataFrame:
    return _read_optional(Path(path))


def _read_optional(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        if path.suffix.lower() == ".parquet":
            return pl.read_parquet(path)
        if path.suffix.lower() == ".csv":
            return pl.read_csv(path, infer_schema_length=None)
    except Exception:
        return pl.DataFrame()
    return pl.DataFrame()


def _repo_root_from_output(output_root: Path) -> Path:
    resolved = output_root.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / "research_xau_vol_oi").exists():
            return candidate
    return resolved.parent


def _first_present(frame: pl.DataFrame, columns: list[str]) -> str | None:
    lowered = {column.lower(): column for column in frame.columns}
    for candidate in columns:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _wall_label(row: dict[str, Any]) -> str:
    return f"{_text(row.get('wall_type'))}_{_format_level(row.get('strike'))}"


def _format_level(value: Any) -> str:
    number = _float(value)
    return "n/a" if number is None else f"{number:.2f}"


def _best_float(frame: pl.DataFrame, column: str) -> float | None:
    if frame.is_empty() or column not in frame.columns:
        return None
    values = [_float(value) for value in frame.get_column(column).to_list()]
    clean = [value for value in values if value is not None]
    return clean[-1] if clean else None


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _write_artifact(frame: pl.DataFrame, csv_path: Path, md_path: Path, title: str) -> None:
    frame.write_csv(csv_path)
    md_path.write_text(
        _safe_report_text(_artifact_markdown(title, frame)),
        encoding="utf-8",
    )


def _artifact_markdown(title: str, frame: pl.DataFrame) -> str:
    return "\n\n".join([f"# {title}", RESEARCH_WARNING, _frame_markdown(frame)])


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 40) -> str:
    if frame.is_empty():
        return "_No rows._"
    sample = frame.head(limit)
    lines = [
        "| " + " | ".join(sample.columns) + " |",
        "| " + " | ".join("---" for _ in sample.columns) + " |",
    ]
    for row in sample.to_dicts():
        lines.append(
            "| "
            + " | ".join(_markdown_cell(row.get(column, "")) for column in sample.columns)
            + " |"
        )
    if frame.height > limit:
        lines.append(f"\n_Showing {limit} of {frame.height} rows._")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return _safe_text(value).replace("|", "\\|").replace("\n", " ")[:700]


def _safe_report_text(text: str) -> str:
    return _safe_text(text)


def _safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _safe_text(value) if isinstance(value, str) else value for key, value in row.items()}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"[A-Za-z]:\\Users\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"/(?:Users|home|mnt|var|tmp)/[^\s|)<>\"']+", "<REDACTED_PATH>", text)
    text = re.sub(r"\bbuy\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsell\b", "direction", text, flags=re.IGNORECASE)
    text = re.sub(r"profitable|profitability", "money-result", text, flags=re.IGNORECASE)
    text = re.sub(r"predicts price|guaranteed edge|safe to trade", "blocked phrase", text, flags=re.IGNORECASE)
    return text.strip()


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=schema)
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for column, dtype in schema.items():
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None).cast(dtype).alias(column))
        else:
            frame = frame.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return frame.select(list(schema))


def _insufficient_daily_state(*, trade_date: str = "", latest_price: float | None = None) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "latest_price": latest_price,
        "top_wall_above": "",
        "top_wall_below": "",
        "active_wall": "",
        "max_call_volume_wall": "",
        "max_put_volume_wall": "",
        "max_total_volume_wall": "",
        "nearest_context_wall_above": "",
        "nearest_context_wall_below": "",
        "low_volume_gap_above": "",
        "low_volume_gap_below": "",
        "wall_state": "NO_CLEAR_WALL",
        "action_label": "INSUFFICIENT_DATA",
        "plain_english_summary": "Fetched CME wall rows are unavailable.",
    }


def _insufficient_latest_state(latest_price: float | None) -> dict[str, Any]:
    return {
        "latest_price": latest_price,
        "top_3_walls_above": "",
        "top_3_walls_below": "",
        "active_wall": "",
        "current_cme_wall_role": "INSUFFICIENT_SAMPLE",
        "final_action_label": "INSUFFICIENT_DATA",
        "sample_size_warning": True,
        "plain_english_summary": "Fetched CME wall rows are unavailable.",
    }


def _output_paths(output_root: Path) -> dict[str, Path]:
    return {
        "rankings_csv": output_root / "fetched_cme_wall_rankings.csv",
        "rankings_md": output_root / "fetched_cme_wall_rankings.md",
        "daily_state_csv": output_root / "fetched_cme_daily_wall_state.csv",
        "daily_state_md": output_root / "fetched_cme_daily_wall_state.md",
        "outcome_journal_csv": output_root / "fetched_cme_wall_outcome_journal.csv",
        "outcome_journal_md": output_root / "fetched_cme_wall_outcome_journal.md",
        "role_summary_csv": output_root / "fetched_cme_wall_role_summary.csv",
        "role_summary_md": output_root / "fetched_cme_wall_role_summary.md",
        "ranked_latest_state_csv": output_root / "xau_indicator_latest_state_with_ranked_cme_walls.csv",
        "ranked_latest_state_md": output_root / "xau_indicator_latest_state_with_ranked_cme_walls.md",
    }


def _ranking_schema() -> dict[str, Any]:
    return {
        "snapshot_timestamp": pl.Utf8,
        "trade_date": pl.Utf8,
        "expiration": pl.Utf8,
        "dte": pl.Float64,
        "future_price": pl.Float64,
        "strike": pl.Float64,
        "option_type": pl.Utf8,
        "call_volume": pl.Float64,
        "put_volume": pl.Float64,
        "total_volume": pl.Float64,
        "open_interest": pl.Float64,
        "implied_volatility": pl.Float64,
        "distance_from_price": pl.Float64,
        "side_relative_to_price": pl.Utf8,
        "wall_type": pl.Utf8,
        "wall_score": pl.Float64,
        "rank_overall": pl.Int64,
        "rank_above": pl.Int64,
        "rank_below": pl.Int64,
        "active_threshold_passed": pl.Boolean,
        "context_threshold_passed": pl.Boolean,
        "notes": pl.Utf8,
    }


def _daily_state_schema() -> dict[str, Any]:
    return {
        "trade_date": pl.Utf8,
        "latest_price": pl.Float64,
        "top_wall_above": pl.Utf8,
        "top_wall_below": pl.Utf8,
        "active_wall": pl.Utf8,
        "max_call_volume_wall": pl.Utf8,
        "max_put_volume_wall": pl.Utf8,
        "max_total_volume_wall": pl.Utf8,
        "nearest_context_wall_above": pl.Utf8,
        "nearest_context_wall_below": pl.Utf8,
        "low_volume_gap_above": pl.Utf8,
        "low_volume_gap_below": pl.Utf8,
        "wall_state": pl.Utf8,
        "action_label": pl.Utf8,
        "plain_english_summary": pl.Utf8,
    }


def _outcome_schema() -> dict[str, Any]:
    return {
        "snapshot_timestamp": pl.Utf8,
        "wall_level": pl.Float64,
        "wall_type": pl.Utf8,
        "option_type": pl.Utf8,
        "distance_bucket": pl.Utf8,
        "volume_bucket": pl.Utf8,
        "oi_bucket": pl.Utf8,
        "dte_bucket": pl.Utf8,
        "price_at_snapshot": pl.Float64,
        "distance_from_price": pl.Float64,
        "outcome_window": pl.Utf8,
        "touched_wall": pl.Boolean,
        "rejected_wall": pl.Boolean,
        "accepted_wall": pl.Boolean,
        "closed_nearer_to_wall": pl.Boolean,
        "wall_acted_as_target": pl.Boolean,
        "wall_acted_as_barrier": pl.Boolean,
        "outcome_status": pl.Utf8,
        "interpretation": pl.Utf8,
    }


def _role_schema() -> dict[str, Any]:
    return {
        "wall_type": pl.Utf8,
        "option_type": pl.Utf8,
        "distance_bucket": pl.Utf8,
        "volume_bucket": pl.Utf8,
        "oi_bucket": pl.Utf8,
        "dte_bucket": pl.Utf8,
        "event_count": pl.Int64,
        "touch_rate": pl.Float64,
        "rejection_rate": pl.Float64,
        "acceptance_rate": pl.Float64,
        "magnet_rate": pl.Float64,
        "ignored_rate": pl.Float64,
        "sample_size_warning": pl.Boolean,
        "current_role": pl.Utf8,
    }


def _latest_state_schema() -> dict[str, Any]:
    return {
        "latest_price": pl.Float64,
        "top_3_walls_above": pl.Utf8,
        "top_3_walls_below": pl.Utf8,
        "active_wall": pl.Utf8,
        "current_cme_wall_role": pl.Utf8,
        "final_action_label": pl.Utf8,
        "sample_size_warning": pl.Boolean,
        "plain_english_summary": pl.Utf8,
    }


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
