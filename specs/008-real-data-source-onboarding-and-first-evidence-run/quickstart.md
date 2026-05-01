# Quickstart: Real Data-Source Onboarding And First Evidence Run

This quickstart validates the research-only data-source onboarding and first evidence workflow. It must not use private trading keys, broker keys, wallet keys, live execution, paper trading, or shadow trading.

## 1. Backend Checks

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/ -q
```

Expected:

- Backend imports successfully.
- Existing tests continue passing.

## 2. Frontend Checks

```powershell
cd frontend
npm install
npm run build
```

Expected:

- Frontend dependencies install.
- Production build succeeds.

## 3. Artifact Guard

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

If using PowerShell Core on Linux or macOS:

```powershell
pwsh -File scripts/check_generated_artifacts.ps1
```

Expected:

- No tracked generated artifacts are found.
- `data/raw`, `data/processed`, `data/reports`, `.env*`, `*.parquet`, `*.duckdb`, `.venv`, `.next`, and `node_modules` remain untracked.

## 4. Start Backend

```powershell
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Verify:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`

## 5. Check Data-Source Readiness

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/data-sources/readiness"
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/data-sources/capabilities"
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/data-sources/missing-data"
```

Confirm:

- Binance public is public/no-key and research-only.
- Yahoo Finance is OHLCV/proxy-only.
- Local files are schema-dependent.
- Optional Kaiko, Tardis, CoinGlass, CryptoQuant, and CME/QuikStrike-style sources are configured or missing without exposing secret values.
- Missing optional paid keys do not fail the MVP.

## 6. Run Preflight

Use real local/public processed data for final research runs. Synthetic fixture files are allowed only for automated tests and smoke validation.

```powershell
$body = @{
  crypto_assets = @("BTCUSDT", "ETHUSDT", "SOLUSDT")
  crypto_timeframe = "15m"
  proxy_assets = @("SPY", "QQQ", "GLD", "GC=F")
  proxy_timeframe = "1d"
  xau_options_oi_file_path = "data/raw/xau/options_oi_sample.csv"
  require_optional_vendors = @("kaiko_optional", "tardis_optional")
  requested_capabilities = @("ohlcv", "open_interest", "funding", "iv")
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/data-sources/preflight" `
  -ContentType "application/json" `
  -Body $body
```

Confirm:

- Missing crypto processed features include Binance download/process instructions.
- Missing proxy processed features include Yahoo OHLCV processing instructions.
- Yahoo unsupported OI, funding, IV, gold options OI, futures OI, and XAUUSD execution requests are labeled unsupported.
- Missing or invalid XAU options OI files include required local file columns.
- Optional paid provider absence is non-blocking.
- No synthetic data is substituted for real research evidence.

## 7. Run First Evidence Workflow

```powershell
$body = @{
  name = "First evidence run"
  preflight = @{
    crypto_assets = @("BTCUSDT")
    crypto_timeframe = "15m"
    proxy_assets = @("SPY", "GLD")
    proxy_timeframe = "1d"
    xau_options_oi_file_path = "data/raw/xau/options_oi_sample.csv"
    research_only_acknowledged = $true
  }
  use_existing_research_report_ids = @()
  use_existing_xau_report_id = $null
  run_when_partial = $true
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 10

$result = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/evidence/first-run" `
  -ContentType "application/json" `
  -Body $body

$result.first_run_id
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/v1/evidence/first-run/$($result.first_run_id)"
```

Confirm:

- Response includes `first_run_id`.
- Response includes linked feature 007 `execution_run_id` when execution is created.
- Blocked workflows remain visible.
- Missing-data checklist is returned.
- Research-only warnings are present.

## 8. Dashboard Smoke

Start the frontend:

```powershell
cd frontend
npm run dev
```

Open:

- `http://localhost:3000/data-sources`

Confirm the page shows:

- Source readiness cards.
- Provider capability matrix.
- Optional provider key status as configured or missing only.
- Public/no-key source availability.
- Local XAU file requirements.
- Missing-data checklist.
- First evidence run status and linked report ids when available.
- Research-only disclaimer.

## 9. Forbidden Scope Review

Review:

- `backend/pyproject.toml`
- `frontend/package.json`
- `.github/workflows/validation.yml`
- `backend/src/`
- `frontend/src/`

Confirm no:

- Live trading.
- Paper trading.
- Shadow trading.
- Private trading keys.
- Broker integration.
- Real order execution.
- Wallet/private-key handling.
- Rust execution engine.
- ClickHouse.
- PostgreSQL.
- Kafka, Redpanda, or NATS.
- Kubernetes.
- ML model training.
- Profitability, predictive power, safety, or live-readiness claims.

## 10. Success Criteria

The feature is ready when:

- Readiness, capabilities, missing-data, preflight, and first-run endpoints behave as documented.
- `/data-sources` dashboard shows readiness and first-run status.
- Optional paid keys are absence-tolerant and never exposed.
- Public/local MVP path works when required data exists.
- Existing backend tests pass.
- Frontend build passes.
- Artifact guard passes.
