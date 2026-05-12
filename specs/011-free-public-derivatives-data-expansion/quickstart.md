# Quickstart: Free Public Derivatives Data Expansion

**Date**: 2026-05-12  
**Feature**: 011-free-public-derivatives-data-expansion

This quickstart describes the validation path after implementation. The feature is research-only and must not require live trading, paper trading, shadow trading, private trading keys, broker credentials, wallet/private-key handling, paid vendor credentials, real execution, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML training.

## 1. Verify Existing Checks

From `backend/`:

```powershell
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_free_derivatives_*.py -v
python -m pytest tests/integration/test_free_derivatives_*.py -v
python -m pytest tests/contract/test_free_derivatives_api_contracts.py -v
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

## 2. Fixture-Based Validation

Automated tests and CI must use mocked public responses or local fixture files only.

Fixture coverage should include:

- CFTC futures-only gold rows
- CFTC futures-and-options combined gold rows
- CFTC non-gold rows that must be filtered out
- GVZ daily close rows with at least one date gap
- Deribit instruments for call and put options
- Deribit option summary rows with open interest, mark IV, bid IV, ask IV, underlying price, volume, and partial greeks
- Deribit rows with missing public fields

Expected behavior:

- Processed CFTC output keeps futures-only and combined categories separate.
- Processed GVZ output is labeled as GLD-options-derived proxy volatility.
- Processed Deribit output is labeled as crypto options data only.
- Partial or missing fixture fields produce visible limitations, not fabricated values.

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

## 4. Check Readiness And Capabilities

Call:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/data-sources/readiness"
Invoke-RestMethod "http://localhost:8000/api/v1/data-sources/capabilities"
Invoke-RestMethod "http://localhost:8000/api/v1/data-sources/missing-data"
```

Confirm:

- `cftc_cot` is present.
- `gvz` is present.
- `deribit_public_options` is present.
- CFTC is labeled weekly broad positioning only.
- GVZ is labeled GLD-options-derived proxy volatility, not CME gold options IV surface.
- Deribit is labeled crypto options only, not XAU/gold data.
- XAU local strike-level options OI remains a local CSV/Parquet import requirement.
- No secret values, masked values, partial values, or hashes are exposed.

## 5. Run A Fixture Free Derivatives Bootstrap

Use local fixture paths or mocked responses in development validation:

```powershell
$body = @{
  include_cftc = $true
  include_gvz = $true
  include_deribit = $true
  cftc = @{
    years = @(2025, 2026)
    categories = @("futures_only", "futures_and_options_combined")
    market_filters = @("gold", "comex")
    source_urls = @()
    local_fixture_paths = @("backend/tests/fixtures/free_derivatives/cftc_gold.csv")
  }
  gvz = @{
    series_id = "GVZCLS"
    start_date = "2025-01-01"
    end_date = "2026-05-12"
    local_fixture_path = "backend/tests/fixtures/free_derivatives/gvzcls.csv"
  }
  deribit = @{
    underlyings = @("BTC", "ETH")
    include_expired = $false
    fixture_instruments_path = "backend/tests/fixtures/free_derivatives/deribit_instruments.json"
    fixture_summary_path = "backend/tests/fixtures/free_derivatives/deribit_summary.json"
  }
  run_label = "fixture-smoke"
  report_format = "both"
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 20

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/data-sources/bootstrap/free-derivatives" `
  -ContentType "application/json" `
  -Body $body
```

Expected response includes:

- `run_id`
- run `status`
- source results for CFTC, GVZ, and Deribit
- generated raw output paths
- generated processed output paths
- generated report paths
- warnings
- limitations
- missing-data actions when any source is partial/skipped/failed
- research-only warnings

## 6. Inspect Saved Runs

List runs:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/data-sources/bootstrap/free-derivatives/runs"
```

Read one run:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}"
```

Generated artifacts should appear under ignored paths:

```text
data/raw/cftc/
data/raw/gvz/
data/raw/deribit/
data/processed/cftc/
data/processed/gvz/
data/processed/deribit/
data/reports/free_derivatives/
```

They must remain ignored by git.

## 7. Optional Explicit Public Smoke

Only run this manually when internet access is available and source availability is expected. Do not run this as part of automated tests.

Manual public smoke may:

- Download current public CFTC historical compressed files for selected years.
- Download public GVZ daily close rows.
- Request Deribit public instruments and public book summaries for BTC and ETH options.

Stop and return clear missing-data actions if a public source is unavailable, rate limited, or incomplete. Do not fabricate rows.

## 8. Dashboard Check

From `frontend/`:

```powershell
npm run dev
```

Open:

```text
http://localhost:3000/data-sources
```

Verify the page shows:

- CFTC COT readiness
- GVZ readiness
- Deribit public options readiness
- latest free-derivatives run selector or summary
- output paths for completed sources
- source limitation labels
- missing-data actions
- XAU local options OI requirement reminder
- research-only disclaimer
- no secret values

Confirm no browser console errors if browser smoke tooling is available.

## 9. Forbidden Scope Review

Before marking implementation complete:

```powershell
rg -n -i "live trading|paper trading|shadow trading|private key|private-key|broker|order execution|real execution|wallet|paid vendor credential|rust|clickhouse|postgresql|postgres|kafka|redpanda|nats|kubernetes|sklearn|tensorflow|torch|ml training|buy signal|sell signal|profitable|profitability|predictive|safe to trade|live ready|live-readiness" backend/src frontend/src backend/pyproject.toml frontend/package.json .github/workflows/validation.yml
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

Expected result:

- Any matches are guardrail/disclaimer text only.
- No live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet handling, paid vendor credentials, Rust execution engine, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell execution signal behavior, or prohibited claims were introduced.
- No generated raw, processed, report, or local fixture data is tracked.
