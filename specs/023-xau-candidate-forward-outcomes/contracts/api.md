# API Contract: XAU Candidate Forward Outcomes

All endpoints are local research-only endpoints mounted under `/api/v1`.

Every successful response includes:

- `research_only=true`
- `signal_allowed=false`
- `no_signal_reasons`
- `artifact_paths`

## POST /api/v1/research/xau/candidate-outcomes/run

Runs one local outcome calculation from a saved candidate artifact and local price bars.

```json
{
  "candidate_set_path": "backend/data/reports/xau_daily_structural_map/{map_id}/candidates.json",
  "price_bars_path": "backend/data/imports/xau_price_bars.csv",
  "windows": ["30m", "1h", "4h", "session_close", "next_day"],
  "research_only_acknowledged": true
}
```

Response model: `XauCandidateOutcomeRunResult`.

Key response fields:

- `outcome_run_id`
- `candidate_set_id`
- `map_id`
- `candidate_count`
- `outcome_count`
- `unavailable_count`
- `artifact_paths`
- `outcome_set`

## GET /api/v1/research/xau/candidate-outcomes/latest

Returns the latest persisted outcome run, or a blocked empty-state response when no outcome run exists.

Response model: `XauCandidateOutcomeLatestResponse`.

## GET /api/v1/research/xau/candidate-outcomes/{outcome_run_id}

Reads one persisted outcome run.

Response model: `XauCandidateOutcomeRunResult`.

Errors:

- `400 VALIDATION_ERROR` for unsafe run ids.
- `404 NOT_FOUND` when the run does not exist.

## Forbidden Behavior

The API does not expose buy/sell signals, alerts, order instructions, position sizing, PnL, broker access, paper trading, live trading, or automatic trade placement.
