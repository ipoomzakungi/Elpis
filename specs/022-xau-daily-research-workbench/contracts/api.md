# API Contract: XAU Daily Research Workbench

All endpoints are local research-only endpoints mounted under `/api/v1`.

Every successful response includes:

- `research_only=true`
- `signal_allowed=false`
- `readiness`
- `missing_inputs`
- `no_signal_reasons`
- `artifact_paths`

## POST /api/v1/research/xau/workbench/run

Runs one workbench request.

```json
{
  "session_date": "2026-06-02",
  "expiration_code": "OG1M6",
  "traded_instrument": "XAUUSD",
  "cme_source": "local_bundle",
  "input_dir": "backend/data/imports/xau_quikstrike_20260602",
  "gc_reference_price": 4549.2,
  "traded_reference_price": 4536.7,
  "session_open_price": 4538.0,
  "confirmation_state": "rejection",
  "iv_state": "stable",
  "flow_state": "not_breakout_confirmed",
  "run_candidates": true,
  "research_only_acknowledged": true
}
```

Response model: `XauDailyWorkbenchRunResult`.

Key response fields:

- `run_id`
- `map_id`
- `candidate_set_id`
- `readiness`
- `daily_map`
- `candidate_set`
- `candidate_metadata`
- `provider_statuses`
- `basis_snapshot`

## GET /api/v1/research/xau/workbench/latest

Returns the latest persisted workbench run, or a blocked empty-state response when none exists.

Response model: `XauDailyWorkbenchLatestResponse`.

## GET /api/v1/research/xau/workbench/runs/{run_id}

Reads one persisted workbench run.

Response model: `XauDailyWorkbenchRunResult`.

Errors:

- `400 VALIDATION_ERROR` for unsafe run ids.
- `404 NOT_FOUND` when the run does not exist.

## GET /api/v1/research/xau/workbench/maps/{map_id}

Reads one persisted structural map through the workbench API.

Response model: `XauDailyWorkbenchMapResponse`.

Errors:

- `400 VALIDATION_ERROR` for unsafe map ids.
- `404 NOT_FOUND` when the map does not exist.

## GET /api/v1/research/xau/workbench/candidates/{map_id}

Reads candidate sidecars for a persisted map.

Response model: `XauDailyWorkbenchCandidateResponse`.

Errors:

- `400 VALIDATION_ERROR` for unsafe map ids.
- `404 NOT_FOUND` when candidate sidecars do not exist.

## Forbidden Behavior

The API does not expose buy/sell signals, alerts, order instructions, position sizing, PnL, broker access, paper trading, live trading, or automatic trade placement.
