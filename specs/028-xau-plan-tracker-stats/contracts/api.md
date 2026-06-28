# API Contract: XAU Plan Tracker Stats

## POST `/api/v1/research/xau/plan-tracker/stats`

Request body: `XauPlanTrackerStatsRequest`

Response: `XauPlanTrackerStatsResult` with:

- `run_count`
- `snapshot_count`, `order_count`
- global counts + run summaries
- research flags (`research_only=true`, `signal_allowed=false`)

## GET `/api/v1/research/xau/plan-tracker/stats/{run_id}`

Query parameters:

- `planning_times` (repeatable, `HH:MM`)
- `sides` (repeatable: `long_reversion` | `short_reversion`)
- `statuses` (enum values from tracked order status)
- `include_unavailable_orders` (bool)

Response: `XauPlanTrackerStatsResult`

## Error

- `404` if run_id is unknown
