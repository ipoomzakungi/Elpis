"""Read-only transcript and market-data recovery audit with privacy redaction.

The audit is intentionally portable: committed code does not name private local
folders, private corpus archives, Codex rollout IDs, or user-specific paths.
External transcript roots and source-identifying keywords must be supplied via
environment variables or an ignored local TOML file.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from research_xau_vol_oi.config import ResearchConfig


TRANSCRIPT_EXTENSIONS = {".txt", ".zip"}
MARKET_EXTENSIONS = {".csv", ".parquet", ".xlsx", ".xls", ".json", ".jsonl", ".md"}
FORBIDDEN_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    "site-packages",
}
DATE_RE = re.compile(r"(?P<year>20\d{2})[-_ ]?(?P<month>\d{2})[-_ ]?(?P<day>\d{2})")
THAI_RE = re.compile(r"[\u0e00-\u0e7f]")
SRT_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s+-->\s+\d{1,2}:\d{2}:\d{2}")
LOCAL_CONFIG_PATH = Path(".xau_local_sources.toml")


@dataclass(frozen=True)
class RecoveryAuditConfig:
    """Local-only recovery settings.

    Defaults are safe for committed runs: project-local roots only, no Codex
    home/session scan, no private keywords, and redacted paths in outputs.
    """

    search_roots: tuple[Path, ...] = (Path("."), Path("data"), Path("outputs"))
    transcript_roots: tuple[Path, ...] = (Path("."), Path("data"), Path("outputs"))
    keyword_patterns: tuple[str, ...] = ()
    include_codex_roots: bool = False
    redact_paths: bool = True
    local_debug: bool = False


@dataclass(frozen=True)
class DataRecoveryAuditResult:
    """Outputs and summary fields from the read-only recovery audit."""

    transcript_manifest: pl.DataFrame
    market_coverage: pl.DataFrame
    alignment: pl.DataFrame
    session_hits: pl.DataFrame
    privacy_audit: pl.DataFrame
    full_corpus_found: bool
    full_corpus_path: str | None
    full_corpus_zip_path: str | None
    likely_session_path: str | None
    market_date_start: str | None
    market_date_end: str | None
    full_validation_dates: int
    logic_only_dates: int


def run_data_recovery_audit_layer(
    *,
    output_dir: str | Path,
    config: ResearchConfig | None = None,
    recovery_config: RecoveryAuditConfig | None = None,
    transcript_roots: list[str | Path] | None = None,
    session_roots: list[str | Path] | None = None,
    market_roots: list[str | Path] | None = None,
) -> DataRecoveryAuditResult:
    """Run the read-only source recovery and coverage audit."""

    cfg = recovery_config or build_recovery_audit_config()
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    transcript_manifest = build_transcript_corpus_manifest(
        transcript_roots or list(default_transcript_roots(config, cfg)),
        recovery_config=cfg,
    )
    session_hits = search_codex_session_roots(
        session_roots if session_roots is not None else list(default_session_roots(cfg)),
        recovery_config=cfg,
    )
    market_coverage = build_market_data_coverage_manifest(
        market_roots or list(default_market_roots(config, cfg)),
        recovery_config=cfg,
    )
    alignment = build_transcript_market_coverage_alignment(
        transcript_manifest,
        market_coverage,
    )
    privacy_audit = build_privacy_path_audit(recovery_config=cfg)
    result = summarize_data_recovery(
        transcript_manifest=transcript_manifest,
        market_coverage=market_coverage,
        alignment=alignment,
        session_hits=session_hits,
        privacy_audit=privacy_audit,
    )

    transcript_manifest.write_csv(output_root / "transcript_corpus_manifest.csv")
    market_coverage.write_csv(output_root / "market_data_coverage_manifest.csv")
    alignment.write_csv(output_root / "transcript_market_coverage_alignment.csv")
    session_hits.write_csv(output_root / "codex_session_hits.csv")
    privacy_audit.write_csv(output_root / "privacy_path_audit.csv")

    (output_root / "transcript_corpus_manifest.md").write_text(
        transcript_manifest_markdown(transcript_manifest, result),
        encoding="utf-8",
    )
    (output_root / "market_data_coverage_report.md").write_text(
        market_coverage_markdown(market_coverage, result),
        encoding="utf-8",
    )
    (output_root / "transcript_market_coverage_alignment.md").write_text(
        alignment_markdown(alignment, result),
        encoding="utf-8",
    )
    (output_root / "codex_session_search_report.md").write_text(
        codex_session_search_markdown(session_hits, result),
        encoding="utf-8",
    )
    (output_root / "source_recovery_action_plan.md").write_text(
        source_recovery_action_plan_markdown(result),
        encoding="utf-8",
    )
    (output_root / "privacy_path_audit_report.md").write_text(
        privacy_path_audit_markdown(privacy_audit),
        encoding="utf-8",
    )
    return result


def build_recovery_audit_config(
    *,
    local_config_path: str | Path = LOCAL_CONFIG_PATH,
) -> RecoveryAuditConfig:
    """Build recovery config from safe defaults, ignored TOML, and env vars."""

    values: dict[str, Any] = {
        "search_roots": [Path("."), Path("data"), Path("outputs")],
        "transcript_roots": [Path("."), Path("data"), Path("outputs")],
        "keyword_patterns": [],
        "include_codex_roots": False,
        "redact_paths": True,
        "local_debug": False,
    }
    toml_path = Path(local_config_path)
    if toml_path.exists():
        local_values = _read_local_config(toml_path)
        values.update({key: value for key, value in local_values.items() if value is not None})

    env_map = {
        "search_roots": "XAU_RECOVERY_SEARCH_ROOTS",
        "transcript_roots": "XAU_TRANSCRIPT_ROOTS",
        "keyword_patterns": "XAU_RECOVERY_KEYWORDS",
        "include_codex_roots": "XAU_INCLUDE_CODEX_ROOTS",
        "local_debug": "XAU_RECOVERY_LOCAL_DEBUG",
        "redact_paths": "XAU_RECOVERY_REDACT_PATHS",
    }
    for key, env_name in env_map.items():
        raw = os.getenv(env_name)
        if raw is None:
            continue
        if key in {"search_roots", "transcript_roots"}:
            values[key] = [Path(item) for item in _split_config_list(raw)]
        elif key == "keyword_patterns":
            values[key] = _split_config_list(raw)
        else:
            values[key] = _parse_bool(raw)

    return RecoveryAuditConfig(
        search_roots=tuple(Path(root) for root in values["search_roots"]),
        transcript_roots=tuple(Path(root) for root in values["transcript_roots"]),
        keyword_patterns=tuple(str(pattern) for pattern in values["keyword_patterns"]),
        include_codex_roots=bool(values["include_codex_roots"]),
        redact_paths=bool(values["redact_paths"]),
        local_debug=bool(values["local_debug"]),
    )


def default_transcript_roots(
    config: ResearchConfig | None = None,
    recovery_config: RecoveryAuditConfig | None = None,
) -> tuple[Path, ...]:
    """Return safe transcript roots without scanning home directories."""

    cfg = config or ResearchConfig()
    recovery = recovery_config or build_recovery_audit_config()
    roots = [*recovery.transcript_roots, *cfg.data_roots]
    return tuple(_dedupe_existing_roots([Path(root) for root in roots]))


def default_market_roots(
    config: ResearchConfig | None = None,
    recovery_config: RecoveryAuditConfig | None = None,
) -> tuple[Path, ...]:
    """Return safe market-data roots without scanning home directories."""

    cfg = config or ResearchConfig()
    recovery = recovery_config or build_recovery_audit_config()
    roots = [*recovery.search_roots, *cfg.data_roots]
    return tuple(_dedupe_existing_roots([Path(root) for root in roots]))


def default_session_roots(recovery_config: RecoveryAuditConfig | None = None) -> tuple[Path, ...]:
    """Return Codex/session roots only when explicitly enabled locally."""

    cfg = recovery_config or build_recovery_audit_config()
    if not cfg.include_codex_roots:
        return ()
    home = Path.home()
    codex_root = home / ".codex"
    roots = [
        Path(".codex"),
        codex_root / "memories" / "rollout_summaries",
        codex_root / "sessions",
        codex_root / "tasks",
        codex_root / "projects",
        home / ".cache" / "codex",
    ]
    return tuple(_dedupe_existing_roots(roots))


def build_transcript_corpus_manifest(
    roots: list[str | Path],
    *,
    recovery_config: RecoveryAuditConfig | None = None,
) -> pl.DataFrame:
    """Build a transcript file and zip-entry manifest with redacted paths."""

    cfg = recovery_config or build_recovery_audit_config()
    resolved_roots = _dedupe_existing_roots([Path(root) for root in roots])
    root_stats = _root_transcript_stats(resolved_roots)
    rows: list[dict[str, Any]] = []
    for path in _iter_files(resolved_roots, TRANSCRIPT_EXTENSIONS):
        source_type = _classify_transcript_source(path, cfg, root_stats, resolved_roots)
        if path.suffix.lower() == ".zip":
            rows.extend(_zip_transcript_rows(path, cfg, source_type))
        elif _looks_like_transcript_file(path):
            rows.append(_transcript_file_row(path, cfg, source_type))
    frame = _frame(rows, _transcript_manifest_schema())
    if frame.is_empty():
        return frame
    return _add_duplicate_groups(frame).sort(["detected_date", "source_id_hash"])


def build_market_data_coverage_manifest(
    roots: list[str | Path],
    *,
    recovery_config: RecoveryAuditConfig | None = None,
) -> pl.DataFrame:
    """Build a file-level coverage manifest for local market data artifacts."""

    cfg = recovery_config or build_recovery_audit_config()
    rows: list[dict[str, Any]] = []
    for path in _iter_files(roots, MARKET_EXTENSIONS):
        if _looks_like_market_file(path):
            rows.append(_market_file_row(path, cfg))
    frame = _frame(rows, _market_manifest_schema())
    if frame.is_empty():
        return frame
    return frame.sort(["date_start", "source_name", "source_id_hash"])


def search_codex_session_roots(
    roots: list[str | Path],
    *,
    recovery_config: RecoveryAuditConfig | None = None,
) -> pl.DataFrame:
    """Search configured session roots for recovery clues with redacted output."""

    cfg = recovery_config or build_recovery_audit_config()
    rows: list[dict[str, Any]] = []
    patterns = _safe_keyword_patterns(cfg)
    for path in _iter_files(roots, {".md", ".jsonl", ".json", ".txt", ".log"}):
        text = _read_text(path, limit_chars=250_000)
        terms = [pattern for pattern in patterns if pattern.lower() in text.lower()]
        if not terms:
            continue
        path_fields = _path_fields(str(path), cfg, file_kind="session")
        rows.append(
            {
                **path_fields,
                "file_name": _display_file_name(path.name, cfg, file_kind="session"),
                "matched_terms": ";".join(hash_source_id(term) for term in terms),
                "likely_role": _session_role(text, terms),
                "thread_id": "",
                "rollout_path": redact_text(_extract_after(text, "rollout_path:"), cfg),
                "cwd": redact_text(_extract_after(text, "cwd:"), cfg),
                "notes": _session_notes(text, terms),
            }
        )
    return _frame(rows, _session_hit_schema()).sort("source_id_hash")


def build_transcript_market_coverage_alignment(
    transcript_manifest: pl.DataFrame,
    market_coverage: pl.DataFrame,
) -> pl.DataFrame:
    """Align transcript dates against available market data windows."""

    transcript_counts = _transcript_counts_by_date(transcript_manifest)
    rows: list[dict[str, Any]] = []
    for transcript_date, count in sorted(transcript_counts.items()):
        flags = _market_flags_for_date(market_coverage, transcript_date)
        can_full = all(
            [
                flags["has_xau_price_data"],
                flags["has_cme_options_oi_data"],
                flags["has_cme_iv_data"],
                flags["has_cme_futures_data"] or flags["has_basis_data"],
            ]
        )
        can_price = flags["has_xau_price_data"]
        reason = _alignment_reason(flags, can_full, can_price)
        rows.append(
            {
                "transcript_date": transcript_date.isoformat(),
                "transcript_count": count,
                "has_transcript": True,
                **flags,
                "can_run_full_vol_oi_validation": can_full,
                "can_run_logic_only_extraction": True,
                "can_run_price_only_outcome_test": can_price,
                "reason_if_not_full_validation": "" if can_full else reason,
            }
        )
    return _frame(rows, _alignment_schema()).sort("transcript_date")


def build_privacy_path_audit(
    *,
    recovery_config: RecoveryAuditConfig | None = None,
) -> pl.DataFrame:
    """Audit current tree/history for generic risky path/session patterns."""

    cfg = recovery_config or build_recovery_audit_config()
    patterns = [
        {
            "risky_string": "legacy_full_corpus_constant",
            "current_pattern": "FULL_CORPUS_" + "WORKSPACE",
            "history_pattern": "FULL_CORPUS_" + "WORKSPACE",
            "severity": "HIGH",
            "remediation": "Remove source-identifying constants from committed code.",
        },
        {
            "risky_string": "personal_windows_home_path",
            "current_pattern": "C:" + "/Users",
            "history_pattern": "C:" + "/Users",
            "severity": "HIGH",
            "remediation": "Use env/TOML local config and redacted paths.",
        },
        {
            "risky_string": "codex_session_path",
            "current_pattern": ".codex" + "/sessions",
            "history_pattern": ".codex" + "/sessions",
            "severity": "HIGH",
            "remediation": "Disable home/session scanning by default and redact session paths.",
        },
        {
            "risky_string": "codex_rollout_id",
            "current_pattern": "roll" + "out-",
            "history_pattern": "roll" + "out-",
            "severity": "HIGH",
            "remediation": "Redact rollout file IDs in reports.",
        },
    ]
    rows: list[dict[str, Any]] = []
    for item in patterns:
        current_hits = _git_grep(item["current_pattern"])
        history_hits = _git_log_pickaxe(item["history_pattern"])
        rows.append(
            {
                "risky_string": item["risky_string"],
                "found_in_current_tree": bool(current_hits),
                "found_in_git_history": bool(history_hits),
                "files_or_commits": redact_text(
                    "; ".join([*current_hits[:10], *history_hits[:10]]),
                    cfg,
                ),
                "severity": item["severity"],
                "remediation": item["remediation"],
            }
        )
    for index, pattern in enumerate(cfg.keyword_patterns, start=1):
        current_hits = _git_grep(pattern)
        history_hits = _git_log_pickaxe(pattern)
        rows.append(
            {
                "risky_string": f"configured_private_keyword_{index}_{hash_source_id(pattern)}",
                "found_in_current_tree": bool(current_hits),
                "found_in_git_history": bool(history_hits),
                "files_or_commits": redact_text(
                    "; ".join([*current_hits[:10], *history_hits[:10]]),
                    cfg,
                ),
                "severity": "HIGH",
                "remediation": "Keep private source keywords in ignored local config only.",
            }
        )
    return _frame(rows, _privacy_audit_schema())


def summarize_data_recovery(
    *,
    transcript_manifest: pl.DataFrame,
    market_coverage: pl.DataFrame,
    alignment: pl.DataFrame,
    session_hits: pl.DataFrame,
    privacy_audit: pl.DataFrame | None = None,
) -> DataRecoveryAuditResult:
    """Summarize recovery findings into fields used by reports."""

    full_rows = (
        transcript_manifest.filter(pl.col("source_type") == "FULL_CORPUS")
        if not transcript_manifest.is_empty()
        else transcript_manifest
    )
    full_txt_count = (
        full_rows.filter(pl.col("file_name").str.contains("TRANSCRIPT_FILE")).height
        if not full_rows.is_empty()
        else 0
    )
    full_corpus_found = full_txt_count >= 800 or _has_full_corpus_zip(transcript_manifest)
    full_corpus_path = _first_redacted_full_corpus_path(full_rows)
    zip_path = _first_full_corpus_zip(transcript_manifest)
    likely_session_path = _likely_session_path(session_hits)
    start, end = _market_date_bounds(market_coverage)
    full_validation_dates = (
        alignment.filter(pl.col("can_run_full_vol_oi_validation")).height
        if not alignment.is_empty()
        else 0
    )
    logic_only_dates = (
        alignment.filter(~pl.col("can_run_full_vol_oi_validation")).height
        if not alignment.is_empty()
        else 0
    )
    return DataRecoveryAuditResult(
        transcript_manifest=transcript_manifest,
        market_coverage=market_coverage,
        alignment=alignment,
        session_hits=session_hits,
        privacy_audit=privacy_audit if privacy_audit is not None else pl.DataFrame(),
        full_corpus_found=full_corpus_found,
        full_corpus_path=full_corpus_path,
        full_corpus_zip_path=zip_path,
        likely_session_path=likely_session_path,
        market_date_start=start,
        market_date_end=end,
        full_validation_dates=full_validation_dates,
        logic_only_dates=logic_only_dates,
    )


def redact_path(
    path: str,
    recovery_config: RecoveryAuditConfig | None = None,
) -> str:
    """Return a path safe for committed/default reports."""

    cfg = recovery_config or build_recovery_audit_config()
    if cfg.local_debug and not cfg.redact_paths:
        return path
    redacted = redact_text(path, cfg)
    if not cfg.redact_paths:
        return redacted
    base, _, member = redacted.partition("!")
    basename = Path(base).name or "<SOURCE_FILE>"
    safe_name = _display_file_name(basename, cfg, file_kind="path")
    if member and cfg.local_debug:
        return f"<REDACTED_PATH>/{safe_name}!{Path(member).name}"
    return f"<REDACTED_PATH>/{safe_name}"


def redact_text(
    text: str,
    recovery_config: RecoveryAuditConfig | None = None,
) -> str:
    """Redact user paths, session IDs, and locally configured private keywords."""

    cfg = recovery_config or build_recovery_audit_config()
    if cfg.local_debug and not cfg.redact_paths:
        return text
    redacted = str(text)
    home = str(Path.home())
    if home:
        redacted = redacted.replace(home, "<USER_HOME>")
        redacted = redacted.replace(home.replace("\\", "/"), "<USER_HOME>")
    redacted = re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/`\s]+", "<USER_HOME>", redacted)
    redacted = re.sub(
        r"\.codex[\\/]+sessions(?:[\\/]+[^`\s;|]+)*",
        "<CODEX_SESSION_DIR>",
        redacted,
        flags=re.IGNORECASE,
    )
    rollout_prefix = "roll" + "out-"
    redacted = re.sub(
        rf"{rollout_prefix}[^\\/`\s;|]+\.jsonl",
        f"{rollout_prefix}<REDACTED>.jsonl",
        redacted,
        flags=re.IGNORECASE,
    )
    for root in [*cfg.search_roots, *cfg.transcript_roots]:
        try:
            root_text = str(Path(root).expanduser().resolve())
        except OSError:
            root_text = str(root)
        if root_text and Path(root_text).is_absolute():
            redacted = redacted.replace(root_text, "<EXTERNAL_CORPUS_ROOT>")
            redacted = redacted.replace(root_text.replace("\\", "/"), "<EXTERNAL_CORPUS_ROOT>")
    for pattern in cfg.keyword_patterns:
        if pattern:
            redacted = redacted.replace(pattern, "<PRIVATE_CORPUS_SOURCE>")
    return redacted


def hash_source_id(value: str) -> str:
    """Create a stable non-reversible source identifier."""

    return hashlib.sha256(str(value).encode("utf-8", errors="ignore")).hexdigest()[:16]


def transcript_manifest_markdown(
    manifest: pl.DataFrame,
    result: DataRecoveryAuditResult,
) -> str:
    """Render a transcript corpus manifest summary."""

    counts = (
        manifest.group_by("source_type").len().sort("source_type")
        if not manifest.is_empty()
        else pl.DataFrame()
    )
    source_zip_counts = _source_zip_counts(manifest)
    dates = _date_range_from_column(manifest, "detected_date")
    full_dates = _full_extracted_date_range(manifest)
    return "\n".join(
        [
            "# Transcript Corpus Manifest",
            "",
            f"- Large external transcript corpus found: {result.full_corpus_found}",
            f"- Full corpus path: `{result.full_corpus_path or 'not found'}`",
            f"- Full corpus archive: `{result.full_corpus_zip_path or 'not found'}`",
            f"- Extracted full-corpus text files found: {_full_extracted_txt_count(manifest)}",
            f"- Extracted full-corpus date range: {full_dates[0] or 'n/a'} "
            f"to {full_dates[1] or 'n/a'}",
            f"- Detected transcript date range: {dates[0] or 'n/a'} to {dates[1] or 'n/a'}",
            f"- Manifest rows: {manifest.height}",
            "",
            "## Counts By Source Type",
            "",
            _frame_markdown(counts),
            "",
            "## Extracted Files Vs Zip Entries",
            "",
            _frame_markdown(source_zip_counts),
            "",
            "## Notes",
            "",
            "- Zip entries are inventoried by hash; source files are not extracted.",
            "- Manifest rows can exceed the clean extracted text-file count because the "
            "audit lists extracted files, zip entries, and project-local subsets.",
            "- Default mode redacts paths and private source names.",
        ]
    )


def market_coverage_markdown(
    coverage: pl.DataFrame,
    result: DataRecoveryAuditResult,
) -> str:
    """Render a market data coverage report."""

    counts = (
        coverage.group_by("source_name").len().sort("source_name")
        if not coverage.is_empty()
        else pl.DataFrame()
    )
    return "\n".join(
        [
            "# Market Data Coverage Report",
            "",
            f"- Market date range: {result.market_date_start or 'n/a'} "
            f"to {result.market_date_end or 'n/a'}",
            f"- Coverage rows: {coverage.height}",
            "",
            "## Counts By Source",
            "",
            _frame_markdown(counts),
            "",
            "## Coverage Detail",
            "",
            _frame_markdown(coverage),
            "",
            "## Interpretation",
            "",
            "- Full Vol-OI validation requires XAU/GC price, CME option OI, IV, and "
            "futures/basis coverage on the same transcript date.",
            "- Transcript history without matching CME data is logic extraction only.",
        ]
    )


def alignment_markdown(
    alignment: pl.DataFrame,
    result: DataRecoveryAuditResult,
) -> str:
    """Render transcript-vs-market coverage alignment."""

    return "\n".join(
        [
            "# Transcript Market Coverage Alignment",
            "",
            f"- Full Vol-OI validation dates: {result.full_validation_dates}",
            f"- Logic-only transcript dates: {result.logic_only_dates}",
            "",
            "## Alignment Preview",
            "",
            _frame_markdown(alignment),
            "",
            "## Classification Rules",
            "",
            "- Transcript + no CME data: logic extraction only.",
            "- Transcript + price data only: price-only outcome tests are possible.",
            "- Transcript + price + CME OI + IV + futures/basis: full validation is possible.",
        ]
    )


def codex_session_search_markdown(
    session_hits: pl.DataFrame,
    result: DataRecoveryAuditResult,
) -> str:
    """Render session recovery findings without leaking local paths."""

    return "\n".join(
        [
            "# Codex Session Search Report",
            "",
            f"- Large external transcript corpus found? {result.full_corpus_found}",
            f"- Corpus path: `{result.full_corpus_path or 'not found'}`",
            f"- Original archive found: `{result.full_corpus_zip_path or 'not found'}`",
            f"- Likely session log: `{result.likely_session_path or 'not found'}`",
            "- Session scanning is disabled by default. Enable it only with local config "
            "or environment variables, and keep redaction enabled.",
            "",
            "## Session Hits",
            "",
            _frame_markdown(session_hits),
        ]
    )


def source_recovery_action_plan_markdown(result: DataRecoveryAuditResult) -> str:
    """Render the recommended next action from recovery findings."""

    fetch_transcripts = "No" if result.full_corpus_found else "Configure local source roots first"
    fetch_cme = "Yes" if result.full_validation_dates < result.logic_only_dates else "Maybe"
    return "\n".join(
        [
            "# Source Recovery Action Plan",
            "",
            f"- Should we fetch transcripts again? {fetch_transcripts}.",
            f"- Should we fetch more CME data instead? {fetch_cme}.",
            f"- Current market coverage range: {result.market_date_start or 'n/a'} "
            f"to {result.market_date_end or 'n/a'}.",
            f"- Full validation dates: {result.full_validation_dates}.",
            f"- Logic-only dates: {result.logic_only_dates}.",
            "",
            "## Recommended Next Action",
            "",
            "- Use ignored local config to point at external transcript corpora.",
            "- Keep recovered transcript history as a source for logic taxonomy and "
            "repeated-rule extraction.",
            "- Treat unmatched transcript dates as logic-only coverage.",
            "- Prioritize importing more CME/QuikStrike history before claiming "
            "transcript-rule validation.",
        ]
    )


def privacy_path_audit_markdown(audit: pl.DataFrame) -> str:
    """Render privacy audit rows."""

    current_clean = (
        audit.filter(pl.col("found_in_current_tree")).is_empty()
        if not audit.is_empty()
        else True
    )
    return "\n".join(
        [
            "# Privacy Path Audit Report",
            "",
            f"- Current tree clean for audited generic patterns: {current_clean}",
            "- History rows may include unrelated older commits; inspect severity and "
            "remediation before merging.",
            "",
            _frame_markdown(audit),
        ]
    )


def _read_local_config(path: Path) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    recovery = parsed.get("recovery", {})
    return {
        "search_roots": [Path(item) for item in recovery.get("search_roots", [])]
        or None,
        "transcript_roots": [Path(item) for item in recovery.get("transcript_roots", [])]
        or None,
        "keyword_patterns": [str(item) for item in recovery.get("keyword_patterns", [])]
        or None,
        "include_codex_roots": recovery.get("include_codex_roots"),
        "redact_paths": recovery.get("redact_paths"),
        "local_debug": recovery.get("local_debug"),
    }


def _split_config_list(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;\n]", raw) if item.strip()]


def _parse_bool(raw: str | bool) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _transcript_file_row(
    path: Path,
    config: RecoveryAuditConfig,
    source_type: str,
) -> dict[str, Any]:
    text = _read_text(path)
    return _transcript_row_from_text(
        raw_path=str(path),
        raw_name=path.name,
        text=text,
        size_bytes=_safe_size(path),
        source_type=source_type,
        notes="source file",
        config=config,
    )


def _zip_transcript_rows(
    path: Path,
    config: RecoveryAuditConfig,
    source_type: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".txt"):
                    continue
                with archive.open(info) as handle:
                    text = handle.read().decode("utf-8", errors="ignore")
                rows.append(
                    _transcript_row_from_text(
                        raw_path=f"{path}!{info.filename}",
                        raw_name=Path(info.filename).name,
                        text=text,
                        size_bytes=info.file_size,
                        source_type=source_type,
                        notes="zip entry; not extracted",
                        config=config,
                    )
                )
    except (OSError, zipfile.BadZipFile):
        rows.append(
            _empty_transcript_row(
                path,
                source_type=source_type,
                notes="zip unreadable",
                config=config,
            )
        )
    return rows


def _transcript_row_from_text(
    *,
    raw_path: str,
    raw_name: str,
    text: str,
    size_bytes: int,
    source_type: str,
    notes: str,
    config: RecoveryAuditConfig,
) -> dict[str, Any]:
    path_fields = _path_fields(raw_path, config, file_kind="transcript")
    detected = _detect_date(raw_name) or _detect_date(text[:2_000])
    return {
        **path_fields,
        "file_name": _display_file_name(raw_name, config, file_kind="transcript"),
        "detected_date": detected.isoformat() if detected else None,
        "source_type": source_type,
        "size_bytes": size_bytes,
        "line_count": text.count("\n") + 1 if text else 0,
        "character_count": len(text),
        "has_thai_text": bool(THAI_RE.search(text)),
        "has_srt_timestamps": bool(SRT_RE.search(text)),
        "detected_title": _display_title(_detect_title(text), config),
        "duplicate_group": _content_hash(text),
        "usable_for_logic_extraction": bool(text.strip()) and bool(THAI_RE.search(text)),
        "notes": notes,
    }


def _empty_transcript_row(
    path: Path,
    *,
    source_type: str,
    notes: str,
    config: RecoveryAuditConfig,
) -> dict[str, Any]:
    path_fields = _path_fields(str(path), config, file_kind="transcript")
    detected = _detect_date(path.name)
    return {
        **path_fields,
        "file_name": _display_file_name(path.name, config, file_kind="transcript"),
        "detected_date": detected.isoformat() if detected else None,
        "source_type": source_type,
        "size_bytes": _safe_size(path),
        "line_count": 0,
        "character_count": 0,
        "has_thai_text": False,
        "has_srt_timestamps": False,
        "detected_title": "",
        "duplicate_group": "",
        "usable_for_logic_extraction": False,
        "notes": notes,
    }


def _market_file_row(path: Path, config: RecoveryAuditConfig) -> dict[str, Any]:
    frame, columns, row_count, notes = _read_market_frame(path)
    detected_start, detected_end = _date_bounds_from_frame_or_name(frame, path)
    source_name = _market_source_name(path, columns)
    key_columns = _key_columns_detected(columns)
    missing = _missing_key_columns(source_name, key_columns)
    symbols = _symbols_detected(frame, path)
    path_fields = _path_fields(str(path), config, file_kind="market")
    return {
        **path_fields,
        "source_name": source_name,
        "file_name": _display_file_name(path.name, config, file_kind="market"),
        "rows_count": row_count,
        "date_start": detected_start,
        "date_end": detected_end,
        "symbols_detected": symbols,
        "key_columns_detected": ";".join(key_columns),
        "missing_key_columns": ";".join(missing),
        "usable_for_alignment": bool(detected_start and detected_end and not missing),
        "notes": notes,
    }


def _read_market_frame(path: Path) -> tuple[pl.DataFrame, list[str], int | None, str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".parquet":
            frame = pl.read_parquet(path)
        elif suffix == ".csv":
            frame = pl.read_csv(path, infer_schema_length=1_000, ignore_errors=True)
        elif suffix in {".xlsx", ".xls"}:
            frame = pl.read_excel(path)
        elif suffix in {".json", ".jsonl"}:
            frame = pl.read_ndjson(path) if suffix == ".jsonl" else pl.read_json(path)
        else:
            text = _read_text(path, limit_chars=20_000)
            return pl.DataFrame(), [], None, f"text artifact; {len(text)} chars inspected"
        return frame, frame.columns, frame.height, "tabular file read"
    except Exception as exc:  # noqa: BLE001 - manifest should surface unreadable files
        return pl.DataFrame(), [], None, f"read failed: {exc}"


def _date_bounds_from_frame_or_name(
    frame: pl.DataFrame,
    path: Path,
) -> tuple[str | None, str | None]:
    if not frame.is_empty():
        for column in _date_candidate_columns(frame.columns):
            dates = [_parse_date_value(value) for value in frame.get_column(column).to_list()]
            dates = [value for value in dates if value is not None]
            if dates:
                return min(dates).isoformat(), max(dates).isoformat()
    dates = _detect_all_dates(path.name)
    if dates:
        return min(dates).isoformat(), max(dates).isoformat()
    return None, None


def _market_source_name(path: Path, columns: list[str]) -> str:
    lower = str(path).lower()
    normalized = {_normalize_col(column) for column in columns}
    if "xau_feature_table" in lower:
        return "FEATURE_TABLE"
    if "signal_events" in lower:
        return "SIGNAL_EVENTS"
    if "backtest_trades" in lower:
        return "BACKTEST_TRADES"
    if "quikstrike" in lower or (
        {"strike", "expiry"}.intersection(normalized)
        and {"open_interest", "oi", "call_oi", "put_oi"}.intersection(normalized)
    ):
        return "CME_OPTIONS_OI"
    if "gc=f" in lower or "yahoo" in lower or {"open", "high", "low", "close"}.issubset(normalized):
        return "YAHOO_XAU_PRICE"
    if "oi_walls" in lower or "wall" in lower:
        return "OI_WALLS"
    if "xau" in lower or "gold" in lower:
        return "XAU_RESEARCH_ARTIFACT"
    return "UNKNOWN_MARKET_ARTIFACT"


def _key_columns_detected(columns: list[str]) -> list[str]:
    aliases = {
        "timestamp": {"timestamp", "datetime", "date", "event_timestamp", "time"},
        "open": {"open"},
        "high": {"high"},
        "low": {"low"},
        "close": {"close", "price", "last"},
        "volume": {"volume", "intraday_volume"},
        "strike": {"strike", "option_strike", "cme_option_strike"},
        "expiry": {"expiry", "expiration", "expiration_date"},
        "dte": {"dte", "days_to_expiry"},
        "open_interest": {"open_interest", "total_oi", "oi", "call_oi", "put_oi"},
        "oi_change": {"oi_change", "open_interest_change", "change_oi"},
        "iv": {"iv", "implied_volatility", "annualized_iv_percent"},
        "futures_price": {"futures_price", "gold_futures_price", "underlying_futures_price"},
        "spot_price": {"spot_price", "xauusd_spot_price", "xau_price"},
        "basis": {"basis"},
        "wall_score": {"wall_score"},
        "sigma_position": {"sigma_position"},
    }
    normalized = {_normalize_col(column) for column in columns}
    return [key for key, names in aliases.items() if normalized.intersection(names)]


def _missing_key_columns(source_name: str, detected: list[str]) -> list[str]:
    requirements = {
        "YAHOO_XAU_PRICE": ["timestamp", "close"],
        "CME_OPTIONS_OI": ["strike", "expiry", "open_interest", "iv"],
        "FEATURE_TABLE": ["timestamp", "close", "sigma_position", "basis", "wall_score"],
        "SIGNAL_EVENTS": ["timestamp"],
        "BACKTEST_TRADES": ["timestamp"],
        "OI_WALLS": ["strike", "wall_score", "basis"],
    }
    required = requirements.get(source_name, [])
    return [name for name in required if name not in detected]


def _symbols_detected(frame: pl.DataFrame, path: Path) -> str:
    for column in frame.columns if not frame.is_empty() else []:
        if _normalize_col(column) in {"symbol", "ticker", "source_symbol"}:
            values = frame.get_column(column).drop_nulls().unique().head(10).to_list()
            return ";".join(str(value) for value in values)
    lower = path.name.lower()
    if "gc=f" in lower:
        return "GC=F"
    if "xau" in lower:
        return "XAU"
    if "gold" in lower:
        return "GOLD"
    return ""


def _market_flags_for_date(market_coverage: pl.DataFrame, transcript_date: date) -> dict[str, bool]:
    flags = {
        "has_xau_price_data": False,
        "has_cme_options_oi_data": False,
        "has_cme_iv_data": False,
        "has_cme_futures_data": False,
        "has_basis_data": False,
    }
    if market_coverage.is_empty():
        return flags
    for row in market_coverage.to_dicts():
        start = _parse_date_value(row.get("date_start"))
        end = _parse_date_value(row.get("date_end"))
        if start is None or end is None or not (start <= transcript_date <= end):
            continue
        source = str(row.get("source_name") or "")
        keys = set(str(row.get("key_columns_detected") or "").split(";"))
        if source in {"YAHOO_XAU_PRICE", "FEATURE_TABLE", "SIGNAL_EVENTS", "BACKTEST_TRADES"}:
            flags["has_xau_price_data"] = True
        if source in {"CME_OPTIONS_OI", "OI_WALLS", "FEATURE_TABLE"}:
            flags["has_cme_options_oi_data"] = True
        if source in {"CME_OPTIONS_OI", "FEATURE_TABLE"} and "iv" in keys:
            flags["has_cme_iv_data"] = True
        if "futures_price" in keys:
            flags["has_cme_futures_data"] = True
        if source in {"FEATURE_TABLE", "OI_WALLS", "CME_OPTIONS_OI"} and "basis" in keys:
            flags["has_basis_data"] = True
    return flags


def _alignment_reason(flags: dict[str, bool], can_full: bool, can_price: bool) -> str:
    if can_full:
        return ""
    missing = [name for name, value in flags.items() if not value]
    if can_price:
        return "price-only outcome test possible; missing " + ", ".join(missing)
    return "logic-only extraction; missing " + ", ".join(missing)


def _transcript_counts_by_date(manifest: pl.DataFrame) -> dict[date, int]:
    if manifest.is_empty() or "detected_date" not in manifest.columns:
        return {}
    counts: dict[date, int] = {}
    rows = manifest.filter(pl.col("usable_for_logic_extraction")).to_dicts()
    for row in rows:
        value = _parse_date_value(row.get("detected_date"))
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _looks_like_transcript_file(path: Path) -> bool:
    lower = str(path).lower()
    return path.suffix.lower() == ".txt" and (
        "transcript" in lower
        or "youtube" in lower
        or "report" in lower
        or bool(_detect_date(path.name))
    )


def _looks_like_market_file(path: Path) -> bool:
    lower = str(path).lower()
    if "site-packages" in lower:
        return False
    terms = (
        "xau",
        "gold",
        "gc=f",
        "quikstrike",
        "cme",
        "yahoo",
        "feature_table",
        "signal_events",
        "backtest_trades",
        "oi_walls",
    )
    return any(term in lower for term in terms)


def _classify_transcript_source(
    path: Path,
    config: RecoveryAuditConfig,
    root_stats: dict[Path, dict[str, Any]],
    roots: list[Path],
) -> str:
    lower_path = str(path).lower()
    if any(pattern.lower() in lower_path for pattern in config.keyword_patterns if pattern):
        return "FULL_CORPUS"
    root = _matching_root(path, roots)
    stats = root_stats.get(root, {}) if root else {}
    if int(stats.get("transcript_count", 0)) >= 800:
        return "FULL_CORPUS"
    if int(stats.get("transcript_count", 0)) <= 50 and int(stats.get("transcript_count", 0)) > 0:
        dates = stats.get("dates", [])
        if len(dates) >= 2 and (max(dates) - min(dates)).days <= 14:
            return "WEEK_SUBSET"
    return "UNKNOWN"


def _root_transcript_stats(roots: list[Path]) -> dict[Path, dict[str, Any]]:
    stats: dict[Path, dict[str, Any]] = {}
    for root in roots:
        count = 0
        dates: list[date] = []
        for path in _iter_files([root], TRANSCRIPT_EXTENSIONS):
            if path.suffix.lower() == ".zip":
                zip_count, zip_dates = _zip_entry_stats(path)
                count += zip_count
                dates.extend(zip_dates)
            elif _looks_like_transcript_file(path):
                count += 1
                detected = _detect_date(path.name)
                if detected:
                    dates.append(detected)
        stats[root] = {"transcript_count": count, "dates": dates}
    return stats


def _zip_entry_stats(path: Path) -> tuple[int, list[date]]:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = [info for info in archive.infolist() if info.filename.lower().endswith(".txt")]
    except (OSError, zipfile.BadZipFile):
        return 0, []
    dates = [_detect_date(info.filename) for info in entries]
    return len(entries), [value for value in dates if value is not None]


def _iter_files(roots: list[str | Path], extensions: set[str], max_files: int = 50_000):
    seen_roots: set[Path] = set()
    yielded: set[Path] = set()
    count = 0
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        if not root.exists():
            continue
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in seen_roots:
            continue
        seen_roots.add(root)
        iterator = [root] if root.is_file() else root.rglob("*")
        for path in iterator:
            if count >= max_files:
                return
            try:
                if not path.is_file() or path.suffix.lower() not in extensions:
                    continue
                if _skip_path(path):
                    continue
                resolved_path = path.resolve()
                if resolved_path in yielded:
                    continue
            except OSError:
                continue
            yielded.add(resolved_path)
            count += 1
            yield path


def _skip_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts.intersection(FORBIDDEN_SKIP_DIRS))


def _dedupe_existing_roots(roots: list[Path]) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        expanded = root.expanduser()
        try:
            key = str(expanded.resolve()) if expanded.exists() else str(expanded)
        except OSError:
            key = str(expanded)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(expanded)
    return deduped


def _matching_root(path: Path, roots: list[Path]) -> Path | None:
    try:
        resolved_path = path.resolve()
    except OSError:
        return None
    candidates: list[Path] = []
    for root in roots:
        try:
            resolved_root = root.resolve()
            resolved_path.relative_to(resolved_root)
            candidates.append(root)
        except (OSError, ValueError):
            continue
    return max(candidates, key=lambda item: len(str(item))) if candidates else None


def _read_text(path: Path, limit_chars: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return text[:limit_chars] if limit_chars is not None else text


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _detect_date(text: str) -> date | None:
    dates = _detect_all_dates(text)
    return dates[0] if dates else None


def _detect_all_dates(text: str) -> list[date]:
    dates: list[date] = []
    for match in DATE_RE.finditer(text):
        try:
            dates.append(
                date(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                )
            )
        except ValueError:
            continue
    return dates


def _parse_date_value(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    detected = _detect_date(text[:30])
    if detected is not None:
        return detected
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _date_candidate_columns(columns: list[str]) -> list[str]:
    priority = []
    for column in columns:
        normalized = _normalize_col(column)
        if normalized in {
            "timestamp",
            "datetime",
            "date",
            "time",
            "event_timestamp",
            "entry_timestamp",
            "available_wall_timestamp",
            "iv_available_timestamp",
        }:
            priority.append(column)
    return priority


def _detect_title(text: str) -> str:
    for line in text.splitlines()[:10]:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("title:"):
            return stripped.split(":", 1)[1].strip()[:200]
        if not SRT_RE.search(stripped):
            return stripped[:200]
    return ""


def _display_title(title: str, config: RecoveryAuditConfig) -> str:
    if config.local_debug:
        return redact_text(title, config)
    return "<TRANSCRIPT_TITLE>" if title else ""


def _display_file_name(name: str, config: RecoveryAuditConfig, *, file_kind: str) -> str:
    if config.local_debug:
        return redact_text(name, config)
    suffix = Path(name).suffix
    if file_kind == "transcript":
        return f"<TRANSCRIPT_FILE>{suffix or '.txt'}"
    if file_kind == "session":
        return "<SESSION_FILE>"
    if _contains_configured_private_keyword(name, config):
        return "<PRIVATE_CORPUS_SOURCE>"
    return Path(name).name


def _contains_configured_private_keyword(text: str, config: RecoveryAuditConfig) -> bool:
    lower = text.lower()
    return any(pattern.lower() in lower for pattern in config.keyword_patterns if pattern)


def _safe_keyword_patterns(config: RecoveryAuditConfig) -> tuple[str, ...]:
    generic = ("transcript", "corpus", "youtube", "xau", "cme", "quikstrike")
    return tuple(dict.fromkeys([*generic, *config.keyword_patterns]))


def _path_fields(raw_path: str, config: RecoveryAuditConfig, *, file_kind: str) -> dict[str, Any]:
    if config.redact_paths and not config.local_debug and file_kind in {"transcript", "session"}:
        raw_base = str(raw_path).split("!", 1)[0]
        safe_name = _display_file_name(Path(raw_base).name, config, file_kind=file_kind)
        redacted = f"<REDACTED_PATH>/{safe_name}"
    else:
        redacted = redact_path(raw_path, config)
    return {
        "source_id_hash": hash_source_id(raw_path),
        "file_path": redacted,
        "redacted_file_path": redacted,
        "path_redacted": redacted != raw_path,
    }


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _add_duplicate_groups(frame: pl.DataFrame) -> pl.DataFrame:
    duplicates = (
        frame.group_by("duplicate_group")
        .len()
        .filter((pl.col("duplicate_group") != "") & (pl.col("len") > 1))
    )
    duplicate_hashes = set(duplicates.get_column("duplicate_group").to_list())
    return frame.with_columns(
        pl.when(pl.col("duplicate_group").is_in(duplicate_hashes))
        .then(pl.col("duplicate_group"))
        .otherwise(pl.lit(""))
        .alias("duplicate_group")
    )


def _normalize_col(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")


def _frame(rows: list[dict[str, Any]], schema: dict[str, Any]) -> pl.DataFrame:
    if rows:
        return pl.DataFrame(rows).select(list(schema))
    return pl.DataFrame(schema=schema)


def _transcript_manifest_schema() -> dict[str, Any]:
    return {
        "source_id_hash": pl.Utf8,
        "file_path": pl.Utf8,
        "redacted_file_path": pl.Utf8,
        "path_redacted": pl.Boolean,
        "file_name": pl.Utf8,
        "detected_date": pl.Utf8,
        "source_type": pl.Utf8,
        "size_bytes": pl.Int64,
        "line_count": pl.Int64,
        "character_count": pl.Int64,
        "has_thai_text": pl.Boolean,
        "has_srt_timestamps": pl.Boolean,
        "detected_title": pl.Utf8,
        "duplicate_group": pl.Utf8,
        "usable_for_logic_extraction": pl.Boolean,
        "notes": pl.Utf8,
    }


def _market_manifest_schema() -> dict[str, Any]:
    return {
        "source_id_hash": pl.Utf8,
        "file_path": pl.Utf8,
        "redacted_file_path": pl.Utf8,
        "path_redacted": pl.Boolean,
        "source_name": pl.Utf8,
        "file_name": pl.Utf8,
        "rows_count": pl.Int64,
        "date_start": pl.Utf8,
        "date_end": pl.Utf8,
        "symbols_detected": pl.Utf8,
        "key_columns_detected": pl.Utf8,
        "missing_key_columns": pl.Utf8,
        "usable_for_alignment": pl.Boolean,
        "notes": pl.Utf8,
    }


def _alignment_schema() -> dict[str, Any]:
    return {
        "transcript_date": pl.Utf8,
        "transcript_count": pl.Int64,
        "has_transcript": pl.Boolean,
        "has_xau_price_data": pl.Boolean,
        "has_cme_options_oi_data": pl.Boolean,
        "has_cme_iv_data": pl.Boolean,
        "has_cme_futures_data": pl.Boolean,
        "has_basis_data": pl.Boolean,
        "can_run_full_vol_oi_validation": pl.Boolean,
        "can_run_logic_only_extraction": pl.Boolean,
        "can_run_price_only_outcome_test": pl.Boolean,
        "reason_if_not_full_validation": pl.Utf8,
    }


def _session_hit_schema() -> dict[str, Any]:
    return {
        "source_id_hash": pl.Utf8,
        "file_path": pl.Utf8,
        "redacted_file_path": pl.Utf8,
        "path_redacted": pl.Boolean,
        "file_name": pl.Utf8,
        "matched_terms": pl.Utf8,
        "likely_role": pl.Utf8,
        "thread_id": pl.Utf8,
        "rollout_path": pl.Utf8,
        "cwd": pl.Utf8,
        "notes": pl.Utf8,
    }


def _privacy_audit_schema() -> dict[str, Any]:
    return {
        "risky_string": pl.Utf8,
        "found_in_current_tree": pl.Boolean,
        "found_in_git_history": pl.Boolean,
        "files_or_commits": pl.Utf8,
        "severity": pl.Utf8,
        "remediation": pl.Utf8,
    }


def _session_role(text: str, matched_terms: list[str]) -> str:
    lower = text.lower()
    if len(set(matched_terms)) >= 2 and "transcript" in lower:
        return "LARGE_TRANSCRIPT_CORPUS"
    if "xau" in lower and "cme" in lower:
        return "PROJECT_TRANSCRIPT_SUBSET"
    return "TRANSCRIPT_RELATED_SESSION"


def _extract_after(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.strip().lower().startswith(prefix.lower()):
            return line.split(":", 1)[1].strip()
    return ""


def _session_notes(text: str, matched_terms: list[str]) -> str:
    notes = []
    lower = text.lower()
    if matched_terms:
        notes.append(f"matched_terms={len(matched_terms)}")
    if "transcript" in lower:
        notes.append("mentions transcript corpus")
    if "zip" in lower or "archive" in lower:
        notes.append("mentions archive")
    return "; ".join(notes)


def _has_full_corpus_zip(manifest: pl.DataFrame) -> bool:
    if manifest.is_empty():
        return False
    rows = manifest.filter((pl.col("source_type") == "FULL_CORPUS") & pl.col("notes").str.contains("zip"))
    return not rows.is_empty()


def _first_redacted_full_corpus_path(frame: pl.DataFrame) -> str | None:
    if frame.is_empty():
        return None
    return str(frame.get_column("redacted_file_path").head(1).item())


def _first_full_corpus_zip(manifest: pl.DataFrame) -> str | None:
    if manifest.is_empty():
        return None
    rows = manifest.filter((pl.col("source_type") == "FULL_CORPUS") & pl.col("notes").str.contains("zip"))
    if rows.is_empty():
        return None
    return str(rows.get_column("redacted_file_path").head(1).item())


def _likely_session_path(session_hits: pl.DataFrame) -> str | None:
    if session_hits.is_empty():
        return None
    rows = session_hits.filter(pl.col("likely_role") == "LARGE_TRANSCRIPT_CORPUS")
    rows = rows if not rows.is_empty() else session_hits
    return str(rows.get_column("redacted_file_path").head(1).item())


def _market_date_bounds(market_coverage: pl.DataFrame) -> tuple[str | None, str | None]:
    if market_coverage.is_empty():
        return None, None
    starts = [_parse_date_value(value) for value in market_coverage.get_column("date_start").to_list()]
    ends = [_parse_date_value(value) for value in market_coverage.get_column("date_end").to_list()]
    dates = [value for value in [*starts, *ends] if value is not None]
    if not dates:
        return None, None
    return min(dates).isoformat(), max(dates).isoformat()


def _date_range_from_column(frame: pl.DataFrame, column: str) -> tuple[str | None, str | None]:
    if frame.is_empty() or column not in frame.columns:
        return None, None
    dates = [_parse_date_value(value) for value in frame.get_column(column).to_list()]
    dates = [value for value in dates if value is not None]
    if not dates:
        return None, None
    return min(dates).isoformat(), max(dates).isoformat()


def _full_extracted_txt_count(manifest: pl.DataFrame) -> int:
    if manifest.is_empty():
        return 0
    return manifest.filter(
        (pl.col("source_type") == "FULL_CORPUS")
        & ~pl.col("notes").str.contains("zip")
        & pl.col("file_name").str.contains("TRANSCRIPT_FILE")
    ).height


def _full_extracted_date_range(manifest: pl.DataFrame) -> tuple[str | None, str | None]:
    if manifest.is_empty():
        return None, None
    full_extracted = manifest.filter(
        (pl.col("source_type") == "FULL_CORPUS")
        & ~pl.col("notes").str.contains("zip")
        & pl.col("file_name").str.contains("TRANSCRIPT_FILE")
    )
    return _date_range_from_column(full_extracted, "detected_date")


def _source_zip_counts(manifest: pl.DataFrame) -> pl.DataFrame:
    if manifest.is_empty():
        return pl.DataFrame()
    return (
        manifest.with_columns(pl.col("notes").str.contains("zip").alias("is_zip_entry"))
        .group_by(["source_type", "is_zip_entry"])
        .len()
        .sort(["source_type", "is_zip_entry"])
    )


def _git_grep(pattern: str) -> list[str]:
    return _run_git(["grep", "-n", "--", pattern])


def _git_log_pickaxe(pattern: str) -> list[str]:
    return _run_git(["log", "--all", "--oneline", "-S", pattern])


def _run_git(args: list[str]) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return []
    if completed.returncode not in {0, 1}:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _frame_markdown(frame: pl.DataFrame) -> str:
    if frame.is_empty():
        return "_No rows._"
    columns = frame.columns
    rows = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for raw in frame.head(20).to_dicts():
        rows.append("| " + " | ".join(str(raw.get(column, "")) for column in columns) + " |")
    return "\n".join(rows)
