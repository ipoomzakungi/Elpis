# Quickstart: Backtest and Reporting Engine

**Date**: 2026-04-27  
**Feature**: 003-backtest-reporting-engine

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm
- Existing Elpis v0 local setup
- Existing processed feature data, starting with `data/processed/btcusdt_15m_features.parquet`

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

Use the existing OI Regime Lab flow:

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

## Run a Backtest

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/backtests/run `
  -Method Post `
  -ContentType "application/json" `
  -Body '{
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
  }'
```

Expected:

- Response includes `run_id`, `status`, `metrics`, `warnings`, and artifact paths.
- A completed MVP run writes `metadata.json`, `config.json`, `trades.parquet`, `equity.parquet`, `metrics.json`, and `report.json` under `data/reports/{run_id}/`.
- If the selected configuration produces no simulated trades, the run still completes with an inspectable empty trade log, flat equity curve, and metric notes explaining that trade ratios are undefined.
- If processed features are missing, `POST /api/v1/backtests/run` returns a structured `NOT_FOUND` response that names the expected feature path.
- Invalid assumptions such as leverage above 1 or max positions above 1 return a structured `VALIDATION_ERROR` response.
- No generated report artifacts are committed to git.

## Inspect Reports Through API

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/backtests
Invoke-RestMethod http://localhost:8000/api/v1/backtests/<run_id>
Invoke-RestMethod http://localhost:8000/api/v1/backtests/<run_id>/trades
Invoke-RestMethod http://localhost:8000/api/v1/backtests/<run_id>/metrics
Invoke-RestMethod http://localhost:8000/api/v1/backtests/<run_id>/equity
```

## Dashboard Check

Start frontend:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000/backtests` or the implemented backtest panel and verify:

- Run selector lists completed runs.
- Summary metric cards render.
- Equity curve renders.
- Drawdown curve renders.
- Trade table renders.
- Regime performance table renders.
- Strategy mode and baseline comparison sections render.
- Report assumptions and limitations are visible.
- Text does not claim profitability or live-trading readiness.

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

## Smoke Tests

- Unit metrics: no trades, wins/losses, drawdown, expectancy, profit factor.
- Unit portfolio: fees, slippage, fixed fractional sizing, max-one-position, stop/TP exits.
- Unit strategies: RANGE-only grid signals and breakout-only signals.
- Integration: synthetic feature DataFrame produces deterministic trades, equity, metrics, and report artifacts.
- Contract: all backtest endpoints return expected success/error shapes.
- Compatibility: existing provider list/download, feature processing, and dashboard root still work.

## v0 Guardrails

Do not add or configure any of the following while implementing this feature:

- Live trading
- Private exchange API keys
- Real order execution
- Broker integration
- Wallet/private-key handling
- Leverage execution beyond v0 simulated `leverage=1`
- Rust
- ClickHouse
- PostgreSQL
- Kafka, Redpanda, or NATS
- Kubernetes
- ML model training

Reports are historical simulation outputs under documented assumptions only. They must not be described as proof of profitability, predictive power, safety, or live-trading readiness.