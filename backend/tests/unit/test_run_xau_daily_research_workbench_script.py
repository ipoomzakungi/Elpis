import json
from pathlib import Path

from scripts.run_xau_daily_research_workbench import main
from tests.unit.test_xau_daily_workbench_service import _write_temp_bundle


def test_script_help_returns_zero(capsys) -> None:
    exit_code = main(["--help"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "--cme-source" in captured.out


def test_script_runs_fixture_bundle_and_prints_summary(
    tmp_path: Path,
    capsys,
) -> None:
    input_dir = _write_temp_bundle(tmp_path)

    exit_code = main(
        [
            "--session-date",
            "2026-06-02",
            "--expiration-code",
            "OG1M6",
            "--traded-instrument",
            "XAUUSD",
            "--cme-source",
            "local_bundle",
            "--input-dir",
            str(input_dir),
            "--gc-reference-price",
            "4549.2",
            "--traded-reference-price",
            "4536.7",
            "--session-open-price",
            "4538.0",
            "--output-root",
            str(tmp_path / "data" / "reports"),
            "--map-id",
            "test_script_workbench_map",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["map_id"] == "test_script_workbench_map"
    assert payload["candidate_set_id"]
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True


def test_script_missing_report_json_prints_clean_error(
    tmp_path: Path,
    capsys,
) -> None:
    input_dir = tmp_path / "empty"
    input_dir.mkdir()

    exit_code = main(
        [
            "--session-date",
            "2026-06-02",
            "--expiration-code",
            "OG1M6",
            "--traded-instrument",
            "XAUUSD",
            "--cme-source",
            "local_bundle",
            "--input-dir",
            str(input_dir),
            "--output-root",
            str(tmp_path / "data" / "reports"),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "blocked"
    assert payload["missing_inputs"][0]["input_name"] == "04_xau_vol_oi_report_report.json"
    assert "Traceback" not in captured.err
