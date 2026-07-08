from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models.xau_systematic_research import (
    XauSystematicCmeSourceMode,
    XauSystematicCycleRequest,
    XauSystematicPriceProvider,
)
from src.xau_quikstrike_fusion.report_store import XauQuikStrikeFusionReportStore
from src.xau_systematic_research.orchestrator import XauSystematicResearchOrchestrator
from tests.unit.test_xau_systematic_alignment_engine import _fusion_report


def test_orchestrator_runs_with_latest_existing_cme_and_local_bars(tmp_path: Path) -> None:
    reports_dir = tmp_path / "data" / "reports"
    import_root = tmp_path / "data" / "imports"
    XauQuikStrikeFusionReportStore(reports_dir=reports_dir).persist_report(_fusion_report())
    _write_bars(import_root / "xauusd_1m.csv")

    result = XauSystematicResearchOrchestrator(
        reports_dir=reports_dir,
        import_root=import_root,
    ).run(
        XauSystematicCycleRequest(
            cycle_label="manual",
            cycle_time="manual",
            cme_source_mode=XauSystematicCmeSourceMode.LATEST_EXISTING,
            price_provider=XauSystematicPriceProvider.LATEST_LOCAL_IMPORT,
            output_root=reports_dir,
            research_only_acknowledged=True,
        )
    )

    assert result.signal_allowed is False
    assert result.research_only is True
    assert (result.output_dir / "ai_research_pack.json").exists()
    assert (result.output_dir / "ai_handoff_context.md").exists()
    assert result.aligned_state.cme.fusion_report_id == "fusion_report"
    assert result.aligned_state.price.latest_price is not None


def _write_bars(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo("Asia/Bangkok")
    start = datetime(2026, 6, 8, 13, 0, tzinfo=tz)
    lines = ["timestamp,open,high,low,close,volume\n"]
    for index in range(121):
        timestamp = start + timedelta(minutes=index)
        close = 4050 + (index * 0.05)
        lines.append(
            f"{timestamp.isoformat()},{close},{close + 1},{close - 1},{close},10\n"
        )
    path.write_text("".join(lines), encoding="utf-8")
