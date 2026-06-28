import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from src.models.xau_daily_workbench import (
    XauDailyWorkbenchCmeSource,
    XauDailyWorkbenchReadiness,
    XauDailyWorkbenchRunRequest,
)
from src.models.xau_sd_oi_candidate import (
    XauSdOiCandidateSide,
)
from src.xau_daily_workbench.service import (
    FUSED_ROWS_FILENAME,
    REPORT_JSON_FILENAME,
    WALLS_PARQUET_FILENAME,
    XauDailyWorkbenchService,
)
from src.xau_quikstrike_fusion.expected_range import build_expected_range_snapshot


def test_full_fixture_workbench_run_creates_map_and_candidates(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_full",
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
        )
    )

    assert result.readiness == XauDailyWorkbenchReadiness.COMPLETED
    assert result.map_id == "test_xau_workbench_full"
    assert result.candidate_set_id is not None
    assert result.daily_map is not None
    assert result.candidate_set is not None
    assert result.daily_map.signal_allowed is False
    assert result.candidate_set.signal_allowed is False
    assert result.candidate_set.candidates[0].side == XauSdOiCandidateSide.NO_TRADE
    assert (service.map_store.report_dir("test_xau_workbench_full") / "map.json").exists()
    assert (service.map_store.report_dir("test_xau_workbench_full") / "candidates.json").exists()
    assert (service.map_store.report_dir("test_xau_workbench_full") / "candidates.md").exists()
    assert (
        service.map_store.report_dir("test_xau_workbench_full") / "candidate_metadata.json"
    ).exists()


def test_missing_cme_source_fails_cleanly(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")

    result = service.run(
        _request(
            input_dir=tmp_path / "missing_bundle",
            map_id="test_xau_workbench_missing_source",
        )
    )

    assert result.readiness == XauDailyWorkbenchReadiness.BLOCKED
    assert result.map_id is None
    assert "input_dir" in _missing_names(result)
    assert result.signal_allowed is False
    assert result.research_only is True


def test_missing_basis_gives_blocked_no_trade_candidate(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_missing_basis",
            gc_reference_price=None,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
        )
    )

    assert result.readiness == XauDailyWorkbenchReadiness.BLOCKED
    assert result.candidate_set is not None
    candidate = result.candidate_set.candidates[0]
    assert candidate.side == XauSdOiCandidateSide.NO_TRADE
    assert "basis" in _missing_names(result)
    assert candidate.signal_allowed is False


def test_missing_session_open_gives_blocked_no_trade_candidate(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_missing_open",
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=None,
        )
    )

    assert result.readiness == XauDailyWorkbenchReadiness.BLOCKED
    assert result.candidate_set is not None
    candidate = result.candidate_set.candidates[0]
    assert candidate.side == XauSdOiCandidateSide.NO_TRADE
    assert "session_open_price" in _missing_names(result)
    assert candidate.signal_allowed is False


def test_inside_two_sd_is_monitor_only(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_inside_2sd",
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
            confirmation_state="neutral",
            iv_state="stable",
            flow_state="neutral",
        )
    )

    assert result.candidate_set is not None
    candidate = result.candidate_set.candidates[0]
    assert candidate.side == XauSdOiCandidateSide.NO_TRADE
    assert candidate.signal_allowed is False


def test_upper_two_to_three_sd_rejection_creates_short_candidate(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_upper_rejection",
            gc_reference_price=4812.5,
            traded_reference_price=4800.0,
            session_open_price=4538.0,
            confirmation_state="rejection",
            iv_state="stable",
            flow_state="not_breakout_confirmed",
        )
    )

    assert result.candidate_set is not None
    candidate = result.candidate_set.candidates[0]
    assert candidate.side == XauSdOiCandidateSide.SHORT_REVERSION_CANDIDATE
    assert candidate.target_1 is not None
    assert candidate.stop_reference is not None
    assert candidate.signal_allowed is False


def test_lower_two_to_three_sd_rejection_creates_long_candidate(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_lower_rejection",
            gc_reference_price=4262.5,
            traded_reference_price=4250.0,
            session_open_price=4538.0,
            confirmation_state="close_back_inside",
            iv_state="compressing",
            flow_state="not_breakout_confirmed",
        )
    )

    assert result.candidate_set is not None
    candidate = result.candidate_set.candidates[0]
    assert candidate.side == XauSdOiCandidateSide.LONG_REVERSION_CANDIDATE
    assert candidate.target_1 is not None
    assert candidate.stop_reference is not None
    assert candidate.signal_allowed is False


def test_breakout_context_marks_breakout_risk(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_breakout_risk",
            gc_reference_price=4912.5,
            traded_reference_price=4900.0,
            session_open_price=4538.0,
            confirmation_state="acceptance",
            iv_state="expanding",
            flow_state="flow_through_wall",
        )
    )

    assert result.candidate_set is not None
    candidate = result.candidate_set.candidates[0]
    assert candidate.side == XauSdOiCandidateSide.BREAKOUT_RISK
    assert candidate.signal_allowed is False


def test_candidate_artifacts_roundtrip(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    created = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_roundtrip",
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
        )
    )

    loaded = service.read_candidates("test_xau_workbench_roundtrip")

    assert loaded.map_id == created.map_id
    assert loaded.candidate_set_id == created.candidate_set_id
    assert loaded.candidate_metadata.signal_allowed is False
    assert loaded.candidate_set.signal_allowed is False
    assert loaded.candidate_set.candidate_count == 1
    assert loaded.artifact_paths["candidates_json"].endswith("candidates.json")


def test_signal_allowed_false_everywhere(tmp_path: Path) -> None:
    service = XauDailyWorkbenchService(reports_dir=tmp_path / "data" / "reports")
    input_dir = _write_temp_bundle(tmp_path)

    result = service.run(
        _request(
            input_dir=input_dir,
            map_id="test_xau_workbench_signal_disabled",
            gc_reference_price=4549.2,
            traded_reference_price=4536.7,
            session_open_price=4538.0,
        )
    )

    assert result.signal_allowed is False
    assert result.daily_map is not None
    assert result.daily_map.signal_allowed is False
    assert result.candidate_set is not None
    assert result.candidate_set.signal_allowed is False
    assert all(candidate.signal_allowed is False for candidate in result.candidate_set.candidates)
    assert result.candidate_metadata is not None
    assert result.candidate_metadata.signal_allowed is False
    assert result.provider_statuses
    assert result.map_artifact_paths
    assert result.candidate_artifact_paths


def _request(
    *,
    input_dir: Path,
    map_id: str,
    gc_reference_price: float | None = 4549.2,
    traded_reference_price: float | None = 4536.7,
    session_open_price: float | None = 4538.0,
    confirmation_state: str = "unavailable",
    iv_state: str = "unavailable",
    flow_state: str = "unavailable",
) -> XauDailyWorkbenchRunRequest:
    return XauDailyWorkbenchRunRequest(
        session_date=date(2026, 6, 2),
        expiration_code="OG1M6",
        traded_instrument="XAUUSD",
        cme_source=XauDailyWorkbenchCmeSource.LOCAL_BUNDLE,
        input_dir=input_dir,
        map_id=map_id,
        gc_reference_price=gc_reference_price,
        traded_reference_price=traded_reference_price,
        session_open_price=session_open_price,
        confirmation_state=confirmation_state,
        iv_state=iv_state,
        flow_state=flow_state,
        run_candidates=True,
        research_only_acknowledged=True,
    )


def _missing_names(result) -> set[str]:
    return {item.input_name for item in result.missing_inputs}


def _write_temp_bundle(tmp_path: Path) -> Path:
    input_dir = tmp_path / "xau_quikstrike_20260602"
    input_dir.mkdir(exist_ok=True)
    (input_dir / REPORT_JSON_FILENAME).write_text(
        json.dumps(
            {
                "report": {
                    "report_id": "test_xau_vol_oi_20260602",
                    "session_date": "2026-06-02",
                    "expected_range_snapshot": _snapshot_payload(),
                    "limitations": ["Fixture local XAU Vol-OI report."],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (input_dir / FUSED_ROWS_FILENAME).write_text("[]\n", encoding="utf-8")
    pl.DataFrame(
        [
            {
                "wall_id": "wall_4550_call",
                "expiry": "2026-06-05",
                "expiration_code": "OG1M6",
                "strike": 4550.0,
                "option_type": "call",
                "open_interest": 1000.0,
                "oi_change": None,
                "volume": None,
                "wall_score": 0.42,
                "freshness_state": "confirmed",
            }
        ],
        schema_overrides={"oi_change": pl.Float64, "volume": pl.Float64},
    ).write_parquet(input_dir / WALLS_PARQUET_FILENAME)
    return input_dir


def _snapshot_payload() -> dict:
    return build_expected_range_snapshot(
        source_report_id="vol2vol_20260604",
        source_view="QUIKOPTIONS VOL2VOL",
        capture_timestamp=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
        product="Gold",
        option_product_code="OG|GC",
        futures_symbol="GC",
        expiration_code="OG1M6",
        expiry_date=date(2026, 6, 5),
        reference_futures_price=4549.2,
        report_level_iv=0.2508,
        vol_settle=0.2508,
        fractional_dte=3.47,
        cme_numeric_1sd=111.3,
        cme_numeric_2sd=222.6,
        cme_numeric_3sd=333.9,
        upper_1sd=4660.5,
        lower_1sd=4437.9,
        upper_2sd=4771.8,
        lower_2sd=4326.6,
        upper_3sd=4883.1,
        lower_3sd=4215.3,
    ).model_dump(mode="json")
