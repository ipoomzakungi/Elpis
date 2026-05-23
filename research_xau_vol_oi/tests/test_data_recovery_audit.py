import zipfile
from datetime import datetime
from pathlib import Path

import polars as pl

from research_xau_vol_oi.data_recovery_audit import (
    RecoveryAuditConfig,
    build_market_data_coverage_manifest,
    build_recovery_audit_config,
    build_transcript_corpus_manifest,
    build_transcript_market_coverage_alignment,
    default_session_roots,
    hash_source_id,
    redact_path,
    redact_text,
    run_data_recovery_audit_layer,
    search_codex_session_roots,
)


def test_transcript_manifest_redacts_paths_and_detects_duplicates(tmp_path) -> None:
    corpus = tmp_path / "large_bundle.zip"
    thai_text = "Title: synthetic 2026-01-02\nทองคำ open interest example"
    with zipfile.ZipFile(corpus, "w") as archive:
        archive.writestr("synthetic_2026-01-02_a.txt", thai_text)
        archive.writestr("synthetic_2026-01-02_b.txt", thai_text)
    config = RecoveryAuditConfig(keyword_patterns=("large_bundle",))

    manifest = build_transcript_corpus_manifest([tmp_path], recovery_config=config)

    assert manifest.height == 2
    assert set(manifest.get_column("source_type").to_list()) == {"FULL_CORPUS"}
    assert manifest.get_column("path_redacted").to_list() == [True, True]
    assert manifest.get_column("file_name").to_list() == ["<TRANSCRIPT_FILE>.txt"] * 2
    assert manifest.filter(pl.col("duplicate_group") != "").height == 2
    assert "large_bundle" not in "\n".join(manifest.get_column("file_path").to_list())


def test_default_config_does_not_scan_home_or_codex() -> None:
    config = build_recovery_audit_config(local_config_path=Path("missing-local-config.toml"))

    assert config.include_codex_roots is False
    assert default_session_roots(config) == ()
    assert all(not root.is_absolute() for root in config.search_roots)


def test_env_config_can_add_external_roots(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XAU_RECOVERY_SEARCH_ROOTS", str(tmp_path))
    monkeypatch.setenv("XAU_TRANSCRIPT_ROOTS", str(tmp_path / "transcripts"))
    monkeypatch.setenv("XAU_RECOVERY_KEYWORDS", "private-pattern")
    monkeypatch.setenv("XAU_INCLUDE_CODEX_ROOTS", "true")

    config = build_recovery_audit_config(local_config_path=tmp_path / "missing.toml")

    assert config.search_roots == (tmp_path,)
    assert config.transcript_roots == (tmp_path / "transcripts",)
    assert config.keyword_patterns == ("private-pattern",)
    assert config.include_codex_roots is True


def test_redaction_hides_windows_home_codex_session_and_rollout_id() -> None:
    risky_path = "C:" + "/Users/" + "localuser/.codex" + "/sessions/2099/01/01/"
    risky_path += "roll" + "out-2099-01-01T00-00-00-abcdef.jsonl"

    redacted_path = redact_path(risky_path)
    redacted_text = redact_text(risky_path)

    assert "localuser" not in redacted_path
    assert "localuser" not in redacted_text
    assert ".codex" not in redacted_text
    assert "abcdef" not in redacted_text
    assert "<REDACTED_PATH>" in redacted_path


def test_local_debug_false_prevents_unredacted_paths(tmp_path) -> None:
    raw_path = str(tmp_path / "private_source.txt")

    assert raw_path not in redact_path(raw_path, RecoveryAuditConfig(local_debug=False))


def test_local_debug_true_can_return_unredacted_when_redaction_disabled(tmp_path) -> None:
    raw_path = str(tmp_path / "private_source.txt")
    config = RecoveryAuditConfig(local_debug=True, redact_paths=False)

    assert redact_path(raw_path, config) == raw_path


def test_hash_source_id_is_stable_and_non_literal() -> None:
    value = "private/source/path"

    assert hash_source_id(value) == hash_source_id(value)
    assert value not in hash_source_id(value)


def test_market_coverage_detects_price_and_cme_requirements(tmp_path) -> None:
    price_path = tmp_path / "gc=f_15m_ohlcv_20260102_20260103.csv"
    pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 1, 2, 9),
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
            },
            {
                "timestamp": datetime(2026, 1, 3, 9),
                "open": 2.0,
                "high": 3.0,
                "low": 1.5,
                "close": 2.5,
            },
        ]
    ).write_csv(price_path)
    cme_path = tmp_path / "quikstrike_xau_20260103.csv"
    pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 1, 3, 10),
                "strike": 2400,
                "expiry": "2026-01-28",
                "open_interest": 100,
                "iv": 18.0,
                "basis": 12.0,
                "futures_price": 2412.0,
            }
        ]
    ).write_csv(cme_path)

    coverage = build_market_data_coverage_manifest([tmp_path])

    assert {"YAHOO_XAU_PRICE", "CME_OPTIONS_OI"}.issubset(
        set(coverage.get_column("source_name").to_list())
    )
    assert coverage.get_column("path_redacted").to_list() == [True, True]
    cme = coverage.filter(pl.col("source_name") == "CME_OPTIONS_OI").row(0, named=True)
    assert "iv" in cme["key_columns_detected"]
    assert cme["usable_for_alignment"] is True


def test_alignment_classifies_logic_price_and_full_validation(tmp_path) -> None:
    transcript_root = tmp_path / "transcripts"
    transcript_root.mkdir()
    for day in ["2026-01-01", "2026-01-02", "2026-01-03"]:
        (transcript_root / f"synthetic_{day}.txt").write_text(
            f"Title: {day}\nทองคำ open interest example",
            encoding="utf-8",
        )
    price = tmp_path / "gc=f_20260102_20260103.csv"
    pl.DataFrame(
        [
            {"timestamp": datetime(2026, 1, 2), "close": 1.0},
            {"timestamp": datetime(2026, 1, 3), "close": 2.0},
        ]
    ).write_csv(price)
    cme = tmp_path / "quikstrike_xau_20260103.csv"
    pl.DataFrame(
        [
            {
                "timestamp": datetime(2026, 1, 3),
                "strike": 2400,
                "expiry": "2026-01-28",
                "open_interest": 100,
                "iv": 18.0,
                "basis": 10.0,
                "futures_price": 2410.0,
            }
        ]
    ).write_csv(cme)

    transcripts = build_transcript_corpus_manifest([transcript_root])
    market = build_market_data_coverage_manifest([tmp_path])
    alignment = build_transcript_market_coverage_alignment(transcripts, market)

    by_date = {row["transcript_date"]: row for row in alignment.to_dicts()}
    assert by_date["2026-01-01"]["can_run_logic_only_extraction"] is True
    assert by_date["2026-01-01"]["can_run_price_only_outcome_test"] is False
    assert by_date["2026-01-02"]["can_run_price_only_outcome_test"] is True
    assert by_date["2026-01-02"]["can_run_full_vol_oi_validation"] is False
    assert by_date["2026-01-03"]["can_run_full_vol_oi_validation"] is True


def test_session_search_redacts_paths_and_hashes_terms(tmp_path) -> None:
    log = tmp_path / "summary.md"
    log.write_text(
        "\n".join(
            [
                "thread_id: abc",
                "rollout_path: D:/private/workspace/session.jsonl",
                "cwd: D:/private/workspace",
                "Created private-pattern transcript archive.",
            ]
        ),
        encoding="utf-8",
    )
    config = RecoveryAuditConfig(keyword_patterns=("private-pattern",))

    hits = search_codex_session_roots([tmp_path], recovery_config=config)

    assert hits.height == 1
    row = hits.row(0, named=True)
    assert row["likely_role"] == "LARGE_TRANSCRIPT_CORPUS"
    assert "private-pattern" not in row["matched_terms"]
    assert "D:/private" not in row["file_path"]


def test_run_data_recovery_audit_layer_writes_redacted_outputs(tmp_path) -> None:
    transcript = tmp_path / "synthetic_2026-01-02.txt"
    transcript.write_text("Title: 2026-01-02\nทองคำ open interest example", encoding="utf-8")

    result = run_data_recovery_audit_layer(
        output_dir=tmp_path / "outputs",
        recovery_config=RecoveryAuditConfig(),
        transcript_roots=[tmp_path],
        market_roots=[tmp_path],
        session_roots=[tmp_path],
    )

    assert result.transcript_manifest.height == 1
    assert (tmp_path / "outputs" / "transcript_corpus_manifest.csv").exists()
    assert (tmp_path / "outputs" / "privacy_path_audit_report.md").exists()
    assert result.logic_only_dates == 1
    report = (tmp_path / "outputs" / "transcript_corpus_manifest.md").read_text(encoding="utf-8")
    assert str(tmp_path) not in report


def test_local_config_file_name_is_gitignored() -> None:
    ignore_text = Path(".gitignore").read_text(encoding="utf-8")

    assert ".xau_local_sources.toml" in ignore_text
