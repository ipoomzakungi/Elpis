from __future__ import annotations

import json
from pathlib import Path

from src.xau_market_context.latest_artifact import (
    find_latest_fusion_report,
    find_latest_price_bars,
)
from src.xau_market_context.price_provider import extract_gc_reference_from_fusion


def test_latest_fusion_resolver_picks_newest_valid_folder(tmp_path: Path) -> None:
    old = _fusion_folder(tmp_path, "old", "2026-06-29T06:00:00+00:00")
    newest = _fusion_folder(tmp_path, "newest", "2026-06-29T07:00:00+00:00")
    assert old.exists()

    assert find_latest_fusion_report(tmp_path) == newest


def test_latest_fusion_resolver_skips_corrupt_and_empty_folders(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "report.json").write_text("{not-json", encoding="utf-8")
    valid = _fusion_folder(tmp_path, "valid", "2026-06-29T06:00:00+00:00")

    assert find_latest_fusion_report(tmp_path) == valid


def test_gc_price_extraction_chooses_most_frequent_non_null_future_reference(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "fusion"
    folder.mkdir()
    (folder / "metadata.json").write_text(
        json.dumps({"created_at": "2026-06-29T06:02:49+00:00"}),
        encoding="utf-8",
    )
    (folder / "fused_rows.json").write_text(
        json.dumps(
            [
                {"matrix_value": {"future_reference_price": 4070.0}},
                {"vol2vol_value": {"future_reference_price": 4070.0}},
                {"matrix_value": {"future_reference_price": 4069.5}},
            ]
        ),
        encoding="utf-8",
    )

    price = extract_gc_reference_from_fusion(folder)

    assert price.price == 4070.0
    assert price.timestamp is not None
    assert price.provider_quality == "research_good"


def test_find_latest_price_bars_prefers_recent_supported_xau_file(tmp_path: Path) -> None:
    ignored = tmp_path / "xau.parquet"
    ignored.write_text("unsupported", encoding="utf-8")
    path = tmp_path / "xauusd_1m_latest.csv"
    path.write_text("timestamp,open,high,low,close\n", encoding="utf-8")

    assert find_latest_price_bars(tmp_path, "XAUUSD") == path


def _fusion_folder(root: Path, name: str, created_at: str) -> Path:
    folder = root / name
    folder.mkdir()
    (folder / "metadata.json").write_text(
        json.dumps({"created_at": created_at}),
        encoding="utf-8",
    )
    (folder / "fused_rows.json").write_text("[]", encoding="utf-8")
    return folder

