# Quickstart: XAU Plan Tracker Stats

## Build a one-run stats summary

```bash
python backend/scripts/run_xau_plan_tracker.py --session-date 2026-06-08 ... --price-bars-path path/to/xau.csv
python backend/scripts/run_xau_plan_tracker_stats.py --run-id <run_id> --output-root data
```

## Aggregate filtered stats via API

`POST /api/v1/research/xau/plan-tracker/stats`

```json
{
  "session_date_from": "2026-06-01",
  "session_date_to": "2026-06-09",
  "planning_times": ["10:10", "18:10"],
  "sides": ["long_reversion", "short_reversion"],
  "include_unavailable_orders": false,
  "max_runs": 5
}
```

Expected response includes:

- `run_count`
- `run_summaries`
- `signal_allowed` / `research_only`

## Run-specific query

`GET /api/v1/research/xau/plan-tracker/stats/<run_id>?planning_times=10:10&include_unavailable_orders=false`
