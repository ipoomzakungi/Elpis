from __future__ import annotations

from pathlib import Path

import polars as pl

from research_xau_vol_oi.gemini_guru_rulebook_ingest import (
    build_cme_wall_test_plan,
    build_dukascopy_rule_test_plan,
    build_rule_families,
    build_rulebook_caution_audit,
    gemini_guru_rulebook_report_lines,
    parse_gemini_rulebook_claims,
    report_text_is_safe,
    run_gemini_guru_rulebook_ingest,
)


def test_supported_becomes_transcript_supported_not_data_validated() -> None:
    claims = parse_gemini_rulebook_claims(_rulebook_text())
    row = claims.filter(pl.col("claim_id") == "WALL_AS_MAGNET").row(0, named=True)

    assert row["claimed_support_status"] == "Supported"
    assert row["corrected_support_status"] == "TRANSCRIPT_SUPPORTED"
    assert row["data_validation_status"] != "DATA_VALIDATED"


def test_wall_as_magnet_parsed() -> None:
    claims = parse_gemini_rulebook_claims(_rulebook_text())
    row = claims.filter(pl.col("claim_id") == "WALL_AS_MAGNET").row(0, named=True)

    assert "pgkz8_59cHs" in row["transcript_source_id"]
    assert "magnet" in row["plain_english_logic"].lower()


def test_3sd_and_3_5sd_parsed() -> None:
    claims = parse_gemini_rulebook_claims(_rulebook_text())
    ids = set(claims.get_column("claim_id").to_list())

    assert "ENTRY_3SD_EXTREME" in ids
    assert "STOP_3_5SD" in ids
    assert (
        claims.filter(pl.col("claim_id") == "STOP_3_5SD")
        .row(0, named=True)["corrected_support_status"]
        == "TRANSCRIPT_SUPPORTED"
    )


def test_25_and_12_50_rules_parsed() -> None:
    claims = parse_gemini_rulebook_claims(_rulebook_text())
    families = build_rule_families(claims)
    ids = set(families["sd_grid"].get_column("rule_id").to_list())

    assert "$25_GRID_CLUSTERING" in ids
    assert "$12_50_HALF_BLOCK_CLUSTERING" in ids
    assert "TP_FULL_BLOCK_25" in ids
    assert "TP_HALF_BLOCK_12_50" in ids


def test_dukascopy_testable_rules_identified() -> None:
    claims = parse_gemini_rulebook_claims(_rulebook_text())
    plan = build_dukascopy_rule_test_plan(claims)
    rows = {row["rule_id"]: row for row in plan.to_dicts()}

    assert rows["NO_TRADE_1SD"]["current_testable"] is True
    assert rows["ENTRY_2SD_3SD"]["data_validation_status"] == "TESTABLE_WITH_DUKASCOPY"
    assert rows["$25_GRID_CLUSTERING"]["priority"] == 9


def test_cme_only_rules_require_cme_data() -> None:
    plan = build_cme_wall_test_plan(
        inputs={
            "cme_oi": pl.DataFrame(),
            "cme_iv": pl.DataFrame(),
            "basis": pl.DataFrame(),
            "overlap_validation": pl.DataFrame(),
        }
    )
    row = plan.filter(pl.col("rule_id") == "WALL_AS_MAGNET").row(0, named=True)

    assert "total_oi" in row["required_cme_fields"]
    assert row["current_testable_rows"] == 0
    assert row["can_test_now"] is False


def test_caution_audit_flags_must_enter() -> None:
    claims = parse_gemini_rulebook_claims(_rulebook_text())
    caution = build_rulebook_caution_audit(_rulebook_text(), claims)

    assert (
        caution.filter(pl.col("caution_type") == "MUST_ENTER_LANGUAGE").height
        >= 1
    )


def test_output_never_contains_buy_or_sell(tmp_path: Path) -> None:
    rulebook_path = tmp_path / "rulebook.txt"
    rulebook_path.write_text(_rulebook_text(), encoding="utf-8")

    run_gemini_guru_rulebook_ingest(
        output_dir=tmp_path,
        rulebook_path=rulebook_path,
    )
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.glob("gemini_*")
        if path.suffix in {".csv", ".md"}
    )

    assert "BUY" not in combined.upper()
    assert "SELL" not in combined.upper()


def test_report_does_not_claim_profitability(tmp_path: Path) -> None:
    rulebook_path = tmp_path / "rulebook.txt"
    rulebook_path.write_text(_rulebook_text(), encoding="utf-8")
    result = run_gemini_guru_rulebook_ingest(
        output_dir=tmp_path,
        rulebook_path=rulebook_path,
    )
    report = "\n".join(gemini_guru_rulebook_report_lines(result))

    assert "profitable" not in report.lower()
    assert "profitability" not in report.lower()
    assert report_text_is_safe(report)


def test_redacted_paths_only(tmp_path: Path) -> None:
    raw_path = r"C:\Users\example\private\source.csv"
    rulebook_path = tmp_path / "rulebook.txt"
    rulebook_path.write_text(_rulebook_text(extra_evidence=raw_path), encoding="utf-8")

    run_gemini_guru_rulebook_ingest(
        output_dir=tmp_path,
        rulebook_path=rulebook_path,
    )
    text = (tmp_path / "gemini_guru_rulebook_claims.md").read_text(encoding="utf-8")

    assert raw_path not in text
    assert "C:\\Users" not in text
    assert "<REDACTED_PATH>" in text


def _rulebook_text(*, extra_evidence: str = "") -> str:
    return f"""
### F. Specific Hypotheses Verification

#### 1. WALL_AS_MAGNET

* **Verification Status:** **Supported.**
* **Guru Logic & Condition:** Price attraction to a wall is bounded by 100 points.
* **Source Reference:** 02/02/2026 `[pgkz8_59cHs]` (*"มันเยอะที่ไหนมันก็ต้องไปที่นั่น"*).

#### 2. WALL_AS_TP

* **Verification Status:** **Supported.**
* **Source Reference:** 04/02/2026 `[lU0UkVg4kek]` (*"SL ครึ่งบล็อกก็ TP ครึ่งบล็อกสิครับ"*).

#### 3. WALL_AS_REJECTION

* **Verification Status:** **Supported.**
* **Source Reference:** 10/03/2026 `[00M34LEjnCk]` (*"บทวิจัยก็พิสูจน์แล้ว"*).

#### 4. WALL_AS_ACCEPTANCE

* **Verification Status:** **Supported.**
* **Source Reference:** 05/03/2026 `[Yiq8zZNJ8b4]` (*"ใช้ time frame 1 ชั่วโมงเนี่ยแล้วปิดเหนือให้ได้"*).

#### 9. $25_GRID

* **Verification Status:** **Supported.**
* **Source Reference:** 06/04/2026 `[IlAZCw4bxGg]` (*"บล็อก 25"*); 22/05/2026 `[q5Vyo3GO8Ow]` (*"ครึ่งบล็อก"*). {extra_evidence}

#### 10. SD_GRID_ENTRY

* **Verification Status:** **Supported.**
* **Source Reference:** 21/04/2026 `[O8RvHz0WIxo]` (*"โซน 2 SD ขึ้นไป"*).

#### 11. 3SD_ENTRY

* **Verification Status:** **Supported.**
* **Source Reference:** 28/04/2026 `[CwLM6VOQzrY]` (*"3 SD must enter; buy here and sell there"*).

#### 12. 3.5SD_STOP

* **Verification Status:** **Supported.**
* **Source Reference:** 27/04/2026 `[5XrXds7UHfA]` (*"ถ้าหลุดเป็น 3 SD ก็จริงแต่ระวัง"*).

#### 13. NO_TRADE_MIDDLE

* **Verification Status:** **Supported.**
* **Source Reference:** 11/03/2026 `[loecTu1_T9U]` (*"1 SD ไม่เทรด"*).

#### 14. ACCEPTANCE_CONFIRMATION

* **Verification Status:** **Supported.**
* **Source Reference:** 05/03/2026 `[Yiq8zZNJ8b4]` (*"1 ชั่วโมงปิดเหนือ"*).

#### 15. REJECTION_CONFIRMATION

* **Verification Status:** **Supported.**
* **Source Reference:** 28/04/2026 `[1rnyKcPNgps]` (*"เเตะแล้วก็รีเวิร์สลงมา"*).

### SECTION 5: STOP LOSS / INVALIDATION RULES

#### Rule 5.1: Half-Block Midpoint Invalidation

* **Source Evidence:** 05/05/2026 `[sI5ak_i6Ojk]`: *"คัท 12.5 เหรียญ"*.

### SECTION 6: NO-TRADE RULES

#### Rule 6.2: CME Data Delay Disconnection

* **Source Evidence:** 12/03/2026 `[HrSHvlUiCho]`: *"มี data ไม่ได้อัปเดตไม่ต้องเทรด"*.
"""
