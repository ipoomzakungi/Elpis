# Quickstart: XAU Vol-OI Wall Engine

**Date**: 2026-05-01  
**Feature**: 006-xau-vol-oi-wall-engine

This quickstart describes the expected validation path after implementation. It uses local sample gold options OI data for research validation only and must not rely on fabricated live trading inputs.

## 1. Verify Existing Checks

From `backend/`:

```powershell
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/ -q
```

From `frontend/`:

```powershell
npm install
npm run build
```

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## 2. Prepare A Local Gold Options OI Sample

Create or place a local CSV/Parquet file under an ignored research data folder such as:

```text
data/raw/xau/sample_gold_options_oi.csv
```

Required columns:

```text
date or timestamp
expiry
strike
option_type
open_interest
```

Optional columns:

```text
oi_change
volume
implied_volatility
underlying_futures_price
xauusd_spot_price
delta
gamma
```

Do not commit imported datasets or generated reports.

## 3. Start Backend

From `backend/`:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

## 4. Run An XAU Vol-OI Report

Submit a report request:

```powershell
$body = @{
  options_oi_file_path = "data/raw/xau/sample_gold_options_oi.csv"
  session_date = "2026-04-30"
  spot_reference = @{
    source = "manual"
    symbol = "XAUUSD"
    price = 2403.0
    timestamp = "2026-04-30T16:00:00Z"
    reference_type = "spot"
  }
  futures_reference = @{
    source = "manual"
    symbol = "GC"
    price = 2410.0
    timestamp = "2026-04-30T16:00:00Z"
    reference_type = "futures"
  }
  volatility_snapshot = @{
    implied_volatility = 0.16
    source = "iv"
    days_to_expiry = 7
  }
  include_2sd_range = $true
  min_wall_score = 0.0
  report_format = "both"
} | ConvertTo-Json -Depth 20

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/xau/vol-oi/reports" `
  -ContentType "application/json" `
  -Body $body
```

Expected behavior:

- The response includes `report_id`, basis snapshot, expected range, wall count, zone count, warnings, and limitations.
- Each wall preserves original futures strike and basis-adjusted spot-equivalent level.
- IV-based range is labeled as IV-based.
- Reports state that OI walls and volatility ranges are research zones only.

## 5. Inspect Saved Reports

List reports:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/xau/vol-oi/reports"
```

Read report:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/xau/vol-oi/reports/{report_id}"
```

Read sections:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/xau/vol-oi/reports/{report_id}/walls"
Invoke-RestMethod "http://localhost:8000/api/v1/xau/vol-oi/reports/{report_id}/zones"
```

Generated report artifacts should appear under:

```text
data/reports/{report_id}/
```

They must remain ignored by git.

## 6. Start Dashboard

From `frontend/`:

```powershell
npm run dev
```

Open:

```text
http://localhost:3000/xau-vol-oi
```

Verify the page shows:

- report selector
- selected session/date
- spot and futures reference
- futures-to-spot basis snapshot
- expected range with source label
- basis-adjusted OI wall table
- zone classification table
- missing-data warnings
- source limitation notes
- no-trade warnings
- research-only disclaimer

## 7. Guardrail Review

Before committing implementation:

```powershell
rg -n -i "live trading|paper trading|shadow trading|private key|api_key|broker|order execution|wallet|rust|clickhouse|postgres|kafka|kubernetes|sklearn|tensorflow|torch" backend/src frontend/src backend/pyproject.toml frontend/package.json .github/workflows/validation.yml
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

Expected result:

- No forbidden dependency or infrastructure additions.
- Any source hits are guardrail/disclaimer text only.
- No imported local data or generated XAU report artifact is tracked.
