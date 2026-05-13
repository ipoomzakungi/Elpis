from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.routes.quikstrike_matrix import get_quikstrike_matrix_report_store
from src.main import app
from src.quikstrike_matrix.report_store import QuikStrikeMatrixReportStore


def test_quikstrike_matrix_fixture_flow_preserves_all_three_views(tmp_path: Path):
    store = QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_quikstrike_matrix_report_store] = lambda: store
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/quikstrike-matrix/extractions/from-fixture",
            json=_payload(),
        )
    app.dependency_overrides.clear()
    assert response.status_code == 201
    report = response.json()

    assert report["status"] == "completed"
    assert report["row_count"] == 12
    assert report["strike_count"] == 1
    assert report["expiration_count"] == 2
    assert report["mapping"]["status"] == "valid"
    assert report["conversion_result"]["status"] == "completed"
    assert report["conversion_result"]["row_count"] == 4
    assert {
        summary["view_type"] for summary in report["view_summaries"]
    } == {"open_interest_matrix", "oi_change_matrix", "volume_matrix"}

    app.dependency_overrides[get_quikstrike_matrix_report_store] = lambda: store
    with TestClient(app) as client:
        conversion = client.get(
            f"/api/v1/quikstrike-matrix/extractions/{report['extraction_id']}/conversion"
        )
    app.dependency_overrides.clear()
    assert conversion.status_code == 200
    rows = conversion.json()["rows"]
    assert len(rows) == 4
    assert any(row["open_interest"] == 120 for row in rows)
    assert any(row["oi_change"] == -12 for row in rows)
    assert any(row["volume"] == 33 for row in rows)

    persisted_files = [
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    ]
    assert any(path.startswith("data/raw/quikstrike_matrix/") for path in persisted_files)
    assert any(path.startswith("data/processed/quikstrike_matrix/") for path in persisted_files)
    assert any(path.startswith("data/reports/quikstrike_matrix/") for path in persisted_files)


def test_quikstrike_matrix_fixture_flow_does_not_return_secret_material(tmp_path: Path):
    store = QuikStrikeMatrixReportStore(reports_dir=tmp_path / "data" / "reports")
    app.dependency_overrides[get_quikstrike_matrix_report_store] = lambda: store
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/quikstrike-matrix/extractions/from-fixture",
            json=_payload(),
        )
    app.dependency_overrides.clear()
    payload = response.text.lower()

    assert response.status_code == 201
    assert "bearer abc" not in payload
    assert "set-cookie:" not in payload
    assert "__viewstate" not in payload
    assert "sessionid=" not in payload


def _payload() -> dict:
    timestamp = datetime(2026, 5, 13, tzinfo=UTC).isoformat()
    return {
        "requested_views": [
            "open_interest_matrix",
            "oi_change_matrix",
            "volume_matrix",
        ],
        "metadata_by_view": {
            view: {
                "capture_timestamp": timestamp,
                "product": "Gold (OG|GC)",
                "option_product_code": "OG|GC",
                "futures_symbol": "GC",
                "source_menu": "OPEN INTEREST Matrix",
                "selected_view_type": view,
                "selected_view_label": view,
                "raw_visible_text": "Gold (OG|GC) OPEN INTEREST Matrix",
            }
            for view in ("open_interest_matrix", "oi_change_matrix", "volume_matrix")
        },
        "tables_by_view": {
            "open_interest_matrix": _table("open_interest_matrix", "120", "95", "10", "11"),
            "oi_change_matrix": _table("oi_change_matrix", "-12", "8", "4", "5"),
            "volume_matrix": _table("volume_matrix", "33", "21", "7", "6"),
        },
        "persist_report": True,
        "research_only_acknowledged": True,
    }


def _table(view_type: str, value_1: str, value_2: str, value_3: str, value_4: str) -> dict:
    return {
        "view_type": view_type,
        "html_table": (
            "<table><thead><tr><th>Strike</th><th colspan='2'>G2RK6 GC 2 DTE 4722.6</th>"
            "<th colspan='2'>G2RM6 GC 30 DTE 4740.5</th></tr>"
            "<tr><th></th><th>Call</th><th>Put</th><th>Call</th><th>Put</th></tr></thead>"
            f"<tbody><tr><th>4700</th><td>{value_1}</td><td>{value_2}</td>"
            f"<td>{value_3}</td><td>{value_4}</td></tr></tbody></table>"
        ),
    }
