"""Daily forward journal data gate and outcome readiness checks.

This layer is research-only. It decides whether local daily forward journal
rows should be created or outcome windows can be resolved from available OHLC
coverage. It never fabricates candles, changes frozen rules, or creates trading
instructions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import polars as pl


UTC_ZONE = ZoneInfo("UTC")
BANGKOK_ZONE = ZoneInfo("Asia/Bangkok")
CME_EXCHANGE_ZONE = ZoneInfo("America/Chicago")
WINDOW_ORDER = ("30m", "1h", "4h", "session_close", "next_day")
INTRADAY_WINDOWS = {"30m", "1h", "4h"}
RUN_STATES = {
    "SKIP_MARKET_CLOSED",
    "SKIP_WEEKEND_ARTIFACT",
    "WAIT_FOR_INTRADAY_OHLC",
    "WAIT_FOR_MANUAL_CME_SNAPSHOT",
    "CREATE_PENDING_JOURNAL_ROWS",
    "RESOLVE_PARTIAL_OUTCOMES",
    "RESOLVE_FULL_OUTCOMES",
    "DATA_ERROR_NEEDS_FIX",
}
FINAL_RECOMMENDATIONS = {
    "WAIT_FOR_NEXT_MARKET_SESSION",
    "WAIT_FOR_INTRADAY_OHLC",
    "RESOLVE_OUTCOME_READY",
    "CREATE_NEW_JOURNAL_READY",
    "DATA_FEED_FIX_REQUIRED",
    "MANUAL_CME_SNAPSHOT_REQUIRED",
    "SKIP_WEEKEND_ARTIFACT",
}
FORBIDDEN_REPORT_PHRASES = (
    "profitable",
    "guaranteed edge",
    "predicts price",
    "safe to trade",
    "live ready",
    "live-readiness evidence",
)


@dataclass(frozen=True)
class OhlcSource:
    """Normalized local OHLC source metadata used for provider audit and coverage."""

    provider_name: str
    symbol: str
    timeframe: str
    path: Path | None
    latest_timestamp: datetime | None
    date_range_start: datetime | None
    date_range_end: datetime | None
    rows: int
    granularity: str
    current_status: str
    usable_for: tuple[str, ...]
    recommended_fix: str
    proxy_label: str = ""


@dataclass(frozen=True)
class PendingJournal:
    """Minimal forward journal state needed for readiness checks."""

    journal_id: str
    observation_timestamp: datetime
    trade_date: str
    session_date: str
    outcome_windows: tuple[str, ...]


@dataclass(frozen=True)
class SpeckitPrereqWarning:
    """Non-blocking prerequisite status for the current branch naming guard."""

    status: str
    branch_name: str
    blocking: bool
    message: str


@dataclass(frozen=True)
class DailyForwardDataGateResult:
    """Generated daily gate artifacts and final recommendation."""

    calendar_gate: pl.DataFrame
    outcome_coverage: pl.DataFrame
    provider_audit: pl.DataFrame
    run_decision: pl.DataFrame
    final_recommendation: str
    daily_note_path: Path
    speckit_warning: SpeckitPrereqWarning
    speckit_warning_path: Path


def run_daily_forward_data_gate(
    *,
    output_dir: str | Path = "outputs",
    repo_root: str | Path = ".",
    current_date: date | None = None,
    daily_approx_allowed: bool = False,
    branch_name: str | None = None,
) -> DailyForwardDataGateResult:
    """Run the daily forward data gate and write CSV/Markdown artifacts."""

    root = Path(repo_root)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    today = current_date or datetime.now(BANGKOK_ZONE).date()

    replay_rows = load_replay_rows(output_root)
    latest_replay = latest_replay_state(replay_rows)
    journals = discover_pending_forward_journals(root, replay_rows)
    ohlc_sources = discover_ohlc_sources(root, today=today, latest_replay=latest_replay)
    provider_audit = provider_audit_frame(ohlc_sources)
    outcome_coverage = build_outcome_coverage_frame(
        journals,
        ohlc_sources,
        today=today,
        daily_approx_allowed=daily_approx_allowed,
    )
    can_resolve_any = _any_true(outcome_coverage, "can_resolve_any_window")
    calendar_gate = build_calendar_gate_frame(
        today=today,
        latest_replay=latest_replay,
        can_resolve_pending=can_resolve_any,
    )
    run_decision, final_recommendation = build_run_decision_frame(
        calendar_gate=calendar_gate,
        outcome_coverage=outcome_coverage,
        provider_audit=provider_audit,
        latest_replay=latest_replay,
        pending_journal_count=len(journals),
    )
    warning = build_speckit_prereq_warning(branch_name or current_git_branch(root))

    calendar_gate.write_csv(output_root / "daily_forward_data_gate.csv")
    outcome_coverage.write_csv(output_root / "outcome_coverage_check.csv")
    provider_audit.write_csv(output_root / "forward_data_provider_audit.csv")
    run_decision.write_csv(output_root / "daily_forward_run_decision.csv")
    _write_markdown_table(
        output_root / "daily_forward_data_gate.md",
        "# Daily Forward Data Gate",
        calendar_gate,
    )
    _write_markdown_table(
        output_root / "outcome_coverage_check.md",
        "# Outcome Coverage Check",
        outcome_coverage,
    )
    _write_markdown_table(
        output_root / "forward_data_provider_audit.md",
        "# Forward Data Provider Audit",
        provider_audit,
    )
    _write_markdown_table(
        output_root / "daily_forward_run_decision.md",
        "# Daily Forward Run Decision",
        run_decision,
    )
    warning_path = output_root / "speckit_prereq_warning.md"
    warning_path.write_text(speckit_warning_markdown(warning), encoding="utf-8")
    daily_note_path = write_daily_journal_note(
        output_root=output_root,
        today=today,
        calendar_gate=calendar_gate,
        outcome_coverage=outcome_coverage,
        provider_audit=provider_audit,
        run_decision=run_decision,
        final_recommendation=final_recommendation,
    )

    return DailyForwardDataGateResult(
        calendar_gate=calendar_gate,
        outcome_coverage=outcome_coverage,
        provider_audit=provider_audit,
        run_decision=run_decision,
        final_recommendation=final_recommendation,
        daily_note_path=daily_note_path,
        speckit_warning=warning,
        speckit_warning_path=warning_path,
    )


def load_replay_rows(output_root: Path) -> list[dict[str, Any]]:
    """Load market-session replay rows from the most specific local artifact."""

    candidates = [
        output_root / "current_week_replay_after_market_session_remap.csv",
        output_root / "current_week_replay_after_approved_remap.csv",
        output_root / "current_week_cme_guru_replay.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    return []


def latest_replay_state(replay_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the latest replay row with weekend-artifact inference."""

    if not replay_rows:
        return {
            "latest_available_replay_date": "",
            "latest_resolved_market_session_date": "",
            "is_weekend_artifact": False,
            "data_state": "MISSING_REPLAY",
            "row": {},
        }
    sorted_rows = sorted(
        replay_rows,
        key=lambda row: str(
            row.get("original_replay_date")
            or row.get("trade_date")
            or row.get("market_session_date")
            or ""
        ),
    )
    row = sorted_rows[-1]
    replay_date = str(row.get("original_replay_date") or row.get("trade_date") or "")
    resolved = str(
        row.get("resolved_market_session_date")
        or row.get("proposed_market_session_date")
        or row.get("market_session_date")
        or replay_date
    )
    replay_day = _parse_date(replay_date)
    resolved_day = _parse_date(resolved)
    weekend_artifact = bool(
        replay_day
        and is_weekend(replay_day)
        and resolved_day
        and replay_day != resolved_day
    )
    data_state = "WEEKEND_ARTIFACT" if weekend_artifact else "MARKET_SESSION_REPLAY"
    return {
        "latest_available_replay_date": replay_date,
        "latest_resolved_market_session_date": resolved,
        "is_weekend_artifact": weekend_artifact,
        "data_state": data_state,
        "row": row,
    }


def build_calendar_gate_frame(
    *,
    today: date,
    latest_replay: dict[str, Any],
    can_resolve_pending: bool,
) -> pl.DataFrame:
    """Build the market calendar/session gate rows for today and latest replay."""

    latest_replay_date = _parse_date(str(latest_replay.get("latest_available_replay_date") or ""))
    dates = [today]
    if latest_replay_date and latest_replay_date != today:
        dates.append(latest_replay_date)

    rows = []
    for calendar_day in dates:
        weekend = is_weekend(calendar_day)
        expected_session = expected_market_session_date(calendar_day)
        latest_artifact = bool(latest_replay.get("is_weekend_artifact"))
        latest_replay_text = str(latest_replay.get("latest_available_replay_date") or "")
        latest_resolved = str(latest_replay.get("latest_resolved_market_session_date") or "")
        provider_lag = latest_replay_date is None or latest_replay_date < expected_session
        create_rows = (
            not weekend
            and not latest_artifact
            and not provider_lag
            and latest_replay_date == expected_session
        )
        reason = calendar_reason(
            calendar_day=calendar_day,
            weekend=weekend,
            latest_artifact=latest_artifact,
            provider_lag=provider_lag,
            latest_replay_date=latest_replay_text,
            latest_resolved=latest_resolved,
        )
        rows.append(
            {
                "calendar_date": calendar_day.isoformat(),
                "day_of_week": calendar_day.strftime("%A"),
                "is_weekend": weekend,
                "is_market_session_expected": not weekend,
                "expected_market_session_date": expected_session.isoformat(),
                "latest_available_replay_date": latest_replay_text,
                "latest_resolved_market_session_date": latest_resolved,
                "is_weekend_artifact": latest_artifact,
                "should_create_new_journal_rows": create_rows,
                "should_resolve_pending_outcomes": bool(
                    can_resolve_pending and not weekend and not latest_artifact
                ),
                "reason_plain_english": reason,
                "timezone_utc": UTC_ZONE.key,
                "timezone_asia_bangkok": BANGKOK_ZONE.key,
                "timezone_cme_exchange": CME_EXCHANGE_ZONE.key,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def calendar_reason(
    *,
    calendar_day: date,
    weekend: bool,
    latest_artifact: bool,
    provider_lag: bool,
    latest_replay_date: str,
    latest_resolved: str,
) -> str:
    """Return a plain-English decision reason without trading claims."""

    if latest_artifact:
        return (
            f"Latest replay row {latest_replay_date} is a weekend artifact resolved "
            f"to market session {latest_resolved}; do not treat it as a new signal."
        )
    if weekend:
        return (
            f"{calendar_day.isoformat()} is a weekend calendar date; wait for the "
            "next market session data before creating new journal rows."
        )
    if provider_lag:
        return "WAIT_FOR_NEXT_SESSION_DATA: provider or replay data has not caught up."
    return "Market-session data is present; journal creation can be considered research-only."


def discover_pending_forward_journals(
    repo_root: Path,
    replay_rows: list[dict[str, Any]],
) -> list[PendingJournal]:
    """Discover pending local forward journal entries under ignored report roots."""

    roots = (
        repo_root / "backend" / "data" / "reports" / "xau_forward_journal",
        repo_root / "data" / "reports" / "xau_forward_journal",
    )
    session_by_date = _session_map(replay_rows)
    journals = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for metadata_path in root.glob("*/metadata.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                outcomes_path = metadata_path.parent / "outcomes.json"
                outcomes = json.loads(outcomes_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not any(str(item.get("status") or "").lower() == "pending" for item in outcomes):
                continue
            journal_id = str(metadata.get("journal_id") or metadata_path.parent.name)
            if journal_id in seen:
                continue
            snapshot = _parse_datetime(metadata.get("snapshot_time"))
            if snapshot is None:
                continue
            trade_date = str(metadata.get("data_date") or snapshot.date().isoformat())
            session_date = session_by_date.get(trade_date, trade_date)
            windows = tuple(str(item.get("window") or "") for item in outcomes if item.get("window"))
            journals.append(
                PendingJournal(
                    journal_id=journal_id,
                    observation_timestamp=snapshot,
                    trade_date=trade_date,
                    session_date=session_date,
                    outcome_windows=windows or WINDOW_ORDER,
                )
            )
            seen.add(journal_id)
    return sorted(journals, key=lambda item: (item.trade_date, item.journal_id))


def build_outcome_coverage_frame(
    journals: Iterable[PendingJournal],
    ohlc_sources: Iterable[OhlcSource],
    *,
    today: date,
    daily_approx_allowed: bool = False,
) -> pl.DataFrame:
    """Check pending journal outcome windows against available OHLC coverage."""

    source_list = list(ohlc_sources)
    rows = [
        coverage_row_for_journal(
            journal,
            source_list,
            today=today,
            daily_approx_allowed=daily_approx_allowed,
        )
        for journal in journals
    ]
    return pl.DataFrame(rows, schema=_outcome_coverage_schema(), infer_schema_length=None)


def coverage_row_for_journal(
    journal: PendingJournal,
    ohlc_sources: list[OhlcSource],
    *,
    today: date,
    daily_approx_allowed: bool = False,
) -> dict[str, Any]:
    """Return one outcome coverage row for a pending journal."""

    windows = required_window_ranges(journal.observation_timestamp)
    intraday_sources = [
        source
        for source in ohlc_sources
        if source.granularity == "INTRADAY"
        and source.current_status in {"AVAILABLE", "STALE"}
        and source.symbol in {"GC=F", "XAU/USD"}
    ]
    daily_sources = [
        source
        for source in ohlc_sources
        if source.granularity == "DAILY"
        and source.current_status in {"AVAILABLE", "STALE"}
    ]
    coverage: dict[str, bool] = {}
    for window, (start, end) in windows.items():
        full_intraday = any(source_covers(source, start, end) for source in intraday_sources)
        full_daily = (
            window not in INTRADAY_WINDOWS
            and daily_approx_allowed
            and any(daily_source_covers(source, end) for source in daily_sources)
        )
        coverage[window] = bool(full_intraday or full_daily)

    latest_intraday = max(
        (source.latest_timestamp for source in intraday_sources if source.latest_timestamp),
        default=None,
    )
    available_sources = "|".join(
        f"{source.symbol} {source.timeframe} {source.proxy_label}".strip()
        for source in source_list_for_display(ohlc_sources)
    )
    missing = [window for window in WINDOW_ORDER if not coverage.get(window, False)]
    can_any = any(coverage.values())
    can_full = all(coverage.get(window, False) for window in WINDOW_ORDER)
    reason = missing_coverage_reason(
        missing,
        latest_intraday=latest_intraday,
        observation=journal.observation_timestamp,
        has_daily=bool(daily_sources),
        has_intraday=bool(intraday_sources),
    )
    return {
        "journal_id": journal.journal_id,
        "observation_timestamp": _iso(journal.observation_timestamp),
        "trade_date": journal.trade_date,
        "session_date": journal.session_date,
        "required_windows": "|".join(WINDOW_ORDER),
        "required_ohlc_granularity": (
            "intraday_ohlc_required_for_30m_1h_4h; "
            "daily_approx_for_session_close_next_day_only_if_configured"
        ),
        "available_ohlc_sources": available_sources,
        "latest_available_ohlc_timestamp": _iso(latest_intraday),
        "coverage_30m": coverage["30m"],
        "coverage_1h": coverage["1h"],
        "coverage_4h": coverage["4h"],
        "coverage_session_close": coverage["session_close"],
        "coverage_next_day": coverage["next_day"],
        "can_resolve_any_window": can_any,
        "can_resolve_full_outcome": can_full,
        "missing_coverage_reason": reason,
        "next_check_recommended_at": _iso(next_check_recommended_at(today)),
    }


def required_window_ranges(observation_timestamp: datetime) -> dict[str, tuple[datetime, datetime]]:
    """Return conservative UTC outcome windows from a snapshot timestamp."""

    start = observation_timestamp.astimezone(UTC)
    session_close = datetime.combine(start.date(), time(21, 0), tzinfo=UTC)
    if session_close <= start:
        session_close += timedelta(days=1)
    return {
        "30m": (start, start + timedelta(minutes=30)),
        "1h": (start, start + timedelta(hours=1)),
        "4h": (start, start + timedelta(hours=4)),
        "session_close": (start, session_close),
        "next_day": (start, start + timedelta(days=1)),
    }


def source_covers(source: OhlcSource, start: datetime, end: datetime) -> bool:
    """Return whether source timestamp bounds cover a full intraday window."""

    if source.date_range_start is None or source.date_range_end is None:
        return False
    return source.date_range_start <= start and source.date_range_end >= end


def daily_source_covers(source: OhlcSource, required_end: datetime) -> bool:
    """Return whether a daily source has a row for the required end date."""

    if source.date_range_end is None:
        return False
    return source.date_range_end.date() >= required_end.date()


def missing_coverage_reason(
    missing: list[str],
    *,
    latest_intraday: datetime | None,
    observation: datetime,
    has_daily: bool,
    has_intraday: bool,
) -> str:
    """Explain why pending windows cannot be resolved."""

    if not missing:
        return "All required windows have usable OHLC coverage."
    if not has_intraday and has_daily:
        return (
            "Only daily OHLC is available. Daily OHLC cannot resolve 30m, 1h, "
            "or 4h intraday windows."
        )
    if latest_intraday and latest_intraday < observation:
        return (
            f"Latest intraday OHLC timestamp {_iso(latest_intraday)} is before "
            f"observation {_iso(observation)}; missing windows: {'|'.join(missing)}."
        )
    if not has_intraday:
        return f"No approved intraday OHLC source is available; missing windows: {'|'.join(missing)}."
    return f"Intraday OHLC does not fully cover required windows: {'|'.join(missing)}."


def discover_ohlc_sources(
    repo_root: Path,
    *,
    today: date,
    latest_replay: dict[str, Any],
) -> list[OhlcSource]:
    """Audit local public/proxy/manual data feeds used by the daily gate."""

    del today
    latest_session = str(latest_replay.get("latest_resolved_market_session_date") or "")
    gld_allowed = yahoo_symbol_allowed("GLD", repo_root=repo_root)
    return [
        yahoo_ohlc_source(
            repo_root,
            provider_name="Yahoo Finance",
            symbol="GC=F",
            timeframe="1m",
            pattern="gc=f_1m_ohlcv*.parquet",
            usable_for=("INTRADAY_OUTCOME",),
            latest_session=latest_session,
            proxy_label="PROXY_ONLY",
        ),
        yahoo_ohlc_source(
            repo_root,
            provider_name="Yahoo Finance",
            symbol="GC=F",
            timeframe="1d",
            pattern="gc=f_1d_ohlcv*.parquet",
            usable_for=("JOURNAL_OBSERVATION", "DAILY_APPROX_OUTCOME", "MARKET_MAP"),
            latest_session=latest_session,
            proxy_label="PROXY_ONLY",
        ),
        canonical_source(
            repo_root,
            provider_name="Local XAU/USD spot",
            symbol="XAU/USD",
            timeframe="intraday",
            path=repo_root / "outputs" / "cme_canonical_xau_spot_price.parquet",
            usable_for=("INTRADAY_OUTCOME", "MARKET_MAP"),
            latest_session=latest_session,
            requested_granularity="INTRADAY",
        ),
        canonical_source(
            repo_root,
            provider_name="Local XAU/USD spot",
            symbol="XAU/USD",
            timeframe="1d",
            path=repo_root / "outputs" / "cme_canonical_xau_spot_price.parquet",
            usable_for=("JOURNAL_OBSERVATION", "DAILY_APPROX_OUTCOME", "MARKET_MAP"),
            latest_session=latest_session,
            requested_granularity="DAILY",
        ),
        yahoo_ohlc_source(
            repo_root,
            provider_name="Yahoo Finance",
            symbol="GLD",
            timeframe="1d",
            pattern="gld_1d_ohlcv*.parquet",
            usable_for=("DAILY_APPROX_OUTCOME", "MARKET_MAP"),
            latest_session=latest_session,
            proxy_label="PROXY_ONLY",
            blocked_by_whitelist=not gld_allowed,
        ),
        manual_snapshot_source(repo_root, latest_session=latest_session),
        canonical_source(
            repo_root,
            provider_name="Local CME OI files",
            symbol="GC options",
            timeframe="daily",
            path=repo_root / "outputs" / "cme_canonical_option_oi_by_strike.parquet",
            usable_for=("MARKET_MAP",),
            latest_session=latest_session,
            requested_granularity="DAILY",
        ),
        transcript_metadata_source(repo_root),
    ]


def yahoo_ohlc_source(
    repo_root: Path,
    *,
    provider_name: str,
    symbol: str,
    timeframe: str,
    pattern: str,
    usable_for: tuple[str, ...],
    latest_session: str,
    proxy_label: str,
    blocked_by_whitelist: bool = False,
) -> OhlcSource:
    """Build a Yahoo local OHLC audit row."""

    if blocked_by_whitelist:
        return OhlcSource(
            provider_name=provider_name,
            symbol=symbol,
            timeframe=timeframe,
            path=None,
            latest_timestamp=None,
            date_range_start=None,
            date_range_end=None,
            rows=0,
            granularity=_granularity_from_timeframe(timeframe),
            current_status="BLOCKED_BY_WHITELIST",
            usable_for=usable_for,
            recommended_fix=(
                "Add GLD only as a research-only PROXY_ONLY Yahoo symbol before "
                "bootstrapping; do not treat it as XAU/USD spot."
            ),
            proxy_label=proxy_label,
        )
    path = _latest_matching_file(repo_root / "data" / "raw" / "yahoo", pattern)
    if path is None:
        return _missing_source(provider_name, symbol, timeframe, usable_for, proxy_label)
    stats = timestamp_stats(path)
    status = _availability_status(stats["end"], latest_session)
    fix = (
        "Refresh Yahoo OHLC after the next market session if this source is needed "
        "for outcome coverage."
    )
    if symbol == "GLD":
        fix = (
            "GLD is whitelisted as research-only PROXY_ONLY; rerun GLD daily "
            "bootstrap if GLD proxy evidence is needed."
        )
    return OhlcSource(
        provider_name=provider_name,
        symbol=symbol,
        timeframe=timeframe,
        path=path,
        latest_timestamp=stats["end"],
        date_range_start=stats["start"],
        date_range_end=stats["end"],
        rows=stats["rows"],
        granularity=_granularity_from_timeframe(timeframe),
        current_status=status,
        usable_for=usable_for,
        recommended_fix=fix,
        proxy_label=proxy_label,
    )


def canonical_source(
    repo_root: Path,
    *,
    provider_name: str,
    symbol: str,
    timeframe: str,
    path: Path,
    usable_for: tuple[str, ...],
    latest_session: str,
    requested_granularity: str,
) -> OhlcSource:
    """Build an audit row for a local canonical file."""

    if not path.exists():
        return _missing_source(provider_name, symbol, timeframe, usable_for, "")
    stats = (
        timestamp_stats_for_intraday(path)
        if requested_granularity == "INTRADAY"
        else timestamp_stats(path)
    )
    detected = detected_granularity(path, stats["rows"])
    if requested_granularity == "INTRADAY" and (detected == "DAILY" or stats["rows"] == 0):
        return OhlcSource(
            provider_name=provider_name,
            symbol=symbol,
            timeframe=timeframe,
            path=path,
            latest_timestamp=stats["end"],
            date_range_start=stats["start"],
            date_range_end=stats["end"],
            rows=stats["rows"],
            granularity="DAILY",
            current_status="MISSING",
            usable_for=usable_for,
            recommended_fix="Import XAU/USD intraday spot OHLC before intraday outcomes.",
        )
    status = _availability_status(stats["end"], latest_session)
    return OhlcSource(
        provider_name=provider_name,
        symbol=symbol,
        timeframe=timeframe,
        path=path,
        latest_timestamp=stats["end"],
        date_range_start=stats["start"],
        date_range_end=stats["end"],
        rows=stats["rows"],
        granularity=requested_granularity,
        current_status=status,
        usable_for=usable_for,
        recommended_fix="Refresh or import this local file if the latest session is missing.",
    )


def manual_snapshot_source(repo_root: Path, *, latest_session: str) -> OhlcSource:
    """Audit CME/QuikStrike manual snapshot availability."""

    roots = (
        repo_root / "backend" / "data" / "reports" / "xau_forward_journal",
        repo_root / "data" / "reports" / "xau_forward_journal",
    )
    latest_timestamp: datetime | None = None
    for root in roots:
        if not root.exists():
            continue
        for metadata_path in root.glob("*/metadata.json"):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            snapshot = _parse_datetime(metadata.get("snapshot_time"))
            if snapshot and (latest_timestamp is None or snapshot > latest_timestamp):
                latest_timestamp = snapshot
    status = "MANUAL_REQUIRED"
    if latest_timestamp and latest_session and latest_timestamp.date().isoformat() >= latest_session:
        status = "AVAILABLE"
    return OhlcSource(
        provider_name="CME/QuikStrike manual snapshot",
        symbol="GC options",
        timeframe="daily_snapshot",
        path=None,
        latest_timestamp=latest_timestamp,
        date_range_start=latest_timestamp,
        date_range_end=latest_timestamp,
        rows=1 if latest_timestamp else 0,
        granularity="MANUAL",
        current_status=status,
        usable_for=("JOURNAL_OBSERVATION", "MARKET_MAP"),
        recommended_fix=(
            "Capture the next real market-session CME/QuikStrike snapshot manually; "
            "do not create weekend artifact signals."
        ),
    )


def transcript_metadata_source(repo_root: Path) -> OhlcSource:
    """Audit transcript metadata files for timing context."""

    candidates = list((repo_root / "outputs").glob("transcript_*metadata*.csv"))
    candidates.extend(
        (repo_root / "data" / "reports" / "youtube_transcripts").glob("**/manifest*.csv")
    )
    path = max(candidates, key=lambda item: item.stat().st_mtime, default=None)
    latest = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) if path else None
    return OhlcSource(
        provider_name="Local transcript metadata files",
        symbol="MTraders transcripts",
        timeframe="metadata",
        path=path,
        latest_timestamp=latest,
        date_range_start=latest,
        date_range_end=latest,
        rows=1 if path else 0,
        granularity="METADATA",
        current_status="AVAILABLE" if path else "MISSING",
        usable_for=("TRANSCRIPT_TIMING",),
        recommended_fix="Refresh transcript metadata only if same-day timing evidence is needed.",
    )


def provider_audit_frame(sources: Iterable[OhlcSource]) -> pl.DataFrame:
    """Convert source metadata into the requested provider audit table."""

    rows = [
        {
            "provider_name": source.provider_name,
            "symbol": source.symbol,
            "timeframe": source.timeframe,
            "latest_timestamp": _iso(source.latest_timestamp),
            "date_range_start": _iso(source.date_range_start),
            "date_range_end": _iso(source.date_range_end),
            "usable_for": "|".join(source.usable_for),
            "current_status": source.current_status,
            "recommended_fix": source.recommended_fix,
            "proxy_label": source.proxy_label,
        }
        for source in sources
    ]
    return pl.DataFrame(rows, schema=_provider_audit_schema(), infer_schema_length=None)


def build_run_decision_frame(
    *,
    calendar_gate: pl.DataFrame,
    outcome_coverage: pl.DataFrame,
    provider_audit: pl.DataFrame,
    latest_replay: dict[str, Any],
    pending_journal_count: int,
) -> tuple[pl.DataFrame, str]:
    """Choose the conservative daily run state and final recommendation."""

    create_rows = _any_true(calendar_gate, "should_create_new_journal_rows")
    resolve_any = _any_true(outcome_coverage, "can_resolve_any_window")
    resolve_full = _any_true(outcome_coverage, "can_resolve_full_outcome")
    missing_coverage = _join_unique(outcome_coverage, "missing_coverage_reason")
    missing_providers = _join_provider_gaps(provider_audit)
    missing_data_text = missing_coverage or missing_providers or "none_detected"
    if bool(latest_replay.get("is_weekend_artifact")):
        run_state = "SKIP_WEEKEND_ARTIFACT"
        final = "SKIP_WEEKEND_ARTIFACT"
        safe_action = "No new journal rows and no outcome resolution are safe from this artifact."
        next_action = "Wait for the next real market-session replay row, then rerun this gate."
        resolve_any = False
        resolve_full = False
        missing_data_text = (
            _latest_pending_missing_coverage(outcome_coverage)
            or "Latest replay is a weekend artifact; wait for next session data."
        )
    elif not create_rows and pending_journal_count == 0:
        run_state = "SKIP_MARKET_CLOSED"
        final = "WAIT_FOR_NEXT_MARKET_SESSION"
        safe_action = "No journal action is safe until the next session data exists."
        next_action = "Refresh the daily data after the next market session closes."
    elif resolve_full:
        run_state = "RESOLVE_FULL_OUTCOMES"
        final = "RESOLVE_OUTCOME_READY"
        safe_action = "Full outcome resolution is ready for covered pending rows."
        next_action = "Run the outcome resolver with the audited OHLC source labels."
    elif resolve_any:
        run_state = "RESOLVE_PARTIAL_OUTCOMES"
        final = "RESOLVE_OUTCOME_READY"
        safe_action = "Partial outcome resolution is possible only for fully covered windows."
        next_action = "Resolve only covered windows and leave missing windows pending."
    elif pending_journal_count > 0:
        run_state = "WAIT_FOR_INTRADAY_OHLC"
        final = "WAIT_FOR_INTRADAY_OHLC"
        safe_action = "Pending outcomes must remain pending until intraday OHLC overlaps windows."
        next_action = "Refresh GC=F 1m or approved XAU/USD intraday OHLC, then rerun this gate."
    elif create_rows:
        run_state = "CREATE_PENDING_JOURNAL_ROWS"
        final = "CREATE_NEW_JOURNAL_READY"
        safe_action = "A new pending research journal row can be created."
        next_action = "Create pending journal rows only from the current real market session."
    else:
        run_state = "WAIT_FOR_MANUAL_CME_SNAPSHOT"
        final = "MANUAL_CME_SNAPSHOT_REQUIRED"
        safe_action = "No journal or outcome action is safe until manual snapshot data exists."
        next_action = "Capture the next real CME/QuikStrike snapshot and rerun this gate."

    rows = [
        {
            "run_state": run_state,
            "final_recommendation": final,
            "what_was_checked": (
                "market_calendar|latest_replay|pending_journals|ohlc_coverage|"
                "provider_audit|speckit_branch_warning"
            ),
            "what_data_is_missing": missing_data_text,
            "any_action_safe_today": bool(create_rows or resolve_any),
            "safe_action_today": safe_action,
            "next_exact_user_action": next_action,
            "should_create_new_journal_rows": bool(create_rows),
            "should_resolve_pending_outcomes": bool(resolve_any),
        }
    ]
    return pl.DataFrame(rows, infer_schema_length=None), final


def write_daily_journal_note(
    *,
    output_root: Path,
    today: date,
    calendar_gate: pl.DataFrame,
    outcome_coverage: pl.DataFrame,
    provider_audit: pl.DataFrame,
    run_decision: pl.DataFrame,
    final_recommendation: str,
) -> Path:
    """Write the safe daily note under ignored outputs/daily_forward_notes."""

    note_dir = output_root / "daily_forward_notes"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"frozen_rule_journal_{today.strftime('%Y%m%d')}.md"
    latest_journal = _last_value(outcome_coverage, "journal_id") or "none"
    pending = outcome_coverage.height
    run_state = _first_value(run_decision, "run_state")
    lines = [
        f"# Frozen Rule Journal - {today.isoformat()}",
        "",
        "Scope: local XAU research-only daily data gate.",
        "",
        "## Market Calendar State",
        "",
        _frame_markdown(calendar_gate),
        "",
        "## Replay State",
        "",
        f"- Latest pending/replay-linked journal: `{latest_journal}`",
        f"- Pending journal rows checked: `{pending}`",
        "",
        "## Data Provider State",
        "",
        _frame_markdown(provider_audit),
        "",
        "## Journal State",
        "",
        f"- Daily run state: `{run_state}`",
        f"- Final recommendation: `{final_recommendation}`",
        "",
        "## Pending Outcomes",
        "",
        _frame_markdown(outcome_coverage),
        "",
        "## Next Action",
        "",
        f"- {_first_value(run_decision, 'next_exact_user_action')}",
        "",
        "## No Tuning Statement",
        "",
        "- Frozen thresholds, rules, scores, and strategy logic were not changed.",
    ]
    text = _safe_report_text("\n".join(lines))
    path.write_text(text, encoding="utf-8")
    return path


def daily_forward_data_gate_report_lines(
    result: DailyForwardDataGateResult | None,
) -> list[str]:
    """Return research_report.md sections for this layer."""

    if result is None:
        return [
            "## Daily Forward Data Gate",
            "",
            "Daily Forward Data Gate was not run.",
        ]
    decision = result.run_decision
    return [
        "## Daily Forward Data Gate",
        "",
        _frame_markdown(result.calendar_gate),
        "",
        "## Outcome Coverage Check",
        "",
        _frame_markdown(result.outcome_coverage),
        "",
        "## Provider/Data Feed Audit",
        "",
        _frame_markdown(result.provider_audit),
        "",
        "## Daily Forward Run Decision",
        "",
        _frame_markdown(result.run_decision),
        "",
        "## Pending Outcome State",
        "",
        f"- Pending rows checked: `{result.outcome_coverage.height}`",
        f"- Can resolve any window: `{_any_true(result.outcome_coverage, 'can_resolve_any_window')}`",
        f"- Can resolve full outcome: `{_any_true(result.outcome_coverage, 'can_resolve_full_outcome')}`",
        "",
        "## Safe Next Action",
        "",
        f"- Final recommendation: `{result.final_recommendation}`",
        f"- Next action: {_first_value(decision, 'next_exact_user_action')}",
        f"- Speckit prereq warning: `{result.speckit_warning.status}`",
    ]


def build_speckit_prereq_warning(branch_name: str) -> SpeckitPrereqWarning:
    """Classify branch naming prereq failures as non-blocking when appropriate."""

    branch = branch_name.strip() or "UNKNOWN"
    numbered = re.match(r"^(\d{3,}|\d{8}-\d{6})-[A-Za-z0-9._-]+$", branch)
    if numbered:
        return SpeckitPrereqWarning(
            status="PASS",
            branch_name=branch,
            blocking=False,
            message="Speckit feature branch naming prerequisite passed.",
        )
    return SpeckitPrereqWarning(
        status="NON_BLOCKING_BRANCH_NAMING_WARNING",
        branch_name=branch,
        blocking=False,
        message=(
            "Speckit prereq helper failed only because the current branch is not "
            "a numbered feature branch; this is recorded without weakening guardrails."
        ),
    )


def speckit_warning_markdown(warning: SpeckitPrereqWarning) -> str:
    """Render the Speckit warning artifact."""

    return "\n".join(
        [
            "# Speckit Prereq Warning",
            "",
            f"- Status: `{warning.status}`",
            f"- Branch: `{warning.branch_name}`",
            f"- Blocking: `{str(warning.blocking).lower()}`",
            f"- Message: {warning.message}",
        ]
    )


def yahoo_symbol_allowed(symbol: str, *, repo_root: Path) -> bool:
    """Check the repo-local Yahoo provider whitelist without importing private config."""

    provider_path = repo_root / "backend" / "src" / "providers" / "yahoo_finance_provider.py"
    if not provider_path.exists():
        return False
    try:
        text = provider_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return f'symbol="{symbol.upper()}"' in text or f"symbol='{symbol.upper()}'" in text


def proxy_only_label(symbol: str) -> str:
    """Return proxy-only labels for supported gold proxy symbols."""

    return "PROXY_ONLY" if symbol.upper() in {"GC=F", "GLD"} else ""


def is_weekend(day: date) -> bool:
    """Return true for Saturday/Sunday calendar dates."""

    return day.weekday() >= 5


def expected_market_session_date(calendar_day: date) -> date:
    """Return the market session date expected for a calendar date."""

    if not is_weekend(calendar_day):
        return calendar_day
    shifted = calendar_day
    while is_weekend(shifted):
        shifted -= timedelta(days=1)
    return shifted


def next_check_recommended_at(today: date) -> datetime:
    """Return the next exact UTC check time after expected session close."""

    next_day = today + timedelta(days=1)
    while is_weekend(next_day):
        next_day += timedelta(days=1)
    return datetime.combine(next_day, time(22, 0), tzinfo=UTC)


def source_list_for_display(sources: Iterable[OhlcSource]) -> list[OhlcSource]:
    """Return displayable sources without missing rows."""

    return [source for source in sources if source.current_status != "MISSING"]


def timestamp_stats(path: Path) -> dict[str, Any]:
    """Read local table timestamp bounds with safe fallbacks."""

    try:
        frame = _read_table(path)
    except Exception:
        return {"start": None, "end": None, "rows": 0}
    if frame.is_empty():
        return {"start": None, "end": None, "rows": 0}
    timestamp_col = _find_timestamp_column(frame.columns)
    if timestamp_col is None:
        return {"start": None, "end": None, "rows": frame.height}
    timestamps = [_parse_datetime(value) for value in frame.get_column(timestamp_col).to_list()]
    clean = [value for value in timestamps if value is not None]
    if not clean:
        return {"start": None, "end": None, "rows": frame.height}
    return {"start": min(clean), "end": max(clean), "rows": frame.height}


def timestamp_stats_for_intraday(path: Path) -> dict[str, Any]:
    """Return timestamp bounds after excluding one-row daily artifact dates."""

    try:
        frame = _read_table(path)
    except Exception:
        return {"start": None, "end": None, "rows": 0}
    if frame.is_empty():
        return {"start": None, "end": None, "rows": 0}
    if "trade_date" in frame.columns:
        active_dates = (
            frame.group_by("trade_date")
            .len()
            .filter(pl.col("len") > 1)
            .get_column("trade_date")
            .to_list()
        )
        frame = frame.filter(pl.col("trade_date").is_in(active_dates))
        if frame.is_empty():
            return {"start": None, "end": None, "rows": 0}
    timestamp_col = _find_timestamp_column(frame.columns)
    if timestamp_col is None:
        return {"start": None, "end": None, "rows": frame.height}
    timestamps = [_parse_datetime(value) for value in frame.get_column(timestamp_col).to_list()]
    clean = [value for value in timestamps if value is not None]
    if not clean:
        return {"start": None, "end": None, "rows": frame.height}
    return {"start": min(clean), "end": max(clean), "rows": frame.height}


def detected_granularity(path: Path, rows: int) -> str:
    """Infer basic timestamp granularity for audit purposes."""

    lower = path.name.lower()
    if any(token in lower for token in ("_1m_", "_2m_", "_5m_", "_15m_", "_1h_")):
        return "INTRADAY"
    if "_1d_" in lower or rows <= 1:
        return "DAILY"
    try:
        frame = _read_table(path)
    except Exception:
        return "UNKNOWN"
    if frame.is_empty():
        return "UNKNOWN"
    timestamp_col = _find_timestamp_column(frame.columns)
    if timestamp_col is not None and frame.height > 1:
        timestamps = sorted(
            {
                value
                for value in (
                    _parse_datetime(item) for item in frame.get_column(timestamp_col).to_list()
                )
                if value is not None
            }
        )
        if len(timestamps) > 1:
            min_delta = min(
                (right - left).total_seconds()
                for left, right in zip(timestamps, timestamps[1:], strict=False)
            )
            return "INTRADAY" if min_delta < 12 * 60 * 60 else "DAILY"
    if "trade_date" not in frame.columns:
        return "UNKNOWN"
    max_rows = max(frame.group_by("trade_date").len().get_column("len").to_list())
    return "INTRADAY" if max_rows > 1 else "DAILY"


def current_git_branch(repo_root: Path) -> str:
    """Return current git branch or UNKNOWN without failing the pipeline."""

    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    return completed.stdout.strip() or "UNKNOWN"


def _latest_matching_file(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    candidates = sorted(root.glob(pattern))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (timestamp_stats(item)["end"] or datetime.min.replace(tzinfo=UTC), item.name))


def _missing_source(
    provider_name: str,
    symbol: str,
    timeframe: str,
    usable_for: tuple[str, ...],
    proxy_label: str,
) -> OhlcSource:
    return OhlcSource(
        provider_name=provider_name,
        symbol=symbol,
        timeframe=timeframe,
        path=None,
        latest_timestamp=None,
        date_range_start=None,
        date_range_end=None,
        rows=0,
        granularity=_granularity_from_timeframe(timeframe),
        current_status="MISSING",
        usable_for=usable_for,
        recommended_fix="Import or refresh this research data feed before using it.",
        proxy_label=proxy_label,
    )


def _availability_status(latest: datetime | None, latest_session: str) -> str:
    if latest is None:
        return "MISSING"
    session = _parse_date(latest_session)
    if session and latest.date() < session:
        return "STALE"
    return "AVAILABLE"


def _granularity_from_timeframe(timeframe: str) -> str:
    return "DAILY" if timeframe.lower() in {"1d", "daily"} else "INTRADAY"


def _read_table(path: Path) -> pl.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pl.read_parquet(path)
    if suffix == ".csv":
        return pl.read_csv(path)
    return pl.DataFrame()


def _find_timestamp_column(columns: Iterable[str]) -> str | None:
    normalized = {_normalize_name(column): column for column in columns}
    for candidate in (
        "timestamp",
        "datetime",
        "date",
        "trade_date",
        "asof_timestamp",
        "snapshot_time",
        "created_at",
    ):
        if candidate in normalized:
            return normalized[candidate]
    return None


def _session_map(replay_rows: list[dict[str, Any]]) -> dict[str, str]:
    mapping = {}
    for row in replay_rows:
        original = str(row.get("original_replay_date") or row.get("trade_date") or "")
        resolved = str(
            row.get("resolved_market_session_date")
            or row.get("proposed_market_session_date")
            or row.get("market_session_date")
            or original
        )
        if original:
            mapping[original] = resolved
    return mapping


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time(), tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed_date = _parse_date(text)
        if parsed_date is None:
            return None
        return datetime.combine(parsed_date, time(), tzinfo=UTC)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _any_true(frame: pl.DataFrame, column: str) -> bool:
    if frame.is_empty() or column not in frame.columns:
        return False
    return any(bool(value) for value in frame.get_column(column).to_list())


def _join_unique(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    values = [str(value) for value in frame.get_column(column).to_list() if value]
    return " | ".join(dict.fromkeys(values))


def _join_provider_gaps(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return ""
    rows = []
    for row in frame.to_dicts():
        if row.get("current_status") in {"MISSING", "STALE", "BLOCKED_BY_WHITELIST", "MANUAL_REQUIRED"}:
            rows.append(f"{row.get('provider_name')} {row.get('symbol')}: {row.get('current_status')}")
    return " | ".join(rows)


def _latest_pending_missing_coverage(frame: pl.DataFrame) -> str:
    if frame.is_empty() or "missing_coverage_reason" not in frame.columns:
        return ""
    pending = frame.filter(pl.col("can_resolve_full_outcome").not_())
    if pending.is_empty():
        return ""
    row = pending.tail(1).to_dicts()[0]
    return str(row.get("missing_coverage_reason") or "")


def _first_value(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    value = frame.get_column(column).head(1).item()
    return str(value)


def _last_value(frame: pl.DataFrame, column: str) -> str:
    if frame.is_empty() or column not in frame.columns:
        return ""
    value = frame.get_column(column).tail(1).item()
    return str(value)


def _safe_report_text(text: str) -> str:
    lower = text.lower()
    for phrase in FORBIDDEN_REPORT_PHRASES:
        if phrase in lower:
            raise ValueError(f"Forbidden report phrase: {phrase}")
    return text


def _write_markdown_table(path: Path, title: str, frame: pl.DataFrame) -> None:
    text = _safe_report_text("\n\n".join([title, _frame_markdown(frame)]))
    path.write_text(text, encoding="utf-8")


def _frame_markdown(frame: pl.DataFrame, *, limit: int = 20) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.head(limit).to_dicts():
        lines.append("| " + " | ".join(_markdown_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _redacted_path(path: Path) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.=-]", "_", path.name)[:80] or "source"
    digest = hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:8]
    return f"<REDACTED_PATH>/{safe_name}|{digest}{path.suffix.lower()}"


def _outcome_coverage_schema() -> dict[str, Any]:
    return {
        "journal_id": pl.String,
        "observation_timestamp": pl.String,
        "trade_date": pl.String,
        "session_date": pl.String,
        "required_windows": pl.String,
        "required_ohlc_granularity": pl.String,
        "available_ohlc_sources": pl.String,
        "latest_available_ohlc_timestamp": pl.String,
        "coverage_30m": pl.Boolean,
        "coverage_1h": pl.Boolean,
        "coverage_4h": pl.Boolean,
        "coverage_session_close": pl.Boolean,
        "coverage_next_day": pl.Boolean,
        "can_resolve_any_window": pl.Boolean,
        "can_resolve_full_outcome": pl.Boolean,
        "missing_coverage_reason": pl.String,
        "next_check_recommended_at": pl.String,
    }


def _provider_audit_schema() -> dict[str, Any]:
    return {
        "provider_name": pl.String,
        "symbol": pl.String,
        "timeframe": pl.String,
        "latest_timestamp": pl.String,
        "date_range_start": pl.String,
        "date_range_end": pl.String,
        "usable_for": pl.String,
        "current_status": pl.String,
        "recommended_fix": pl.String,
        "proxy_label": pl.String,
    }


def main() -> None:
    """CLI entry point for manual local runs."""

    result = run_daily_forward_data_gate()
    print(f"daily_run_decision: {_first_value(result.run_decision, 'run_state')}")
    print(f"final_recommendation: {result.final_recommendation}")
    print(f"daily_note: {result.daily_note_path.as_posix()}")


if __name__ == "__main__":
    main()
