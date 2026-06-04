# Quickstart: XAU Real Structural Map From Bundle

**Feature**: 020a-xau-real-structural-map-from-bundle
**Date**: 2026-06-04

## Scope

This feature turns saved local XAU QuikStrike/XAU Vol-OI artifacts into a persisted daily structural map. It does not add forward outcomes, signals, alerts, broker execution, PnL, ML, or backtests.

## Local Usage

### Python Helper

```python
from datetime import date
from pathlib import Path

from src.xau_daily_structural_map.bundle_adapter import (
    generate_xau_daily_structural_map_from_bundle,
)

result = generate_xau_daily_structural_map_from_bundle(
    map_id="xau_daily_structural_map_2026-06-02_OG1M6",
    session_date=date(2026, 6, 2),
    xau_vol_oi_report_path=Path("04_xau_vol_oi_report_report.json"),
    walls_path=Path("04_xau_vol_oi_report_walls.parquet"),
    fused_rows_path=Path("03_xau_quikstrike_fusion_fused_rows.json"),
    traded_instrument="XAUUSD",
    traded_reference_price=4536.7,
    gc_reference_price=4549.2,
    manual_basis=None,
    session_open_price=4538.0,
    session_open_source="manual_research_input",
)
```

### Real Local Bundle Script

After copying the real bundle files into `backend/data/imports/xau_quikstrike_20260602/`,
run from the repository root:

```powershell
python backend/scripts/generate_xau_map_from_local_bundle.py `
  --input-dir backend/data/imports/xau_quikstrike_20260602 `
  --session-date 2026-06-02 `
  --expiration-code OG1M6 `
  --traded-instrument XAUUSD `
  --gc-reference-price 4549.2 `
  --traded-reference-price YOUR_XAU_PRICE `
  --session-open-price YOUR_SESSION_OPEN
```

Expected output:

```text
data/reports/xau_daily_structural_map/xau_daily_structural_map_2026-06-02_OG1M6/
|-- metadata.json
|-- map.json
|-- map.md
`-- walls.json
```

## Focused Validation

Run from `backend/`:

```powershell
python -m pytest tests/unit/test_xau_daily_structural_map_store.py -q
python -m pytest tests/unit/test_xau_daily_structural_map.py -q
python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q
python -m pytest tests/unit/test_xau_daily_structural_map_bundle_adapter.py -q
python -m pytest tests/unit/test_generate_xau_map_from_local_bundle.py -q
python -c "from src.main import app; print('backend import ok')"
```

Run ruff from `backend/`:

```powershell
ruff check src/xau_daily_structural_map/bundle_adapter.py tests/unit/test_xau_daily_structural_map_bundle_adapter.py scripts/generate_xau_map_from_local_bundle.py tests/unit/test_generate_xau_map_from_local_bundle.py
```

Expected results:

- Full-context bundle map is ready and round-trips.
- Missing basis keeps spot-equivalent levels null.
- Missing expected range keeps SD fields null.
- Range-label-only context does not create numeric SD bands.
- Null OI-change and volume remain null.
- Missing parquet falls back to embedded walls.
- No-wall bundles still persist with a limitation.
