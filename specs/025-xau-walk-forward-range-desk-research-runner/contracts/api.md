# API Contract: XAU Walk-Forward Range Desk Research Runner

All endpoints are local research-only endpoints mounted under `/api/v1`.

Every successful response includes:

- `research_only=true`
- `signal_allowed=false`

## POST /api/v1/research/xau/walk-forward/run

Runs one planning-only or walk-forward research capture using latest existing, fixture, or manual inputs.

```json
{
  "session_date": "2026-06-08",
  "cme_source": "latest_existing",
  "price_source": "manual",
  "future_reference_price": 4500.0,
  "traded_reference_price": 4470.0,
  "research_only_acknowledged": true
}
```

Response model: `XauWalkForwardRunResult`.

## GET /api/v1/research/xau/walk-forward/latest

Returns the latest persisted run result.

## GET /api/v1/research/xau/walk-forward/runs/{run_id}

Returns one persisted run result.

## GET /api/v1/research/xau/walk-forward/runs/{run_id}/orders

Returns persisted research order plans.

## GET /api/v1/research/xau/walk-forward/runs/{run_id}/snapshots

Returns persisted snapshot records.

## Forbidden Behavior

The API does not expose buy/sell signals, alerts, broker order IDs, order instructions, real position sizing, real PnL, paper trading, live trading, or automatic trade placement.
