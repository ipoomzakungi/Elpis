# API Contract: XAU Plan Tracker

All endpoints are local research-only endpoints mounted under `/api/v1`.

Every successful response includes:

- `research_only=true`
- `signal_allowed=false`

## POST /api/v1/research/xau/plan-tracker/run

Runs a research-only plan tracker using local bars or a configured Dukascopy CLI command.

```json
{
  "session_date": "2026-06-08",
  "planning_times": ["10:10", "18:10"],
  "price_bars_path": "data/imports/xau_bars_20260608.csv",
  "cme_source": "fixture",
  "recovery_multiplier": 3.0,
  "near_miss_threshold_points": 0.25,
  "research_only_acknowledged": true
}
```

Response model: `XauPlanTrackerRunResult`.

## GET /api/v1/research/xau/plan-tracker/latest

Returns latest persisted plan tracker result.

## GET /api/v1/research/xau/plan-tracker/runs/{run_id}

Returns one persisted run result.

## GET /api/v1/research/xau/plan-tracker/runs/{run_id}/orders

Returns tracked simulated orders.

## GET /api/v1/research/xau/plan-tracker/runs/{run_id}/snapshots

Returns plan tracker snapshots.

## Forbidden Behavior

The API does not expose live buy/sell signals, alerts, order instructions, position sizing, real PnL, broker access, paper trading, live trading, automatic trade placement, or strategy profitability claims.
