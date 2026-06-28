import json
from pathlib import Path

from scripts.run_xau_candidate_forward_outcomes import main
from tests.unit.test_xau_candidate_outcome_store import (
    _write_candidate_set,
    _write_price_bars,
)


def test_script_help_returns_zero(capsys) -> None:
    exit_code = main(["--help"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "--candidate-set-path" in captured.out


def test_script_fixture_run_writes_outcome_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    candidate_path = _write_candidate_set(tmp_path)
    price_path = _write_price_bars(tmp_path)

    exit_code = main(
        [
            "--candidate-set-path",
            str(candidate_path),
            "--price-bars-path",
            str(price_path),
            "--window",
            "30m",
            "--output-root",
            str(tmp_path / "data" / "reports"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["outcome_run_id"]
    assert payload["candidate_count"] == 1
    assert payload["outcome_count"] == 1
    assert payload["artifact_paths"]["outcomes_json"].endswith("outcomes.json")
    assert payload["signal_allowed"] is False
    assert payload["research_only"] is True
