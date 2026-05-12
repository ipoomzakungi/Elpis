import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from src.free_derivatives.deribit import (
    create_deribit_request_plan,
    load_deribit_fixture_rows,
    normalize_deribit_instruments,
    normalize_deribit_summary_snapshots,
    parse_deribit_instrument_name,
)
from src.free_derivatives.orchestration import assemble_placeholder_bootstrap_run
from src.free_derivatives.processing import build_deribit_option_wall_snapshots
from src.free_derivatives.report_store import FreeDerivativesReportStore
from src.models.free_derivatives import (
    DeribitOptionsRequest,
    DeribitOptionSummarySnapshot,
    DeribitOptionType,
    FreeDerivativesArtifactType,
    FreeDerivativesBootstrapRequest,
    FreeDerivativesRunStatus,
    FreeDerivativesSourceStatus,
)


def test_deribit_request_plan_preserves_underlyings_expired_flag_fixtures_and_snapshot(
    tmp_path,
):
    instruments_path = tmp_path / "deribit_instruments.json"
    summary_path = tmp_path / "deribit_summary.json"
    snapshot_timestamp = datetime(2026, 5, 12, 10, 0, tzinfo=UTC)
    request = DeribitOptionsRequest(
        underlyings=["btc", "ETH", "btc"],
        include_expired=True,
        snapshot_timestamp=snapshot_timestamp,
        fixture_instruments_path=instruments_path,
        fixture_summary_path=summary_path,
    )

    plan = create_deribit_request_plan(request)

    assert [item.underlying for item in plan] == ["BTC", "ETH"]
    assert [item.requested_item for item in plan] == [
        "BTC:options:include_expired",
        "ETH:options:include_expired",
    ]
    assert all(item.include_expired is True for item in plan)
    assert all(item.snapshot_timestamp == snapshot_timestamp for item in plan)
    assert all(item.fixture_instruments_path == instruments_path for item in plan)
    assert all(item.fixture_summary_path == summary_path for item in plan)


def test_deribit_instrument_parser_normalizes_expiry_strike_call_put_and_filters():
    call = parse_deribit_instrument_name("BTC-27JUN25-100000-C")
    put = parse_deribit_instrument_name("ETH-28MAR25-3500-P")

    assert call.underlying == "BTC"
    assert call.expiry == date(2025, 6, 27)
    assert call.strike == 100000.0
    assert call.option_type == DeribitOptionType.CALL
    assert put.underlying == "ETH"
    assert put.expiry == date(2025, 3, 28)
    assert put.strike == 3500.0
    assert put.option_type == DeribitOptionType.PUT

    instruments = normalize_deribit_instruments(
        [
            {"instrument_name": "BTC-27JUN25-100000-C", "is_active": True},
            {"instrument_name": "SOL-27JUN25-150-C", "is_active": True},
        ],
        requested_underlyings=["BTC", "ETH"],
        include_expired=False,
    )

    assert [instrument.instrument_name for instrument in instruments] == [
        "BTC-27JUN25-100000-C"
    ]

    with pytest.raises(ValueError, match="safe Deribit option instrument name"):
        parse_deribit_instrument_name("../BAD")


def test_deribit_public_summary_normalizes_iv_oi_underlying_volume_and_greeks():
    snapshot_timestamp = datetime(2026, 5, 12, 10, 0, tzinfo=UTC)
    snapshots = normalize_deribit_summary_snapshots(
        [
            {
                "instrument_name": "BTC-27JUN25-100000-C",
                "open_interest": "12.5",
                "mark_iv": "62.1",
                "bid_iv": "61.8",
                "ask_iv": "62.4",
                "underlying_price": "100500",
                "volume": "42",
                "greeks": {
                    "delta": "0.42",
                    "gamma": "0.00015",
                    "vega": "78.5",
                    "theta": "-25.2",
                },
            }
        ],
        requested_underlyings=["BTC"],
        snapshot_timestamp=snapshot_timestamp,
    )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.snapshot_timestamp == snapshot_timestamp
    assert snapshot.instrument_name == "BTC-27JUN25-100000-C"
    assert snapshot.underlying == "BTC"
    assert snapshot.expiry == date(2025, 6, 27)
    assert snapshot.strike == 100000.0
    assert snapshot.option_type == DeribitOptionType.CALL
    assert snapshot.open_interest == 12.5
    assert snapshot.mark_iv == 62.1
    assert snapshot.bid_iv == 61.8
    assert snapshot.ask_iv == 62.4
    assert snapshot.underlying_price == 100500.0
    assert snapshot.volume == 42.0
    assert snapshot.delta == 0.42
    assert snapshot.gamma == 0.00015
    assert snapshot.vega == 78.5
    assert snapshot.theta == -25.2


def test_deribit_missing_iv_or_oi_fields_are_visible_partial_limitations():
    snapshots = normalize_deribit_summary_snapshots(
        [{"instrument_name": "BTC-27JUN25-100000-C", "volume": "3"}],
        requested_underlyings=["BTC"],
        snapshot_timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
    )

    assert len(snapshots) == 1
    assert snapshots[0].open_interest is None
    assert snapshots[0].mark_iv is None
    assert any("missing public IV/OI" in item for item in snapshots[0].limitations)


def test_deribit_option_wall_snapshots_aggregate_by_contract_terms():
    snapshot_timestamp = datetime(2026, 5, 12, 10, 0, tzinfo=UTC)
    snapshots = [
        _snapshot(
            instrument_name="BTC-27JUN25-100000-C",
            snapshot_timestamp=snapshot_timestamp,
            open_interest=12.0,
            mark_iv=62.0,
            volume=10.0,
        ),
        _snapshot(
            instrument_name="BTC-27JUN25-100000-C",
            snapshot_timestamp=snapshot_timestamp,
            open_interest=8.0,
            mark_iv=64.0,
            volume=15.0,
        ),
        _snapshot(
            instrument_name="BTC-27JUN25-90000-P",
            snapshot_timestamp=snapshot_timestamp,
            open_interest=5.0,
            mark_iv=70.0,
            volume=4.0,
        ),
    ]

    walls = build_deribit_option_wall_snapshots(snapshots)

    assert len(walls) == 2
    call_wall = next(wall for wall in walls if wall.option_type == DeribitOptionType.CALL)
    assert call_wall.underlying == "BTC"
    assert call_wall.expiry == date(2025, 6, 27)
    assert call_wall.strike == 100000.0
    assert call_wall.total_open_interest == 20.0
    assert call_wall.average_mark_iv == 63.0
    assert call_wall.volume == 25.0
    assert call_wall.instrument_count == 2


def test_deribit_orchestration_runs_deribit_alone_and_writes_generated_artifacts(
    tmp_path,
):
    instruments_path = _write_json(tmp_path / "instruments.json", _sample_instruments())
    summary_path = _write_json(tmp_path / "summary.json", _sample_summary_rows())
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    request = FreeDerivativesBootstrapRequest(
        include_cftc=False,
        include_gvz=False,
        include_deribit=True,
        deribit={
            "underlyings": ["BTC", "ETH"],
            "snapshot_timestamp": "2026-05-12T10:00:00Z",
            "fixture_instruments_path": instruments_path,
            "fixture_summary_path": summary_path,
        },
        research_only_acknowledged=True,
    )

    run = assemble_placeholder_bootstrap_run(request, store=store)

    assert run.status == FreeDerivativesRunStatus.COMPLETED
    assert len(run.source_results) == 1
    result = run.source_results[0]
    assert result.status == FreeDerivativesSourceStatus.COMPLETED
    assert result.instrument_count == 3
    assert result.row_count == 3
    assert result.snapshot_timestamp == datetime(2026, 5, 12, 10, 0, tzinfo=UTC)
    assert {
        artifact.artifact_type for artifact in result.artifacts
    } == {
        FreeDerivativesArtifactType.RAW_DERIBIT_INSTRUMENTS,
        FreeDerivativesArtifactType.RAW_DERIBIT_SUMMARY,
        FreeDerivativesArtifactType.PROCESSED_DERIBIT_OPTIONS,
        FreeDerivativesArtifactType.PROCESSED_DERIBIT_WALLS,
    }
    assert any("crypto options data only" in item for item in result.limitations)
    assert any("public/no-key" in item for item in result.limitations)


def test_deribit_orchestration_returns_partial_for_missing_iv_or_oi_fields(tmp_path):
    instruments_path = _write_json(tmp_path / "instruments.json", _sample_instruments())
    summary_path = _write_json(
        tmp_path / "summary.json",
        [{"instrument_name": "BTC-27JUN25-100000-C", "volume": "3"}],
    )
    store = FreeDerivativesReportStore(
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    request = FreeDerivativesBootstrapRequest(
        include_cftc=False,
        include_gvz=False,
        include_deribit=True,
        deribit={
            "underlyings": ["BTC"],
            "fixture_instruments_path": instruments_path,
            "fixture_summary_path": summary_path,
        },
        research_only_acknowledged=True,
    )

    run = assemble_placeholder_bootstrap_run(request, store=store)

    assert run.status == FreeDerivativesRunStatus.PARTIAL
    assert run.source_results[0].status == FreeDerivativesSourceStatus.PARTIAL
    assert "missing public IV/OI" in " ".join(run.source_results[0].warnings)


def test_deribit_orchestration_returns_skipped_when_fixtures_are_missing():
    request = FreeDerivativesBootstrapRequest(
        include_cftc=False,
        include_gvz=False,
        include_deribit=True,
        research_only_acknowledged=True,
    )

    run = assemble_placeholder_bootstrap_run(request)

    assert run.status == FreeDerivativesRunStatus.BLOCKED
    assert run.source_results[0].status == FreeDerivativesSourceStatus.SKIPPED
    assert run.source_results[0].artifacts == []
    assert run.source_results[0].missing_data_actions


def test_deribit_fixture_reader_accepts_public_result_wrappers(tmp_path):
    instruments_path = _write_json(
        tmp_path / "instruments.json",
        {"result": {"instruments": _sample_instruments()}},
    )
    summary_path = _write_json(tmp_path / "summary.json", {"result": _sample_summary_rows()})

    instruments = load_deribit_fixture_rows(instruments_path)
    summary = load_deribit_fixture_rows(summary_path)

    assert len(instruments) == 3
    assert len(summary) == 3


def _snapshot(
    *,
    instrument_name: str,
    snapshot_timestamp: datetime,
    open_interest: float | None,
    mark_iv: float | None,
    volume: float | None,
) -> DeribitOptionSummarySnapshot:
    parsed = parse_deribit_instrument_name(instrument_name)
    return DeribitOptionSummarySnapshot(
        snapshot_timestamp=snapshot_timestamp,
        instrument_name=parsed.instrument_name,
        underlying=parsed.underlying,
        expiry=parsed.expiry,
        strike=parsed.strike,
        option_type=parsed.option_type,
        open_interest=open_interest,
        mark_iv=mark_iv,
        volume=volume,
        raw_payload={"instrument_name": instrument_name},
        limitations=[],
    )


def _sample_instruments() -> list[dict[str, object]]:
    return [
        {"instrument_name": "BTC-27JUN25-100000-C", "is_active": True},
        {"instrument_name": "BTC-27JUN25-90000-P", "is_active": True},
        {"instrument_name": "ETH-28MAR25-3500-P", "is_active": True},
    ]


def _sample_summary_rows() -> list[dict[str, object]]:
    return [
        {
            "instrument_name": "BTC-27JUN25-100000-C",
            "open_interest": 12.5,
            "mark_iv": 62.1,
            "bid_iv": 61.8,
            "ask_iv": 62.4,
            "underlying_price": 100500,
            "volume": 42,
        },
        {
            "instrument_name": "BTC-27JUN25-90000-P",
            "open_interest": 7.0,
            "mark_iv": 70.1,
            "bid_iv": 69.8,
            "ask_iv": 70.4,
            "underlying_price": 100500,
            "volume": 11,
        },
        {
            "instrument_name": "ETH-28MAR25-3500-P",
            "open_interest": 25,
            "mark_iv": 55.0,
            "bid_iv": 54.6,
            "ask_iv": 55.4,
            "underlying_price": 3400,
            "volume": 9,
        },
    ]


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
