import json
from pathlib import Path

import polars as pl

from src.models.xau_candidate_outcome import (
    XauCandidateOutcomeRunRequest,
    XauCandidateOutcomeWindow,
)
from src.xau_candidate_outcomes.service import XauCandidateOutcomeService
from tests.unit.test_xau_candidate_outcome_calculator import (
    TIMESTAMP,
    _candidate_set,
    _short_candidate,
)


def test_candidate_artifact_roundtrip_builds_persists_and_loads_outcomes(
    tmp_path: Path,
) -> None:
    candidate_path = _write_candidate_set(tmp_path)
    price_path = _write_price_bars(tmp_path)
    service = XauCandidateOutcomeService(reports_dir=tmp_path / "data" / "reports")

    result = service.run(
        XauCandidateOutcomeRunRequest(
            candidate_set_path=candidate_path,
            price_bars_path=price_path,
            windows=[XauCandidateOutcomeWindow.THIRTY_MINUTES],
            research_only_acknowledged=True,
        )
    )
    loaded = service.read_result(result.outcome_run_id)

    assert result.outcome_run_id == loaded.outcome_run_id
    assert loaded.outcome_count == 1
    assert loaded.signal_allowed is False
    assert (service.store.report_dir(result.outcome_run_id) / "outcome_metadata.json").exists()
    assert (service.store.report_dir(result.outcome_run_id) / "outcomes.json").exists()
    assert (service.store.report_dir(result.outcome_run_id) / "outcomes.md").exists()


def _write_candidate_set(tmp_path: Path) -> Path:
    candidate_set = _candidate_set(_short_candidate())
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(candidate_set.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _write_price_bars(tmp_path: Path) -> Path:
    path = tmp_path / "price_bars.csv"
    pl.DataFrame(
        [
            {
                "timestamp": TIMESTAMP.isoformat(),
                "open": 112.0,
                "high": 114.0,
                "low": 108.0,
                "close": 109.0,
            },
            {
                "timestamp": (TIMESTAMP.replace(minute=45)).isoformat(),
                "open": 109.0,
                "high": 110.0,
                "low": 99.0,
                "close": 100.0,
            },
            {
                "timestamp": (TIMESTAMP.replace(minute=0, hour=15)).isoformat(),
                "open": 100.0,
                "high": 101.0,
                "low": 98.0,
                "close": 99.0,
            },
        ]
    ).write_csv(path)
    return path


__all__ = [
    "_write_candidate_set",
    "_write_price_bars",
]
