from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from src.models.xau_systematic_research import XauSystematicSourceStatus
from src.xau_systematic_research.dukascopy_node_provider import DukascopyNodeProvider


def test_dukascopy_node_command_template_fills_placeholders(tmp_path: Path) -> None:
    provider = DukascopyNodeProvider(import_root=tmp_path)
    command = provider.build_command(
        command_template=(
            "npx dukascopy-node -i {symbol} -from {from_iso} -to {to_iso} "
            "-t {timeframe} -f csv -o {output_path}"
        ),
        symbol="xauusd",
        from_time=datetime.fromisoformat("2026-06-08T10:00:00+07:00"),
        to_time=datetime.fromisoformat("2026-06-08T10:15:00+07:00"),
        timeframe="m1",
        output_path=tmp_path / "bars.csv",
    )

    assert "-i xauusd" in command
    assert "-from 2026-06-08T10:00:00+07:00" in command
    assert "-to 2026-06-08T10:15:00+07:00" in command
    assert f"-o {tmp_path / 'bars.csv'}" in command


def test_dukascopy_node_failure_returns_unavailable_without_raising(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=2, stderr="token=abc failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = DukascopyNodeProvider(import_root=tmp_path).fetch(
        command_template="node fetch.js -i {symbol} -o {output_path}",
        session_date=datetime.fromisoformat("2026-06-08T10:00:00+07:00").date(),
        from_time=datetime.fromisoformat("2026-06-08T10:00:00+07:00"),
        to_time=datetime.fromisoformat("2026-06-08T10:15:00+07:00"),
    )

    assert result.provider_status == XauSystematicSourceStatus.UNAVAILABLE
    assert result.bars_count == 0
    assert result.stderr is not None
    assert "token=[REDACTED]" in result.stderr
    assert result.signal_allowed is False
