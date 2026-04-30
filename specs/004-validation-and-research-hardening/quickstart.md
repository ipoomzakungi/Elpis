# Quickstart: Validation and Research Hardening

**Date**: 2026-04-27  
**Feature**: 004-validation-and-research-hardening

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm
- Existing Elpis v0 local setup
- Completed backtest/reporting MVP from feature 003
- Existing processed feature data for real-data validation, starting with `data/processed/btcusdt_15m_features.parquet`

## Setup

### Backend

```powershell
cd backend
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"
```

### Frontend

```powershell
cd frontend
npm install
npm run build
```

## Generate Processed Features If Needed

Use the existing public-data research flow before real-data validation:

```powershell
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Then from another terminal:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/download `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"symbol":"BTCUSDT","interval":"15m","days":30}'

Invoke-RestMethod http://localhost:8000/api/v1/process `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"symbol":"BTCUSDT","interval":"15m"}'
```

Confirm:

```powershell
Test-Path data/processed/btcusdt_15m_features.parquet
```

If the file is missing, validation must return clear download/process instructions instead of using synthetic data for the real-data report.

## Run a Validation Report

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/backtests/validation/run `
  -Method Post `
  -ContentType "application/json" `
  -Body '{
    "base_config": {
      "symbol":"BTCUSDT",
      "provider":"binance",
      "timeframe":"15m",
      "initial_equity":10000,
      "assumptions":{
        "fee_rate":0.0004,
        "slippage_rate":0.0002,
        "risk_per_trade":0.01,
        "max_positions":1,
        "allow_short":true,
        "allow_compounding":false,
        "leverage":1,
        "ambiguous_intrabar_policy":"stop_first"
      },
      "strategies":[
        {"mode":"grid_range","enabled":true,"allow_short":true,"entry_threshold":0.15,"atr_buffer":1.0,"take_profit":{"mode":"range_mid"}},
        {"mode":"breakout","enabled":true,"allow_short":true,"atr_buffer":1.0,"risk_reward_multiple":2.0}
      ],
      "baselines":["buy_hold","price_breakout"],
      "report_format":"both"
    },
    "capital_sizing":{"buy_hold_capital_fraction":1.0,"buy_hold_sizing_mode":"capital_fraction"},
    "stress_profiles":["normal","high_fee","high_slippage","worst_reasonable_cost"],
    "sensitivity_grid":{
      "grid_entry_threshold":[0.1,0.15,0.2],
      "atr_stop_buffer":[0.75,1.0,1.25],
      "breakout_risk_reward_multiple":[1.5,2.0,2.5],
      "fee_slippage_profile":["normal","high_fee"]
    },
    "walk_forward":{"split_count":3,"minimum_rows_per_split":20},
    "include_real_data_check":true
  }'
```

Expected:

- Response includes `validation_run_id`, status, source data identity, per-mode metrics, stress results, sensitivity results, walk-forward results, regime coverage, concentration report, warnings, and artifact paths.
- Buy-and-hold uses capital-fraction sizing by default and is reported as a baseline.
- Active strategy notional is capped to available equity when leverage is 1, and cap events are recorded.
- Equity output distinguishes realized equity and mark-to-market total equity where close prices allow it.
- Reports do not present an unlabeled global total return as combined portfolio performance.
- Reports do not claim profitability, predictive power, safety, or live-trading readiness.
- Generated artifacts are written under `data/reports/{validation_run_id}/` and remain untracked.

## Inspect Validation Reports Through API

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/backtests/validation
Invoke-RestMethod http://localhost:8000/api/v1/backtests/validation/<validation_run_id>
Invoke-RestMethod http://localhost:8000/api/v1/backtests/validation/<validation_run_id>/stress
Invoke-RestMethod http://localhost:8000/api/v1/backtests/validation/<validation_run_id>/sensitivity
Invoke-RestMethod http://localhost:8000/api/v1/backtests/validation/<validation_run_id>/walk-forward
Invoke-RestMethod http://localhost:8000/api/v1/backtests/validation/<validation_run_id>/concentration
```

Final endpoint names:

- `POST /api/v1/backtests/validation/run`
- `GET /api/v1/backtests/validation`
- `GET /api/v1/backtests/validation/{validation_run_id}`
- `GET /api/v1/backtests/validation/{validation_run_id}/stress`
- `GET /api/v1/backtests/validation/{validation_run_id}/sensitivity`
- `GET /api/v1/backtests/validation/{validation_run_id}/walk-forward`
- `GET /api/v1/backtests/validation/{validation_run_id}/concentration`

## Dashboard Check

Start frontend:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000/backtests` or `http://localhost:3000/validation` if a separate validation page is implemented, and verify:

- Validation report selector lists completed validation runs.
- Per-strategy metrics render separately from per-baseline metrics.
- Fee/slippage stress table renders.
- Parameter sensitivity table renders.
- Walk-forward split table renders.
- Regime coverage table renders.
- Best/worst trades render.
- Concentration warnings render.
- Notional cap warnings render.
- Text states that outputs are historical research validation only and not profitability evidence or live-readiness evidence.

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

## Required Test Coverage

- Unit: capital-based buy-and-hold sizing.
- Unit: no-leverage notional cap and cap-event notes.
- Unit: per-strategy and per-baseline metrics.
- Unit: mark-to-market equity or explicit realized-only labeling.
- Unit: fee/slippage stress profile generation and aggregation.
- Unit: parameter sensitivity result aggregation and fragility flags.
- Unit: walk-forward split generation.
- Unit: regime coverage and trade concentration metrics.
- Integration: full validation report on synthetic processed features.
- Integration: real-data validation returns clear missing-data instructions when processed features do not exist.
- Contract: validation endpoints return expected success/error shapes.
- Frontend: production build passes after validation report UI changes.
- CI: backend tests, frontend build, and artifact guard checks pass without private secrets.

## Generated Artifact Guard Check

Run before committing:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

Expected:

- `data/reports`, `data/processed`, `node_modules`, `.venv`, `.env*`, Parquet files, DuckDB files, and build outputs are not committed.
- Validation artifacts generated during smoke tests remain ignored.

## CI Commands

The repository workflow `.github/workflows/validation.yml` runs without private secrets:

- Backend: `pip install -e ".[dev]"`, backend import, and `pytest tests/ -q`
- Frontend: `npm install` and `npm run build`
- Artifact guard: `scripts/check_generated_artifacts.ps1`

## v0 Guardrails

Do not add or configure any of the following while implementing this feature:

- Live trading
- Private exchange API keys
- Real order execution
- Broker integration
- Wallet/private-key handling
- Rust execution engine
- ClickHouse
- PostgreSQL
- Kafka, Redpanda, or NATS
- Kubernetes
- ML model training
- Paper trading
- Shadow trading

Reports are historical simulation and validation outputs under documented assumptions only. They must not be described as proof of profitability, predictive power, safety, or live-trading readiness.
