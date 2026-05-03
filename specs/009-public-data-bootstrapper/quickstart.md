# Quickstart: Public Data Bootstrapper

## Scope

This feature prepares public/no-key research data for the existing data-source onboarding, preflight, and evidence workflows. It downloads only public Binance crypto data and Yahoo OHLCV proxy data when explicitly invoked. It does not add live trading, paper trading, shadow trading, private keys, broker integration, order execution, wallet handling, paid vendor downloads, or strategy claims.

## Prerequisites

- Backend dependencies installed for the existing Elpis research API.
- Frontend dependencies installed for the existing dashboard.
- `data/raw/`, `data/processed/`, and `data/reports/` remain ignored by version control.
- No `.env` or secret file is required for the MVP public bootstrap.

## Backend Validation

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_data_bootstrap_binance.py -v
python -m pytest tests/unit/test_data_bootstrap_yahoo.py -v
python -m pytest tests/unit/test_data_bootstrap_processing.py -v
python -m pytest tests/integration/test_data_bootstrap_flow.py -v
python -m pytest tests/contract/test_data_sources_api_contracts.py -v
python -m pytest tests/ -q
```

Automated tests must use mocked Binance/Yahoo responses and synthetic fixtures. They must not run real external downloads.

## Frontend And Artifact Guard

```powershell
cd frontend
npm run build

cd ..
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## API Smoke Flow

Start the backend:

```powershell
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Start a public bootstrap run:

```powershell
$body = @{
  include_binance = $true
  binance_symbols = @("BTCUSDT", "ETHUSDT", "SOLUSDT")
  optional_binance_symbols = @()
  binance_timeframes = @("15m")
  include_binance_open_interest = $true
  include_binance_funding = $true
  include_yahoo = $true
  yahoo_symbols = @("SPY", "QQQ", "GLD", "GC=F")
  yahoo_timeframes = @("1d")
  days = 90
  run_preflight_after = $true
  include_xau_local_instructions = $true
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/data-sources/bootstrap/public `
  -ContentType "application/json" `
  -Body $body
```

Expected response:

- `bootstrap_run_id`
- `status` as `completed`, `partial`, `blocked`, or `failed`
- per-asset results for requested Binance and Yahoo assets
- raw output paths under `data/raw/`
- processed feature paths under `data/processed/`
- source limitation notes
- XAU local import instructions
- research-only warnings

List saved bootstrap runs:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/data-sources/bootstrap/runs
```

Read one bootstrap run:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/data-sources/bootstrap/runs/<bootstrap_run_id>
```

## Expected Local Outputs

Successful Binance items should produce paths like:

```text
data/raw/binance/btcusdt_15m_ohlcv.parquet
data/raw/binance/btcusdt_15m_open_interest.parquet
data/raw/binance/btcusdt_15m_funding_rate.parquet
data/processed/btcusdt_15m_features.parquet
```

Successful Yahoo items should produce paths like:

```text
data/raw/yahoo/spy_1d_ohlcv.parquet
data/processed/spy_1d_features.parquet
data/raw/yahoo/gc=f_1d_ohlcv.parquet
data/processed/gc=f_1d_features.parquet
```

Report artifacts should be under:

```text
data/reports/data_bootstrap/<bootstrap_run_id>/
```

These paths must remain ignored and untracked.

## Preflight Readiness Check

After a bootstrap run with `run_preflight_after=true`, the response should include an embedded feature 008 preflight result. A separate preflight check can also be run:

```powershell
$preflight = @{
  crypto_assets = @("BTCUSDT", "ETHUSDT", "SOLUSDT")
  crypto_timeframe = "15m"
  proxy_assets = @("SPY", "QQQ", "GLD", "GC=F")
  proxy_timeframe = "1d"
  requested_capabilities = @("ohlcv", "open_interest", "funding")
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/data-sources/preflight `
  -ContentType "application/json" `
  -Body $preflight
```

The generated processed files should be recognized for completed assets. XAU options OI should remain blocked until the user imports a local CSV or Parquet file with the required schema.

## Dashboard Smoke Flow

Start the frontend:

```powershell
cd frontend
npm run dev
```

Open:

```text
http://localhost:3000/data-sources
```

Confirm:

- Data Sources navigation link is present.
- Public bootstrap controls are visible.
- Bootstrap run selector or latest-run panel is visible.
- Downloaded, skipped, and failed assets render.
- Output paths and source limitation notes render.
- Yahoo Finance is labeled OHLCV-only.
- XAU options OI local import requirements render.
- Research-only disclaimer is visible.
- No browser console errors appear during the smoke flow.

## Forbidden Scope Review

Before marking the feature complete, inspect:

- `backend/pyproject.toml`
- `frontend/package.json`
- `.github/workflows/validation.yml`
- `backend/src/`
- `frontend/src/`

Confirm no live trading, paper trading, shadow trading, private trading keys, broker integration, wallet/private-key handling, real order execution, Rust execution engine, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, ML model training, buy/sell signal behavior, profitability claims, predictive claims, safety claims, or live-readiness claims were introduced.

## Git Hygiene

Before committing:

```powershell
git status --short --untracked-files=all
```

Do not stage:

- `.env`
- `.env.*`
- `.venv`
- `node_modules`
- `.next`
- `data/raw`
- `data/processed`
- `data/reports`
- `*.parquet`
- `*.duckdb`
- generated report files
- secret values
