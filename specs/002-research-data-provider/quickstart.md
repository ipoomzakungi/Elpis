# Quickstart: Research Data Provider Layer

**Date**: 2026-04-26  
**Feature**: 002-research-data-provider

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm
- Git
- Existing Elpis v0 local setup

## Setup

### 1. Backend

```powershell
cd backend
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run build
```

## Run the Application

### 1. Start Backend

```powershell
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Verify:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/docs
```

### 2. Start Frontend

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000`.

## Provider Metadata Checks

### List Providers

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/providers
```

Expected providers:

- `binance`: OHLCV, open interest, funding rate, no auth
- `yahoo_finance`: OHLCV only, no auth
- `local_file`: capability depends on validated CSV/Parquet columns, no auth

### Get Yahoo Finance Details

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/providers/yahoo_finance
```

Expected: `supports_ohlcv=true`, `supports_open_interest=false`, `supports_funding_rate=false`.

### Get Yahoo Finance Symbols

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/providers/yahoo_finance/symbols
```

Expected: curated research symbols include `SPY`, `QQQ`, `GC=F`, and `BTC-USD`.

## Binance Backward Compatibility Smoke Test

### Provider-Aware Download

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/data/download `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"provider":"binance","symbol":"BTCUSDT","timeframe":"15m","days":30,"data_types":["ohlcv","open_interest","funding_rate"]}'
```

Confirm the existing raw files are still present or still readable:

```powershell
Test-Path data/raw/btcusdt_15m_ohlcv.parquet
Test-Path data/raw/btcusdt_15m_oi.parquet
Test-Path data/raw/btcusdt_15m_funding.parquet
```

### Existing Endpoint Still Works

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/download `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"symbol":"BTCUSDT","interval":"15m","days":30}'
```

### Process Features

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/process `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"symbol":"BTCUSDT","interval":"15m"}'
```

Confirm:

```powershell
Test-Path data/processed/btcusdt_15m_features.parquet
```

## Yahoo Finance OHLCV Smoke Test

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/data/download `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"provider":"yahoo_finance","symbol":"SPY","timeframe":"1d","days":365,"data_types":["ohlcv"]}'
```

Expected:

- Download completes with OHLCV artifact.
- No open interest or funding artifact is created.
- Provider metadata says OI and funding are unsupported.

### Unsupported Capability Check

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/data/download `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"provider":"yahoo_finance","symbol":"SPY","timeframe":"1d","days":365,"data_types":["open_interest"]}'
```

Expected: structured `UNSUPPORTED_CAPABILITY` response or partial response with `open_interest` listed in `skipped_data_types`, depending on whether any supported data type was also requested.

## Local File Validation Smoke Test

Create a small local sample file:

```powershell
New-Item -ItemType Directory -Force data/imports | Out-Null
@'
timestamp,open,high,low,close,volume
2026-04-24T00:00:00Z,100,110,95,105,1000
2026-04-25T00:00:00Z,105,112,101,109,1200
'@ | Set-Content data/imports/sample_ohlcv.csv
```

Validate/import it through the provider-aware path:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/data/download `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"provider":"local_file","symbol":"SAMPLE","timeframe":"1d","local_file_path":"data/imports/sample_ohlcv.csv","data_types":["ohlcv"]}'
```

Expected:

- Validation passes.
- OHLCV capability is detected.
- Optional OI/funding capabilities are false unless valid columns exist.

## Dashboard Checks

Open `http://localhost:3000` and verify:

- Provider selector is visible.
- Provider capabilities are visible.
- Selected provider, symbol, and timeframe are visible.
- Binance BTCUSDT 15m still displays price, range lines, open interest, funding, volume, regime panel, and data quality panel after download/process.
- Yahoo Finance can be selected and downloaded through the provider-aware path.
- OI and funding panels show "Not supported by this provider" for Yahoo Finance instead of breaking.

Current dashboard limitation: chart read/process endpoints still use the legacy Binance-oriented data path. Non-Binance provider downloads are stored as provider-aware raw artifacts, but provider-aware chart loading is a later slice.

## Required Test Commands

### Backend

```powershell
cd backend
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"
pytest tests/ -v
```

### Frontend

```powershell
cd frontend
npm install
npm run build
```

## v0 Guardrails

Do not add or configure any of the following while implementing this feature:

- Live trading
- Private exchange API keys
- Order execution
- Rust
- ClickHouse
- PostgreSQL
- Kafka, Redpanda, or NATS
- Kubernetes
- ML model training
