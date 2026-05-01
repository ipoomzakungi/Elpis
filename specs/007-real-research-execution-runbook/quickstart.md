# Quickstart: Real Research Execution Runbook

## Purpose

Use this feature to coordinate completed Elpis research workflows and generate a final evidence report. It is research-only and must not be interpreted as profitability, prediction, safety, or live-readiness evidence.

## Prerequisites

- Completed feature 005 multi-asset research reports are available, or processed feature files exist for requested crypto/proxy assets.
- Completed feature 006 XAU Vol-OI reports are available, or a local gold options OI CSV/Parquet file exists.
- Generated artifacts remain under ignored local `data/` paths.
- No synthetic data is used for final real research runs. Synthetic fixtures are allowed only in automated tests.

## Backend Checks

```powershell
cd backend
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/ -q
```

## Frontend Checks

```powershell
cd frontend
npm install
npm run build
```

## Artifact Guard

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

If using PowerShell Core:

```powershell
pwsh -File scripts/check_generated_artifacts.ps1
```

## Start Backend

```powershell
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Verify:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`

## Create An Execution Run

Example request with one crypto workflow, one proxy workflow, and one XAU workflow:

```powershell
$body = @{
  name = "May 2026 evidence run"
  research_only_acknowledged = $true
  crypto = @{
    enabled = $true
    primary_assets = @("BTCUSDT", "ETHUSDT", "SOLUSDT")
    optional_assets = @()
    timeframe = "15m"
    required_feature_groups = @("ohlcv", "regime", "open_interest", "funding", "volume_confirmation")
  }
  proxy = @{
    enabled = $true
    assets = @("SPY", "GC=F")
    provider = "yahoo_finance"
    timeframe = "1d"
    required_feature_groups = @("ohlcv")
  }
  xau = @{
    enabled = $true
    options_oi_file_path = "data/local/xau/options_oi.csv"
    include_2sd_range = $true
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/research/execution-runs" `
  -ContentType "application/json" `
  -Body $body
```

Expected behavior:

- Response includes `execution_run_id`.
- Completed workflows include linked report IDs where available.
- Missing processed features produce download/process instructions.
- Missing XAU options OI files produce local import schema instructions.
- Yahoo/proxy unsupported OI, funding, gold options OI, futures OI, IV, and XAUUSD execution requirements are labeled unsupported.
- Research-only warnings are included.

## Inspect Results

```powershell
$runId = "rex_20260501_000001"

Invoke-RestMethod "http://localhost:8000/api/v1/research/execution-runs"
Invoke-RestMethod "http://localhost:8000/api/v1/research/execution-runs/$runId"
Invoke-RestMethod "http://localhost:8000/api/v1/research/execution-runs/$runId/evidence"
Invoke-RestMethod "http://localhost:8000/api/v1/research/execution-runs/$runId/missing-data"
```

## Dashboard Smoke

```powershell
cd frontend
npm run dev
```

Open:

- `http://localhost:3000/evidence`

Confirm the page shows:

- Execution run selector.
- Workflow status cards.
- Linked crypto, proxy, and XAU report IDs.
- Evidence decision table.
- Missing-data checklist.
- Source limitations, including Yahoo/proxy OHLCV-only labeling.
- Research-only disclaimer.

## Forbidden Scope Review

Before committing implementation changes, inspect:

- `backend/pyproject.toml`
- `frontend/package.json`
- `.github/workflows/validation.yml`
- `backend/src/`
- `frontend/src/`

Confirm no additions of:

- live trading
- paper trading
- shadow trading
- private API keys
- broker integration
- real execution
- wallet/private-key handling
- Rust execution engine
- ClickHouse
- PostgreSQL
- Kafka, Redpanda, or NATS
- Kubernetes
- ML model training
- profitability, predictive, safety, or live-readiness claims

## Expected Generated Files

Evidence artifacts are written under:

```text
data/reports/research_execution/<execution_run_id>/
|-- metadata.json
|-- normalized_config.json
|-- evidence.json
|-- evidence.md
`-- missing_data.json
```

These files are generated artifacts and must remain ignored and untracked.
