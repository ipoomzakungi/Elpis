# Contract: XAU Bundle To Daily Structural Map Adapter

**Feature**: 020a-xau-real-structural-map-from-bundle

This is a local helper contract. It is not an HTTP API, broker contract, alert contract, order contract, execution contract, or live-trading contract.

## Function

```python
from datetime import date
from pathlib import Path

from src.models.xau_daily_structural_map import XauDailyStructuralMapReportResult

def generate_xau_daily_structural_map_from_bundle(
    *,
    map_id: str,
    session_date: date,
    xau_vol_oi_report_path: Path,
    walls_path: Path | None = None,
    fused_rows_path: Path | None = None,
    traded_instrument: str,
    traded_reference_price: float | None,
    gc_reference_price: float | None,
    manual_basis: float | None,
    session_open_price: float | None,
    session_open_source: str | None,
    output_root: Path | None = None,
    overwrite_allowed: bool = False,
) -> XauDailyStructuralMapReportResult:
    ...
```

## Required Behavior

- Read `xau_vol_oi_report_path` as JSON.
- Read `walls_path` as parquet when it exists.
- Fall back to embedded report JSON walls when parquet is absent.
- Preserve null `oi_change` and `volume`.
- Use expected-range snapshot fields when present.
- Do not convert `range_label` into numeric SD bands.
- Use manual basis first, computed reference basis second, unavailable basis otherwise.
- Persist using Feature 019 report store.
- Return metadata, map, and artifact references.

## Output Guarantees

- `signal_allowed` is false.
- Missing context is represented by null fields, no-signal reasons, readiness, and limitations.
- Artifact paths stay under `data/reports/xau_daily_structural_map/`.
- Local imported options data carries an independent-verification limitation.

## Forbidden Scope

The adapter must not create forward outcomes, reaction labels, entries, stops, PnL, alerts, broker calls, execution requests, private-key handling, ML models, or backtests.
